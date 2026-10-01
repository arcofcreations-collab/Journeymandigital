"""Hidden acceptance tests for F01 (expenses): claims record the date the expense was incurred.

Seed facts (computed from spec/apps/expenses_seed.json):
  68 claims have a submitted_at; the 12 drafts 1 8 9 19 20 29 39 46 54 73 75 79 have none.
  claims submitted on 2026-01-28: 7 26 49 59; on 2026-02-24: 3 12 67.
  claim 20: sam (8), travel, 1553.42, draft. claim 22: sam, approved, submitted 2026-01-09T15:00:00.
  claim 2: victor (11), submitted 2026-01-25T12:00:00, manager omar (4).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
DRAFTS = [1, 8, 9, 19, 20, 29, 39, 46, 54, 73, 75, 79]


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


def test_existing_claims_migrated_from_submission_date():
    app = fresh_app()
    items = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert [c["id"] for c in items] == list(range(1, 81))
    for c in items:
        assert "incurred_on" in c, c["id"]
        if c["submitted_at"] is None:
            assert c["incurred_on"] is None, c["id"]
        else:
            assert c["incurred_on"] == c["submitted_at"][:10], c["id"]
    assert [c["id"] for c in items if c["incurred_on"] is None] == DRAFTS
    assert claim(app, 2)["incurred_on"] == "2026-01-25"
    assert claim(app, 7, user="yusuf")["incurred_on"] == "2026-01-28"
    c22 = claim(app, 22, user="sam")
    assert c22["incurred_on"] == "2026-01-09"
    assert c22["status"] == "approved" and c22["amount"] == 1455.12 and c22["decided_by"] == 4


def test_filter_by_incurred_on():
    app = fresh_app()
    assert ids(app.get("/api/claims?incurred_on=2026-01-28", user="fiona", now=NOW)) == [7, 26, 49, 59]
    assert ids(app.get("/api/claims?incurred_on=2026-02-24", user="fiona", now=NOW)) == [3, 12, 67]
    # read permission still applies to filtered lists (marco manages quinn and tariq, not uma)
    assert ids(app.get("/api/claims?incurred_on=2026-02-24", user="marco", now=NOW)) == [3, 12]


def test_create_with_and_without_incurred_on():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 42.5, "category": "meals", "description": "Lunch",
                                 "incurred_on": "2026-02-27"}, user="priya", now=NOW)
    assert r.status == 201, r
    assert r.json["incurred_on"] == "2026-02-27" and r.json["status"] == "draft" and r.json["employee"] == 5
    r = app.post("/api/claims", {"amount": 10, "category": "travel", "description": "Bus"}, user="priya", now=NOW)
    assert r.status == 201, r
    assert "incurred_on" in r.json and r.json["incurred_on"] is None
    # today is allowed
    r = app.post("/api/claims", {"amount": 10, "category": "travel", "description": "Bus",
                                 "incurred_on": "2026-03-01"}, user="priya", now="2026-03-01T00:00:05")
    assert r.status == 201 and r.json["incurred_on"] == "2026-03-01"


def test_incurred_on_validation():
    app = fresh_app()
    base = {"amount": 10, "category": "travel", "description": "Bus"}
    for bad in ("2026-03-02", "2026-02-30", "01/03/2026", "2026-3-1", "yesterday", 20260301, True, ""):
        r = app.post("/api/claims", dict(base, incurred_on=bad), user="priya", now=NOW)
        assert_error(r, 400, "validation")
    assert ids(app.get("/api/claims", user="priya", now=NOW)) == [14, 33, 44, 45, 51]
    for bad in ("2026-03-02", "2026-13-01"):
        assert_error(app.patch("/api/claims/20", {"incurred_on": bad}, user="sam", now=NOW), 400, "validation")
    assert claim(app, 20)["incurred_on"] is None


def test_patch_incurred_on_follows_patch_rules():
    app = fresh_app()
    r = app.patch("/api/claims/20", {"incurred_on": "2026-02-20"}, user="sam", now=NOW)
    assert r.status == 200, r
    assert r.json["incurred_on"] == "2026-02-20" and r.json["amount"] == 1553.42 and r.json["status"] == "draft"
    for user in ("omar", "fiona", "priya"):
        assert_error(app.patch("/api/claims/20", {"incurred_on": "2026-02-21"}, user=user, now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/claims/22", {"incurred_on": "2026-01-02"}, user="sam", now=NOW), 409, "conflict")
    # 409 wins over 400
    assert_error(app.patch("/api/claims/22", {"incurred_on": "not a date"}, user="sam", now=NOW), 409, "conflict")
    r = app.patch("/api/claims/20", {"incurred_on": None}, user="sam", now=NOW)
    assert r.status == 200 and r.json["incurred_on"] is None
    assert claim(app, 22)["incurred_on"] == "2026-01-09"


def test_submit_requires_incurred_on():
    app = fresh_app()
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")
    c = claim(app, 20)
    assert c["status"] == "draft" and c["submitted_at"] is None
    # 403 still wins for someone else's draft
    assert_error(app.post("/api/claims/20/submit", {}, user="omar", now=NOW), 403, "forbidden")
    assert app.patch("/api/claims/20", {"incurred_on": "2026-02-26"}, user="sam", now=NOW).status == 200
    r = app.post("/api/claims/20/submit", {}, user="sam", now="2026-03-02T09:30:00")
    assert r.status == 200, r
    assert r.json["status"] == "submitted" and r.json["submitted_at"] == "2026-03-02T09:30:00"
    assert r.json["incurred_on"] == "2026-02-26"
    # wrong state still 409
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/22/submit", {}, user="sam", now=NOW), 409, "conflict")


def test_ui_submit_form_and_fields():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/20", user="sam", now=NOW).text)
    assert "incurred_on" in ui.fields
    assert "submit" not in ui.actions
    assert app.patch("/api/claims/20", {"incurred_on": "2026-02-26"}, user="sam", now=NOW).status == 200
    ui = parse_ui(app.get("/ui/claims/20", user="sam", now=NOW).text)
    assert ui.fields["incurred_on"] == "2026-02-26"
    assert "submit" in ui.actions
    ui = parse_ui(app.get("/ui/claims/7", user="yusuf", now=NOW).text)
    assert ui.fields["incurred_on"] == "2026-01-28"
    r = app.get("/ui/claims/new", user="sam", now=NOW)
    assert r.status == 200
    assert {"amount", "category", "description", "incurred_on"} <= set(parse_ui(r.text).inputs)


def test_full_lifecycle_with_incurred_on():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 321.25, "category": "travel", "description": "Bus",
                                 "incurred_on": "2026-03-01"}, user="rosa", now="2026-03-02T08:00:00")
    assert r.status == 201, r
    cid = r.json["id"]
    assert app.post(f"/api/claims/{cid}/submit", {}, user="rosa", now="2026-03-03T10:00:00").status == 200
    r = app.post(f"/api/claims/{cid}/approve", {}, user="nadia", now="2026-03-04T11:00:00")
    assert r.status == 200 and r.json["decided_by"] == 3
    before = len(outbox(app))
    r = app.post(f"/api/claims/{cid}/pay", {}, user="fiona", now="2026-03-05T12:00:00")
    assert r.status == 200 and r.json["status"] == "paid" and r.json["incurred_on"] == "2026-03-01"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": cid, "employee": 7, "amount": 321.25}


def test_existing_workflow_unchanged():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {}, user="omar", now=NOW)
    assert r.status == 200 and r.json["status"] == "approved" and r.json["incurred_on"] == "2026-01-25"
    r = app.post("/api/claims/58/reject", {"reason": "Duplicate"}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["rejection_reason"] == "Duplicate"
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["status"] == "paid"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}
    # protected fields remain protected
    assert_error(app.post("/api/claims", {"amount": 5, "category": "meals", "description": "x",
                                          "status": "approved"}, user="sam", now=NOW), 400, "validation")
