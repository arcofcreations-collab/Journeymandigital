"""Hidden acceptance tests for E06 (maintenance, after E01-E05): site-scoped supervisors and the manager role.

Facts (seed): sofia (1) North -> manager; tomas (2) supervisor South; yara (16) supervisor East.
  South orders and East orders as listed below (tomas/yara requested only orders of their own site).
  Time entries on South orders: 9 10 11 12 13 15 19 20 22 24 27 29 30 32 36 37.
  After E05: workloads olga 1, sara 2, tess 2, nils 3, ravi 4.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

SOUTH_ORDERS = [12, 13, 16, 17, 18, 20, 23, 31, 32, 35, 39, 42, 44, 45, 46, 50, 53, 54, 56, 58, 59,
                60, 61, 64, 68, 71, 72, 73, 76, 78, 80]
EAST_ORDERS = [1, 2, 7, 15, 19, 22, 27, 29, 30, 33, 47, 66, 69, 81]
NORTH_ORDERS = [3, 4, 5, 6, 8, 9, 10, 11, 14, 21, 24, 25, 26, 28, 34, 36, 37, 38, 40, 41, 43, 48, 49,
                51, 52, 55, 57, 62, 63, 65, 67, 70, 74, 75, 77, 79, 82]
SOUTH_ENTRIES = [9, 10, 11, 12, 13, 15, 19, 20, 22, 24, 27, 29, 30, 32, 36, 37]


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


def wo(app, oid, user="sofia", now=NOW):
    r = app.get(f"/api/work_orders/{oid}", user=user, now=now)
    assert r.status == 200, r
    return r.json


def assign(app, oid, tech, user):
    return app.post(f"/api/work_orders/{oid}/assign", {"technician": tech}, user=user, now=NOW)


# --------------------------------------------------------------------------- data and reads

def test_sofia_becomes_manager():
    app = fresh_app()
    s = app.get("/api/staff/1", user="ruth", now=NOW).json
    assert s["role"] == "manager" and s["site"] == "North" and s["username"] == "sofia" and s["active"] is True
    assert ids(app.get("/api/staff?role=manager", user="ruth", now=NOW)) == [1]
    assert ids(app.get("/api/staff?role=supervisor", user="ruth", now=NOW)) == [2, 16]
    assert ids(app.get("/api/work_orders", user="sofia", now=NOW)) == list(range(1, 83))
    assert ids(app.get("/api/time_entries", user="sofia", now=NOW)) == list(range(1, 40))


def test_supervisors_read_only_their_site():
    app = fresh_app()
    assert ids(app.get("/api/work_orders", user="tomas", now=NOW)) == SOUTH_ORDERS
    assert ids(app.get("/api/work_orders", user="yara", now=NOW)) == EAST_ORDERS
    assert_error(app.get("/api/work_orders/74", user="tomas", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/work_orders/78", user="yara", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/time_entries", user="tomas", now=NOW)) == SOUTH_ENTRIES
    assert ids(app.get("/api/time_entries", user="yara", now=NOW)) == [1, 4]
    assert parse_ui(app.get("/ui/work_orders", user="yara", now=NOW).text).rows == EAST_ORDERS
    assert app.get("/ui/work_orders/74", user="tomas", now=NOW).status == 403
    # staff, assets and parts stay readable by everyone
    assert ids(app.get("/api/assets", user="tomas", now=NOW)) == list(range(1, 32))
    assert ids(app.get("/api/parts", user="yara", now=NOW)) == list(range(1, 9))
    assert ids(app.get("/api/staff", user="yara", now=NOW)) == list(range(1, 17))
    # other roles unchanged
    assert ids(app.get("/api/work_orders", user="nils", now=NOW)) == NORTH_ORDERS
    assert ids(app.get("/api/work_orders", user="ruth", now=NOW)) == [9, 34, 38, 49, 55, 74, 77]


# --------------------------------------------------------------------------- work-order rights

def test_supervisor_order_rights_limited_to_site():
    app = fresh_app()
    before = outbox(app)
    assert_error(assign(app, 74, 9, user="tomas"), 403, "forbidden")
    assert_error(assign(app, 79, 9, user="tomas"), 403, "forbidden")          # 403 before 409
    assert_error(assign(app, 69, 999, user="tomas"), 403, "forbidden")        # 403 before 400
    assert_error(app.post("/api/work_orders/62/cancel", {"reason": "x"}, user="tomas", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/work_orders/54", {"priority": "p1"}, user="yara", now=NOW), 403, "forbidden")
    assert outbox(app) == before
    r = app.patch("/api/work_orders/54", {"priority": "p1"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["due_date"] == "2026-02-15"
    r = app.post("/api/work_orders/61/cancel", {"reason": "Motor swapped"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled"
    r = assign(app, 69, 12, user="yara")
    assert r.status == 200 and r.json["assignee"] == 12
    # the manager acts on every site
    r = assign(app, 74, 9, user="sofia")
    assert r.status == 200 and r.json["assignee"] == 9
    r = app.post("/api/work_orders/66/cancel", {"reason": "Duplicate"}, user="sofia", now=NOW)
    assert r.status == 200
    r = app.patch("/api/work_orders/78", {"title": "Sensor misaligned (door 2)"}, user="sofia", now=NOW)
    assert r.status == 200


def test_supervisor_creates_orders_only_for_own_site():
    app = fresh_app()
    assert_error(app.post("/api/work_orders", {"asset": 1, "title": "x", "priority": "p3"}, user="tomas", now=NOW),
                 403, "forbidden")
    assert_error(app.post("/api/work_orders", {"asset": 1}, user="tomas", now=NOW), 403, "forbidden")
    r = app.post("/api/work_orders", {"asset": 16, "title": "Guard loose", "priority": "p2"}, user="tomas", now=NOW)
    assert r.status == 201 and r.json["requested_by"] == 2
    r = app.post("/api/work_orders", {"asset": 26, "title": "Lift inspection", "priority": "p2"}, user="sofia", now=NOW)
    assert r.status == 201 and r.json["requested_by"] == 1
    assert r.json["id"] in ids(app.get("/api/work_orders", user="yara", now=NOW))
    assert r.json["id"] not in ids(app.get("/api/work_orders", user="tomas", now=NOW))


# --------------------------------------------------------------------------- assets, parts, staff

def test_assets_are_site_scoped_for_supervisors():
    app = fresh_app()
    body = {"tag": "S-NEW-01", "name": "Compressor 2", "site": "South", "criticality": "medium"}
    r = app.post("/api/assets", body, user="tomas", now=NOW)
    assert r.status == 201, r
    assert_error(app.post("/api/assets", dict(body, tag="N-NEW-01", site="North"), user="tomas", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/assets", dict(body, tag="N-NEW-02", site="North", criticality="x"), user="tomas", now=NOW),
                 403, "forbidden")
    assert_error(app.post("/api/assets", {"tag": "S-NEW-03", "name": "X", "criticality": "low"}, user="tomas", now=NOW),
                 400, "validation")
    assert_error(app.patch("/api/assets/1", {"name": "AHU"}, user="tomas", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/assets/14", {"site": "North"}, user="tomas", now=NOW), 403, "forbidden")
    r = app.patch("/api/assets/14", {"name": "AHU South"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["name"] == "AHU South"
    assert_error(app.delete("/api/assets/24", user="yara", now=NOW), 403, "forbidden")
    assert app.delete("/api/assets/24", user="tomas", now=NOW).status == 204
    assert app.delete("/api/assets/31", user="yara", now=NOW).status == 204
    r = app.patch("/api/assets/7", {"site": "South"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["site"] == "South"
    assert app.get("/api/assets/1", user="ruth", now=NOW).json["name"] == "Air handler 1"


def test_parts_are_site_scoped_for_supervisors():
    app = fresh_app()
    r = app.patch("/api/parts/4", {"quantity": 10}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["quantity"] == 10
    assert_error(app.patch("/api/parts/1", {"quantity": 1}, user="tomas", now=NOW), 403, "forbidden")
    body = {"sku": "S-OIL", "name": "Oil", "unit_cost": 5.0, "quantity": 4, "reorder_level": 1}
    assert_error(app.post("/api/parts", dict(body, site="North"), user="tomas", now=NOW), 403, "forbidden")
    assert app.post("/api/parts", dict(body, site="South"), user="tomas", now=NOW).status == 201
    assert_error(app.delete("/api/parts/7", user="tomas", now=NOW), 403, "forbidden")
    assert app.delete("/api/parts/7", user="yara", now=NOW).status == 204
    r = app.patch("/api/parts/1", {"reorder_level": 6}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["reorder_level"] == 6
    assert app.get("/api/parts/1", user="ruth", now=NOW).json["quantity"] == 12


def test_only_managers_write_staff():
    app = fresh_app()
    body = {"username": "zane", "name": "Zane", "role": "technician", "site": "South"}
    for user in ("tomas", "yara", "ruth"):
        assert_error(app.post("/api/staff", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/staff", {}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/staff/15", {"active": False}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/staff/14", user=user, now=NOW), 403, "forbidden")
    assert_error(app.post("/api/staff", dict(body, role="boss"), user="sofia", now=NOW), 400, "validation")
    r = app.post("/api/staff", dict(body, username="max", role="manager", site="East"), user="sofia", now=NOW)
    assert r.status == 201 and r.json["role"] == "manager"
    assert ids(app.get("/api/work_orders", user="max", now=NOW)) == list(range(1, 83))
    r = app.post("/api/staff", body, user="sofia", now=NOW)
    assert r.status == 201
    zid = r.json["id"]
    r = assign(app, 76, zid, user="tomas")
    assert r.status == 200 and r.json["assignee"] == zid


def test_promoted_supervisor_gets_global_rights():
    app = fresh_app()
    r = app.patch("/api/staff/16", {"role": "manager"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["role"] == "manager"
    assert ids(app.get("/api/work_orders", user="yara", now=NOW)) == list(range(1, 83))
    r = assign(app, 74, 9, user="yara")
    assert r.status == 200
    r = app.post("/api/staff", {"username": "zoe", "name": "Zoe", "role": "requester", "site": "East"},
                 user="yara", now=NOW)
    assert r.status == 201


# --------------------------------------------------------------------------- UI and preserved behaviour

def test_ui_follows_new_rights():
    app = fresh_app()
    assert app.get("/ui/staff/new", user="tomas", now=NOW).status == 403
    assert app.get("/ui/staff/new", user="sofia", now=NOW).status == 200
    assert app.get("/ui/assets/new", user="tomas", now=NOW).status == 200
    assert app.get("/ui/parts/new", user="yara", now=NOW).status == 200
    assert app.get("/ui/assets/new", user="ruth", now=NOW).status == 403
    assert app.get("/ui/parts/new", user="nils", now=NOW).status == 403
    acts = set(parse_ui(app.get("/ui/work_orders/76", user="tomas", now=NOW).text).actions)
    assert {"assign", "cancel"} <= acts
    acts = set(parse_ui(app.get("/ui/work_orders/74", user="sofia", now=NOW).text).actions)
    assert {"assign", "cancel"} <= acts
    acts = set(parse_ui(app.get("/ui/work_orders/66", user="yara", now=NOW).text).actions)
    assert {"assign", "cancel"} <= acts


def test_earlier_rules_preserved():
    app = fresh_app()
    assert_error(assign(app, 74, 8, user="sofia"), 409, "conflict")          # nils at the cap
    assert assign(app, 76, 11, user="tomas").status == 200                   # sara 2 -> 3
    assert_error(assign(app, 78, 11, user="tomas"), 409, "conflict")
    assert_error(app.post("/api/work_orders/78/claim", {}, user="wade", now=NOW), 404, "not_found")
    assert app.post("/api/work_orders/80/log_time", {"minutes": 30}, user="wade", now=NOW).status == 200
    r = app.post("/api/work_orders/80/complete", {"resolution": "Door rehung"}, user="wade", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 30
    assert_error(app.post("/api/work_orders", {"asset": 21, "title": "x", "priority": "p4"}, user="tomas", now=NOW),
                 400, "validation")
    # requesters keep their rights
    r = app.post("/api/work_orders/74/cancel", {"reason": "Fixed"}, user="ruth", now=NOW)
    assert r.status == 200
