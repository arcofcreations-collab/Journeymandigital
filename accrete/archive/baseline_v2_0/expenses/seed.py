"""Rebuild ``data.db`` from scratch: baseline schema + ``seed_data.json`` + every later migration.

    python seed.py                 # from this directory: replaces data.db
    python dev.py check            # verifies that this rebuild equals the committed data.db

``seed_data.json`` is the starting data *at schema version ``SEED_SCHEMA_VERSION``* (the
baseline, 0001). It is never edited: every later change to the data (backfills, new fixed
records, renamed values) is written as SQL in a migration, and this script replays those
migrations over the seed exactly as ``create_app()`` replays them over the committed data.db.
So a rebuild and the migrated data.db always hold the same data. Seed records keep their ids.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from expenses_app import db  # noqa: E402

DATABASE_PATH = os.path.join(HERE, "data.db")
SEED_PATH = os.path.join(HERE, "seed_data.json")
SEED_SCHEMA_VERSION = 1  # seed_data.json matches the schema after migration 0001


def load_seed(conn, seed):
    # Managers come before their reports in the seed file, so foreign keys hold row by row.
    conn.executemany(
        "INSERT INTO employees (id, username, name, role, manager_id, department)"
        " VALUES (:id, :username, :name, :role, :manager, :department)",
        seed["employees"],
    )
    conn.executemany(
        "INSERT INTO claims (id, employee_id, amount, category, description, status,"
        " submitted_at, decided_at, decided_by_id, rejection_reason)"
        " VALUES (:id, :employee, :amount, :category, :description, :status,"
        " :submitted_at, :decided_at, :decided_by, :rejection_reason)",
        seed["claims"],
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


def main():
    seed = build(DATABASE_PATH)
    print(f"seeded {DATABASE_PATH}: " + ", ".join(f"{len(v)} {k}" for k, v in seed.items()))


if __name__ == "__main__":
    main()
