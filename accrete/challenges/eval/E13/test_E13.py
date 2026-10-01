"""Hidden acceptance tests for E13 (expenses): withdraw submitted claims, revise rejected claims.

Seed facts (spec/apps/expenses_seed.json), NOW = 2026-03-01T12:00:00:
  submitted within the last 7 days: 3 (quinn, 2026-02-24T14:00:00), 62 (xena, 2026-02-23T16:00:00),
  67 (uma, 2026-02-24T11:00:00); older submitted e.g. 2 (victor, 2026-01-25T12:00:00).
  rejected: 7 (yusuf, "Missing receipt", decided 2026-01-30T09:00:00 by 4), 14 (priya, "Over policy limit", by 4),
  10 (tariq, by 2). quinn's manager is marco (2); yusuf's and priya's manager is omar (4).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


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


def act(app, cid, action, user, now=NOW, body=None):
    return app.post(f"/api/claims/{cid}/{action}", body or {}, user=user, now=now)


def test_new_fields_default_and_read_only():
    app = fresh_app()
    items = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert len(items) == 80
    assert all(c["revision"] == 0 and c["previous_rejection_reason"] is None for c in items)
    c = claim(app, 7)
    assert c["rejection_reason"] == "Missing receipt" and c["status"] == "rejected"
    r = app.post("/api/claims", {"amount": 10, "category": "meals", "description": "x"}, user="sam", now=NOW)
    assert r.status == 201 and r.json["revision"] == 0 and r.json["previous_rejection_reason"] is None
    for field, value in (("revision", 1), ("previous_rejection_reason", "x")):
        assert_error(app.post("/api/claims", {"amount": 10, "category": "meals", "description": "x", field: value},
                              user="sam", now=NOW), 400, "validation")
        assert_error(app.patch("/api/claims/20", {field: value}, user="sam", now=NOW), 400, "validation")


def test_withdraw_recent_submission_and_resubmit():
    app = fresh_app()
    r = act(app, 3, "withdraw", "quinn")
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "draft" and c["submitted_at"] is None and c["decided_at"] is None and c["revision"] == 0
    r = app.patch("/api/claims/3", {"amount": 400}, user="quinn", now=NOW)
    assert r.status == 200 and r.json["amount"] == 400
    r = act(app, 3, "submit", "quinn", now=T2)
    assert r.status == 200 and r.json["submitted_at"] == T2
    r = act(app, 3, "approve", "marco", now=T2)
    assert r.status == 200 and r.json["decided_by"] == 2
    assert claim(app, 3, user="quinn")["revision"] == 0


def test_withdraw_window_is_seven_days():
    app = fresh_app()
    assert act(app, 3, "withdraw", "quinn", now="2026-03-03T14:00:00").status == 200    # exactly 7 days
    app = fresh_app()
    assert_error(act(app, 3, "withdraw", "quinn", now="2026-03-03T14:00:01"), 409, "conflict")
    assert_error(act(app, 2, "withdraw", "victor"), 409, "conflict")
    assert_error(act(app, 62, "withdraw", "xena", now="2026-03-02T16:00:01"), 409, "conflict")
    assert act(app, 62, "withdraw", "xena", now="2026-03-02T15:59:59").status == 200
    c = claim(app, 3)
    assert c["status"] == "submitted" and c["submitted_at"] == "2026-02-24T14:00:00"


def test_withdraw_permissions_and_states():
    app = fresh_app()
    for user in ("marco", "fiona", "sam"):
        assert_error(act(app, 3, "withdraw", user), 403, "forbidden")
    assert_error(act(app, 22, "withdraw", "marco"), 403, "forbidden")    # 403 before 409
    for cid, user in ((20, "sam"), (22, "sam"), (42, "sam"), (7, "yusuf")):
        assert_error(act(app, cid, "withdraw", user), 409, "conflict")
    assert claim(app, 3)["status"] == "submitted"


def test_revise_rejected_claim_up_to_twice():
    app = fresh_app()
    r = act(app, 7, "revise", "yusuf", now=T2)
    assert r.status == 200, r
    c = r.json
    expected = {"status": "draft", "revision": 1, "previous_rejection_reason": "Missing receipt",
                "rejection_reason": None, "decided_at": None, "decided_by": None, "submitted_at": None,
                "amount": 613.88, "employee": 14}
    for k, v in expected.items():
        assert c[k] == v, (k, c.get(k))
    assert app.patch("/api/claims/7", {"amount": 600}, user="yusuf", now=T2).status == 200
    assert act(app, 7, "submit", "yusuf", now=T2).status == 200
    r = act(app, 7, "reject", "omar", now=T2, body={"reason": "Still missing"})
    assert r.status == 200 and r.json["revision"] == 1 and r.json["previous_rejection_reason"] == "Missing receipt"
    r = act(app, 7, "revise", "yusuf", now=T2)
    assert r.status == 200 and r.json["revision"] == 2 and r.json["previous_rejection_reason"] == "Still missing"
    assert act(app, 7, "submit", "yusuf", now=T2).status == 200
    assert act(app, 7, "reject", "omar", now=T2, body={"reason": "Third time"}).status == 200
    assert_error(act(app, 7, "revise", "yusuf", now=T2), 409, "conflict")
    c = claim(app, 7)
    assert c["status"] == "rejected" and c["revision"] == 2 and c["rejection_reason"] == "Third time"


def test_revise_permissions_and_states():
    app = fresh_app()
    for user in ("omar", "fiona", "priya"):
        assert_error(act(app, 7, "revise", user), 403, "forbidden")
    assert_error(act(app, 5, "revise", "omar"), 403, "forbidden")        # 403 before 409
    for cid, user in ((5, "yusuf"), (75, "yusuf"), (31, "yusuf"), (22, "sam")):
        assert_error(act(app, cid, "revise", user), 409, "conflict")
    c = claim(app, 7)
    assert c["status"] == "rejected" and c["decided_by"] == 4 and c["decided_at"] == "2026-01-30T09:00:00"


def test_revised_claim_can_be_approved_paid_or_deleted():
    app = fresh_app()
    assert act(app, 14, "revise", "priya").status == 200
    assert act(app, 14, "submit", "priya", now=T2).status == 200
    assert act(app, 14, "approve", "omar", now=T2).status == 200
    before = len(outbox(app))
    r = act(app, 14, "pay", "fiona", now=T2)
    assert r.status == 200 and r.json["status"] == "paid" and r.json["revision"] == 1
    assert outbox(app)[before]["payload"] == {"claim": 14, "employee": 5, "amount": 1377.2}
    assert act(app, 10, "revise", "tariq").status == 200
    assert app.delete("/api/claims/10", user="tariq", now=NOW).status == 204


def test_ui_withdraw_and_revise_forms():
    app = fresh_app()
    assert "withdraw" in parse_ui(app.get("/ui/claims/3", user="quinn", now=NOW).text).actions
    assert "withdraw" not in parse_ui(app.get("/ui/claims/3", user="quinn", now="2026-03-04T00:00:00").text).actions
    assert "withdraw" not in parse_ui(app.get("/ui/claims/3", user="marco", now=NOW).text).actions
    assert "withdraw" not in parse_ui(app.get("/ui/claims/2", user="victor", now=NOW).text).actions
    assert "revise" in parse_ui(app.get("/ui/claims/7", user="yusuf", now=NOW).text).actions
    assert "revise" not in parse_ui(app.get("/ui/claims/7", user="omar", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/claims/7", user="yusuf", now=NOW).text)
    assert "revision" in ui.fields and "previous_rejection_reason" in ui.fields
    assert ui.fields["revision"] == "0"
