"""Hidden acceptance tests for F03 (expenses, after F01-F02): managers may approve less than claimed.

Seed facts (computed from spec/apps/expenses_seed.json after the F01-F03 migrations):
  approved claims: 4 12 13 18 21 22 27 33 34 37 38 41 44 50 59 61 65 66 68 69 74 76 78
  paid claims:     6 11 16 17 24 26 31 32 42 45 47 48 49 51 55 56 57 64 70 71 77
  capped (approved, amount above the policy maximum of the migrated category):
    21 victor meals 1644.21 -> 400 ; 22 sam meals 1455.12 -> 400 ; 38 uma other 1207.79 -> 1000
  claim 2: victor (11), meals, 734.81, submitted; manager omar (4).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
APPROVED = [4, 12, 13, 18, 21, 22, 27, 33, 34, 37, 38, 41, 44, 50, 59, 61, 65, 66, 68, 69, 74, 76, 78]
PAID = [6, 11, 16, 17, 24, 26, 31, 32, 42, 45, 47, 48, 49, 51, 55, 56, 57, 64, 70, 71, 77]
CAPPED = {21: 400, 22: 400, 38: 1000}
NOTE = "Capped at policy maximum"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def claim(app, cid, user="fiona", now=NOW):
    r = app.get(f"/api/claims/{cid}", user=user, now=now)
    assert r.status == 200, r
    return r.json


def outbox(app):
    r = app.get("/api/_outbox", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def test_existing_claims_migrated():
    app = fresh_app()
    items = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert [c["id"] for c in items if c["status"] == "approved"] == APPROVED
    assert [c["id"] for c in items if c["status"] == "paid"] == PAID
    for c in items:
        assert "approved_amount" in c and "approval_note" in c, c["id"]
        if c["id"] in CAPPED:
            assert c["approved_amount"] == CAPPED[c["id"]], c["id"]
            assert c["approval_note"] == NOTE, c["id"]
        elif c["status"] in ("approved", "paid"):
            assert c["approved_amount"] == c["amount"], c["id"]
            assert c["approval_note"] is None, c["id"]
        else:
            assert c["approved_amount"] is None and c["approval_note"] is None, c["id"]
    c = claim(app, 22, user="sam")
    assert c["amount"] == 1455.12 and c["status"] == "approved" and c["decided_by"] == 4
    assert c["decided_at"] == "2026-01-11T13:00:00" and c["category"] == "meals"
    assert claim(app, 38, user="uma")["approved_amount"] == 1000
    assert claim(app, 6, user="victor")["approved_amount"] == 1122.39


def test_approve_without_amount_approves_full_amount():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {}, user="omar", now="2026-03-02T09:30:00")
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "approved" and c["approved_amount"] == 734.81 and c["approval_note"] is None
    assert c["decided_by"] == 4 and c["decided_at"] == "2026-03-02T09:30:00" and c["amount"] == 734.81


def test_partial_approval_with_note():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {"amount": 500, "note": "Only the client dinner is covered"},
                 user="omar", now=NOW)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "approved" and c["approved_amount"] == 500
    assert c["approval_note"] == "Only the client dinner is covered"
    assert c["amount"] == 734.81 and c["decided_by"] == 4
    assert claim(app, 2, user="victor")["approved_amount"] == 500


def test_full_amount_with_optional_note():
    app = fresh_app()
    r = app.post("/api/claims/58/approve", {"amount": 1118.43, "note": "Checked receipts"}, user="nadia", now=NOW)
    assert r.status == 200, r
    assert r.json["approved_amount"] == 1118.43 and r.json["approval_note"] == "Checked receipts"
    r = app.post("/api/claims/72/approve", {"amount": 1646.02}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["approved_amount"] == 1646.02 and r.json["approval_note"] is None


def test_approve_parameter_validation():
    app = fresh_app()
    for body in ({"amount": 500}, {"amount": 500, "note": "  "}, {"amount": 500, "note": ""},
                 {"amount": 734.82}, {"amount": 0}, {"amount": -10}, {"amount": "500", "note": "x"},
                 {"amount": True, "note": "x"}, {"amount": None, "note": "x"}, {"amount": 500, "note": 7}):
        assert_error(app.post("/api/claims/2/approve", body, user="omar", now=NOW), 400, "validation")
    c = claim(app, 2)
    assert c["status"] == "submitted" and c["approved_amount"] is None and c["decided_by"] is None


def test_approve_order_of_checks():
    app = fresh_app()
    # 403 before 409 and 400
    assert_error(app.post("/api/claims/2/approve", {"amount": -1}, user="marco", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/22/approve", {"amount": -1}, user="marco", now=NOW), 403, "forbidden")
    # 409 before 400
    assert_error(app.post("/api/claims/22/approve", {"amount": -1}, user="omar", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/20/approve", {"amount": 5, "note": "x"}, user="omar", now=NOW), 409, "conflict")
    assert claim(app, 22)["approved_amount"] == 400


def test_payment_uses_approved_amount():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "paid" and r.json["approved_amount"] == 400 and r.json["amount"] == 1455.12
    assert r.json["approval_note"] == NOTE
    r = app.post("/api/claims/38/pay", {}, user="fiona", now=NOW)
    assert r.status == 200
    r = app.post("/api/claims/4/pay", {}, user="fiona", now=NOW)
    assert r.status == 200
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["payment"] * 3
    assert [m["payload"] for m in msgs] == [
        {"claim": 22, "employee": 8, "amount": 400},
        {"claim": 38, "employee": 10, "amount": 1000},
        {"claim": 4, "employee": 10, "amount": 558.67},
    ]


def test_partial_lifecycle_pays_partial_amount():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 900, "category": "travel", "description": "Train",
                                 "incurred_on": "2026-02-25"}, user="rosa", now=NOW)
    assert r.status == 201, r
    cid = r.json["id"]
    assert r.json["approved_amount"] is None and r.json["approval_note"] is None
    assert app.post(f"/api/claims/{cid}/submit", {}, user="rosa", now=NOW).status == 200
    r = app.post(f"/api/claims/{cid}/approve", {"amount": 612.4, "note": "Standard class only"}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["approved_amount"] == 612.4
    before = len(outbox(app))
    assert app.post(f"/api/claims/{cid}/pay", {}, user="fiona", now=NOW).status == 200
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["payload"] == {"claim": cid, "employee": 7, "amount": 612.4}


def test_reject_leaves_approval_fields_empty():
    app = fresh_app()
    r = app.post("/api/claims/58/reject", {"reason": "Duplicate"}, user="nadia", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "rejected" and r.json["approved_amount"] is None and r.json["approval_note"] is None


def test_approval_fields_cannot_be_set_by_clients():
    app = fresh_app()
    base = {"amount": 50, "category": "travel", "description": "Taxi"}
    for extra in ({"approved_amount": 50}, {"approval_note": "ok"}):
        assert_error(app.post("/api/claims", dict(base, **extra), user="sam", now=NOW), 400, "validation")
        assert_error(app.patch("/api/claims/20", extra, user="sam", now=NOW), 400, "validation")
    c = claim(app, 20)
    assert c["approved_amount"] is None and c["approval_note"] is None
    assert ids(app.get("/api/claims", user="sam", now=NOW)) == [20, 22, 42, 48, 54, 61, 73]


def test_ui_shows_approval_fields_and_forms():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/22", user="sam", now=NOW).text)
    assert ui.fields["approval_note"] == NOTE
    assert "approved_amount" in ui.fields
    ui = parse_ui(app.get("/ui/claims/2", user="omar", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "pay" in ui.actions and "approve" not in ui.actions


def test_earlier_rules_still_apply():
    app = fresh_app()
    # F01: submit needs incurred_on; F02: category maximum on create
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims", {"amount": 400.01, "category": "meals", "description": "x"},
                          user="sam", now=NOW), 400, "validation")
    assert ids(app.get("/api/claims?category=lodging", user="fiona", now=NOW)) == \
        [1, 7, 11, 15, 17, 31, 36, 39, 43, 48, 54, 55, 57]
    assert app.get("/api/category_policies/2", user="sam", now=NOW).json["max_amount"] == 400
