"""Hidden acceptance tests for F08 (maintenance): requesters may withdraw assigned orders, and the
technician is told when assigned work is cancelled.

Seed facts (computed from spec/apps/maintenance_seed.json):
  77: assigned to nils (8), requested by ruth (3).   49: in_progress, nils, requested by ruth.
  66: assigned to tess (12), requested by mei (7).    72: assigned to sara (11), requested by sara.
  73: assigned to ravi (10), requested by pavel (6).  79: in_progress, olga (9), requested by sofia (1).
  74: open, requested by ruth.  2: completed, requested by mei.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
ACTIONS = ("assign", "start", "complete", "cancel")


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def outbox(app):
    r = app.get("/api/_outbox", user="sofia", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def wo(app, oid):
    r = app.get(f"/api/work_orders/{oid}", user="sofia", now=NOW)
    assert r.status == 200, r
    return r.json


def test_requester_cancels_assigned_order_and_technician_is_told():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/77/cancel", {"reason": "Lift fixed by vendor"}, user="ruth", now=NOW)
    assert r.status == 200, r
    o = r.json
    assert o["status"] == "cancelled" and o["cancel_reason"] == "Lift fixed by vendor"
    assert o["assignee"] == 8 and o["started_at"] is None and o["overdue"] is False
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "assignment_cancelled"
    assert msgs[-1]["payload"] == {"work_order": 77, "technician": 8, "reason": "Lift fixed by vendor"}
    assert_error(app.post("/api/work_orders/77/start", {}, user="nils", now=NOW), 409, "conflict")
    assert app.get("/api/assets/5", user="ruth", now=NOW).json["open_orders"] == 0


def test_requester_still_cannot_cancel_in_progress():
    app = fresh_app()
    before = outbox(app)
    assert_error(app.post("/api/work_orders/49/cancel", {"reason": "no longer needed"}, user="ruth", now=NOW),
                 409, "conflict")
    assert_error(app.post("/api/work_orders/2/cancel", {"reason": "x"}, user="mei", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert wo(app, 49)["status"] == "in_progress"


def test_cancel_permissions_unchanged_for_others():
    app = fresh_app()
    before = outbox(app)
    for user in ("nils", "kofi", "olga", "vera"):
        assert_error(app.post("/api/work_orders/77/cancel", {"reason": "no"}, user=user, now=NOW), 403, "forbidden")
    # 403 wins over 409
    assert_error(app.post("/api/work_orders/2/cancel", {"reason": "x"}, user="ruth", now=NOW), 403, "forbidden")
    # reason still required (and 400 comes after the state check)
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        assert_error(app.post("/api/work_orders/77/cancel", body, user="ruth", now=NOW), 400, "validation")
    assert_error(app.post("/api/work_orders/49/cancel", {}, user="ruth", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert wo(app, 77)["status"] == "assigned"


def test_open_order_cancel_emits_nothing():
    app = fresh_app()
    before = outbox(app)
    r = app.post("/api/work_orders/74/cancel", {"reason": "Fixed itself"}, user="ruth", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled" and r.json["assignee"] is None
    r = app.post("/api/work_orders/76/cancel", {"reason": "Duplicate"}, user="tomas", now=NOW)
    assert r.status == 200
    assert outbox(app) == before


def test_supervisor_cancels_assigned_and_in_progress_orders():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/79/cancel", {"reason": "False alarm"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["assignee"] == 9 and r.json["started_at"] == "2026-02-28T16:00:00"
    assert app.post("/api/work_orders/73/assign", {"technician": 15}, user="tomas", now=NOW).status == 200
    r = app.post("/api/work_orders/73/cancel", {"reason": "Boiler replaced"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["assignee"] == 15
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["assignment_cancelled", "assignment", "assignment_cancelled"]
    assert msgs[0]["payload"] == {"work_order": 79, "technician": 9, "reason": "False alarm"}
    assert msgs[2]["payload"] == {"work_order": 73, "technician": 15, "reason": "Boiler replaced"}


def test_requester_who_is_also_assignee():
    app = fresh_app()
    r = app.post("/api/work_orders/72/cancel", {"reason": "Rollers arrived damaged"}, user="sara", now=NOW)
    assert r.status == 200, r
    assert outbox(app)[-1]["payload"] == {"work_order": 72, "technician": 11, "reason": "Rollers arrived damaged"}
    r = app.post("/api/work_orders/66/cancel", {"reason": "Belt replaced in-house"}, user="mei", now=NOW)
    assert r.status == 200
    assert outbox(app)[-1]["payload"] == {"work_order": 66, "technician": 12, "reason": "Belt replaced in-house"}


def test_ui_cancel_form_for_requester():
    app = fresh_app()

    def actions(oid, user):
        r = app.get(f"/ui/work_orders/{oid}", user=user, now=NOW)
        assert r.status == 200, (oid, user, r)
        return set(parse_ui(r.text).actions) & set(ACTIONS)

    assert actions(77, "ruth") == {"cancel"}
    assert actions(49, "ruth") == set()
    assert actions(74, "ruth") == {"cancel"}
    assert actions(66, "mei") == {"cancel"}
    assert actions(77, "nils") == {"start"}
    assert actions(77, "sofia") == {"assign", "cancel"}


def test_other_operations_still_emit_nothing():
    app = fresh_app()
    before = outbox(app)
    assert app.post("/api/work_orders", {"asset": 1, "title": "Noise", "priority": "low"}, user="ruth",
                    now=NOW).status == 201
    assert app.patch("/api/work_orders/74", {"title": "x"}, user="ruth", now=NOW).status == 200
    assert app.post("/api/work_orders/77/start", {}, user="nils", now=NOW).status == 200
    assert outbox(app) == before
    r = app.post("/api/work_orders/77/complete", {"resolution": "Reset", "labor_minutes": 30}, user="nils", now=NOW)
    assert r.status == 200
    assert [m["channel"] for m in outbox(app)[len(before):]] == ["work_completed"]
