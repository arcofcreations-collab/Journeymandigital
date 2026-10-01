"""Hidden acceptance tests for E04 (maintenance, after E01-E03): time entries, derived labor_minutes.

Back-fill computed from spec/apps/maintenance_seed.json: the 39 completed orders (ascending id) get entries
1..39 (entry 1 = order 2, entry 6 = order 9 by olga 360 min, entry 27 = order 42 by sara 480 min,
entry 39 = order 70 by umar 240 min). umar (13) logged entries 2 3 5 14 17 25 26 33 34 35 39.
In-progress orders (no entries): 47 49 53 56 61 62 79 80.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

LABOR = {2: 315, 4: 345, 5: 45, 7: 330, 8: 210, 9: 360, 10: 225, 11: 360, 12: 150, 16: 315, 17: 450, 18: 405,
         20: 390, 21: 330, 23: 270, 24: 345, 26: 420, 28: 255, 31: 165, 32: 330, 34: 150, 35: 75, 36: 375,
         39: 135, 40: 225, 41: 210, 42: 480, 43: 135, 44: 60, 46: 30, 48: 120, 50: 405, 51: 225, 55: 105,
         57: 390, 58: 75, 59: 150, 67: 105, 70: 240}
NILS_ENTRIES = [2, 3, 5, 6, 7, 8, 14, 16, 17, 18, 21, 23, 25, 26, 28, 31, 33, 34, 35, 38, 39]
WADE_ENTRIES = [9, 10, 11, 12, 13, 15, 19, 20, 22, 24, 27, 29, 30, 32, 36, 37]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="sofia", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def get(app, path, user="sofia", now=NOW):
    r = app.get(path, user=user, now=now)
    assert r.status == 200, r
    return r.json


def log(app, oid, body, user, now=NOW):
    return app.post(f"/api/work_orders/{oid}/log_time", body, user=user, now=now)


def entries_snapshot(app):
    return get(app, "/api/time_entries")["items"], get(app, "/api/work_orders")["items"], outbox(app)


# --------------------------------------------------------------------------- back-fill

def test_time_entries_backfilled_from_labor_minutes():
    app = fresh_app()
    items = get(app, "/api/time_entries")["items"]
    assert [t["id"] for t in items] == list(range(1, 40))
    assert [t["work_order"] for t in items] == sorted(LABOR)
    for t in items:
        assert t["minutes"] == LABOR[t["work_order"]] and t["note"] == "migrated", t
    e = get(app, "/api/time_entries/6")
    for k, v in {"work_order": 9, "technician": 9, "minutes": 360, "logged_at": "2025-10-23T18:00:00",
                 "note": "migrated"}.items():
        assert e[k] == v, (k, e.get(k))
    e = get(app, "/api/time_entries/39")
    assert (e["work_order"], e["technician"], e["minutes"], e["logged_at"]) == (70, 13, 240, "2026-02-27T12:00:00")
    assert ids(app.get("/api/time_entries?technician=13", user="sofia", now=NOW)) == [2, 3, 5, 14, 17, 25, 26, 33, 34, 35, 39]
    orders = get(app, "/api/work_orders")["items"]
    for o in orders:
        assert o["labor_minutes"] == LABOR.get(o["id"]), (o["id"], o["labor_minutes"])
    assert get(app, "/api/work_orders/42", user="sara")["labor_minutes"] == 480


def test_time_entries_follow_work_order_read_rules():
    app = fresh_app()
    assert ids(app.get("/api/time_entries", user="mei", now=NOW)) == [1, 4]
    assert ids(app.get("/api/time_entries", user="tess", now=NOW)) == [1, 4]
    assert ids(app.get("/api/time_entries", user="ruth", now=NOW)) == [6, 21, 34]
    assert ids(app.get("/api/time_entries", user="kofi", now=NOW)) == [8, 35]
    assert ids(app.get("/api/time_entries", user="lina", now=NOW)) == [19]
    assert ids(app.get("/api/time_entries", user="nils", now=NOW)) == NILS_ENTRIES
    assert ids(app.get("/api/time_entries", user="wade", now=NOW)) == WADE_ENTRIES
    assert ids(app.get("/api/time_entries", user="yara", now=NOW)) == list(range(1, 40))
    assert_error(app.get("/api/time_entries/6", user="mei", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/time_entries/9", user="nils", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/time_entries/999", user="mei", now=NOW), 404, "not_found")
    assert parse_ui(app.get("/ui/time_entries", user="ruth", now=NOW).text).rows == [6, 21, 34]


# --------------------------------------------------------------------------- log_time / complete

def test_log_time_then_complete():
    app = fresh_app()
    r = log(app, 62, {"minutes": 45, "note": "Fan replaced"}, user="nils", now=T2)
    assert r.status == 200, r
    assert r.json["id"] == 62 and r.json["labor_minutes"] == 45 and r.json["status"] == "in_progress"
    new = get(app, "/api/time_entries?work_order=62")["items"]
    assert len(new) == 1 and new[0]["id"] > 39
    for k, v in {"work_order": 62, "technician": 8, "minutes": 45, "logged_at": T2, "note": "Fan replaced"}.items():
        assert new[0][k] == v, (k, new[0].get(k))
    r = log(app, 62, {"minutes": 30}, user="nils", now=T2)
    assert r.status == 200 and r.json["labor_minutes"] == 75
    assert get(app, "/api/time_entries?work_order=62")["items"][1]["note"] is None
    before = len(outbox(app))
    r = app.post("/api/work_orders/62/complete", {"resolution": "Filter and fan replaced"}, user="nils", now=T2)
    assert r.status == 200, r
    assert r.json["status"] == "completed" and r.json["labor_minutes"] == 75 and r.json["completed_at"] == T2
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["work_completed"]
    assert msgs[0]["payload"] == {"work_order": 62, "asset": 2, "technician": 8, "labor_minutes": 75, "parts_cost": 0}
    assert_error(log(app, 62, {"minutes": 5}, user="nils", now=T2), 409, "conflict")


def test_complete_requires_a_time_entry():
    app = fresh_app()
    snap = entries_snapshot(app)
    assert_error(app.post("/api/work_orders/62/complete", {"resolution": "x"}, user="nils", now=NOW), 409, "conflict")
    assert_error(app.post("/api/work_orders/62/complete", {"resolution": "x", "labor_minutes": 30},
                          user="nils", now=NOW), 409, "conflict")
    assert_error(app.post("/api/work_orders/62/complete", {}, user="nils", now=NOW), 409, "conflict")
    assert entries_snapshot(app) == snap
    assert log(app, 62, {"minutes": 10}, user="nils").status == 200
    before = outbox(app)
    for body in ({"resolution": "x", "labor_minutes": 10}, {"resolution": ""}, {}, {"resolution": "x", "foo": 1}):
        assert_error(app.post("/api/work_orders/62/complete", body, user="nils", now=NOW), 400, "validation")
    assert outbox(app) == before
    r = app.post("/api/work_orders/62/complete", {"resolution": "x"}, user="nils", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 10


def test_log_time_validation():
    app = fresh_app()
    snap = entries_snapshot(app)
    for body in ({}, {"minutes": 0}, {"minutes": 601}, {"minutes": -5}, {"minutes": 1.5}, {"minutes": "30"},
                 {"minutes": True}, {"minutes": None}, {"minutes": 30, "note": 5},
                 {"minutes": 30, "technician": 9}, {"minutes": 30, "logged_at": NOW}):
        assert_error(log(app, 62, body, user="nils"), 400, "validation")
    assert entries_snapshot(app) == snap
    assert log(app, 62, {"minutes": 600, "note": None}, user="nils").status == 200
    assert log(app, 62, {"minutes": 1}, user="nils").status == 200
    assert get(app, "/api/work_orders/62")["labor_minutes"] == 601


def test_log_time_permissions_and_state():
    app = fresh_app()
    snap = entries_snapshot(app)
    for user in ("olga", "sofia", "kofi", "umar"):
        assert_error(log(app, 62, {"minutes": 10}, user=user), 403, "forbidden")
    assert_error(log(app, 77, {"minutes": 10}, user="nils"), 409, "conflict")     # assigned
    assert_error(log(app, 74, {"minutes": 10}, user="nils"), 403, "forbidden")    # open, not assignee
    assert_error(log(app, 2, {"minutes": 10}, user="nils"), 403, "forbidden")     # 403 before 409
    assert_error(log(app, 2, {"minutes": 10}, user="tess"), 409, "conflict")      # completed
    assert_error(log(app, 2, {"minutes": 0}, user="tess"), 409, "conflict")       # 409 before 400
    assert_error(log(app, 999, {"minutes": 10}, user="tess"), 404, "not_found")
    assert entries_snapshot(app) == snap


def test_time_entries_and_labor_are_read_only():
    app = fresh_app()
    body = {"work_order": 62, "technician": 8, "minutes": 10, "logged_at": NOW, "note": None}
    for user in ("sofia", "nils"):
        assert_error(app.post("/api/time_entries", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/time_entries/1", {"minutes": 1}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/time_entries/1", user=user, now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/work_orders/74", {"labor_minutes": 5}, user="sofia", now=NOW), 400, "validation")
    assert_error(app.post("/api/work_orders", {"asset": 2, "title": "x", "priority": "p3", "labor_minutes": 5},
                          user="ruth", now=NOW), 400, "validation")
    r = app.post("/api/work_orders", {"asset": 2, "title": "Noisy", "priority": "p3"}, user="ruth", now=NOW)
    assert r.status == 201 and r.json["labor_minutes"] is None
    assert get(app, "/api/time_entries/1")["minutes"] == 315


def test_cancel_keeps_time_entries():
    app = fresh_app()
    assert log(app, 53, {"minutes": 50}, user="ravi").status == 200
    r = app.post("/api/work_orders/53/cancel", {"reason": "Pump replaced"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 50 and r.json["status"] == "cancelled"
    assert len(get(app, "/api/time_entries?work_order=53")["items"]) == 1
    assert_error(log(app, 53, {"minutes": 5}, user="ravi"), 409, "conflict")


def test_ui_log_time_and_complete_forms():
    app = fresh_app()

    def acts(oid, user):
        r = app.get(f"/ui/work_orders/{oid}", user=user, now=NOW)
        assert r.status == 200, r
        return parse_ui(r.text).actions

    assert "log_time" in acts(62, "nils") and "complete" not in acts(62, "nils")
    assert "log_time" not in acts(62, "olga") and "log_time" not in acts(62, "sofia")
    assert "log_time" not in acts(77, "nils")
    assert log(app, 62, {"minutes": 15}, user="nils").status == 200
    assert "complete" in acts(62, "nils") and "log_time" in acts(62, "nils")
    ui = parse_ui(app.get("/ui/work_orders/62", user="nils", now=NOW).text)
    assert ui.fields["labor_minutes"] == "15"


# --------------------------------------------------------------------------- interaction with E01-E03

def test_full_flow_with_claim_parts_and_time():
    app = fresh_app()
    assert app.post("/api/work_orders/78/claim", {}, user="wade", now=NOW).status == 200
    assert app.post("/api/work_orders/78/start", {}, user="wade", now=NOW).status == 200
    r = app.post("/api/work_orders/78/use_parts", {"items": [{"part": 4, "quantity": 2}]}, user="wade", now=NOW)
    assert r.status == 200
    assert log(app, 78, {"minutes": 20}, user="wade").status == 200
    assert log(app, 78, {"minutes": 25, "note": "Retest"}, user="wade", now=T2).status == 200
    before = len(outbox(app))
    r = app.post("/api/work_orders/78/complete", {"resolution": "Sensor realigned"}, user="wade", now=T2)
    assert r.status == 200, r
    p = outbox(app)[before]["payload"]
    assert set(p) == {"work_order", "asset", "technician", "labor_minutes", "parts_cost"}
    assert (p["work_order"], p["asset"], p["technician"], p["labor_minutes"]) == (78, 22, 15, 45)
    assert round(p["parts_cost"], 2) == 19.6
    assert ids(app.get("/api/time_entries?work_order=78", user="lina", now=T2)) == \
        ids(app.get("/api/time_entries?work_order=78", user="tomas", now=T2))
    # the inactive assignee can still start, log and complete his order
    assert app.post("/api/work_orders/37/start", {}, user="umar", now=NOW).status == 200
    assert log(app, 37, {"minutes": 35}, user="umar").status == 200
    r = app.post("/api/work_orders/37/complete", {"resolution": "Remote re-paired"}, user="umar", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 35 and r.json["priority"] == "p4"
