"""D11 (expenses, depends on D10 claim history): atomic payment runs.

Seed facts (computed from expenses_seed.json):
  approved: 4 uma 558.67 | 12 tariq 380.94 | 13 xena 246.02 | 21 victor 1644.21 | 22 sam 1455.12
            44 priya 1667.52 | 66 quinn 1701.95 | 69 uma 1492.97 | 74 zoe 1407.45 | 78 xena 1658.68
  4 + 12 + 13 = 1185.63
  66 + 78 + 21 + 44 + 69 + 22       = 9620.45  (<= 10000)
  66 + 78 + 21 + 44 + 69 + 22 + 74  = 11027.90 (> 10000)
  2 submitted, 6 paid, 20 draft, 7 rejected
"""
from accept_client import fresh_app

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

AMOUNT = {4: 558.67, 12: 380.94, 13: 246.02, 21: 1644.21, 22: 1455.12, 44: 1667.52, 66: 1701.95,
          69: 1492.97, 74: 1407.45, 78: 1658.68}
EMPLOYEE = {4: 10, 12: 9, 13: 13, 21: 11, 22: 8, 44: 5, 66: 6, 69: 10, 74: 15, 78: 13}


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


def claim(app, cid):
    r = app.get(f"/api/claims/{cid}", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json


def state(app):
    claims = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    evs = app.get("/api/claim_events", user="fiona", now=NOW).json["items"]
    runs = app.get("/api/payment_runs", user="fiona", now=NOW).json["items"]
    return claims, evs, runs, outbox(app)


def test_run_pays_claims_and_emits_messages_in_order():
    app = fresh_app()
    n = len(outbox(app))
    r = app.post("/api/payment_runs", {"claims": [13, 4, 12]}, user="fiona", now=T2)
    assert r.status == 201, r
    run = r.json
    assert run["claims"] == [13, 4, 12]
    assert run["total"] == 1185.63
    assert run["created_by"] == 1 and run["created_at"] == T2
    for cid in (13, 4, 12):
        c = claim(app, cid)
        assert c["status"] == "paid" and c["payment_run"] == run["id"], c
    msgs = outbox(app)[n:]
    assert [m["channel"] for m in msgs] == ["payment", "payment", "payment", "payment_run"]
    assert [m["payload"] for m in msgs[:3]] == [
        {"claim": cid, "employee": EMPLOYEE[cid], "amount": AMOUNT[cid]} for cid in (13, 4, 12)]
    assert msgs[3]["payload"] == {"run": run["id"], "claims": [13, 4, 12], "total": 1185.63}
    r = app.get(f"/api/payment_runs/{run['id']}", user="fiona", now=NOW)
    assert r.status == 200 and r.json["claims"] == [13, 4, 12]


def test_run_records_pay_events():
    app = fresh_app()
    assert app.post("/api/payment_runs", {"claims": [4, 12]}, user="fiona", now=T2).status == 201
    for cid in (4, 12):
        evs = app.get(f"/api/claim_events?claim={cid}", user="fiona", now=NOW).json["items"]
        last = evs[-1]
        assert (last["action"], last["actor"], last["at"], last["from_status"], last["to_status"]) == \
            ("pay", 1, T2, "approved", "paid")


def test_run_with_non_approved_claim_leaves_no_trace():
    app = fresh_app()
    before = state(app)
    for body in ({"claims": [4, 2]}, {"claims": [4, 12, 6]}, {"claims": [20, 4]}, {"claims": [4, 7]}):
        assert_error(app.post("/api/payment_runs", body, user="fiona", now=T2), 409, "conflict")
    assert state(app) == before
    assert claim(app, 4)["status"] == "approved" and claim(app, 4)["payment_run"] is None


def test_run_over_total_cap_leaves_no_trace():
    app = fresh_app()
    before = state(app)
    big = [66, 78, 21, 44, 69, 22, 74]
    assert_error(app.post("/api/payment_runs", {"claims": big}, user="fiona", now=T2), 400, "validation")
    assert state(app) == before
    r = app.post("/api/payment_runs", {"claims": big[:-1]}, user="fiona", now=T2)
    assert r.status == 201 and r.json["total"] == 9620.45
    assert claim(app, 74)["status"] == "approved"


def test_run_validation_leaves_no_trace():
    app = fresh_app()
    before = state(app)
    for body in ({}, {"claims": []}, {"claims": 4}, {"claims": [4, 4]}, {"claims": [4, 999]}):
        assert_error(app.post("/api/payment_runs", body, user="fiona", now=T2), 400, "validation")
    assert state(app) == before


def test_conflict_wins_over_validation():
    app = fresh_app()
    before = state(app)
    assert_error(app.post("/api/payment_runs", {"claims": [2, 2]}, user="fiona", now=T2), 409, "conflict")
    assert state(app) == before


def test_only_finance_creates_and_reads_runs():
    app = fresh_app()
    before = state(app)
    for user in ("omar", "sam", "marco"):
        assert_error(app.post("/api/payment_runs", {"claims": [4]}, user=user, now=T2), 403, "forbidden")
        assert_error(app.post("/api/payment_runs", {}, user=user, now=T2), 403, "forbidden")   # 403 before 400
    assert state(app) == before
    run = app.post("/api/payment_runs", {"claims": [4]}, user="fiona", now=T2).json
    assert ids(app.get("/api/payment_runs", user="sam", now=NOW)) == []
    assert ids(app.get("/api/payment_runs", user="nadia", now=NOW)) == []
    assert_error(app.get(f"/api/payment_runs/{run['id']}", user="nadia", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/payment_runs", user="fiona", now=NOW)) == [run["id"]]


def test_runs_are_immutable():
    app = fresh_app()
    run = app.post("/api/payment_runs", {"claims": [4]}, user="fiona", now=T2).json
    assert_error(app.patch(f"/api/payment_runs/{run['id']}", {"claims": [12]}, user="fiona", now=NOW), 403, "forbidden")
    assert_error(app.delete(f"/api/payment_runs/{run['id']}", user="fiona", now=NOW), 403, "forbidden")
    assert claim(app, 4)["payment_run"] == run["id"]


def test_claims_paid_by_run_cannot_be_paid_again():
    app = fresh_app()
    assert app.post("/api/payment_runs", {"claims": [4]}, user="fiona", now=T2).status == 201
    n = len(outbox(app))
    assert_error(app.post("/api/claims/4/pay", {}, user="fiona", now=NOW), 409, "conflict")
    assert_error(app.post("/api/payment_runs", {"claims": [4]}, user="fiona", now=NOW), 409, "conflict")
    assert len(outbox(app)) == n


def test_individual_pay_unchanged_and_payment_run_null():
    app = fresh_app()
    for c in app.get("/api/claims", user="fiona", now=NOW).json["items"]:
        assert c["payment_run"] is None, c["id"]
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=T2)
    assert r.status == 200 and r.json["status"] == "paid" and r.json["payment_run"] is None
    msgs = outbox(app)
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}
    evs = app.get("/api/claim_events?claim=22", user="fiona", now=NOW).json["items"]
    assert evs[-1]["action"] == "pay" and evs[-1]["actor"] == 1


def test_payment_run_field_is_protected():
    app = fresh_app()
    body = {"amount": 50, "category": "travel", "description": "Taxi", "payment_run": 1}
    assert_error(app.post("/api/claims", body, user="sam", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claims/20", {"payment_run": 1}, user="sam", now=NOW), 400, "validation")
    assert claim(app, 20)["payment_run"] is None
