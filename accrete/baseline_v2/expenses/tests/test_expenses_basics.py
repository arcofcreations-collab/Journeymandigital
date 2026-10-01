"""Authentication, error format and precedence, outbox, filtering and the seed data."""
import os
import sqlite3

from accept_client import fresh_app


def test_missing_or_unknown_user_is_401(app):
    r = app.get("/api/claims")
    assert r.status == 401 and r.json["error"] == "unauthenticated" and r.json["fields"] == {}
    assert app.get("/api/claims", user="ghost").status == 401
    assert app.get("/api/nothing").status == 401


def test_unknown_collection_record_and_action_are_404(app):
    r = app.get("/api/nothing", user="fiona")
    assert r.status == 404 and r.json["error"] == "not_found"
    assert app.get("/api/claims/999", user="fiona").status == 404
    assert app.post("/api/claims/1/archive", {}, user="wen").status == 404
    assert app.post("/api/claims/999/pay", {}, user="fiona").status == 404


def test_seed_data_is_loaded_with_same_ids(app, seed):
    assert app.get("/api/employees", user="zoe").json["items"] == seed["employees"]
    assert app.get("/api/claims", user="fiona").json["items"] == seed["claims"]


def test_database_is_fully_migrated(app):
    conn = sqlite3.connect(os.path.join(app.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]
    conn.close()
    migrations = sorted(os.listdir(os.path.join(app.workdir, "expenses_app", "migrations")))
    assert versions == [int(name[:4]) for name in migrations if name.endswith(".sql")]


def test_new_migrations_are_applied_on_startup(app):
    with open(os.path.join(app.workdir, "expenses_app", "migrations", "9999_test_only.sql"), "w") as fh:
        fh.write("CREATE TABLE test_only (id INTEGER PRIMARY KEY);\n")
    upgraded = fresh_app(app.workdir)
    conn = sqlite3.connect(os.path.join(upgraded.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version")]
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE name = 'test_only'")]
    conn.close()
    assert 9999 in versions and tables == ["test_only"]
    assert upgraded.get("/api/_outbox", user="fiona").status == 200


def test_failed_migration_is_rolled_back(app):
    with open(os.path.join(app.workdir, "expenses_app", "migrations", "9999_broken.sql"), "w") as fh:
        fh.write("CREATE TABLE half_done (id INTEGER);\nTHIS IS NOT SQL;\n")
    try:
        fresh_app(app.workdir)
    except Exception:
        pass
    else:
        raise AssertionError("broken migration should fail startup")
    conn = sqlite3.connect(os.path.join(app.workdir, "data.db"))
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'half_done'").fetchall() == []
    assert 9999 not in [row[0] for row in conn.execute("SELECT version FROM schema_version")]
    conn.close()


def test_filters(app):
    items = app.get("/api/claims?status=draft&employee=12", user="fiona").json["items"]
    assert items and all(c["status"] == "draft" and c["employee"] == 12 for c in items)
    assert [e["id"] for e in app.get("/api/employees?manager=3", user="zoe").json["items"]] == [7, 10, 13]
    assert [e["id"] for e in app.get("/api/employees?manager=null&role=manager", user="zoe").json["items"]] == [2, 3]
    assert [c["id"] for c in app.get("/api/claims?amount=734.81", user="fiona").json["items"]] == [2]
    assert app.get("/api/claims?colour=red", user="fiona").status == 400


def test_outbox_starts_empty(app):
    r = app.get("/api/_outbox", user="priya")
    assert r.status == 200 and r.json == {"items": []}


def test_invalid_x_now_is_400(app):
    assert app.get("/api/claims", user="fiona", now="2026-13-01").status == 400
