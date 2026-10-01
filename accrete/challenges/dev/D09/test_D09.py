"""D09 (expenses, depends on D08): withdraw the second-approval rule (reversal).

After D08, claims 21, 22, 44 were `awaiting_second_approval` with first_approved_by 4 and
first_approved_at equal to their original decided_at. Reversing must restore them to:
  21 approved, decided_by 4, decided_at 2026-01-28T08:00:00
  22 approved, decided_by 4, decided_at 2026-01-11T13:00:00
  44 approved, decided_by 4, decided_at 2026-01-19T14:00:00
Base reading sets (seed): marco reads MARCO_READABLE below.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

RESTORED = {21: ("2026-01-28T08:00:00", 11, 1644.21),
            22: ("2026-01-11T13:00:00", 8, 1455.12),
            44: ("2026-01-19T14:00:00", 5, 1667.52)}
MARCO_READABLE = [1, 3, 8, 10, 11, 12, 18, 19, 24, 25, 29, 34, 35, 43, 46, 50, 52, 53, 55, 56,
                  59, 66, 68, 71, 74]
APPROVED = [4, 12, 13, 18, 21, 22, 27, 33, 34, 37, 38, 41, 44, 50, 59, 61, 65, 66, 68, 69, 74, 76, 78]


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


def claim(app, cid, user="fiona", now=NOW):
    r = app.get(f"/api/claims/{cid}", user=user, now=now)
    assert r.status == 200, r
    return r.json


def test_awaiting_claims_restored_with_first_approval():
    app = fresh_app()
    for cid, (decided_at, emp, amount) in RESTORED.items():
        c = claim(app, cid)
        assert c["status"] == "approved", c
        assert c["decided_by"] == 4 and c["decided_at"] == decided_at, c
        assert c["employee"] == emp and c["amount"] == amount
        assert c["rejection_reason"] is None


def test_second_approval_fields_and_status_gone():
    app = fresh_app()
    items = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert [c["id"] for c in items] == list(range(1, 81))
    for c in items:
        assert "first_approved_by" not in c and "first_approved_at" not in c, c["id"]
        assert c["status"] in ("draft", "submitted", "approved", "rejected", "paid"), c
    assert ids(app.get("/api/claims?status=approved", user="fiona", now=NOW)) == APPROVED
    assert ids(app.get("/api/claims?status=approved&decided_by=4", user="fiona", now=NOW)) == [21, 22, 33, 41, 44, 61]


def test_large_claims_need_single_approval_again():
    app = fresh_app()
    r = app.post("/api/claims/36/approve", {}, user="omar", now=T2)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "approved" and c["decided_by"] == 4 and c["decided_at"] == T2
    assert "first_approved_by" not in c
    r = app.post("/api/claims", {"amount": 4999, "category": "equipment", "description": "Laptop"}, user="sam", now=NOW)
    cid = r.json["id"]
    assert app.post(f"/api/claims/{cid}/submit", {}, user="sam", now=NOW).status == 200
    r = app.post(f"/api/claims/{cid}/approve", {}, user="omar", now=T2)
    assert r.status == 200 and r.json["status"] == "approved"


def test_skip_level_manager_loses_access():
    app = fresh_app()
    assert ids(app.get("/api/claims", user="marco", now=NOW)) == MARCO_READABLE
    assert ids(app.get("/api/claims?employee=5", user="marco", now=NOW)) == []
    for cid in (21, 22, 44):
        assert_error(app.get(f"/api/claims/{cid}", user="marco", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/22/approve", {}, user="marco", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/36/approve", {}, user="marco", now=NOW), 403, "forbidden")


def test_restored_claims_can_be_paid():
    app = fresh_app()
    n = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=T2)
    assert r.status == 200, r
    assert r.json["status"] == "paid" and r.json["decided_by"] == 4 and r.json["decided_at"] == "2026-01-11T13:00:00"
    msgs = outbox(app)
    assert len(msgs) == n + 1
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}


def test_restored_claims_cannot_be_approved_again():
    app = fresh_app()
    assert_error(app.post("/api/claims/22/approve", {}, user="omar", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/44/reject", {"reason": "x"}, user="omar", now=NOW), 409, "conflict")
    assert claim(app, 44)["status"] == "approved"


def test_other_claims_untouched():
    app = fresh_app()
    c = claim(app, 27)
    assert c["status"] == "approved" and c["decided_by"] == 3 and c["decided_at"] == "2026-01-25T17:00:00"
    c = claim(app, 17)
    assert c["status"] == "paid" and c["decided_by"] == 4 and c["decided_at"] == "2026-01-20T17:00:00"
    c = claim(app, 7)
    assert c["status"] == "rejected" and c["rejection_reason"] == "Missing receipt"
    c = claim(app, 36)
    assert c["status"] == "submitted" and c["decided_by"] is None


def test_ui_after_reversal():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert ui.fields["status"] == "approved"
    assert "pay" in ui.actions
    assert "first_approved_by" not in ui.fields and "first_approved_at" not in ui.fields
    ui = parse_ui(app.get("/ui/claims/36", user="omar", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions
    assert app.get("/ui/claims/22", user="marco", now=NOW).status == 403
