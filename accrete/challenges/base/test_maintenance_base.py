"""Strict acceptance tests for the `maintenance` application (spec/apps/maintenance.md + CONTRACT.md).

All expected values are derived from spec/apps/maintenance_seed.json and hard-coded here.

Seed facts used below (computed from the seed file):
  staff: 1 sofia (supervisor, North), 2 tomas (supervisor, South), 3 ruth, 4 kofi (requesters, North),
         5 lina, 6 pavel (requesters, South), 7 mei (requester, East), 8 nils, 9 olga (technicians,
         North), 10 ravi, 11 sara (technicians, South), 12 tess (technician, East),
         13 umar (technician, North, INACTIVE), 14 vera (requester, North, INACTIVE),
         15 wade (technician, South), 16 yara (supervisor, East). Every seed staff member is the
         requester or assignee of at least one work order.
  assets: 1-13 North, 14-24 South, 25-31 East; retired 7 (N-FLT-02), 24 (S-CMP-01), 30 (E-GEN-01);
          assets 24 and 31 have no work orders.
  work orders 1-82: open 30 38 52 54 60 63 65 69 71 74 76 78 81 82 | assigned 37 64 66 68 72 73 75 77 |
          in_progress 47 49 53 56 61 62 79 80 | 39 completed | 13 cancelled.
  overdue at 2026-03-01: 30 37 38 47 52 54 56 61 62 73 76.
  74: N-AHU-01 (asset 1), normal, open, ruth, created 2026-02-26T09:00:00 -> due 2026-03-05.
  77: N-ELV-01 (asset 5), urgent, assigned to nils, requested by ruth, created 2026-02-28 -> due 2026-03-01.
  79: N-FIR-01 (asset 13), urgent, in_progress, olga, requested by sofia.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

ALL_ORDERS = list(range(1, 83))
OPEN = [30, 38, 52, 54, 60, 63, 65, 69, 71, 74, 76, 78, 81, 82]
ASSIGNED = [37, 64, 66, 68, 72, 73, 75, 77]
IN_PROGRESS = [47, 49, 53, 56, 61, 62, 79, 80]
OVERDUE = [30, 37, 38, 47, 52, 54, 56, 61, 62, 73, 76]
NORTH_ORDERS = [3, 4, 5, 6, 8, 9, 10, 11, 14, 21, 24, 25, 26, 28, 34, 36, 37, 38, 40, 41, 43, 48, 49,
                51, 52, 55, 57, 62, 63, 65, 67, 70, 74, 75, 77, 79, 82]
SOUTH_ORDERS = [12, 13, 16, 17, 18, 20, 23, 31, 32, 35, 39, 42, 44, 45, 46, 50, 53, 54, 56, 58, 59,
                60, 61, 64, 68, 71, 72, 73, 76, 78, 80]
EAST_ORDERS = [1, 2, 7, 15, 19, 22, 27, 29, 30, 33, 47, 66, 69, 81]
RUTH_ORDERS = [9, 34, 38, 49, 55, 74, 77]
MEI_ORDERS = [2, 7, 19, 29, 30, 66, 69]
OPEN_ORDERS = {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 0, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1, 13: 1,
               14: 1, 15: 1, 16: 2, 17: 1, 18: 1, 19: 1, 20: 1, 21: 2, 22: 2, 23: 1, 24: 0,
               25: 1, 26: 1, 27: 1, 28: 1, 29: 1, 30: 0, 31: 0}
ACTIONS = ("assign", "start", "complete", "cancel")


def assert_error(r, status, code):
    assert r.status == status, r
    body = r.json
    assert isinstance(body, dict), r
    assert body.get("error") == code, r
    assert isinstance(body.get("message"), str), r
    assert isinstance(body.get("fields"), dict), r


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


def new_order(app, user, asset, priority="normal", title="Leaking tap", now=NOW, **extra):
    body = dict({"asset": asset, "title": title, "priority": priority}, **extra)
    r = app.post("/api/work_orders", body, user=user, now=now)
    assert r.status == 201, r
    return r.json


# --------------------------------------------------------------------------- identity / errors

def test_missing_and_unknown_user_are_401():
    app = fresh_app()
    assert_error(app.get("/api/work_orders", user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/staff", user="nobody", now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/work_orders", {"asset": 1, "title": "x", "priority": "low"},
                          user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/work_orders/74/assign", {"technician": 8}, user="ghost", now=NOW),
                 401, "unauthenticated")
    assert_error(app.get("/api/_outbox", user="ghost", now=NOW), 401, "unauthenticated")


def test_401_precedes_404():
    app = fresh_app()
    assert_error(app.get("/api/work_orders/999", user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/gadgets", user="nobody", now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/work_orders/74/explode", {}, user="nobody", now=NOW), 401, "unauthenticated")


def test_unknown_collection_record_and_action_are_404():
    app = fresh_app()
    assert_error(app.get("/api/gadgets", user="sofia", now=NOW), 404, "not_found")
    assert_error(app.get("/api/work_orders/999", user="sofia", now=NOW), 404, "not_found")
    assert_error(app.get("/api/assets/999", user="ruth", now=NOW), 404, "not_found")
    assert_error(app.get("/api/staff/999", user="ruth", now=NOW), 404, "not_found")
    assert_error(app.post("/api/work_orders/999/assign", {"technician": 8}, user="sofia", now=NOW),
                 404, "not_found")
    assert_error(app.post("/api/work_orders/74/approve", {}, user="sofia", now=NOW), 404, "not_found")
    assert_error(app.post("/api/assets/1/assign", {}, user="sofia", now=NOW), 404, "not_found")


def test_404_precedes_403():
    app = fresh_app()
    # ruth may not read other people's orders, but an unknown id is 404
    assert_error(app.get("/api/work_orders/999", user="ruth", now=NOW), 404, "not_found")
    # nobody may delete work orders, but an unknown one is 404
    assert_error(app.delete("/api/work_orders/999", user="sofia", now=NOW), 404, "not_found")
    assert_error(app.patch("/api/work_orders/999", {"title": "x"}, user="ruth", now=NOW), 404, "not_found")
    assert_error(app.post("/api/work_orders/999/assign", {"technician": 8}, user="ruth", now=NOW),
                 404, "not_found")
    assert_error(app.patch("/api/staff/999", {"name": "x"}, user="ruth", now=NOW), 404, "not_found")
    assert_error(app.delete("/api/assets/999", user="nils", now=NOW), 404, "not_found")


# --------------------------------------------------------------------------- staff and assets: reads

def test_any_user_reads_all_staff_and_assets():
    app = fresh_app()
    for user in ("ruth", "tess", "yara", "vera"):
        assert ids(app.get("/api/staff", user=user, now=NOW)) == list(range(1, 17))
        assert ids(app.get("/api/assets", user=user, now=NOW)) == list(range(1, 32))
    s = app.get("/api/staff/13", user="mei", now=NOW).json
    expected = {"id": 13, "username": "umar", "name": "Umar Farouk", "role": "technician",
                "site": "North", "active": False}
    for k, v in expected.items():
        assert s[k] == v, (k, s.get(k))
    a = app.get("/api/assets/7", user="mei", now=NOW).json
    expected = {"id": 7, "tag": "N-FLT-02", "name": "Forklift 2", "site": "North", "criticality": "medium",
                "retired": True, "open_orders": 0}
    for k, v in expected.items():
        assert a[k] == v, (k, a.get(k))


def test_staff_filters():
    app = fresh_app()
    assert ids(app.get("/api/staff?role=technician", user="ruth", now=NOW)) == [8, 9, 10, 11, 12, 13, 15]
    assert ids(app.get("/api/staff?role=technician&site=South", user="ruth", now=NOW)) == [10, 11, 15]
    assert ids(app.get("/api/staff?active=false", user="ruth", now=NOW)) == [13, 14]
    assert ids(app.get("/api/staff?username=yara", user="ruth", now=NOW)) == [16]
    assert ids(app.get("/api/staff?site=West", user="ruth", now=NOW)) == []
    assert_error(app.get("/api/staff?colour=red", user="ruth", now=NOW), 400, "validation")


def test_asset_open_orders_derived_and_filters():
    app = fresh_app()
    r = app.get("/api/assets", user="kofi", now=NOW)
    got = {a["id"]: a["open_orders"] for a in r.json["items"]}
    assert got == OPEN_ORDERS
    assert ids(app.get("/api/assets?open_orders=2", user="kofi", now=NOW)) == [16, 21, 22]
    assert ids(app.get("/api/assets?retired=true", user="kofi", now=NOW)) == [7, 24, 30]
    assert ids(app.get("/api/assets?site=East&criticality=high", user="kofi", now=NOW)) == [26, 31]
    assert ids(app.get("/api/assets?tag=S-GEN-01", user="kofi", now=NOW)) == [21]


# --------------------------------------------------------------------------- staff and assets: writes

def test_supervisor_creates_staff_with_default_active():
    app = fresh_app()
    body = {"username": "zane", "name": "Zane Ortiz", "role": "technician", "site": "East"}
    r = app.post("/api/staff", body, user="yara", now=NOW)
    assert r.status == 201, r
    for k, v in body.items():
        assert r.json[k] == v, k
    assert r.json["active"] is True
    assert isinstance(r.json["id"], int) and r.json["id"] not in range(1, 17)
    assert ids(app.get("/api/staff", user="ruth", now=NOW))[-1] == r.json["id"]


def test_staff_validation():
    app = fresh_app()
    full = {"username": "zane", "name": "Zane", "role": "technician", "site": "East"}
    for missing in ("username", "name", "role", "site"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/staff", body, user="sofia", now=NOW), 400, "validation")
    for bad in ({"username": "nils"}, {"role": "manager"}, {"active": "yes"}, {"name": "   "},
                {"name": None}, {"shift": "night"}, {"id": 99}):
        assert_error(app.post("/api/staff", dict(full, **bad), user="sofia", now=NOW), 400, "validation")
    assert_error(app.patch("/api/staff/8", {"username": "olga"}, user="sofia", now=NOW), 400, "validation")
    assert_error(app.patch("/api/staff/8", {"role": "boss"}, user="sofia", now=NOW), 400, "validation")
    assert ids(app.get("/api/staff", user="sofia", now=NOW)) == list(range(1, 17))
    assert app.get("/api/staff/8", user="sofia", now=NOW).json["username"] == "nils"


def test_non_supervisors_cannot_write_staff_or_assets():
    app = fresh_app()
    staff_body = {"username": "zane", "name": "Zane", "role": "requester", "site": "North"}
    asset_body = {"tag": "N-NEW-01", "name": "New", "site": "North", "criticality": "low"}
    for user in ("ruth", "nils", "umar"):
        assert_error(app.post("/api/staff", staff_body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/staff", {}, user=user, now=NOW), 403, "forbidden")  # 403 before 400
        assert_error(app.patch("/api/staff/3", {"name": "Ruth A."}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/staff/14", user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/assets", asset_body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/assets/1", {"criticality": "bogus"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/assets/31", user=user, now=NOW), 403, "forbidden")
    assert app.get("/api/staff/3", user="ruth", now=NOW).json["name"] == "Ruth Adler"
    assert app.get("/api/assets/31", user="ruth", now=NOW).status == 200


def test_supervisor_creates_and_updates_asset():
    app = fresh_app()
    r = app.post("/api/assets", {"tag": "S-PMP-03", "name": "Process pump 3", "site": "South",
                                 "criticality": "medium"}, user="tomas", now=NOW)
    assert r.status == 201, r
    a = r.json
    assert a["tag"] == "S-PMP-03" and a["name"] == "Process pump 3" and a["site"] == "South"
    assert a["criticality"] == "medium" and a["retired"] is False and a["open_orders"] == 0
    assert isinstance(a["id"], int) and a["id"] not in range(1, 32)
    r = app.patch("/api/assets/1", {"name": "AHU 1", "criticality": "medium"}, user="yara", now=NOW)
    assert r.status == 200, r
    assert r.json["name"] == "AHU 1" and r.json["criticality"] == "medium"
    assert r.json["tag"] == "N-AHU-01" and r.json["open_orders"] == 1


def test_asset_validation():
    app = fresh_app()
    full = {"tag": "E-NEW-01", "name": "New", "site": "East", "criticality": "low"}
    for missing in ("tag", "name", "site", "criticality"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/assets", body, user="sofia", now=NOW), 400, "validation")
    for bad in ({"tag": "N-AHU-01"}, {"criticality": "extreme"}, {"retired": "no"},
                {"open_orders": 0}, {"tag": ""}):
        assert_error(app.post("/api/assets", dict(full, **bad), user="sofia", now=NOW), 400, "validation")
    assert_error(app.patch("/api/assets/2", {"tag": "N-AHU-01"}, user="sofia", now=NOW), 400, "validation")
    assert ids(app.get("/api/assets", user="sofia", now=NOW)) == list(range(1, 32))


def test_retire_asset_rules():
    app = fresh_app()
    assert_error(app.patch("/api/assets/16", {"retired": True}, user="sofia", now=NOW), 409, "conflict")
    # 409 wins over 400
    assert_error(app.patch("/api/assets/16", {"retired": True, "criticality": "bogus"}, user="sofia", now=NOW),
                 409, "conflict")
    assert app.get("/api/assets/16", user="sofia", now=NOW).json["retired"] is False
    r = app.patch("/api/assets/31", {"retired": True}, user="yara", now=NOW)
    assert r.status == 200 and r.json["retired"] is True
    r = app.patch("/api/assets/7", {"retired": False}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["retired"] is False
    # once its last unfinished order is cancelled, asset 1 can be retired
    assert app.post("/api/work_orders/74/cancel", {"reason": "Duplicate"}, user="sofia", now=NOW).status == 200
    r = app.patch("/api/assets/1", {"retired": True}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["retired"] is True and r.json["open_orders"] == 0


def test_delete_staff_and_asset_rules():
    app = fresh_app()
    for sid in (14, 13, 16):  # all referenced by work orders
        assert_error(app.delete(f"/api/staff/{sid}", user="sofia", now=NOW), 409, "conflict")
    new = app.post("/api/staff", {"username": "temp", "name": "Temp", "role": "requester", "site": "East"},
                   user="sofia", now=NOW).json
    assert app.delete(f"/api/staff/{new['id']}", user="sofia", now=NOW).status == 204
    assert_error(app.get(f"/api/staff/{new['id']}", user="sofia", now=NOW), 404, "not_found")
    assert_error(app.delete("/api/assets/7", user="sofia", now=NOW), 409, "conflict")   # finished orders only
    assert_error(app.delete("/api/assets/16", user="sofia", now=NOW), 409, "conflict")
    assert app.delete("/api/assets/31", user="sofia", now=NOW).status == 204
    assert app.delete("/api/assets/24", user="tomas", now=NOW).status == 204
    assert ids(app.get("/api/assets", user="sofia", now=NOW)) == list(range(1, 24)) + list(range(25, 31))
    assert ids(app.get("/api/staff", user="sofia", now=NOW)) == list(range(1, 17))


def test_new_staff_is_identity_and_assignable():
    app = fresh_app()
    r = app.post("/api/staff", {"username": "zane", "name": "Zane", "role": "technician", "site": "East"},
                 user="yara", now=NOW)
    assert r.status == 201, r
    zid = r.json["id"]
    assert ids(app.get("/api/work_orders", user="zane", now=NOW)) == EAST_ORDERS
    r = app.post("/api/work_orders/69/assign", {"technician": zid}, user="yara", now=NOW)
    assert r.status == 200 and r.json["assignee"] == zid
    r = app.post("/api/work_orders/69/start", {}, user="zane", now=T2)
    assert r.status == 200 and r.json["started_at"] == T2


# --------------------------------------------------------------------------- work orders: reads

def test_work_order_lists_per_role():
    app = fresh_app()
    for user in ("sofia", "tomas", "yara"):
        assert ids(app.get("/api/work_orders", user=user, now=NOW)) == ALL_ORDERS
    assert ids(app.get("/api/work_orders", user="ruth", now=NOW)) == RUTH_ORDERS
    assert ids(app.get("/api/work_orders", user="mei", now=NOW)) == MEI_ORDERS
    assert ids(app.get("/api/work_orders", user="vera", now=NOW)) == [14, 36, 43, 48, 52]
    for user in ("nils", "olga", "umar"):
        assert ids(app.get("/api/work_orders", user=user, now=NOW)) == NORTH_ORDERS
    assert ids(app.get("/api/work_orders", user="wade", now=NOW)) == SOUTH_ORDERS
    assert ids(app.get("/api/work_orders", user="tess", now=NOW)) == EAST_ORDERS


def test_work_order_read_permissions():
    app = fresh_app()
    assert app.get("/api/work_orders/74", user="ruth", now=NOW).status == 200
    for user in ("kofi", "lina", "vera", "ravi", "tess"):
        assert_error(app.get("/api/work_orders/74", user=user, now=NOW), 403, "forbidden")
    for user in ("nils", "umar", "yara"):
        assert app.get("/api/work_orders/74", user=user, now=NOW).status == 200
    # a new South order is visible to South technicians only (and supervisors)
    r = app.post("/api/work_orders", {"asset": 21, "title": "Fuel smell", "priority": "urgent"},
                 user="tomas", now=NOW)
    assert r.status == 201
    assert_error(app.get(f"/api/work_orders/{r.json['id']}", user="nils", now=NOW), 403, "forbidden")
    assert app.get(f"/api/work_orders/{r.json['id']}", user="sara", now=NOW).status == 200


def test_work_order_fields_match_seed():
    app = fresh_app()
    o = wo(app, 47, user="tess")
    expected = {"id": 47, "asset": 29, "title": "Flicker", "description": None, "priority": "low",
                "status": "in_progress", "requested_by": 16, "created_at": "2026-01-28T09:00:00",
                "assignee": 12, "started_at": "2026-02-02T10:00:00", "completed_at": None,
                "resolution": None, "labor_minutes": None, "cancel_reason": None,
                "due_date": "2026-02-27", "overdue": True}
    for k, v in expected.items():
        assert k in o, k
        assert o[k] == v, (k, o[k])
    o = wo(app, 2, user="mei")
    expected = {"asset": 25, "title": "Replace fuse", "priority": "normal", "status": "completed",
                "requested_by": 7, "assignee": 12, "created_at": "2025-10-07T01:00:00",
                "started_at": "2025-10-07T23:00:00", "completed_at": "2025-10-09T05:00:00",
                "resolution": "Cleaned and lubricated", "labor_minutes": 315, "cancel_reason": None,
                "due_date": "2025-10-14", "overdue": False}
    for k, v in expected.items():
        assert o[k] == v, (k, o[k])
    o = wo(app, 3, user="olga")
    expected = {"asset": 6, "status": "cancelled", "requested_by": 13, "assignee": 9,
                "description": "Reported during routine walk-round", "cancel_reason": "Duplicate request",
                "started_at": None, "completed_at": None, "labor_minutes": None, "overdue": False}
    for k, v in expected.items():
        assert o[k] == v, (k, o[k])


def test_due_date_and_overdue_derived():
    app = fresh_app()
    items = app.get("/api/work_orders", user="sofia", now=NOW).json["items"]
    overdue = [o["id"] for o in items if o["overdue"] is True]
    assert overdue == OVERDUE
    assert all(o["overdue"] in (True, False) for o in items)
    due = {o["id"]: o["due_date"] for o in items}
    assert due[74] == "2026-03-05"     # normal: +7
    assert due[82] == "2026-03-02"     # urgent: +1
    assert due[30] == "2026-02-04"     # low: +30
    assert due[37] == "2026-02-14"
    assert due[1] == "2025-10-14"
    assert ids(app.get("/api/work_orders?overdue=true", user="sofia", now=NOW)) == OVERDUE


def test_overdue_uses_now_date_boundary():
    app = fresh_app()
    # order 77 (urgent, created 2026-02-28) is due 2026-03-01
    assert wo(app, 77, now="2026-03-01T23:59:59")["overdue"] is False
    assert wo(app, 77, now="2026-03-02T00:00:00")["overdue"] is True
    later = app.get("/api/work_orders?overdue=true", user="sofia", now="2026-03-02T08:00:00")
    assert ids(later) == [30, 37, 38, 47, 52, 54, 56, 61, 62, 65, 73, 76, 77, 79, 80]
    # an early "now" makes order 30 (due 2026-02-04) not overdue
    assert wo(app, 30, now="2026-02-04T18:00:00")["overdue"] is False
    # finished orders are never overdue
    assert wo(app, 1, now="2027-01-01T00:00:00")["overdue"] is False


def test_work_order_filters():
    app = fresh_app()
    assert ids(app.get("/api/work_orders?status=open", user="sofia", now=NOW)) == OPEN
    assert ids(app.get("/api/work_orders?status=in_progress", user="sofia", now=NOW)) == IN_PROGRESS
    assert ids(app.get("/api/work_orders?status=open&priority=urgent", user="sofia", now=NOW)) == [76, 81, 82]
    assert ids(app.get("/api/work_orders?asset=16", user="sofia", now=NOW)) == [17, 35, 61, 76]
    assert ids(app.get("/api/work_orders?assignee=10&status=assigned", user="sofia", now=NOW)) == [68, 73]
    assert ids(app.get("/api/work_orders?assignee=null&status=cancelled", user="sofia", now=NOW)) == [1, 6, 15, 25, 27, 45]
    # filters respect read permission
    assert ids(app.get("/api/work_orders?status=open", user="ruth", now=NOW)) == [38, 74]
    assert ids(app.get("/api/work_orders?overdue=true", user="nils", now=NOW)) == [37, 38, 52, 62]
    assert_error(app.get("/api/work_orders?site=North", user="sofia", now=NOW), 400, "validation")


# --------------------------------------------------------------------------- work orders: create

def test_requester_creates_work_order_defaults():
    app = fresh_app()
    r = app.post("/api/work_orders", {"asset": 8, "title": "Pump vibrating", "priority": "normal"},
                 user="ruth", now="2026-03-10T08:15:00")
    assert r.status == 201, r
    o = r.json
    assert isinstance(o["id"], int) and o["id"] not in ALL_ORDERS
    expected = {"asset": 8, "title": "Pump vibrating", "description": None, "priority": "normal",
                "status": "open", "requested_by": 3, "created_at": "2026-03-10T08:15:00", "assignee": None,
                "started_at": None, "completed_at": None, "resolution": None, "labor_minutes": None,
                "cancel_reason": None, "due_date": "2026-03-17", "overdue": False}
    for k, v in expected.items():
        assert k in o, k
        assert o[k] == v, (k, o[k])
    assert ids(app.get("/api/work_orders", user="ruth", now=NOW)) == RUTH_ORDERS + [o["id"]]
    assert app.get("/api/assets/8", user="ruth", now=NOW).json["open_orders"] == 2
    # same-site technicians can read it, other requesters cannot
    assert app.get(f"/api/work_orders/{o['id']}", user="olga", now=NOW).status == 200
    assert_error(app.get(f"/api/work_orders/{o['id']}", user="kofi", now=NOW), 403, "forbidden")


def test_create_due_dates_per_priority():
    app = fresh_app()
    late = "2026-02-25T23:30:00"
    assert new_order(app, "tomas", 19, "urgent", now=late)["due_date"] == "2026-02-26"
    assert new_order(app, "tomas", 19, "normal", now=late)["due_date"] == "2026-03-04"
    assert new_order(app, "tomas", 19, "low", now=late)["due_date"] == "2026-03-27"
    o = new_order(app, "lina", 22, "low", description="Gap under door", now="2026-12-15T10:00:00")
    assert o["due_date"] == "2027-01-14" and o["description"] == "Gap under door"


def test_create_site_rule():
    app = fresh_app()
    body = {"asset": 16, "title": "Noise", "priority": "low"}  # South asset
    assert_error(app.post("/api/work_orders", body, user="ruth", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders", body, user="nils", now=NOW), 403, "forbidden")
    # 403 wins over 400
    assert_error(app.post("/api/work_orders", {"asset": 16, "priority": "asap"}, user="ruth", now=NOW),
                 403, "forbidden")
    assert_error(app.post("/api/work_orders", {"asset": 24, "title": "x", "priority": "low"}, user="mei", now=NOW),
                 403, "forbidden")  # retired South asset, East requester
    assert new_order(app, "lina", 16)["requested_by"] == 5
    assert new_order(app, "ravi", 16)["requested_by"] == 10
    o = new_order(app, "sofia", 16)                 # supervisors may create for any site
    assert o["requested_by"] == 1 and o["asset"] == 16
    assert app.get("/api/assets/16", user="sofia", now=NOW).json["open_orders"] == 5


def test_create_validation():
    app = fresh_app()
    full = {"asset": 1, "title": "Noise", "priority": "low"}
    for missing in ("asset", "title", "priority"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/work_orders", body, user="ruth", now=NOW), 400, "validation")
    for bad in ({"priority": "asap"}, {"asset": 999}, {"asset": 7}, {"title": "  "}, {"title": None},
                {"status": "assigned"}, {"requested_by": 3}, {"assignee": 8}, {"created_at": NOW},
                {"due_date": "2026-03-02"}, {"overdue": False}, {"labor_minutes": 5}, {"colour": "red"}):
        assert_error(app.post("/api/work_orders", dict(full, **bad), user="ruth", now=NOW), 400, "validation")
    assert ids(app.get("/api/work_orders", user="sofia", now=NOW)) == ALL_ORDERS


def test_inactive_staff_can_create_orders():
    app = fresh_app()
    assert new_order(app, "vera", 12, "low")["requested_by"] == 14
    o = new_order(app, "umar", 2, "urgent")
    assert o["requested_by"] == 13 and o["status"] == "open"


# --------------------------------------------------------------------------- work orders: patch / delete

def test_requester_patches_open_order():
    app = fresh_app()
    r = app.patch("/api/work_orders/74", {"title": "Loud rattle", "description": None}, user="ruth", now=NOW)
    assert r.status == 200, r
    assert r.json["title"] == "Loud rattle" and r.json["description"] is None
    assert r.json["priority"] == "normal" and r.json["status"] == "open" and r.json["requested_by"] == 3
    assert_error(app.patch("/api/work_orders/74", {"priority": "urgent"}, user="ruth", now=NOW), 403, "forbidden")
    # 77 is assigned: the requester may no longer edit it
    assert_error(app.patch("/api/work_orders/77", {"title": "x"}, user="ruth", now=NOW), 409, "conflict")
    # 403 (priority) wins over 409
    assert_error(app.patch("/api/work_orders/77", {"priority": "low"}, user="ruth", now=NOW), 403, "forbidden")
    # 409 wins over 400
    assert_error(app.patch("/api/work_orders/77", {"title": ""}, user="ruth", now=NOW), 409, "conflict")
    assert wo(app, 74)["priority"] == "normal"
    assert wo(app, 77)["title"] == "Stuck between floors"


def test_supervisor_patch_priority_recomputes_due_date():
    app = fresh_app()
    r = app.patch("/api/work_orders/54", {"priority": "urgent"}, user="yara", now=NOW)
    assert r.status == 200, r
    assert r.json["due_date"] == "2026-02-15" and r.json["overdue"] is True
    r = app.patch("/api/work_orders/62", {"priority": "low", "title": "Filter change (all)"}, user="sofia", now=NOW)
    assert r.status == 200, r
    assert r.json["due_date"] == "2026-03-22" and r.json["overdue"] is False
    assert r.json["status"] == "in_progress" and r.json["assignee"] == 8
    for oid in (2, 3):   # completed, cancelled
        assert_error(app.patch(f"/api/work_orders/{oid}", {"title": "x"}, user="sofia", now=NOW), 409, "conflict")
    assert_error(app.patch("/api/work_orders/2", {"priority": "asap"}, user="sofia", now=NOW), 409, "conflict")
    for bad in ({"priority": "asap"}, {"status": "completed"}, {"asset": 2}, {"assignee": 9},
                {"due_date": "2026-03-30"}, {"title": " "}):
        assert_error(app.patch("/api/work_orders/74", bad, user="sofia", now=NOW), 400, "validation")
    o = wo(app, 74)
    assert o["priority"] == "normal" and o["status"] == "open" and o["asset"] == 1 and o["assignee"] is None


def test_patch_by_others_is_403():
    app = fresh_app()
    for user in ("kofi", "nils", "olga", "vera"):
        assert_error(app.patch("/api/work_orders/74", {"title": "x"}, user=user, now=NOW), 403, "forbidden")
    # the assignee is not the requester: 403, also before 409/400
    assert_error(app.patch("/api/work_orders/79", {"title": "x"}, user="olga", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/work_orders/2", {"status": "open"}, user="tess", now=NOW), 403, "forbidden")
    assert wo(app, 74)["title"] == "Rattling noise"


def test_nobody_deletes_work_orders():
    app = fresh_app()
    for user, oid in (("sofia", 74), ("ruth", 74), ("tomas", 3), ("tess", 2)):
        assert_error(app.delete(f"/api/work_orders/{oid}", user=user, now=NOW), 403, "forbidden")
    assert ids(app.get("/api/work_orders", user="sofia", now=NOW)) == ALL_ORDERS


# --------------------------------------------------------------------------- assign

def test_supervisor_assigns_open_order():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/74/assign", {"technician": 9}, user="sofia", now=T2)
    assert r.status == 200, r
    o = r.json
    assert o["id"] == 74 and o["status"] == "assigned" and o["assignee"] == 9
    assert o["started_at"] is None and o["requested_by"] == 3 and o["due_date"] == "2026-03-05"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    m = msgs[-1]
    assert m["channel"] == "assignment"
    assert m["payload"] == {"work_order": 74, "asset": 1, "technician": 9}
    assert set(m) >= {"id", "channel", "payload", "created_at"} and isinstance(m["id"], int)
    assert app.get("/api/assets/1", user="ruth", now=T2).json["open_orders"] == 1
    # a supervisor from another site may assign too
    r = app.post("/api/work_orders/81/assign", {"technician": 12}, user="tomas", now=T2)
    assert r.status == 200 and r.json["assignee"] == 12


def test_reassign_assigned_order():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/73/assign", {"technician": 15}, user="tomas", now=NOW)
    assert r.status == 200, r
    assert r.json["assignee"] == 15 and r.json["status"] == "assigned"
    r = app.post("/api/work_orders/73/assign", {"technician": 15}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["assignee"] == 15
    msgs = outbox(app)
    assert len(msgs) == before + 2
    assert [m["payload"] for m in msgs[-2:]] == [{"work_order": 73, "asset": 15, "technician": 15}] * 2
    # the previous assignee may no longer start it; the new one may
    assert_error(app.post("/api/work_orders/73/start", {}, user="ravi", now=NOW), 403, "forbidden")
    assert app.post("/api/work_orders/73/start", {}, user="wade", now=NOW).status == 200


def test_assign_technician_validation():
    app = fresh_app()
    before = outbox(app)
    # 74 is a North order: ravi (South), umar (inactive), ruth (requester), sofia (supervisor), unknown, missing
    for body in ({"technician": 10}, {"technician": 13}, {"technician": 3}, {"technician": 1},
                 {"technician": 999}, {}, {"technician": "nils"}):
        assert_error(app.post("/api/work_orders/74/assign", body, user="sofia", now=NOW), 400, "validation")
    o = wo(app, 74)
    assert o["status"] == "open" and o["assignee"] is None
    assert outbox(app) == before


def test_assign_permission_and_state():
    app = fresh_app()
    before = outbox(app)
    for user in ("ruth", "nils", "olga", "umar"):
        assert_error(app.post("/api/work_orders/74/assign", {"technician": 9}, user=user, now=NOW), 403, "forbidden")
    for oid in (79, 2, 3):   # in_progress, completed, cancelled
        assert_error(app.post(f"/api/work_orders/{oid}/assign", {"technician": 9}, user="sofia", now=NOW),
                     409, "conflict")
    # 403 wins over 409, 409 wins over 400
    assert_error(app.post("/api/work_orders/79/assign", {"technician": 9}, user="nils", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders/79/assign", {"technician": 999}, user="sofia", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert wo(app, 79)["assignee"] == 9 and wo(app, 79)["status"] == "in_progress"


# --------------------------------------------------------------------------- start

def test_assignee_starts_order():
    app = fresh_app()
    for user in ("olga", "sofia", "ruth"):
        assert_error(app.post("/api/work_orders/77/start", {}, user=user, now=NOW), 403, "forbidden")
    r = app.post("/api/work_orders/77/start", {}, user="nils", now=T2)
    assert r.status == 200, r
    o = r.json
    assert o["status"] == "in_progress" and o["started_at"] == T2 and o["assignee"] == 8
    assert o["completed_at"] is None and o["overdue"] is True   # due 2026-03-01, now 2026-03-02
    assert_error(app.post("/api/work_orders/77/start", {}, user="nils", now=T2), 409, "conflict")
    assert_error(app.post("/api/work_orders/49/start", {}, user="nils", now=T2), 409, "conflict")  # in_progress
    assert_error(app.post("/api/work_orders/74/start", {}, user="nils", now=T2), 403, "forbidden")  # open, no assignee
    assert wo(app, 77)["started_at"] == T2


def test_inactive_assignee_can_start():
    app = fresh_app()
    r = app.post("/api/work_orders/37/start", {}, user="umar", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "in_progress" and r.json["started_at"] == NOW


# --------------------------------------------------------------------------- complete

def test_assignee_completes_order_and_emits():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/79/complete", {"resolution": "Replaced detector", "labor_minutes": 95},
                 user="olga", now=T2)
    assert r.status == 200, r
    o = r.json
    expected = {"id": 79, "status": "completed", "completed_at": T2, "resolution": "Replaced detector",
                "labor_minutes": 95, "started_at": "2026-02-28T16:00:00", "assignee": 9, "overdue": False}
    for k, v in expected.items():
        assert o[k] == v, (k, o[k])
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "work_completed"
    assert msgs[-1]["payload"] == {"work_order": 79, "asset": 13, "technician": 9, "labor_minutes": 95}
    assert app.get("/api/assets/13", user="ruth", now=T2).json["open_orders"] == 0
    assert_error(app.post("/api/work_orders/79/complete", {"resolution": "again", "labor_minutes": 5},
                          user="olga", now=T2), 409, "conflict")


def test_complete_validation():
    app = fresh_app()
    before = outbox(app)
    for body in ({"labor_minutes": 30}, {"resolution": "", "labor_minutes": 30}, {"resolution": "ok"},
                 {"resolution": "ok", "labor_minutes": 0}, {"resolution": "ok", "labor_minutes": 1.5},
                 {"resolution": "ok", "labor_minutes": "30"}, {"resolution": "ok", "labor_minutes": True},
                 {"resolution": "ok", "labor_minutes": -10}):
        assert_error(app.post("/api/work_orders/62/complete", body, user="nils", now=NOW), 400, "validation")
    # assigned (not started): 409, and 409 wins over 400
    assert_error(app.post("/api/work_orders/77/complete", {"resolution": "ok", "labor_minutes": 10},
                          user="nils", now=NOW), 409, "conflict")
    assert_error(app.post("/api/work_orders/77/complete", {}, user="nils", now=NOW), 409, "conflict")
    assert outbox(app) == before
    o = wo(app, 62)
    assert o["status"] == "in_progress" and o["labor_minutes"] is None and o["resolution"] is None
    r = app.post("/api/work_orders/62/complete", {"resolution": "ok", "labor_minutes": 1}, user="nils", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 1


def test_complete_permissions():
    app = fresh_app()
    body = {"resolution": "Done", "labor_minutes": 30}
    for user in ("olga", "sofia", "kofi", "umar"):
        assert_error(app.post("/api/work_orders/62/complete", body, user=user, now=NOW), 403, "forbidden")
    # 403 wins over 409 (order 2 is completed, tess was its assignee; nils was not)
    assert_error(app.post("/api/work_orders/2/complete", body, user="nils", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders/2/complete", body, user="tess", now=NOW), 409, "conflict")
    assert wo(app, 62)["status"] == "in_progress"


# --------------------------------------------------------------------------- cancel

def test_requester_cancels_own_open_order():
    app = fresh_app()
    r = app.post("/api/work_orders/74/cancel", {"reason": "Fixed itself"}, user="ruth", now=NOW)
    assert r.status == 200, r
    o = r.json
    assert o["status"] == "cancelled" and o["cancel_reason"] == "Fixed itself"
    assert o["assignee"] is None and o["overdue"] is False and o["completed_at"] is None
    assert app.get("/api/assets/1", user="ruth", now=NOW).json["open_orders"] == 0
    # a technician who raised an open order may cancel it too
    r = app.post("/api/work_orders/60/cancel", {"reason": "Duplicate"}, user="ravi", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled"


def test_cancel_permissions_and_states():
    app = fresh_app()
    # requester, but the order is already assigned
    assert_error(app.post("/api/work_orders/77/cancel", {"reason": "no"}, user="ruth", now=NOW), 409, "conflict")
    # not the requester and not a supervisor (the assignee included)
    for user in ("kofi", "nils", "olga"):
        assert_error(app.post("/api/work_orders/74/cancel", {"reason": "no"}, user=user, now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders/77/cancel", {"reason": "no"}, user="nils", now=NOW), 403, "forbidden")
    # finished orders: 409 even for supervisors; 409 wins over 400
    for oid in (2, 3):
        assert_error(app.post(f"/api/work_orders/{oid}/cancel", {"reason": "x"}, user="sofia", now=NOW), 409, "conflict")
    assert_error(app.post("/api/work_orders/2/cancel", {}, user="sofia", now=NOW), 409, "conflict")
    # 403 wins over 409
    assert_error(app.post("/api/work_orders/2/cancel", {"reason": "x"}, user="ruth", now=NOW), 403, "forbidden")
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        assert_error(app.post("/api/work_orders/74/cancel", body, user="ruth", now=NOW), 400, "validation")
    assert wo(app, 74)["status"] == "open" and wo(app, 77)["status"] == "assigned"


def test_supervisor_cancels_in_progress_keeps_assignee():
    app = fresh_app()
    r = app.post("/api/work_orders/62/cancel", {"reason": "Unit replaced"}, user="tomas", now=NOW)
    assert r.status == 200, r
    o = r.json
    assert o["status"] == "cancelled" and o["cancel_reason"] == "Unit replaced"
    assert o["assignee"] == 8 and o["started_at"] == "2026-02-23T09:00:00" and o["overdue"] is False
    assert_error(app.post("/api/work_orders/62/complete", {"resolution": "x", "labor_minutes": 5},
                          user="nils", now=NOW), 409, "conflict")
    # sofia requested in-progress order 79 and is a supervisor: supervisor rules apply
    r = app.post("/api/work_orders/79/cancel", {"reason": "False alarm"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled"


# --------------------------------------------------------------------------- lifecycle / outbox

def test_full_lifecycle():
    app = fresh_app()
    before = len(outbox(app))
    o = new_order(app, "mei", 31, "urgent", title="Panel beeping", now="2026-03-03T08:00:00")
    oid = o["id"]
    assert o["due_date"] == "2026-03-04"
    assert app.get("/api/assets/31", user="mei", now="2026-03-03T08:00:00").json["open_orders"] == 1
    r = app.post(f"/api/work_orders/{oid}/assign", {"technician": 12}, user="yara", now="2026-03-03T08:30:00")
    assert r.status == 200, r
    r = app.post(f"/api/work_orders/{oid}/start", {}, user="tess", now="2026-03-03T09:00:00")
    assert r.status == 200, r
    assert app.get(f"/api/work_orders/{oid}", user="tess", now="2026-03-05T09:00:00").json["overdue"] is True
    r = app.post(f"/api/work_orders/{oid}/complete", {"resolution": "Battery swapped", "labor_minutes": 40},
                 user="tess", now="2026-03-05T10:00:00")
    assert r.status == 200, r
    final = app.get(f"/api/work_orders/{oid}", user="mei", now="2026-03-05T10:00:00").json
    expected = {"status": "completed", "requested_by": 7, "assignee": 12, "created_at": "2026-03-03T08:00:00",
                "started_at": "2026-03-03T09:00:00", "completed_at": "2026-03-05T10:00:00",
                "labor_minutes": 40, "overdue": False}
    for k, v in expected.items():
        assert final[k] == v, (k, final[k])
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["assignment", "work_completed"]
    assert msgs[0]["payload"] == {"work_order": oid, "asset": 31, "technician": 12}
    assert msgs[1]["payload"] == {"work_order": oid, "asset": 31, "technician": 12, "labor_minutes": 40}
    assert app.get("/api/assets/31", user="mei", now="2026-03-05T10:00:00").json["open_orders"] == 0


def test_other_operations_emit_nothing():
    app = fresh_app()
    before = outbox(app)
    new_order(app, "ruth", 1, "urgent")
    assert app.patch("/api/work_orders/74", {"title": "x"}, user="ruth", now=NOW).status == 200
    assert app.post("/api/work_orders/77/start", {}, user="nils", now=NOW).status == 200
    assert app.post("/api/work_orders/74/cancel", {"reason": "x"}, user="ruth", now=NOW).status == 200
    assert app.post("/api/staff", {"username": "zz", "name": "Z", "role": "requester", "site": "East"},
                    user="yara", now=NOW).status == 201
    assert app.patch("/api/assets/31", {"retired": True}, user="yara", now=NOW).status == 200
    assert outbox(app) == before


def test_outbox_readable_by_any_user():
    app = fresh_app()
    assert app.post("/api/work_orders/74/assign", {"technician": 8}, user="sofia", now=NOW).status == 200
    for user in ("mei", "umar", "vera"):
        r = app.get("/api/_outbox", user=user, now=NOW)
        assert r.status == 200, r
        items = r.json["items"]
        assert [m["id"] for m in items] == sorted(m["id"] for m in items)
        assert any(m["channel"] == "assignment" and m["payload"]["work_order"] == 74 for m in items)


# --------------------------------------------------------------------------- UI

def test_ui_lists_follow_read_permissions():
    app = fresh_app()
    r = app.get("/ui/work_orders", user="ruth", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == RUTH_ORDERS
    assert parse_ui(app.get("/ui/work_orders", user="tess", now=NOW).text).rows == EAST_ORDERS
    assert parse_ui(app.get("/ui/work_orders", user="yara", now=NOW).text).rows == ALL_ORDERS
    assert parse_ui(app.get("/ui/assets", user="mei", now=NOW).text).rows == list(range(1, 32))
    assert parse_ui(app.get("/ui/staff", user="umar", now=NOW).text).rows == list(range(1, 17))


def test_ui_work_order_detail_fields():
    app = fresh_app()
    r = app.get("/ui/work_orders/74", user="ruth", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["title"] == "Rattling noise"
    assert ui.fields["description"] == "Loud rattle near the intake"
    assert ui.fields["priority"] == "normal"
    assert ui.fields["status"] == "open"
    assert ui.fields["created_at"] == "2026-02-26T09:00:00"
    assert ui.fields["due_date"] == "2026-03-05"
    assert {"asset", "requested_by", "assignee", "started_at", "completed_at", "resolution",
            "labor_minutes", "cancel_reason", "overdue"} <= set(ui.fields)
    ui = parse_ui(app.get("/ui/work_orders/2", user="tess", now=NOW).text)
    assert ui.fields["resolution"] == "Cleaned and lubricated"
    assert ui.fields["labor_minutes"] == "315"
    ui = parse_ui(app.get("/ui/assets/21", user="mei", now=NOW).text)
    assert ui.fields["tag"] == "S-GEN-01" and ui.fields["criticality"] == "high"
    assert ui.fields["open_orders"] == "2"


def test_ui_actions_per_role_and_state():
    app = fresh_app()

    def actions(oid, user):
        r = app.get(f"/ui/work_orders/{oid}", user=user, now=NOW)
        assert r.status == 200, (oid, user, r)
        return set(parse_ui(r.text).actions) & set(ACTIONS)

    assert actions(74, "sofia") == {"assign", "cancel"}        # open
    assert actions(74, "ruth") == {"cancel"}                   # requester, open
    assert actions(74, "nils") == set()
    assert actions(77, "sofia") == {"assign", "cancel"}        # assigned
    assert actions(77, "nils") == {"start"}
    assert actions(77, "ruth") == set()                        # requester, no longer open
    assert actions(79, "olga") == {"complete"}                 # in progress
    assert actions(79, "sofia") == {"cancel"}
    assert actions(2, "yara") == set()                         # completed
    assert actions(60, "ravi") == {"cancel"}                   # ravi raised this open order
    assert actions(37, "umar") == {"start"}                    # inactive assignee


def test_ui_create_forms():
    app = fresh_app()
    for user in ("ruth", "nils", "sofia"):
        r = app.get("/ui/work_orders/new", user=user, now=NOW)
        assert r.status == 200, (user, r)
        ui = parse_ui(r.text)
        assert ui.creates == ["work_orders"]
        assert {"asset", "title", "description", "priority"} <= set(ui.inputs)
        for f in ("status", "requested_by", "created_at", "assignee", "started_at", "completed_at",
                  "resolution", "labor_minutes", "cancel_reason", "due_date", "overdue"):
            assert f not in ui.inputs, f
    r = app.get("/ui/staff/new", user="tomas", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["staff"] and {"username", "name", "role", "site"} <= set(ui.inputs)
    r = app.get("/ui/assets/new", user="yara", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["assets"] and {"tag", "name", "site", "criticality"} <= set(ui.inputs)
    assert "open_orders" not in ui.inputs


def test_ui_errors_and_forbidden_forms():
    app = fresh_app()
    assert app.get("/ui/staff/new", user="ruth", now=NOW).status == 403
    assert app.get("/ui/assets/new", user="nils", now=NOW).status == 403
    assert app.get("/ui/work_orders/74", user="kofi", now=NOW).status == 403
    assert app.get("/ui/work_orders/74", user="tess", now=NOW).status == 403
    assert app.get("/ui/work_orders/999", user="sofia", now=NOW).status == 404
    assert app.get("/ui/gadgets", user="sofia", now=NOW).status == 404
    assert app.get("/ui/work_orders", user=None, now=NOW).status == 401
    assert app.get("/ui/work_orders/new", user="ghost", now=NOW).status == 401
