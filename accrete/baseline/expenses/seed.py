"""Rebuild ``data.db`` from scratch: apply all migrations, then load ``seed_data.json``.

    python seed.py            # from this directory

Seed records keep their ids. Any existing database file is replaced.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from expenses_app import db  # noqa: E402

DATABASE_PATH = os.path.join(HERE, "data.db")
SEED_PATH = os.path.join(HERE, "seed_data.json")


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
