"""Hidden acceptance tests for F13 (expenses): the claim category `other` is renamed `miscellaneous`.

Seed facts (computed from spec/apps/expenses_seed.json):
  category other: 1 4 11 13 16 18 23 24 30 36 38 39 40 41 51 54 56 60 67 70 71 73 75 76 77 80
  meals: 2 21 22 53 62 72 79. sam's (8) other claims: 54 (draft), 73 (draft).
  claim 1: wen (12), 1271.32, "Hotel night #1", draft. claim 4: uma (10), 558.67, approved.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
OTHER = [1, 4, 11, 13, 16, 18, 23, 24, 30, 36, 38, 39, 40, 41, 51, 54, 56, 60, 67, 70, 71, 73, 75, 76, 77, 80]


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


def test_existing_claims_renamed():
    app = fresh_app()
    assert ids(app.get("/api/claims?category=miscellaneous", user="fiona", now=NOW)) == OTHER
    assert ids(app.get("/api/claims?category=other", user="fiona", now=NOW)) == []
    assert ids(app.get("/api/claims?category=meals", user="fiona", now=NOW)) == [2, 21, 22, 53, 62, 72, 79]
    assert ids(app.get("/api/claims?category=miscellaneous", user="sam", now=NOW)) == [54, 73]
    c = app.get("/api/claims/1", user="wen", now=NOW).json
    expected = {"employee": 12, "amount": 1271.32, "category": "miscellaneous", "description": "Hotel night #1",
                "status": "draft", "submitted_at": None, "decided_at": None, "decided_by": None,
                "rejection_reason": None}
    for k, v in expected.items():
        assert c[k] == v, (k, c.get(k))
    cats = {c["category"] for c in app.get("/api/claims", user="fiona", now=NOW).json["items"]}
    assert cats == {"travel", "meals", "equipment", "miscellaneous"}


def test_create_and_patch_use_new_name():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 25, "category": "miscellaneous", "description": "Stamps"}, user="sam", now=NOW)
    assert r.status == 201 and r.json["category"] == "miscellaneous"
    assert_error(app.post("/api/claims", {"amount": 25, "category": "other", "description": "Stamps"},
                          user="sam", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claims/20", {"category": "other"}, user="sam", now=NOW), 400, "validation")
    r = app.patch("/api/claims/20", {"category": "miscellaneous"}, user="sam", now=NOW)
    assert r.status == 200 and r.json["category"] == "miscellaneous"
    r = app.patch("/api/claims/54", {"category": "travel"}, user="sam", now=NOW)
    assert r.status == 200 and r.json["category"] == "travel"
    for cat in ("travel", "meals", "equipment"):
        assert app.post("/api/claims", {"amount": 5, "category": cat, "description": "x"}, user="sam",
                        now=NOW).status == 201


def test_workflow_and_payment_unchanged():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/4/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["category"] == "miscellaneous" and r.json["status"] == "paid"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["payload"] == {"claim": 4, "employee": 10, "amount": 558.67}
    r = app.post("/api/claims/80/approve", {}, user="omar", now=NOW)
    assert r.status == 200 and r.json["category"] == "miscellaneous"
    r = app.post("/api/claims/73/submit", {}, user="sam", now=NOW)
    assert r.status == 200 and r.json["category"] == "miscellaneous"


def test_ui_shows_new_name():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/4", user="uma", now=NOW).text)
    assert ui.fields["category"] == "miscellaneous"
    ui = parse_ui(app.get("/ui/claims/20", user="sam", now=NOW).text)
    assert ui.fields["category"] == "travel"
