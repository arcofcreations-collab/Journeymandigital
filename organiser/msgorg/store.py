"""Local SQLite archive. Source records are immutable; interpretations and corrections live in separate tables."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3

from . import importer as I

SCHEMA = """
create table if not exists imports(id integer primary key, file text, file_sha256 text, started text,
    declared_count int, parsed int, added int, duplicates int, errors int, error_samples text,
    sms int, mms int, rcs_like int, first_ms int, last_ms int);
create table if not exists contacts(id integer primary key, address_key text unique, display text);
create table if not exists messages(id integer primary key, key text unique, kind text, date_ms int,
    direction text, contact_id int references contacts(id), address text, participants text, body text,
    attachments text, rcs_like int, source_id text, raw text, import_id int references imports(id));
create index if not exists messages_contact_date on messages(contact_id, date_ms);
create table if not exists jobs(id integer primary key, name text unique);
create table if not exists contact_jobs(contact_id int references contacts(id), job_id int references jobs(id),
    primary key(contact_id, job_id));
-- interpretations: derived, recomputable; never written into messages
create table if not exists absence_findings(id integer primary key, contact_id int, first_msg int, work_start text,
    work_end text, status text, kind text, summary text, evidence text, revisions text, rule_version text);
-- user corrections keyed by the stable evidence message key + work date (survive recomputation)
create table if not exists corrections(id integer primary key, msg_key text, work_start text, field text,
    value text, note text, created text);
"""


class _Conn(sqlite3.Connection):
    fts = False


def open_db(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, factory=_Conn)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    try:
        db.execute("create virtual table if not exists msg_fts using fts5(body, content='messages', content_rowid='id')")
        db.fts = True
    except sqlite3.OperationalError:
        db.fts = False
    return db


def _contact(db, address, name):
    k = I.norm_address(address)
    row = db.execute("select id, display from contacts where address_key=?", (k,)).fetchone()
    if row:
        if name and (not row["display"] or row["display"] == address):
            db.execute("update contacts set display=? where id=?", (name, row["id"]))
        return row["id"]
    return db.execute("insert into contacts(address_key, display) values(?,?)", (k, name or address)).lastrowid


def import_file(db, path):
    import hashlib
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
    imp = db.execute("insert into imports(file, file_sha256, started, declared_count) values(?,?,?,?)",
                     (os.path.basename(path), sha, dt.datetime.utcnow().isoformat(timespec="seconds"),
                      I.declared_count(path))).lastrowid
    st = {"parsed": 0, "added": 0, "duplicates": 0, "errors": 0, "sms": 0, "mms": 0, "rcs_like": 0}
    samples, first, last = [], None, None
    with db:
        for rec, err in I.parse(path):
            if err:
                st["errors"] += 1
                if len(samples) < 10:
                    samples.append(err)
                continue
            st["parsed"] += 1
            st[rec["kind"]] += 1
            st["rcs_like"] += bool(rec["rcs_like"])
            first = rec["date_ms"] if first is None else min(first, rec["date_ms"])
            last = rec["date_ms"] if last is None else max(last, rec["date_ms"])
            cid = _contact(db, rec["address"], rec["contact_name"])
            cur = db.execute(
                "insert or ignore into messages(key, kind, date_ms, direction, contact_id, address, participants, body,"
                " attachments, rcs_like, source_id, raw, import_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["key"], rec["kind"], rec["date_ms"], rec["direction"], cid, rec["address"],
                 json.dumps(rec["participants"]), rec["body"], json.dumps(rec["attachments"]), int(rec["rcs_like"]),
                 rec["source_id"], json.dumps(rec["raw"]), imp))
            if cur.rowcount:
                st["added"] += 1
                if db.fts:
                    db.execute("insert into msg_fts(rowid, body) values(?,?)", (cur.lastrowid, rec["body"]))
            else:
                st["duplicates"] += 1
        db.execute("update imports set parsed=?, added=?, duplicates=?, errors=?, error_samples=?, sms=?, mms=?,"
                   " rcs_like=?, first_ms=?, last_ms=? where id=?",
                   (st["parsed"], st["added"], st["duplicates"], st["errors"], json.dumps(samples), st["sms"], st["mms"],
                    st["rcs_like"], first, last, imp))
    return dict(st, import_id=imp, declared=I.declared_count(path), first_ms=first, last_ms=last, error_samples=samples)


def coverage(db):
    r = db.execute("select count(*) n, sum(kind='sms') sms, sum(kind='mms') mms, sum(rcs_like) rcs, min(date_ms) a,"
                   " max(date_ms) b, count(distinct contact_id) c from messages").fetchone()
    imps = [dict(x) for x in db.execute("select * from imports order by id")]
    sent_rcs = db.execute("select count(*) from messages where rcs_like=1 and direction='sent'").fetchone()[0]
    gaps = ["Only what the backup file contained is here: the organiser cannot see messages the backup app could not read.",
            "Outgoing RCS messages may be missing (Google Messages stopped writing them to the phone's message store in 2026).",
            "End-to-end encrypted RCS chats on recent Android versions may be unreadable by backup apps.",
            "WhatsApp, Signal and other apps are not included unless imported separately."]
    if r["rcs"] and not sent_rcs:
        gaps.insert(1, f"{r['rcs']} RCS-like messages imported but none of them sent by you: outgoing RCS is likely missing.")
    for i in imps:
        if i["declared_count"] not in (-1, None) and i["declared_count"] != i["parsed"]:
            gaps.append(f"Import {i['id']} ({i['file']}): backup declares {i['declared_count']} messages, {i['parsed']} parsed.")
        if i["errors"]:
            gaps.append(f"Import {i['id']}: {i['errors']} records could not be read (see error samples).")
    return {"messages": r["n"], "sms": r["sms"], "mms": r["mms"], "rcs_like": r["rcs"], "contacts": r["c"],
            "first": _iso(r["a"]), "last": _iso(r["b"]), "imports": imps, "known_gaps": gaps}


def _iso(ms):
    return None if ms is None else dt.datetime.fromtimestamp(ms / 1000).isoformat(timespec="minutes")


def delete_all(path):
    for p in (path, path + "-wal", path + "-shm", path + "-journal"):
        if os.path.exists(p):
            os.remove(p)
