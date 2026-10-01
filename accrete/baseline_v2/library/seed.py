"""Rebuild ``data.db`` from scratch: baseline schema + ``seed_data.json`` + every later migration.

    python seed.py                 # from this directory: replaces data.db (keeps recorded apply times)
    python dev.py check            # verifies that this rebuild equals the committed data.db

``seed_data.json`` is the starting data *at schema version ``SEED_SCHEMA_VERSION``* (the
baseline, 0001). It is never edited: every later change to the data (backfills, new fixed
records, renamed values) is written as SQL in a migration, and this script replays those
migrations over the seed exactly as ``create_app()`` replays them over the committed data.db.
So a rebuild and the migrated data.db always hold the same data. Seed records keep their ids.
"""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from library_app import db  # noqa: E402

DATABASE_PATH = os.path.join(HERE, "data.db")
SEED_PATH = os.path.join(HERE, "seed_data.json")
SEED_SCHEMA_VERSION = 1  # seed_data.json matches the schema after migration 0001


def load_seed(conn, seed):
    conn.executemany(
        "INSERT INTO members (id, username, name, role, active) VALUES (:id, :username, :name, :role, :active)",
        [{**m, "active": int(m.get("active", True))} for m in seed["members"]],
    )
    conn.executemany(
        "INSERT INTO books (id, title, author, isbn, year) VALUES (:id, :title, :author, :isbn, :year)",
        [{**b, "year": b.get("year")} for b in seed["books"]],
    )
    conn.executemany(
        "INSERT INTO loans (id, book_id, member_id, borrowed_at, due_at, returned_at)"
        " VALUES (:id, :book, :member, :borrowed_at, :due_at, :returned_at)",
        seed["loans"],
    )


def build(database_path):
    """Create a database at ``database_path`` (replacing any file there); return the seed dict."""
    if os.path.exists(database_path):
        os.remove(database_path)
    db.migrate(database_path, up_to=SEED_SCHEMA_VERSION)
    with open(SEED_PATH, encoding="utf-8") as fh:
        seed = json.load(fh)
    conn = db.connect(database_path)
    try:
        conn.execute("BEGIN")
        load_seed(conn, seed)
        conn.execute("COMMIT")
    finally:
        conn.close()
    db.migrate(database_path)  # the later migrations transform the seed like they did data.db
    return seed


def applied_times(database_path):
    """{(version, name): applied_at} recorded in an existing database ({} if there is none)."""
    if not os.path.exists(database_path):
        return {}
    conn = sqlite3.connect(database_path)
    try:
        return {(v, n): a for v, n, a in conn.execute("SELECT version, name, applied_at FROM schema_version")}
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def main():
    # A rebuild keeps the recorded apply times of migrations data.db already had (same version
    # and name); only migrations new to data.db get the current time.
    previous = applied_times(DATABASE_PATH)
    seed = build(DATABASE_PATH)
    conn = sqlite3.connect(DATABASE_PATH)
    try:
        conn.executemany("UPDATE schema_version SET applied_at = ? WHERE version = ? AND name = ?",
                         [(a, v, n) for (v, n), a in previous.items()])
        conn.commit()
    finally:
        conn.close()
    print(f"seeded {DATABASE_PATH}: " + ", ".join(f"{len(v)} {k}" for k, v in seed.items()))


if __name__ == "__main__":
    main()
