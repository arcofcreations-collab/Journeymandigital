"""Persistence for an accrete application instance (one SQLite file).

Tables:
  meta(key, value)            current model (JSON) and counters
  records(eid, rid, data)     current data, values keyed by field id
  outbox(id, json)            integration messages
  requests(seq, json)         recorded API requests and responses (the replay corpus)
  ledger(seq, json)           every applied change: request, operators, report, inverse
  golden(id, json)            probes + responses + data at the last commit (engine-upgrade check)
"""
from __future__ import annotations

import json
import os
import sqlite3

SCHEMA = """
create table if not exists meta(key text primary key, value text);
create table if not exists records(eid text, rid integer, data text, primary key(eid, rid));
create table if not exists outbox(id integer primary key, json text);
create table if not exists requests(seq integer primary key autoincrement, json text);
create table if not exists ledger(seq integer primary key autoincrement, json text);
create table if not exists golden(id integer primary key check (id = 1), json text);
"""

DB_NAME = "app.db"
REQUEST_CORPUS_LIMIT = 3000


class Store:
    def __init__(self, directory):
        self.dir = directory
        self.path = os.path.join(directory, DB_NAME)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    # ---------------------------------------------------------------- whole state
    def load(self):
        meta = dict(self.db.execute("select key, value from meta"))
        model = json.loads(meta["model"]) if "model" in meta else None
        world = {"records": {}, "next_id": json.loads(meta.get("next_id", "{}")), "outbox": [],
                 "outbox_next": int(meta.get("outbox_next", "1"))}
        for eid, rid, data in self.db.execute("select eid, rid, data from records"):
            world["records"].setdefault(eid, {})[rid] = json.loads(data)
        for (row,) in self.db.execute("select json from outbox order by id"):
            world["outbox"].append(json.loads(row))
        return model, world

    def save_all(self, model, world):
        with self.db:
            self.db.execute("delete from records")
            self.db.execute("delete from outbox")
            self.db.executemany("insert into records values (?,?,?)",
                                [(eid, rid, json.dumps(d)) for eid, recs in world["records"].items() for rid, d in recs.items()])
            self.db.executemany("insert into outbox values (?,?)", [(m["id"], json.dumps(m)) for m in world["outbox"]])
            self._meta(model, world)

    def _meta(self, model, world):
        self.db.execute("insert or replace into meta values ('model', ?)", (json.dumps(model),))
        self.db.execute("insert or replace into meta values ('next_id', ?)", (json.dumps(world["next_id"]),))
        self.db.execute("insert or replace into meta values ('outbox_next', ?)", (str(world["outbox_next"]),))

    def save_changes(self, model, world, journal, outbox_mark):
        """Persist only what one request changed."""
        with self.db:
            for eid, rid in {(e, r) for e, r, _ in journal}:
                data = world["records"].get(eid, {}).get(rid)
                if data is None:
                    self.db.execute("delete from records where eid=? and rid=?", (eid, rid))
                else:
                    self.db.execute("insert or replace into records values (?,?,?)", (eid, rid, json.dumps(data)))
            for m in world["outbox"][outbox_mark:]:
                self.db.execute("insert or replace into outbox values (?,?)", (m["id"], json.dumps(m)))
            self._meta(model, world)

    # ---------------------------------------------------------------- request corpus
    def record_request(self, entry):
        with self.db:
            self.db.execute("insert into requests(json) values (?)", (json.dumps(entry),))
            self.db.execute("delete from requests where seq <= (select max(seq) from requests) - ?", (REQUEST_CORPUS_LIMIT,))

    def requests(self, limit=REQUEST_CORPUS_LIMIT):
        rows = self.db.execute("select json from requests order by seq desc limit ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    # ---------------------------------------------------------------- ledger
    def ledger(self):
        return [dict(json.loads(r[1]), seq=r[0]) for r in self.db.execute("select seq, json from ledger order by seq")]

    def append_ledger(self, entry):
        with self.db:
            cur = self.db.execute("insert into ledger(json) values (?)", (json.dumps(entry),))
            return cur.lastrowid

    # ---------------------------------------------------------------- engine-upgrade golden snapshot
    def save_golden(self, snap):
        with self.db:
            self.db.execute("insert or replace into golden values (1, ?)", (json.dumps(snap),))

    def golden(self):
        row = self.db.execute("select json from golden where id = 1").fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.db.close()
