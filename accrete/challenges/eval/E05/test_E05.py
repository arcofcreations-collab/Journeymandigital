"""Hidden acceptance tests for E05 (maintenance, after E01-E04): withdraw self-dispatch, keep the workload cap.

Facts (seed + E02 rule "self = requester is assignee"):
  self-dispatched orders: still assigned -> 72 (S-CNV-02, asset 17, sara, p3) and 75 (N-CMP-01, asset 9, olga, p3)
  go back to open/unassigned; in_progress 56 (ravi), cancelled 22 and 33 (tess) and completed ones keep assignee.
  Workloads afterwards: nils 3, olga 1 [79], umar 1, ravi 4, sara 2 [61 64], wade 1, tess 2.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

OPEN_AFTER = [30, 38, 52, 54, 60, 63, 65, 69, 71, 72, 74, 75, 76, 78, 81, 82]


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


def assign(app, oid, tech, user="sofia"):
    return app.post(f"/api/work_orders/{oid}/assign", {"technician": tech}, user=user, now=NOW)


def test_claim_action_is_gone():
    app = fresh_app()
    before = outbox(app)
    for oid, user in ((78, "wade"), (74, "olga"), (30, "tess"), (74, "ruth"), (999, "wade")):
        assert_error(app.post(f"/api/work_orders/{oid}/claim", {}, user=user, now=NOW), 404, "not_found")
    assert_error(app.post("/api/work_orders/78/claim", {}, user=None, now=NOW), 401, "unauthenticated")
    assert outbox(app) == before
    assert wo(app, 78)["status"] == "open" and wo(app, 78)["assignee"] is None
    for oid, user in ((78, "wade"), (74, "olga"), (30, "tess")):
        assert "claim" not in parse_ui(app.get(f"/ui/work_orders/{oid}", user=user, now=NOW).text).actions


def test_dispatch_field_is_gone():
    app = fresh_app()
    items = app.get("/api/work_orders", user="sofia", now=NOW).json["items"]
    assert len(items) == 82
    assert all("dispatch" not in o for o in items)
    assert_error(app.get("/api/work_orders?dispatch=self", user="sofia", now=NOW), 400, "validation")
    assert_error(app.post("/api/work_orders", {"asset": 2, "title": "x", "priority": "p3", "dispatch": None},
                          user="ruth", now=NOW), 400, "validation")
    assert_error(app.patch("/api/work_orders/74", {"dispatch": "supervisor"}, user="sofia", now=NOW), 400, "validation")
    r = assign(app, 74, 9)
    assert r.status == 200 and "dispatch" not in r.json
    assert "dispatch" not in parse_ui(app.get("/ui/work_orders/74", user="ruth", now=NOW).text).fields


def test_self_dispatched_assigned_orders_return_to_pool():
    app = fresh_app()
    o = wo(app, 72)
    expected = {"status": "open", "assignee": None, "requested_by": 11, "asset": 17, "priority": "p3",
                "title": "Roller replacement", "created_at": "2026-02-25T14:00:00", "started_at": None,
                "due_date": "2026-03-04", "overdue": False}
    for k, v in expected.items():
        assert o[k] == v, (k, o.get(k))
    o = wo(app, 75)
    expected = {"status": "open", "assignee": None, "requested_by": 9, "asset": 9, "priority": "p3",
                "title": "Oil change", "created_at": "2026-02-27T11:00:00"}
    for k, v in expected.items():
        assert o[k] == v, (k, o.get(k))
    assert ids(app.get("/api/work_orders?status=open", user="sofia", now=NOW)) == OPEN_AFTER
    assert ids(app.get("/api/work_orders?status=assigned", user="sofia", now=NOW)) == [37, 64, 66, 68, 73, 77]
    # self-dispatched orders in other states are untouched
    o = wo(app, 56)
    assert o["status"] == "in_progress" and o["assignee"] == 10 and o["started_at"] == "2026-02-17T09:00:00"
    for oid in (22, 33):
        o = wo(app, oid)
        assert o["status"] == "cancelled" and o["assignee"] == 12
    for oid, tech in ((4, 13), (67, 9), (42, 11)):
        o = wo(app, oid)
        assert o["status"] == "completed" and o["assignee"] == tech
    # visibility and asset counters are unchanged
    assert app.get("/api/work_orders/72", user="sara", now=NOW).status == 200
    assert app.get("/api/assets/17", user="ruth", now=NOW).json["open_orders"] == 1
    assert app.get("/api/assets/9", user="ruth", now=NOW).json["open_orders"] == 1


def test_freed_capacity_can_be_assigned():
    app = fresh_app()
    r = assign(app, 76, 11, user="tomas")           # sara 2 -> 3
    assert r.status == 200 and r.json["assignee"] == 11
    assert_error(assign(app, 78, 11, user="tomas"), 409, "conflict")
    for oid in (75, 74):                            # olga 1 -> 2 -> 3
        r = assign(app, oid, 9)
        assert r.status == 200 and r.json["assignee"] == 9
    assert_error(assign(app, 82, 9), 409, "conflict")


def test_workload_cap_kept():
    app = fresh_app()
    before = outbox(app)
    assert_error(assign(app, 74, 8), 409, "conflict")               # nils 3
    assert_error(assign(app, 76, 10, user="tomas"), 409, "conflict")  # ravi 4
    assert_error(assign(app, 74, 13), 400, "validation")             # inactive: 400, not the cap
    assert outbox(app) == before
    r = assign(app, 73, 10, user="tomas")                            # current assignee
    assert r.status == 200 and r.json["assignee"] == 10


def test_requesters_regain_rights_on_returned_orders():
    app = fresh_app()
    r = app.patch("/api/work_orders/72", {"title": "Replace rollers 3-5"}, user="sara", now=NOW)
    assert r.status == 200 and r.json["title"] == "Replace rollers 3-5"
    r = app.post("/api/work_orders/72/cancel", {"reason": "Done with next service"}, user="sara", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled" and r.json["assignee"] is None
    assert_error(app.post("/api/work_orders/75/start", {}, user="olga", now=NOW), 403, "forbidden")
    assert app.post("/api/work_orders/75/cancel", {"reason": "Not needed"}, user="olga", now=NOW).status == 200


def test_earlier_changes_still_work():
    app = fresh_app()
    assert len(app.get("/api/time_entries", user="sofia", now=NOW).json["items"]) == 39
    assert wo(app, 74)["priority"] == "p2" and wo(app, 64)["priority"] == "p4"
    assert_error(app.patch("/api/work_orders/64", {"priority": "p4"}, user="tomas", now=NOW), 400, "validation")
    r = app.post("/api/work_orders/56/use_parts", {"items": [{"part": 4, "quantity": 1}]}, user="ravi", now=NOW)
    assert r.status == 200
    assert app.post("/api/work_orders/56/log_time", {"minutes": 40}, user="ravi", now=NOW).status == 200
    before = len(outbox(app))
    r = app.post("/api/work_orders/56/complete", {"resolution": "Brakes adjusted"}, user="ravi", now=NOW)
    assert r.status == 200 and r.json["labor_minutes"] == 40
    p = outbox(app)[before]["payload"]
    assert set(p) == {"work_order", "asset", "technician", "labor_minutes", "parts_cost"}
    assert (p["work_order"], p["technician"], p["labor_minutes"]) == (56, 10, 40)
    assert round(p["parts_cost"], 2) == 9.8
    # ravi is now at 3 active orders: still full
    assert_error(assign(app, 76, 10, user="tomas"), 409, "conflict")
