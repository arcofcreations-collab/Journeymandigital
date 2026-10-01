"""D08 (expenses): second approval for claims over 1000.00 (with data migration).

Seed facts (computed from expenses_seed.json):
  managers: marco (2, no manager), nadia (3, no manager), omar (4, manager marco)
  omar's reports: priya 5, sam 8, victor 11, yusuf 14  -> their large claims need marco as 2nd approver
  migrated (approved, > 1000, employee's manager has a manager):
    21 victor 1644.21 decided 2026-01-28T08:00:00 by 4
    22 sam    1455.12 decided 2026-01-11T13:00:00 by 4
    44 priya  1667.52 decided 2026-01-19T14:00:00 by 4
  not migrated: approved >1000 decided by marco/nadia (27, 38, 50, 59, 66, 69, 74, 78); paid 17 (victor 1588.92)
  submitted: 36 victor 1655.6, 5 yusuf 1057.93, 2 victor 734.81, 25 zoe 1452.8 (mgr marco),
             43 omar 1663.17 (mgr marco), 72 rosa 1646.02 (mgr nadia)
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"
T3 = "2026-03-03T10:00:00"

MIGRATED = {21: "2026-01-28T08:00:00", 22: "2026-01-11T13:00:00", 44: "2026-01-19T14:00:00"}
MARCO_READABLE_AFTER = [1, 3, 8, 10, 11, 12, 18, 19, 21, 22, 24, 25, 29, 34, 35, 43, 44, 46, 50, 52, 53,
                        55, 56, 59, 66, 68, 71, 74]


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


def submitted_claim(app, user, amount):
    r = app.post("/api/claims", {"amount": amount, "category": "travel", "description": "Trip"}, user=user, now=NOW)
    assert r.status == 201, r
    cid = r.json["id"]
    assert app.post(f"/api/claims/{cid}/submit", {}, user=user, now=NOW).status == 200
    return cid


def test_large_approved_claims_migrated_to_second_approval():
    app = fresh_app()
    for cid, decided_at in MIGRATED.items():
        c = claim(app, cid)
        assert c["status"] == "awaiting_second_approval", c
        assert c["first_approved_by"] == 4 and c["first_approved_at"] == decided_at
        assert c["decided_by"] is None and c["decided_at"] is None
        assert c["rejection_reason"] is None
    c = claim(app, 22)
    assert c["amount"] == 1455.12 and c["employee"] == 8 and c["submitted_at"] == "2026-01-09T15:00:00"
    assert ids(app.get("/api/claims?status=awaiting_second_approval", user="fiona", now=NOW)) == [21, 22, 44]


def test_other_claims_not_migrated():
    app = fresh_app()
    items = {c["id"]: c for c in app.get("/api/claims", user="fiona", now=NOW).json["items"]}
    assert sorted(items) == list(range(1, 81))
    for cid, c in items.items():
        if cid in MIGRATED:
            continue
        assert c["first_approved_by"] is None and c["first_approved_at"] is None, cid
        assert c["status"] != "awaiting_second_approval", cid
    for cid in (27, 38, 50, 59, 66, 69, 74, 78, 33):
        assert items[cid]["status"] == "approved", cid
    assert items[27]["decided_by"] == 3 and items[27]["decided_at"] == "2026-01-25T17:00:00"
    assert items[17]["status"] == "paid" and items[17]["decided_by"] == 4
    assert ids(app.get("/api/claims?status=approved&decided_by=4", user="fiona", now=NOW)) == [33, 41, 61]


def test_large_claim_needs_two_approvals_then_pay():
    app = fresh_app()
    r = app.post("/api/claims/36/approve", {}, user="omar", now=T2)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "awaiting_second_approval"
    assert c["first_approved_by"] == 4 and c["first_approved_at"] == T2
    assert c["decided_by"] is None and c["decided_at"] is None
    assert_error(app.post("/api/claims/36/pay", {}, user="fiona", now=T2), 409, "conflict")
    r = app.post("/api/claims/36/approve", {}, user="marco", now=T3)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "approved" and c["decided_by"] == 2 and c["decided_at"] == T3
    assert c["first_approved_by"] == 4 and c["first_approved_at"] == T2
    n = len(outbox(app))
    assert app.post("/api/claims/36/pay", {}, user="fiona", now=T3).status == 200
    msgs = outbox(app)
    assert len(msgs) == n + 1 and msgs[-1]["payload"] == {"claim": 36, "employee": 11, "amount": 1655.6}


def test_threshold_is_strictly_greater_than_1000():
    app = fresh_app()
    small = submitted_claim(app, "sam", 1000.00)
    big = submitted_claim(app, "sam", 1000.01)
    r = app.post(f"/api/claims/{small}/approve", {}, user="omar", now=T2)
    assert r.status == 200 and r.json["status"] == "approved" and r.json["decided_by"] == 4
    assert r.json["first_approved_by"] is None
    r = app.post(f"/api/claims/{big}/approve", {}, user="omar", now=T2)
    assert r.status == 200 and r.json["status"] == "awaiting_second_approval"


def test_single_approval_when_manager_has_no_manager():
    app = fresh_app()
    for cid, mgr, mgr_id in ((25, "marco", 2), (43, "marco", 2), (72, "nadia", 3)):
        r = app.post(f"/api/claims/{cid}/approve", {}, user=mgr, now=T2)
        assert r.status == 200, r
        assert r.json["status"] == "approved" and r.json["decided_by"] == mgr_id
        assert r.json["first_approved_by"] is None and r.json["first_approved_at"] is None
    r = app.post("/api/claims/2/approve", {}, user="omar", now=T2)  # small claim
    assert r.status == 200 and r.json["status"] == "approved" and r.json["first_approved_by"] is None


def test_second_approver_rejects():
    app = fresh_app()
    assert app.post("/api/claims/5/approve", {}, user="omar", now=T2).status == 200
    assert_error(app.post("/api/claims/5/reject", {}, user="marco", now=T3), 400, "validation")
    assert_error(app.post("/api/claims/5/reject", {"reason": ""}, user="marco", now=T3), 400, "validation")
    r = app.post("/api/claims/5/reject", {"reason": "Not justified"}, user="marco", now=T3)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "rejected" and c["rejection_reason"] == "Not justified"
    assert c["decided_by"] == 2 and c["decided_at"] == T3
    assert c["first_approved_by"] == 4 and c["first_approved_at"] == T2


def test_approve_and_reject_permissions_with_two_levels():
    app = fresh_app()
    # claim 22 awaits marco
    assert_error(app.post("/api/claims/22/approve", {}, user="omar", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/22/reject", {"reason": "x"}, user="omar", now=NOW), 409, "conflict")
    for user in ("nadia", "fiona", "sam", "priya"):
        assert_error(app.post("/api/claims/22/approve", {}, user=user, now=NOW), 403, "forbidden")
    # marco has no rights on omar's reports' claims at other stages
    assert_error(app.post("/api/claims/36/approve", {}, user="marco", now=NOW), 403, "forbidden")   # submitted
    assert_error(app.post("/api/claims/20/approve", {}, user="marco", now=NOW), 403, "forbidden")   # draft
    assert_error(app.post("/api/claims/33/approve", {}, user="marco", now=NOW), 403, "forbidden")   # approved
    assert claim(app, 36)["status"] == "submitted"
    assert app.post("/api/claims/22/approve", {}, user="marco", now=NOW).status == 200
    assert_error(app.post("/api/claims/22/approve", {}, user="marco", now=NOW), 403, "forbidden")   # now approved
    assert_error(app.post("/api/claims/22/approve", {}, user="omar", now=NOW), 409, "conflict")


def test_awaiting_claims_cannot_be_paid():
    app = fresh_app()
    before = outbox(app)
    for cid in MIGRATED:
        assert_error(app.post(f"/api/claims/{cid}/pay", {}, user="fiona", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert claim(app, 22)["status"] == "awaiting_second_approval"


def test_second_approver_can_read_two_step_claims():
    app = fresh_app()
    assert ids(app.get("/api/claims", user="marco", now=NOW)) == MARCO_READABLE_AFTER
    assert claim(app, 44, user="marco")["status"] == "awaiting_second_approval"
    assert ids(app.get("/api/claims?employee=5", user="marco", now=NOW)) == [44]
    assert_error(app.get("/api/claims/33", user="marco", now=NOW), 403, "forbidden")  # single-approval claim
    assert_error(app.get("/api/claims/36", user="marco", now=NOW), 403, "forbidden")
    assert app.post("/api/claims/36/approve", {}, user="omar", now=T2).status == 200
    assert claim(app, 36, user="marco")["first_approved_by"] == 4
    assert_error(app.get("/api/claims/22", user="nadia", now=NOW), 403, "forbidden")


def test_two_step_claim_stays_readable_after_decision():
    app = fresh_app()
    assert app.post("/api/claims/44/reject", {"reason": "Duplicate"}, user="marco", now=T2).status == 200
    assert claim(app, 44, user="marco")["status"] == "rejected"
    assert claim(app, 44, user="priya")["decided_by"] == 2


def test_new_workflow_fields_are_protected():
    app = fresh_app()
    base = {"amount": 50, "category": "travel", "description": "Taxi"}
    for field, value in (("first_approved_by", 4), ("first_approved_at", NOW)):
        assert_error(app.post("/api/claims", dict(base, **{field: value}), user="sam", now=NOW), 400, "validation")
        assert_error(app.patch("/api/claims/20", {field: value}, user="sam", now=NOW), 400, "validation")
    assert_error(app.post("/api/claims", dict(base, status="awaiting_second_approval"), user="sam", now=NOW),
                 400, "validation")
    assert claim(app, 20)["first_approved_by"] is None


def test_ui_second_approval_forms():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/22", user="marco", now=NOW).text)
    assert ui.fields["status"] == "awaiting_second_approval"
    assert "approve" in ui.actions and "reject" in ui.actions and "pay" not in ui.actions
    ui = parse_ui(app.get("/ui/claims/22", user="omar", now=NOW).text)
    assert "approve" not in ui.actions and "reject" not in ui.actions
    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "pay" not in ui.actions
    assert "first_approved_by" in ui.fields and "first_approved_at" in ui.fields
    assert "pay" in parse_ui(app.get("/ui/claims/27", user="fiona", now=NOW).text).actions
