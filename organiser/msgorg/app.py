"""Queries, job labels, corrections, export. Corrections never touch source messages."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

from . import absences as A


def _ms(d, end=False):
    x = dt.datetime.fromisoformat(d) if "T" in d else dt.datetime.combine(dt.date.fromisoformat(d), dt.time.max if end else dt.time.min)
    return int(x.timestamp() * 1000)


def contacts(db):
    return [dict(r) for r in db.execute(
        "select c.id, c.display, c.address_key, count(m.id) n, max(m.date_ms) last_ms,"
        " (select group_concat(j.name) from contact_jobs cj join jobs j on j.id=cj.job_id where cj.contact_id=c.id) jobs"
        " from contacts c left join messages m on m.contact_id=c.id group by c.id order by last_ms desc")]


def search(db, text=None, contact=None, start=None, end=None, job=None, direction=None, limit=200):
    q, a = ["1=1"], []
    if text:
        if getattr(db, "fts", False):
            q.append("m.id in (select rowid from msg_fts where msg_fts match ?)")
            a.append(" ".join(f'"{w}"' for w in text.split()))
        else:
            q.append("m.body like ?")
            a.append(f"%{text}%")
    if contact:
        q.append("(c.display like ? or c.address_key like ?)")
        a += [f"%{contact}%", f"%{contact}%"]
    if start:
        q.append("m.date_ms >= ?")
        a.append(_ms(start))
    if end:
        q.append("m.date_ms <= ?")
        a.append(_ms(end, True))
    if job:
        q.append("m.contact_id in (select cj.contact_id from contact_jobs cj join jobs j on j.id=cj.job_id where j.name=?)")
        a.append(job)
    if direction:
        q.append("m.direction = ?")
        a.append(direction)
    rows = db.execute(f"select m.*, c.display from messages m join contacts c on c.id=m.contact_id where {' and '.join(q)}"
                      f" order by m.date_ms limit ?", a + [limit])
    return [dict(r) for r in rows]


def context(db, msg_id, before=5, after=5):
    m = db.execute("select * from messages where id=?", (msg_id,)).fetchone()
    if not m:
        return []
    b = db.execute("select * from messages where contact_id=? and (date_ms<? or (date_ms=? and id<?)) order by date_ms desc, id desc limit ?",
                   (m["contact_id"], m["date_ms"], m["date_ms"], m["id"], before)).fetchall()
    a = db.execute("select * from messages where contact_id=? and (date_ms>? or (date_ms=? and id>?)) order by date_ms, id limit ?",
                   (m["contact_id"], m["date_ms"], m["date_ms"], m["id"], after)).fetchall()
    return [dict(x) for x in list(reversed(b)) + [m] + list(a)]


def set_job(db, contact, job):
    c = db.execute("select id from contacts where display=? or address_key=? or id=?", (contact, contact, contact)).fetchone()
    if not c:
        raise SystemExit(f"no contact {contact!r}")
    with db:
        db.execute("insert or ignore into jobs(name) values(?)", (job,))
        jid = db.execute("select id from jobs where name=?", (job,)).fetchone()[0]
        db.execute("insert or ignore into contact_jobs values(?,?)", (c["id"], jid))


def unset_job(db, contact, job):
    with db:
        db.execute("delete from contact_jobs where contact_id in (select id from contacts where display=? or address_key=?)"
                   " and job_id in (select id from jobs where name=?)", (contact, contact, job))


def recompute_absences(db, day_first=True):
    with db:
        db.execute("delete from absence_findings")
        for c in db.execute("select id from contacts").fetchall():
            msgs = [dict(r) for r in db.execute("select id, key, date_ms, direction, body from messages where contact_id=?", (c["id"],))]
            has_job = db.execute("select 1 from contact_jobs where contact_id=?", (c["id"],)).fetchone() is not None
            for f in A.analyse_conversation(msgs, day_first=day_first, has_job=has_job):
                db.execute("insert into absence_findings(contact_id, first_msg, work_start, work_end, status, kind, summary,"
                           " evidence, revisions, rule_version) values(?,?,?,?,?,?,?,?,?,?)",
                           (c["id"], f["first_msg"], f["work_start"], f["work_end"], f["status"], f["kind"],
                            json.dumps({k: f[k] for k in ("sent_at", "date_basis", "notes", "actually_taken", "msg_key",
                                                          "rescheduled_to", "context", "context_reason") if k in f}),
                            json.dumps(f["evidence"]), json.dumps(f["revisions"]), A.RULE_VERSION))


def absences(db, contact=None, job=None, start=None, end=None, statuses=None, include_rejected=False, contexts=("work", "unknown")):
    rows = db.execute("select a.*, c.display, (select group_concat(j.name) from contact_jobs cj join jobs j on j.id=cj.job_id"
                      " where cj.contact_id=a.contact_id) jobs from absence_findings a join contacts c on c.id=a.contact_id"
                      " order by a.work_start").fetchall()
    out = []
    for r in rows:
        f = dict(r)
        s = json.loads(f.pop("summary"))
        f.update(s)
        f["evidence"], f["revisions"] = json.loads(f["evidence"]), json.loads(f["revisions"])
        f["corrections"] = []
        for c in db.execute("select * from corrections where msg_key=? and (work_start=? or work_start is null) order by id",
                            (s["msg_key"], f["work_start"])):
            f["corrections"].append(dict(c))
            if c["field"] == "status":
                f["status"] = c["value"]
            elif c["field"] == "work_date":
                f["work_start"], f["work_end"] = (c["value"].split("..") + [c["value"]])[:2]
            elif c["field"] == "job":
                f["jobs"] = c["value"]
            elif c["field"] == "not_absence":
                f["rejected"] = True
            elif c["field"] == "context":
                f["context"], f["context_reason"] = c["value"], "corrected by you"
        f["corrected"] = bool(f["corrections"])
        if f.get("rejected") and not include_rejected:
            continue
        if contact and contact.lower() not in (f["display"] or "").lower():
            continue
        if job and job not in (f["jobs"] or "").split(","):
            continue
        if start and f["work_end"] < start or end and f["work_start"] > end:
            continue
        if contexts and f.get("context") not in contexts:
            continue
        if statuses and f["status"] not in statuses:
            continue
        out.append(f)
    return out


def correct(db, finding_id, field, value, note=""):
    f = db.execute("select summary, work_start from absence_findings where id=?", (finding_id,)).fetchone()
    if not f:
        raise SystemExit(f"no finding {finding_id}")
    key = json.loads(f["summary"])["msg_key"]
    statuses = {"requested", "proposed", "stated", "confirmed", "declined", "cancelled", "rescheduled", "uncertain", "taken"}
    if field not in ("status", "work_date", "job", "not_absence", "context"):
        raise SystemExit("field must be one of status, work_date, job, not_absence, context")
    if field == "context" and value not in ("work", "personal", "unknown"):
        raise SystemExit("context must be work, personal or unknown")
    if field == "status" and value not in statuses:
        raise SystemExit(f"status must be one of {sorted(statuses)}")
    with db:
        db.execute("insert into corrections(msg_key, work_start, field, value, note, created) values(?,?,?,?,?,?)",
                   (key, f["work_start"], field, value, note, dt.datetime.now().isoformat(timespec="seconds")))


def export(findings, fmt="md"):
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["work_start", "work_end", "contact", "job", "context", "status", "sent_at", "date_basis", "evidence", "revisions",
                    "corrected", "actually_taken"])
        for f in findings:
            w.writerow([f["work_start"], f["work_end"], f["display"], f.get("jobs") or "", f.get("context"), f["status"], f["sent_at"],
                        f["date_basis"], " | ".join(f"[{e['at']} {e['direction']}] {e['excerpt']}" for e in f["evidence"]),
                        " | ".join(f"[{e['at']} {e['role']}] {e['excerpt']}" for e in f["revisions"]), f["corrected"],
                        f["actually_taken"]])
        return buf.getvalue()
    lines = ["# Work absences found in messages", "",
             "Statuses describe what the messages establish. Whether the day was actually taken off is not established by messages.", ""]
    for f in findings:
        rng = f["work_start"] + ("" if f["work_end"] == f["work_start"] else f" to {f['work_end']}")
        lines.append(f"## {rng} - {f['display']}{' (' + f['jobs'] + ')' if f.get('jobs') else ''}: **{f['status']}**"
                     + (" (corrected by you)" if f["corrected"] else ""))
        lines.append(f"- Message sent {f['sent_at']}; date basis: {f['date_basis']}")
        lines.append(f"- Context: {f.get('context')} ({f.get('context_reason')})")
        for n in f.get("notes") or []:
            lines.append(f"- Note: {n}")
        for e in f["evidence"]:
            lines.append(f"- > [{e['at']}, {e['direction']}, msg #{e['msg']}] {e['excerpt']}")
        for e in f["revisions"]:
            lines.append(f"- Later ({e['role']}): > [{e['at']}, msg #{e['msg']}] {e['excerpt']}")
        lines.append("")
    return "\n".join(lines)
