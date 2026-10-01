"""Authentication, error format and precedence, outbox, filtering, migrations and the seed data."""
import os
import sqlite3

from accept_client import fresh_app

DERIVED = {"assets": ("open_orders",), "work_orders": ("due_date", "overdue")}


def _without_derived(collection, items):
    return [{k: v for k, v in item.items() if k not in DERIVED.get(collection, ())} for item in items]


def test_missing_or_unknown_user_is_401(app):
    r = app.get("/api/staff")
    assert r.status == 401 and r.json == {"error": "unauthenticated", "message": r.json["message"], "fields": {}}
    assert app.get("/api/staff", user="ghost").status == 401
    assert app.get("/api/nothing").status == 401
    assert app.post("/api/work_orders/1/cancel", {"reason": "x"}).status == 401


def test_inactive_staff_are_valid_identities(app):
    assert app.get("/api/work_orders", user="vera").status == 200  # inactive requester
    r = app.post("/api/work_orders", {"asset": 2, "title": "Noise", "priority": "low"}, user="vera")
    assert r.status == 201 and r.json["requested_by"] == 14


def test_unknown_collection_record_and_action_are_404(app):
    r = app.get("/api/nothing", user="sofia")
    assert r.status == 404 and r.json["error"] == "not_found"
    assert app.get("/api/work_orders/999", user="sofia").status == 404
    assert app.get("/api/staff/999", user="sofia").status == 404
    assert app.post("/api/work_orders/74/archive", {}, user="sofia").status == 404
    assert app.post("/api/work_orders/999/assign", {"technician": 8}, user="ruth").status == 404  # 404 beats 403
    assert app.patch("/api/assets/999", {"retired": "x"}, user="ruth").status == 404
    assert app.get("/ui/nothing", user="sofia").status == 404


def test_seed_data_is_loaded_with_same_ids(app, seed):
    for collection in ("staff", "assets", "work_orders"):
        items = app.get(f"/api/{collection}", user="sofia").json["items"]
        assert _without_derived(collection, items) == seed[collection]


def test_database_is_fully_migrated(app):
    conn = sqlite3.connect(os.path.join(app.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version ORDER BY version")]
    outbox = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    conn.close()
    migrations = sorted(os.listdir(os.path.join(app.workdir, "maintenance_app", "migrations")))
    assert versions == [int(name[:4]) for name in migrations if name.endswith(".sql")]
    assert outbox == 0


def test_new_migrations_are_applied_on_startup(app):
    with open(os.path.join(app.workdir, "maintenance_app", "migrations", "9999_test_only.sql"), "w") as fh:
        fh.write("CREATE TABLE test_only (id INTEGER PRIMARY KEY);\n")
    upgraded = fresh_app(app.workdir)
    conn = sqlite3.connect(os.path.join(upgraded.workdir, "data.db"))
    versions = [row[0] for row in conn.execute("SELECT version FROM schema_version")]
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE name = 'test_only'")]
    conn.close()
    assert 9999 in versions and tables == ["test_only"]
    assert upgraded.get("/api/_outbox", user="sofia").status == 200


def test_failed_migration_is_rolled_back(app):
    with open(os.path.join(app.workdir, "maintenance_app", "migrations", "9999_broken.sql"), "w") as fh:
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


def test_filters(app, seed):
    items = app.get("/api/work_orders?status=open&asset=22", user="sofia").json["items"]
    assert [o["id"] for o in items] == [78]
    expected = [o["id"] for o in seed["work_orders"] if o["assignee"] is None]
    assert [o["id"] for o in app.get("/api/work_orders?assignee=null", user="sofia").json["items"]] == expected
    assert [s["id"] for s in app.get("/api/staff?active=false", user="ruth").json["items"]] == [13, 14]
    assert [s["id"] for s in app.get("/api/staff?role=supervisor&site=East", user="ruth").json["items"]] == [16]
    assert [a["id"] for a in app.get("/api/assets?open_orders=2", user="ruth").json["items"]] == [16, 21, 22]
    assert [o["id"] for o in app.get("/api/work_orders?due_date=2026-03-02", user="sofia").json["items"]] == [66, 81, 82]
    assert app.get("/api/work_orders?id=5", user="sofia").json["items"][0]["id"] == 5
    assert app.get("/api/work_orders?colour=red", user="sofia").status == 400
    assert app.get("/api/assets?nope=1", user="sofia").status == 400


def test_filters_only_see_readable_records(app):
    items = app.get("/api/work_orders?status=open", user="mei").json["items"]
    assert items and all(o["requested_by"] == 7 for o in items)


def test_outbox_starts_empty(app):
    r = app.get("/api/_outbox", user="ruth")
    assert r.status == 200 and r.json == {"items": []}


def test_invalid_x_now_is_400(app):
    assert app.get("/api/staff", user="sofia", now="2026-13-01").status == 400


def test_error_shape(app):
    r = app.post("/api/staff", {"username": "", "name": "X"}, user="sofia")
    assert r.status == 400 and r.json["error"] == "validation"
    assert {"username", "role", "site"} <= set(r.json["fields"])
