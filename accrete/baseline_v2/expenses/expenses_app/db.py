"""SQLite connection handling, transactions and the schema migration runner.

Connections run in autocommit mode (``isolation_level=None``); code that writes wraps
its work in ``with transaction():`` so checks and writes happen atomically.
"""
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import current_app, g

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
MIGRATION_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Return the connection for the current request, opening it on first use."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction():
    """Run the block in a write transaction; commit on success, roll back on any error."""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def init_app(app):
    app.teardown_appcontext(close_db)


# --- migrations ---------------------------------------------------------------------

def available_migrations(migrations_dir=MIGRATIONS_DIR):
    """Return ``[(version, name, path)]`` for every migration file, ordered by version."""
    found = []
    for filename in os.listdir(migrations_dir):
        match = MIGRATION_FILENAME.match(filename)
        if match:
            found.append((int(match.group(1)), match.group(2), os.path.join(migrations_dir, filename)))
        elif filename.endswith(".sql"):
            raise RuntimeError(f"badly named migration file: {filename} (expected NNNN_name.sql)")
    found.sort()
    versions = [version for version, _, _ in found]
    if len(versions) != len(set(versions)):
        raise RuntimeError("two migration files share a version number")
    return found


def applied_versions(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    return {row[0] for row in conn.execute("SELECT version FROM schema_version")}


def migrate(database_path, migrations_dir=MIGRATIONS_DIR, up_to=None):
    """Apply every pending migration in order, each in its own transaction.

    ``up_to`` (a version number) stops after that version; ``seed.py`` uses it to load the
    seed data at the baseline schema and then replay the later migrations over it.
    Returns the list of applied migration file names.

    Foreign keys are switched off while a migration runs (SQLite's recommended way to rebuild
    a table: create ``x_new``, copy, ``DROP TABLE x``, rename ``x_new`` to ``x``) and checked
    with ``PRAGMA foreign_key_check`` before the migration commits: a migration that leaves a
    dangling reference fails and is rolled back.
    """
    conn = connect(database_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # only for this migration connection
    try:
        done = applied_versions(conn)
        applied = []
        for version, name, path in available_migrations(migrations_dir):
            if version in done:
                continue
            if up_to is not None and version > up_to:
                break
            with open(path, encoding="utf-8") as fh:
                sql = fh.read()
            applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            try:
                conn.executescript(f"BEGIN;\n{sql}\n;")
                broken = conn.execute("PRAGMA foreign_key_check").fetchall()
                if broken:
                    raise sqlite3.IntegrityError(
                        f"migration {os.path.basename(path)} leaves dangling references"
                        f" (table, rowid, parent, fk): {[tuple(row) for row in broken[:5]]}"
                    )
                conn.execute(
                    "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, applied_at),
                )
                conn.execute("COMMIT")
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            applied.append(os.path.basename(path))
        return applied
    finally:
        conn.close()
