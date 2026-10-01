"""Authentication, error format and precedence, outbox, filtering and the seed data."""
import os
import sqlite3

from accept_client import fresh_app


def test_missing_user_is_401(app):
    r = app.get("/api/books")
    assert r.status == 401
    assert r.json == {"error": "unauthenticated", "message": r.json["message"], "fields": {}}


def test_unknown_user_is_401(app):
    assert app.get("/api/books", user="nobody").status == 401


def test_401_beats_404(app):
    assert app.get("/api/nothing").status == 401
    assert app.get("/ui/nothing").status == 401


def test_unknown_collection_record_and_action_are_404(app):
    assert app.get("/api/nothing", user="chen").json["error"] == "not_found"
    assert app.get("/api/books/999", user="chen").status == 404
    assert app.post("/api/books/1/burn", {}, user="ada").status == 404
    assert app.post("/api/books/999/borrow", {}, user="chen").status == 404


def test_invalid_x_now_is_400(app):
    r = app.get("/api/books", user="chen", now="yesterday")
    assert r.status == 400 and r.json["error"] == "validation"


def test_missing_x_now_uses_real_clock(app):
    r = app.get("/api/loans/46", user="ada", now=None)
    assert r.status == 200 and r.json["overdue"] is True


def test_seed_data_is_loaded_with_same_ids(app, seed):
    members = app.get("/api/members", user="ada").json["items"]
    assert members == seed["members"]
    books = app.get("/api/books", user="ada").json["items"]
    assert [{k: v for k, v in b.items() if k != "status"} for b in books] == seed["books"]
    loans = app.get("/api/loans", user="ada").json["items"]
    assert [{k: v for k, v in l.items() if k != "overdue"} for l in loans] == seed["loans"]


def test_database_is_fully_migrated(app):
    conn = sqlite3.connect(os.path.join(app.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]
    conn.close()
    migrations = sorted(os.listdir(os.path.join(app.workdir, "library_app", "migrations")))
    assert versions == [int(name[:4]) for name in migrations if name.endswith(".sql")]


def test_new_migrations_are_applied_on_startup(app):
    with open(os.path.join(app.workdir, "library_app", "migrations", "9999_test_only.sql"), "w") as fh:
        fh.write("CREATE TABLE test_only (id INTEGER PRIMARY KEY);\n")
    upgraded = fresh_app(app.workdir)
    conn = sqlite3.connect(os.path.join(upgraded.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version")]
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE name = 'test_only'")]
    conn.close()
    assert 9999 in versions and tables == ["test_only"]
    assert upgraded.get("/api/_outbox", user="chen").status == 200


def test_failed_migration_is_rolled_back(app):
    with open(os.path.join(app.workdir, "library_app", "migrations", "9999_broken.sql"), "w") as fh:
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


def test_filters_match_exactly(app):
    r = app.get("/api/books?author=K. Tanaka&status=available", user="chen")
    assert r.status == 200
    assert r.json["items"]
    assert all(b["author"] == "K. Tanaka" and b["status"] == "available" for b in r.json["items"])
    loans = app.get("/api/loans?book=4", user="ada").json["items"]
    assert [l["id"] for l in loans] == [l["id"] for l in loans if l["book"] == 4] and loans
    assert [m["id"] for m in app.get("/api/members?active=false", user="ada").json["items"]] == [12]
    assert app.get("/api/books?year=null", user="ada").json["items"][0]["year"] is None


def test_filter_on_unknown_field_is_400(app):
    assert app.get("/api/books?colour=red", user="chen").status == 400


def test_lists_are_in_ascending_id_order(app):
    ids = [b["id"] for b in app.get("/api/books", user="chen").json["items"]]
    assert ids == sorted(ids) and len(ids) == 40


def test_outbox_starts_empty_and_is_readable_by_anyone(app):
    r = app.get("/api/_outbox", user="lena")
    assert r.status == 200 and r.json == {"items": []}
    assert app.get("/api/_outbox").status == 401


def test_body_must_be_a_json_object(app):
    assert app.request("POST", "/api/books", None, user="ada").status == 400  # empty: fields missing
    assert app.patch("/api/books/1", ["not", "an", "object"], user="ada").status == 400
    assert app.patch("/api/books/1", ["not", "an", "object"], user="chen").status == 403  # 403 beats 400
