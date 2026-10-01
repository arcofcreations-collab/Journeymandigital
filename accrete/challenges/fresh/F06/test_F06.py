"""Hidden acceptance tests for F06 (expenses, after F01-F05): segregation of duties for finance users.

Seed facts (spec/apps/expenses_seed.json after the F01-F05 migrations):
  fiona (1) is the only finance user. quinn (6) is an employee managed by marco (2) with
  claims 3 (equipment 468.5, submitted) and 66 (equipment 1701.95, approved by marco).
  claim 41: victor (11), other, 635.61, approved; victor's advances 1 (300) and 2 (250).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def money(x):
    return None if x is None else round(x, 2)


def rounded(d):
    return {k: (money(v) if isinstance(v, float) else v) for k, v in d.items()}


def outbox(app):
    r = app.get("/api/_outbox", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def make_quinn_finance(app):
    r = app.patch("/api/employees/6", {"role": "finance"}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["role"] == "finance", r


def snapshot(app):
    return (app.get("/api/advances", user="fiona", now=NOW).json["items"],
            app.get("/api/claims", user="fiona", now=NOW).json["items"], outbox(app))


def test_role_change_takes_effect_immediately():
    app = fresh_app()
    assert ids(app.get("/api/claims", user="quinn", now=NOW)) == [3, 66]
    make_quinn_finance(app)
    assert ids(app.get("/api/claims", user="quinn", now=NOW)) == list(range(1, 81))
    assert ids(app.get("/api/advances", user="quinn", now=NOW)) == [1, 2, 3]
    r = app.post("/api/claims/41/pay", {}, user="quinn", now=NOW)
    assert r.status == 200, r
    assert money(r.json["paid_amount"]) == 85.61 and money(r.json["advance_recovered"]) == 550


def test_finance_cannot_pay_own_claim():
    app = fresh_app()
    make_quinn_finance(app)
    assert app.post("/api/advances", {"employee": 6, "amount": 100, "purpose": "Float"}, user="fiona",
                    now=NOW).status == 201
    before = snapshot(app)
    assert_error(app.post("/api/claims/66/pay", {}, user="quinn", now=NOW), 403, "forbidden")
    # 403 wins over 409 (claim 3 is only submitted)
    assert_error(app.post("/api/claims/3/pay", {}, user="quinn", now=NOW), 403, "forbidden")
    assert snapshot(app) == before
    r = app.post("/api/claims/66/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert money(r.json["paid_amount"]) == 1601.95 and money(r.json["advance_recovered"]) == 100
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 66, "employee": 6, "amount": 1601.95,
                                                    "advance_recovered": 100}


def test_finance_cannot_issue_advance_to_self():
    app = fresh_app()
    before = outbox(app)
    assert_error(app.post("/api/advances", {"employee": 1, "amount": 100, "purpose": "Float"}, user="fiona",
                          now=NOW), 403, "forbidden")
    # 403 wins over 400 for the same body
    assert_error(app.post("/api/advances", {"employee": 1, "amount": -5}, user="fiona", now=NOW), 403, "forbidden")
    assert outbox(app) == before
    assert ids(app.get("/api/advances", user="fiona", now=NOW)) == [1, 2, 3]
    make_quinn_finance(app)
    r = app.post("/api/advances", {"employee": 1, "amount": 100, "purpose": "Float"}, user="quinn", now=NOW)
    assert r.status == 201 and r.json["employee"] == 1 and r.json["issued_by"] == 6
    assert_error(app.post("/api/advances", {"employee": 6, "amount": 100, "purpose": "Float"}, user="quinn",
                          now=NOW), 403, "forbidden")
    # validation still applies to other employees
    assert_error(app.post("/api/advances", {"employee": 7, "amount": -5, "purpose": "x"}, user="fiona", now=NOW),
                 400, "validation")


def test_finance_cannot_change_own_employee_record():
    app = fresh_app()
    assert_error(app.patch("/api/employees/1", {"department": "Treasury"}, user="fiona", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/employees/1", {"role": "boss"}, user="fiona", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/employees/1", user="fiona", now=NOW), 403, "forbidden")
    assert app.get("/api/employees/1", user="sam", now=NOW).json["department"] == "Finance"
    make_quinn_finance(app)
    assert_error(app.patch("/api/employees/6", {"role": "employee"}, user="quinn", now=NOW), 403, "forbidden")
    r = app.patch("/api/employees/1", {"department": "Treasury"}, user="quinn", now=NOW)
    assert r.status == 200 and r.json["department"] == "Treasury"
    r = app.patch("/api/employees/6", {"department": "Finance"}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["department"] == "Finance" and r.json["role"] == "finance"


def test_other_employee_writes_unchanged():
    app = fresh_app()
    r = app.patch("/api/employees/5", {"department": "Sales"}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["department"] == "Sales"
    r = app.post("/api/employees", {"username": "gil", "name": "Gil Moss", "role": "finance", "department": "Finance"},
                 user="fiona", now=NOW)
    assert r.status == 201
    gid = r.json["id"]
    assert app.delete(f"/api/employees/{gid}", user="fiona", now=NOW).status == 204
    for user in ("marco", "sam"):
        assert_error(app.patch("/api/employees/8", {"department": "Sales"}, user=user, now=NOW), 403, "forbidden")


def test_ui_pay_form_hidden_for_own_claim():
    app = fresh_app()
    make_quinn_finance(app)
    assert "pay" not in parse_ui(app.get("/ui/claims/66", user="quinn", now=NOW).text).actions
    assert "pay" in parse_ui(app.get("/ui/claims/66", user="fiona", now=NOW).text).actions
    assert "pay" in parse_ui(app.get("/ui/claims/41", user="quinn", now=NOW).text).actions
    assert app.get("/ui/advances/new", user="quinn", now=NOW).status == 200


def test_earlier_steps_still_work():
    app = fresh_app()
    # F05: approvals are full-amount only; F04: recovery; F03 capped claims were sent back
    assert app.get("/api/claims/22", user="sam", now=NOW).json["status"] == "submitted"
    assert_error(app.post("/api/claims/2/approve", {"amount": 500, "note": "x"}, user="omar", now=NOW), 400, "validation")
    assert app.post("/api/claims/2/approve", {}, user="omar", now=NOW).status == 200
    r = app.post("/api/claims/2/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and money(r.json["advance_recovered"]) == 550 and money(r.json["paid_amount"]) == 184.81
    # F02 / F01
    assert_error(app.post("/api/claims", {"amount": 400.01, "category": "meals", "description": "x"}, user="sam",
                          now=NOW), 400, "validation")
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")
