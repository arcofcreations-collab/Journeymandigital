"""Work order actions: assign, start, complete, cancel; permissions, states, parameters, outbox."""

NOW = "2026-03-02T09:30:00"


def _outbox(app):
    return app.get("/api/_outbox", user="ruth").json["items"]


# --- assign ---------------------------------------------------------------------------

def test_assign(app):
    r = app.post("/api/work_orders/74/assign", {"technician": 9}, user="sofia", now=NOW)
    assert r.status == 200
    assert (r.json["status"], r.json["assignee"]) == ("assigned", 9)
    assert _outbox(app) == [
        {"id": 1, "channel": "assignment", "payload": {"work_order": 74, "asset": 1, "technician": 9},
         "created_at": NOW}
    ]


def test_reassign_including_same_technician(app):
    assert app.post("/api/work_orders/77/assign", {"technician": 9}, user="sofia").json["assignee"] == 9
    r = app.post("/api/work_orders/77/assign", {"technician": 9}, user="tomas")  # any supervisor
    assert r.status == 200 and r.json["status"] == "assigned"
    assert [m["payload"]["technician"] for m in _outbox(app)] == [9, 9]


def test_assign_permission_and_state(app):
    for user in ("ruth", "nils", "olga"):
        assert app.post("/api/work_orders/74/assign", {"technician": 9}, user=user).status == 403
    assert app.post("/api/work_orders/74/assign", {}, user="ruth").status == 403  # 403 beats 400
    for order_id in (49, 2, 1):  # in_progress, completed, cancelled
        assert app.post(f"/api/work_orders/{order_id}/assign", {"technician": 8}, user="sofia").status == 409
    assert app.post("/api/work_orders/49/assign", {}, user="sofia").status == 409  # 409 beats 400


def test_assign_technician_must_be_eligible(app):
    def assign(technician):
        return app.post("/api/work_orders/74/assign", {"technician": technician}, user="sofia").status

    assert assign(10) == 400  # technician at another site
    assert assign(13) == 400  # inactive technician
    assert assign(3) == 400  # requester
    assert assign(1) == 400  # supervisor
    assert assign(999) == 400
    assert assign(None) == 400
    assert assign("9") == 400
    assert assign(True) == 400
    assert app.post("/api/work_orders/74/assign", {}, user="sofia").status == 400
    assert app.get("/api/work_orders/74", user="sofia").json["status"] == "open"
    assert _outbox(app) == []


# --- start ----------------------------------------------------------------------------

def test_start(app):
    assert app.post("/api/work_orders/77/start", {}, user="olga").status == 403  # not the assignee
    assert app.post("/api/work_orders/77/start", {}, user="sofia").status == 403  # supervisors too
    r = app.post("/api/work_orders/77/start", {}, user="nils", now=NOW)
    assert r.status == 200 and (r.json["status"], r.json["started_at"]) == ("in_progress", NOW)
    assert app.post("/api/work_orders/77/start", {}, user="nils").status == 409
    assert app.post("/api/work_orders/74/start", {}, user="nils").status == 403  # unassigned
    assert _outbox(app) == []


def test_inactive_assignee_can_still_start(app):
    assert app.post("/api/work_orders/37/start", {}, user="umar").status == 200


# --- complete -------------------------------------------------------------------------

def test_complete(app):
    body = {"resolution": "Replaced bearing", "labor_minutes": 45}
    assert app.post("/api/work_orders/79/complete", body, user="nils").status == 403
    assert app.post("/api/work_orders/77/complete", body, user="nils").status == 409  # assigned
    r = app.post("/api/work_orders/79/complete", body, user="olga", now=NOW)
    assert r.status == 200
    assert (r.json["status"], r.json["completed_at"], r.json["resolution"], r.json["labor_minutes"]) == (
        "completed", NOW, "Replaced bearing", 45)
    assert r.json["overdue"] is False
    assert _outbox(app) == [
        {"id": 1, "channel": "work_completed",
         "payload": {"work_order": 79, "asset": 13, "technician": 9, "labor_minutes": 45}, "created_at": NOW}
    ]
    assert app.post("/api/work_orders/79/complete", body, user="olga").status == 409


def test_complete_parameters(app):
    def complete(**body):
        return app.post("/api/work_orders/79/complete", body, user="olga").status

    assert complete(labor_minutes=10) == 400
    assert complete(resolution=" ", labor_minutes=10) == 400
    assert complete(resolution="Done") == 400
    for minutes in (0, -5, 1.5, 2.0, "30", True, None):
        assert complete(resolution="Done", labor_minutes=minutes) == 400, minutes
    assert app.get("/api/work_orders/79", user="olga").json["status"] == "in_progress"
    assert _outbox(app) == []
    assert complete(resolution="Done", labor_minutes=1) == 200


# --- cancel ---------------------------------------------------------------------------

def test_supervisor_cancels_unfinished_orders(app):
    for order_id in (74, 77, 79):  # open, assigned, in_progress
        r = app.post(f"/api/work_orders/{order_id}/cancel", {"reason": "Budget"}, user="yara")
        assert r.status == 200 and (r.json["status"], r.json["cancel_reason"]) == ("cancelled", "Budget")
    r = app.get("/api/work_orders/79", user="sofia").json
    assert (r["assignee"], r["started_at"]) == (9, "2026-02-28T16:00:00")  # kept
    assert app.post("/api/work_orders/2/cancel", {"reason": "x"}, user="sofia").status == 409
    assert app.post("/api/work_orders/74/cancel", {"reason": "x"}, user="sofia").status == 409
    assert _outbox(app) == []


def test_requester_cancels_only_open_orders(app):
    assert app.post("/api/work_orders/77/cancel", {"reason": "x"}, user="ruth").status == 409  # assigned
    assert app.post("/api/work_orders/77/cancel", {}, user="ruth").status == 409  # 409 beats 400
    r = app.post("/api/work_orders/74/cancel", {"reason": "Fixed itself"}, user="ruth")
    assert r.status == 200 and r.json["status"] == "cancelled"


def test_others_cannot_cancel(app):
    assert app.post("/api/work_orders/74/cancel", {"reason": "x"}, user="kofi").status == 403
    assert app.post("/api/work_orders/77/cancel", {"reason": "x"}, user="nils").status == 403  # assignee
    assert app.post("/api/work_orders/74/cancel", {}, user="olga").status == 403  # 403 beats 400


def test_cancel_reason_required(app):
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": None}, {"reason": 3}):
        assert app.post("/api/work_orders/74/cancel", body, user="ruth").status == 400
    assert app.get("/api/work_orders/74", user="ruth").json["status"] == "open"


# --- whole lifecycle ------------------------------------------------------------------

def test_full_lifecycle(app):
    order = app.post("/api/work_orders", {"asset": 25, "title": "Leak", "priority": "urgent"}, user="mei").json
    path = f"/api/work_orders/{order['id']}"
    assert app.get(path, user="tess").status == 200  # technician at East
    assert app.post(f"{path}/assign", {"technician": 12}, user="yara").status == 200
    assert app.post(f"{path}/start", {}, user="tess", now="2026-03-01T13:00:00").status == 200
    done = app.post(f"{path}/complete", {"resolution": "Sealed", "labor_minutes": 30}, user="tess",
                    now="2026-03-01T14:00:00").json
    assert done["status"] == "completed" and done["started_at"] == "2026-03-01T13:00:00"
    assert [m["channel"] for m in _outbox(app)] == ["assignment", "work_completed"]
    assert [m["id"] for m in app.get("/api/_outbox?channel=work_completed", user="mei").json["items"]] == [2]
