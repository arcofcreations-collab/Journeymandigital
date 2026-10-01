"""Rebuild ``data.db`` from scratch: apply all migrations, then load ``seed_data.json``.

    python seed.py            # from this directory

Seed records keep their ids. Any existing database file is replaced.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from maintenance_app import db  # noqa: E402

DATABASE_PATH = os.path.join(HERE, "data.db")
SEED_PATH = os.path.join(HERE, "seed_data.json")


def load_seed(conn, seed):
    # Staff and assets first, so the work orders' foreign keys hold row by row.
    conn.executemany(
        "INSERT INTO staff (id, username, name, role, site, active)"
        " VALUES (:id, :username, :name, :role, :site, :active)",
        seed["staff"],
    )
    conn.executemany(
        "INSERT INTO assets (id, tag, name, site, criticality, retired)"
        " VALUES (:id, :tag, :name, :site, :criticality, :retired)",
        seed["assets"],
    )
    conn.executemany(
        "INSERT INTO work_orders (id, asset_id, title, description, priority, status, requested_by_id,"
        " created_at, assignee_id, started_at, completed_at, resolution, labor_minutes, cancel_reason)"
        " VALUES (:id, :asset, :title, :description, :priority, :status, :requested_by,"
        " :created_at, :assignee, :started_at, :completed_at, :resolution, :labor_minutes, :cancel_reason)",
        seed["work_orders"],
    )


def main():
    if os.path.exists(DATABASE_PATH):
        os.remove(DATABASE_PATH)
    db.migrate(DATABASE_PATH)
    with open(SEED_PATH, encoding="utf-8") as fh:
        seed = json.load(fh)
    conn = db.connect(DATABASE_PATH)
    try:
        conn.execute("BEGIN")
        load_seed(conn, seed)
        conn.execute("COMMIT")
    finally:
        conn.close()
    print(f"seeded {DATABASE_PATH}: " + ", ".join(f"{len(v)} {k}" for k, v in seed.items()))


if __name__ == "__main__":
    main()
