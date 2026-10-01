"""Hidden acceptance tests for E12 (expenses): atomic employee offboarding.

Seed facts (spec/apps/expenses_seed.json):
  marco (2) manages 4 6 9 12 15 and has no claims; nadia (3) manages 7 10 13 and has no claims; fiona (1) none.
  omar (4) has submitted claims 43 52 and approved 18 50 59. sam (8): drafts 20 54 73, approved 22 61, paid 42 48.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

MARCO_READABLE = [1, 3, 8, 10, 11, 12, 18, 19, 24, 25, 29, 34, 35, 43, 46, 50, 52, 53, 55, 56,
                  59, 66, 68, 71, 74]
NADIA_READABLE = [4, 9, 13, 16, 26, 27, 30, 32, 37, 38, 39, 47, 57, 58, 62, 63, 65, 67, 69, 70,
                  72, 76, 77, 78]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="sam", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def snapshot(app):
    return (app.get("/api/employees", user="sam", now=NOW).json["items"],
            app.get("/api/claims", user="fiona", now=NOW).json["items"], outbox(app))


def offboard(app, eid, successor, user="fiona", now=NOW):
    body = {} if successor is None else {"successor": successor}
    return app.post(f"/api/employees/{eid}/offboard", body, user=user, now=now)


def test_active_flag_migrated_and_read_only():
    app = fresh_app()
    emps = app.get("/api/employees", user="sam", now=NOW).json["items"]
    assert [e["id"] for e in emps] == list(range(1, 16)) and all(e["active"] is True for e in emps)
    r = app.post("/api/employees", {"username": "anna", "name": "Anna", "role": "employee", "manager": 2,
                                    "department": "Engineering"}, user="fiona", now=NOW)
    assert r.status == 201 and r.json["active"] is True
    assert_error(app.post("/api/employees", {"username": "bo", "name": "Bo", "role": "employee",
                                             "department": "Sales", "active": False}, user="fiona", now=NOW),
                 400, "validation")
    assert_error(app.patch("/api/employees/8", {"active": False}, user="fiona", now=NOW), 400, "validation")
    assert ids(app.get("/api/employees?active=true", user="sam", now=NOW))[:15] == list(range(1, 16))


def test_offboard_manager_reassigns_reports():
    app = fresh_app()
    before = len(outbox(app))
    r = offboard(app, 2, 3, now=T2)
    assert r.status == 200, r
    assert r.json["id"] == 2 and r.json["active"] is False and r.json["username"] == "marco"
    emps = {e["id"]: e for e in app.get("/api/employees", user="sam", now=T2).json["items"]}
    for eid in (4, 6, 9, 12, 15):
        assert emps[eid]["manager"] == 3, eid
    for eid in (5, 8, 11, 14):
        assert emps[eid]["manager"] == 4
    assert emps[3]["active"] is True and emps[3]["manager"] is None
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["employee_offboarded"]
    assert msgs[0]["payload"] == {"employee": 2, "successor": 3, "reassigned": [4, 6, 9, 12, 15], "deleted_claims": []}
    assert ids(app.get("/api/claims", user="nadia", now=T2)) == sorted(MARCO_READABLE + NADIA_READABLE)
    assert ids(app.get("/api/claims", user="marco", now=T2)) == []
    assert_error(app.post("/api/claims/3/approve", {}, user="marco", now=T2), 403, "forbidden")
    r = app.post("/api/claims/43/approve", {}, user="nadia", now=T2)
    assert r.status == 200 and r.json["decided_by"] == 3


def test_offboard_deletes_drafts_once_nothing_is_in_flight():
    app = fresh_app()
    snap = snapshot(app)
    assert_error(offboard(app, 8, 4), 409, "conflict")             # approved 22 and 61 not yet paid
    assert snapshot(app) == snap
    assert app.post("/api/claims/22/pay", {}, user="fiona", now=NOW).status == 200
    assert app.post("/api/claims/61/pay", {}, user="fiona", now=NOW).status == 200
    before = len(outbox(app))
    r = offboard(app, 8, 4)
    assert r.status == 200 and r.json["active"] is False
    assert outbox(app)[before]["payload"] == {"employee": 8, "successor": 4, "reassigned": [], "deleted_claims": [20, 54, 73]}
    for cid in (20, 54, 73):
        assert_error(app.get(f"/api/claims/{cid}", user="fiona", now=NOW), 404, "not_found")
    assert ids(app.get("/api/claims", user="sam", now=NOW)) == [22, 42, 48, 61]
    assert ids(app.get("/api/claims?employee=8", user="omar", now=NOW)) == [22, 42, 48, 61]
    assert app.get("/api/employees/8", user="sam", now=NOW).json["manager"] == 4


def test_invalid_successor_changes_nothing():
    app = fresh_app()
    snap = snapshot(app)
    for successor in (None, 999, 8, 1, 2, 4, "nadia"):
        # None = missing; 8 not a manager; 1 finance; 2 = marco himself; 4 = omar reports to marco
        assert_error(offboard(app, 2, successor), 400, "validation")
    assert snapshot(app) == snap
    r = offboard(app, 3, 2)                                         # nadia -> marco is fine
    assert r.status == 200
    snap = snapshot(app)
    assert_error(offboard(app, 2, 3), 400, "validation")            # nadia is inactive now
    assert snapshot(app) == snap
    assert app.get("/api/employees/7", user="sam", now=NOW).json["manager"] == 2


def test_offboard_permissions_and_conflicts():
    app = fresh_app()
    snap = snapshot(app)
    for user in ("marco", "sam", "omar"):
        assert_error(offboard(app, 2, 3, user=user), 403, "forbidden")
        assert_error(offboard(app, 4, None, user=user), 403, "forbidden")   # 403 before 409/400
    assert_error(offboard(app, 999, 3), 404, "not_found")
    assert_error(offboard(app, 4, 3), 409, "conflict")              # omar: submitted/approved claims
    assert_error(offboard(app, 4, None), 409, "conflict")           # 409 before 400
    assert snapshot(app) == snap
    assert offboard(app, 2, 3).status == 200
    assert_error(offboard(app, 2, 3), 409, "conflict")              # already inactive
    assert_error(offboard(app, 2, 999), 409, "conflict")


def test_inactive_employees_can_read_but_not_write():
    app = fresh_app()
    assert app.post("/api/claims/22/pay", {}, user="fiona", now=NOW).status == 200
    assert app.post("/api/claims/61/pay", {}, user="fiona", now=NOW).status == 200
    assert offboard(app, 8, 4).status == 200
    assert_error(app.post("/api/claims", {"amount": 10, "category": "meals", "description": "x"}, user="sam", now=NOW),
                 403, "forbidden")
    assert app.get("/api/claims/42", user="sam", now=NOW).status == 200
    assert app.get("/ui/claims/new", user="sam", now=NOW).status == 403
    # finance offboarding themselves loses the right to pay but keeps reading
    r = offboard(app, 1, 2)
    assert r.status == 200 and r.json["active"] is False
    assert_error(app.post("/api/claims/4/pay", {}, user="fiona", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/employees", {"username": "x", "name": "X", "role": "employee", "department": "Ops"},
                          user="fiona", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/claims", user="fiona", now=NOW)) == [i for i in range(1, 81) if i not in (20, 54, 73)]


def test_inactive_employee_cannot_become_manager():
    app = fresh_app()
    assert offboard(app, 2, 3).status == 200
    assert_error(app.post("/api/employees", {"username": "anna", "name": "Anna", "role": "employee", "manager": 2,
                                             "department": "Engineering"}, user="fiona", now=NOW), 400, "validation")
    assert_error(app.patch("/api/employees/5", {"manager": 2}, user="fiona", now=NOW), 400, "validation")
    r = app.patch("/api/employees/5", {"manager": 3}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["manager"] == 3


def test_ui_offboard_form():
    app = fresh_app()
    assert "offboard" in parse_ui(app.get("/ui/employees/2", user="fiona", now=NOW).text).actions
    assert "offboard" not in parse_ui(app.get("/ui/employees/2", user="marco", now=NOW).text).actions
    assert "offboard" not in parse_ui(app.get("/ui/employees/4", user="fiona", now=NOW).text).actions  # in flight
    assert offboard(app, 2, 3).status == 200
    ui = parse_ui(app.get("/ui/employees/2", user="fiona", now=NOW).text)
    assert "offboard" not in ui.actions and ui.fields["username"] == "marco"


def test_claims_flow_after_reassignment():
    app = fresh_app()
    assert offboard(app, 2, 3).status == 200
    r = app.post("/api/claims/3/reject", {"reason": "Duplicate"}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 3
    r = app.post("/api/claims/12/pay", {}, user="fiona", now=NOW)
    assert r.status == 200
    assert outbox(app)[-1]["payload"] == {"claim": 12, "employee": 9, "amount": 380.94}
    r = app.post("/api/claims", {"amount": 40, "category": "meals", "description": "Lunch"}, user="tariq", now=NOW)
    assert r.status == 201
    assert app.get(f"/api/claims/{r.json['id']}", user="nadia", now=NOW).status == 200
    assert_error(app.get(f"/api/claims/{r.json['id']}", user="marco", now=NOW), 403, "forbidden")
