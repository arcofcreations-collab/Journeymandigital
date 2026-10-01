"""Hidden acceptance tests for F05 (expenses, after F01-F04): partial approval (F03) is withdrawn.

Seed facts (spec/apps/expenses_seed.json after the F01-F05 migrations):
  claims approved for less than claimed by the F03 migration, now back to `submitted`:
    21 victor (11) meals 1644.21, submitted_at 2026-01-26T10:00:00, manager omar (4)
    22 sam (8)     meals 1455.12, submitted_at 2026-01-09T15:00:00, manager omar (4)
    38 uma (10)    other 1207.79, submitted_at 2026-01-23T11:00:00, manager nadia (3)
  approved after F05: 4 12 13 18 27 33 34 37 41 44 50 59 61 65 66 68 69 74 76 78
  submitted after F05: 2 3 5 15 21 22 25 28 30 36 38 40 43 52 53 58 62 63 67 72 80
  advances (F04): 1 victor 300, 2 victor 250, 3 rosa 500, nothing recovered.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
APPROVED = [4, 12, 13, 18, 27, 33, 34, 37, 41, 44, 50, 59, 61, 65, 66, 68, 69, 74, 76, 78]
SUBMITTED = [2, 3, 5, 15, 21, 22, 25, 28, 30, 36, 38, 40, 43, 52, 53, 58, 62, 63, 67, 72, 80]
PAID = [6, 11, 16, 17, 24, 26, 31, 32, 42, 45, 47, 48, 49, 51, 55, 56, 57, 64, 70, 71, 77]
REVERTED = {21: (11, 1644.21, "2026-01-26T10:00:00"), 22: (8, 1455.12, "2026-01-09T15:00:00"),
            38: (10, 1207.79, "2026-01-23T11:00:00")}


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


def claim(app, cid, user="fiona"):
    r = app.get(f"/api/claims/{cid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def test_capped_approvals_returned_to_manager():
    app = fresh_app()
    for cid, (emp, amount, submitted_at) in REVERTED.items():
        c = claim(app, cid)
        expected = {"employee": emp, "amount": amount, "status": "submitted", "submitted_at": submitted_at,
                    "decided_at": None, "decided_by": None, "rejection_reason": None,
                    "paid_amount": None, "advance_recovered": None}
        for k, v in expected.items():
            assert c[k] == v, (cid, k, c.get(k))
    assert ids(app.get("/api/claims?status=approved", user="fiona", now=NOW)) == APPROVED
    assert ids(app.get("/api/claims?status=submitted", user="fiona", now=NOW)) == SUBMITTED
    assert ids(app.get("/api/claims?status=paid", user="fiona", now=NOW)) == PAID
    # other approved claims keep their decision
    c = claim(app, 41)
    assert c["status"] == "approved" and c["decided_by"] == 4 and c["decided_at"] == "2026-01-31T18:00:00"


def test_approval_amount_fields_removed():
    app = fresh_app()
    for c in app.get("/api/claims", user="fiona", now=NOW).json["items"]:
        assert "approved_amount" not in c and "approval_note" not in c, c["id"]
    r = app.post("/api/claims", {"amount": 20, "category": "travel", "description": "Bus"}, user="sam", now=NOW)
    assert r.status == 201 and "approved_amount" not in r.json and "approval_note" not in r.json
    ui = parse_ui(app.get("/ui/claims/41", user="victor", now=NOW).text)
    assert "approved_amount" not in ui.fields and "approval_note" not in ui.fields
    assert {"paid_amount", "advance_recovered", "incurred_on"} <= set(ui.fields)


def test_approve_takes_no_amount_or_note():
    app = fresh_app()
    for body in ({"amount": 500, "note": "Dinner only"}, {"amount": 1455.12}, {"note": "ok"}):
        assert_error(app.post("/api/claims/22/approve", body, user="omar", now=NOW), 400, "validation")
    assert claim(app, 22)["status"] == "submitted"
    # 403 and 409 still come first
    assert_error(app.post("/api/claims/22/approve", {"amount": 5}, user="marco", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/41/approve", {"amount": 5}, user="omar", now=NOW), 409, "conflict")
    r = app.post("/api/claims/22/approve", {}, user="omar", now="2026-03-02T09:30:00")
    assert r.status == 200, r
    assert r.json["status"] == "approved" and r.json["decided_by"] == 4 and r.json["decided_at"] == "2026-03-02T09:30:00"
    assert "approved_amount" not in r.json


def test_reapproved_claim_pays_full_amount():
    app = fresh_app()
    assert app.post("/api/claims/22/approve", {}, user="omar", now=NOW).status == 200
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert money(r.json["paid_amount"]) == 1455.12 and r.json["advance_recovered"] == 0
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert rounded(msgs[-1]["payload"]) == {"claim": 22, "employee": 8, "amount": 1455.12, "advance_recovered": 0}


def test_recovery_based_on_full_amount():
    app = fresh_app()
    assert app.post("/api/claims/21/approve", {}, user="omar", now=NOW).status == 200
    r = app.post("/api/claims/21/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert money(r.json["advance_recovered"]) == 550 and money(r.json["paid_amount"]) == 1094.21
    for aid in (1, 2):
        a = app.get(f"/api/advances/{aid}", user="fiona", now=NOW).json
        assert money(a["outstanding"]) == 0
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 21, "employee": 11, "amount": 1094.21,
                                                    "advance_recovered": 550}
    r = app.post("/api/claims/41/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["advance_recovered"] == 0 and money(r.json["paid_amount"]) == 635.61


def test_reverted_claims_can_be_rejected():
    app = fresh_app()
    r = app.post("/api/claims/38/reject", {"reason": "Over the other-expenses limit"}, user="nadia", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "rejected" and r.json["decided_by"] == 3
    assert r.json["rejection_reason"] == "Over the other-expenses limit"
    assert_error(app.post("/api/claims/38/pay", {}, user="fiona", now=NOW), 409, "conflict")


def test_paid_claims_keep_payment_record():
    app = fresh_app()
    for cid in PAID:
        c = claim(app, cid)
        assert c["paid_amount"] == c["amount"] and c["advance_recovered"] == 0, cid
    c = claim(app, 17, user="victor")
    assert c["status"] == "paid" and c["decided_by"] == 4 and c["decided_at"] == "2026-01-20T17:00:00"


def test_ui_forms_for_reverted_claims():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/22", user="omar", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions and "pay" not in ui.actions
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "pay" not in ui.actions
    ui = parse_ui(app.get("/ui/claims/41", user="fiona", now=NOW).text)
    assert "pay" in ui.actions


def test_other_steps_unchanged():
    app = fresh_app()
    # F04: advances and recovery
    assert ids(app.get("/api/advances", user="omar", now=NOW)) == [1, 2]
    r = app.post("/api/advances", {"employee": 8, "amount": 100, "purpose": "Float"}, user="fiona", now=NOW)
    assert r.status == 201
    assert app.post("/api/claims/22/approve", {}, user="omar", now=NOW).status == 200
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert money(r.json["advance_recovered"]) == 100 and money(r.json["paid_amount"]) == 1355.12
    # F02 and F01
    assert app.get("/api/category_policies/2", user="sam", now=NOW).json["max_amount"] == 400
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")
    assert claim(app, 7, user="yusuf")["category"] == "lodging"
