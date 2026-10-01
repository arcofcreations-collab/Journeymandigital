"""Rebuild ``data.db`` from scratch: apply all migrations, then load ``seed_data.json``.

    python seed.py            # from this directory

Seed records keep their ids. Any existing database file is replaced.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from library_app import db  # noqa: E402

DATABASE_PATH = os.path.join(HERE, "data.db")
SEED_PATH = os.path.join(HERE, "seed_data.json")


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
