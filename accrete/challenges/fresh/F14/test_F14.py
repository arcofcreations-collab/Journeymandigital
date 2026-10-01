"""Hidden acceptance tests for F14 (expenses): finance can query an approved claim back to the manager.

Seed facts (computed from spec/apps/expenses_seed.json):
  claim 22: sam (8), meals, 1455.12, approved 2026-01-11T13:00:00 by omar (4), submitted 2026-01-09T15:00:00.
  claim 18: omar (4), other, 475.38, approved by marco (2) (omar's manager).
  claim 4:  uma (10), approved by nadia (3).  claim 2: submitted. claim 6: paid. claim 20: draft.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
Q = "Which client was this lunch for?"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def claim(app, cid, user="fiona"):
    r = app.get(f"/api/claims/{cid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def test_existing_claims_have_no_query():
    app = fresh_app()
    for c in app.get("/api/claims", user="fiona", now=NOW).json["items"]:
        assert c["finance_query"] is None and c["query_count"] == 0, c["id"]


def test_finance_queries_approved_claim():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/22/query", {"question": Q}, user="fiona", now="2026-03-02T09:30:00")
    assert r.status == 200, r
    c = r.json
    expected = {"id": 22, "status": "submitted", "decided_at": None, "decided_by": None, "finance_query": Q,
                "query_count": 1, "submitted_at": "2026-01-09T15:00:00", "amount": 1455.12, "employee": 8,
                "rejection_reason": None}
    for k, v in expected.items():
        assert c[k] == v, (k, c.get(k))
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "claim_queried"
    assert msgs[-1]["payload"] == {"claim": 22, "manager": 4, "question": Q}
    assert claim(app, 22, user="sam")["finance_query"] == Q
    assert claim(app, 22, user="omar")["status"] == "submitted"


def test_queried_claim_goes_through_approval_again():
    app = fresh_app()
    assert app.post("/api/claims/22/query", {"question": Q}, user="fiona", now=NOW).status == 200
    assert_error(app.post("/api/claims/22/pay", {}, user="fiona", now=NOW), 409, "conflict")
    r = app.post("/api/claims/22/approve", {}, user="omar", now="2026-03-03T10:00:00")
    assert r.status == 200, r
    assert r.json["status"] == "approved" and r.json["decided_by"] == 4 and r.json["decided_at"] == "2026-03-03T10:00:00"
    assert r.json["finance_query"] is None and r.json["query_count"] == 1
    # only one query per claim
    assert_error(app.post("/api/claims/22/query", {"question": "Again?"}, user="fiona", now=NOW), 409, "conflict")
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["status"] == "paid"
    assert outbox(app)[before]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}


def test_queried_claim_can_be_rejected():
    app = fresh_app()
    assert app.post("/api/claims/4/query", {"question": "Receipt is unreadable"}, user="fiona", now=NOW).status == 200
    r = app.post("/api/claims/4/reject", {"reason": "No readable receipt"}, user="nadia", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "rejected" and r.json["rejection_reason"] == "No readable receipt"
    assert r.json["finance_query"] is None and r.json["query_count"] == 1


def test_manager_in_payload_is_employees_manager():
    app = fresh_app()
    assert app.post("/api/claims/18/query", {"question": "Duplicate of #19?"}, user="fiona", now=NOW).status == 200
    assert outbox(app)[-1]["payload"] == {"claim": 18, "manager": 2, "question": "Duplicate of #19?"}
    assert_error(app.post("/api/claims/18/approve", {}, user="omar", now=NOW), 403, "forbidden")
    assert app.post("/api/claims/18/approve", {}, user="marco", now=NOW).status == 200


def test_query_permissions_states_and_validation():
    app = fresh_app()
    before = outbox(app)
    for user in ("omar", "sam", "marco", "nadia"):
        assert_error(app.post("/api/claims/22/query", {"question": Q}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/claims/22/query", {}, user=user, now=NOW), 403, "forbidden")
    for cid in (2, 6, 7, 20):   # submitted, paid, rejected, draft
        assert_error(app.post(f"/api/claims/{cid}/query", {"question": Q}, user="fiona", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/2/query", {}, user="fiona", now=NOW), 409, "conflict")   # 409 before 400
    for body in ({}, {"question": ""}, {"question": "   "}, {"question": 5}):
        assert_error(app.post("/api/claims/22/query", body, user="fiona", now=NOW), 400, "validation")
    assert_error(app.post("/api/claims/999/query", {"question": Q}, user="fiona", now=NOW), 404, "not_found")
    assert outbox(app) == before
    c = claim(app, 22)
    assert c["status"] == "approved" and c["decided_by"] == 4 and c["finance_query"] is None and c["query_count"] == 0


def test_query_fields_are_protected():
    app = fresh_app()
    base = {"amount": 50, "category": "travel", "description": "Taxi"}
    for extra in ({"finance_query": "x"}, {"query_count": 0}):
        assert_error(app.post("/api/claims", dict(base, **extra), user="sam", now=NOW), 400, "validation")
        assert_error(app.patch("/api/claims/20", extra, user="sam", now=NOW), 400, "validation")
    r = app.post("/api/claims", base, user="sam", now=NOW)
    assert r.status == 201 and r.json["finance_query"] is None and r.json["query_count"] == 0


def test_ui_query_form():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "query" in ui.actions and "pay" in ui.actions
    assert {"finance_query", "query_count"} <= set(ui.fields)
    assert "query" not in parse_ui(app.get("/ui/claims/22", user="omar", now=NOW).text).actions
    assert "query" not in parse_ui(app.get("/ui/claims/2", user="fiona", now=NOW).text).actions
    assert app.post("/api/claims/22/query", {"question": Q}, user="fiona", now=NOW).status == 200
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "query" not in ui.actions and "pay" not in ui.actions
    ui = parse_ui(app.get("/ui/claims/22", user="omar", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions
    assert ui.fields["finance_query"] == Q and ui.fields["query_count"] == "1"


def test_lists_and_filters():
    app = fresh_app()
    assert app.post("/api/claims/22/query", {"question": Q}, user="fiona", now=NOW).status == 200
    assert app.post("/api/claims/4/query", {"question": "Receipt?"}, user="fiona", now=NOW).status == 200
    assert ids(app.get("/api/claims?query_count=1", user="fiona", now=NOW)) == [4, 22]
    assert ids(app.get("/api/claims?query_count=1", user="omar", now=NOW)) == [22]
    assert ids(app.get("/api/claims?status=approved&decided_by=4", user="fiona", now=NOW)) == [21, 33, 41, 44, 61]
