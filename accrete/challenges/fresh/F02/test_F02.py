"""Hidden acceptance tests for F02 (expenses, after F01): finance-managed category policies,
per-category maximums, submission deadlines and the new `lodging` category.

Seed facts (computed from spec/apps/expenses_seed.json after the F01 and F02 migrations):
  "Hotel night" claims -> lodging: 1 7 11 15 17 31 36 39 43 48 54 55 57
  remaining categories:
    travel    5 6 8 9 12 19 20 25 26 27 28 33 34 42 44 45 47 58 61 63 64 69
    meals     2 21 22 53 62 72 79
    equipment 3 10 14 29 32 35 37 46 49 50 52 59 65 66 68 74 78
    other     4 13 16 18 23 24 30 38 40 41 51 56 60 67 70 71 73 75 76 77 80
  claim 79: victor (11), meals, 553.87, draft (above the meals maximum 400).
  claim 20: sam (8), travel, 1553.42, draft, incurred_on null.
  claim 21: victor, meals, 1644.21, approved by omar (4).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
LODGING = [1, 7, 11, 15, 17, 31, 36, 39, 43, 48, 54, 55, 57]
TRAVEL = [5, 6, 8, 9, 12, 19, 20, 25, 26, 27, 28, 33, 34, 42, 44, 45, 47, 58, 61, 63, 64, 69]
MEALS = [2, 21, 22, 53, 62, 72, 79]
EQUIPMENT = [3, 10, 14, 29, 32, 35, 37, 46, 49, 50, 52, 59, 65, 66, 68, 74, 78]
OTHER = [4, 13, 16, 18, 23, 24, 30, 38, 40, 41, 51, 56, 60, 67, 70, 71, 73, 75, 76, 77, 80]
POLICIES = [
    {"id": 1, "category": "travel", "max_amount": 2500, "submit_within_days": 60},
    {"id": 2, "category": "meals", "max_amount": 400, "submit_within_days": 30},
    {"id": 3, "category": "equipment", "max_amount": 2000, "submit_within_days": 90},
    {"id": 4, "category": "other", "max_amount": 1000, "submit_within_days": 60},
    {"id": 5, "category": "lodging", "max_amount": 1800, "submit_within_days": 60},
]


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


def new_claim(app, user, amount, category, incurred_on=None, now=NOW):
    body = {"amount": amount, "category": category, "description": "Test expense"}
    if incurred_on:
        body["incurred_on"] = incurred_on
    return app.post("/api/claims", body, user=user, now=now)


def test_seeded_policies_readable_by_everyone():
    app = fresh_app()
    for user in ("sam", "omar", "fiona"):
        r = app.get("/api/category_policies", user=user, now=NOW)
        assert r.status == 200, r
        items = r.json["items"]
        assert [p["id"] for p in items] == [1, 2, 3, 4, 5]
        for got, exp in zip(items, POLICIES):
            for k, v in exp.items():
                assert got[k] == v, (exp["id"], k, got.get(k))
    r = app.get("/api/category_policies/5", user="priya", now=NOW)
    assert r.status == 200 and r.json["category"] == "lodging" and r.json["max_amount"] == 1800
    assert ids(app.get("/api/category_policies?category=meals", user="sam", now=NOW)) == [2]
    assert_error(app.get("/api/category_policies/99", user="sam", now=NOW), 404, "not_found")
    assert_error(app.get("/api/category_policies", user=None, now=NOW), 401, "unauthenticated")


def test_hotel_claims_migrated_to_lodging():
    app = fresh_app()
    assert ids(app.get("/api/claims?category=lodging", user="fiona", now=NOW)) == LODGING
    assert ids(app.get("/api/claims?category=travel", user="fiona", now=NOW)) == TRAVEL
    assert ids(app.get("/api/claims?category=meals", user="fiona", now=NOW)) == MEALS
    assert ids(app.get("/api/claims?category=equipment", user="fiona", now=NOW)) == EQUIPMENT
    assert ids(app.get("/api/claims?category=other", user="fiona", now=NOW)) == OTHER
    c = claim(app, 7, user="yusuf")
    expected = {"employee": 14, "amount": 613.88, "category": "lodging", "description": "Hotel night #7",
                "status": "rejected", "submitted_at": "2026-01-28T11:00:00", "decided_at": "2026-01-30T09:00:00",
                "decided_by": 4, "rejection_reason": "Missing receipt", "incurred_on": "2026-01-28"}
    for k, v in expected.items():
        assert c[k] == v, (k, c.get(k))
    # amounts above the new maximums are kept as they are
    assert claim(app, 21)["amount"] == 1644.21 and claim(app, 79)["amount"] == 553.87
    assert claim(app, 39)["amount"] == 1748.0 and claim(app, 39)["category"] == "lodging"


def test_create_respects_category_maximum():
    app = fresh_app()
    for amount, category in ((1800, "lodging"), (400, "meals"), (2500, "travel"), (2000, "equipment"), (1000, "other")):
        r = new_claim(app, "sam", amount, category)
        assert r.status == 201, (amount, category, r)
        assert r.json["category"] == category and r.json["amount"] == amount
    for amount, category in ((1800.01, "lodging"), (400.01, "meals"), (2500.01, "travel"), (5000, "equipment"),
                             (1000.5, "other"), (0, "meals"), (-1, "travel")):
        assert_error(new_claim(app, "sam", amount, category), 400, "validation")
    for category in ("food", "Lodging", "", None):
        assert_error(new_claim(app, "sam", 10, category), 400, "validation")
    assert len(ids(app.get("/api/claims", user="sam", now=NOW))) == 7 + 5


def test_patch_checks_maximum_only_when_amount_or_category_sent():
    app = fresh_app()
    r = app.patch("/api/claims/79", {"description": "Team dinner"}, user="victor", now=NOW)
    assert r.status == 200, r
    assert r.json["description"] == "Team dinner" and r.json["amount"] == 553.87 and r.json["category"] == "meals"
    assert_error(app.patch("/api/claims/79", {"amount": 500}, user="victor", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claims/79", {"amount": 553.87}, user="victor", now=NOW), 400, "validation")
    r = app.patch("/api/claims/79", {"category": "travel"}, user="victor", now=NOW)
    assert r.status == 200 and r.json["category"] == "travel" and r.json["amount"] == 553.87
    assert_error(app.patch("/api/claims/79", {"amount": 2600}, user="victor", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claims/79", {"category": "meals"}, user="victor", now=NOW), 400, "validation")
    c = claim(app, 79)
    assert c["category"] == "travel" and c["amount"] == 553.87 and c["description"] == "Team dinner"


def test_submit_refused_above_current_maximum():
    app = fresh_app()
    assert app.patch("/api/claims/79", {"incurred_on": "2026-02-27"}, user="victor", now=NOW).status == 200
    assert_error(app.post("/api/claims/79/submit", {}, user="victor", now=NOW), 409, "conflict")
    assert claim(app, 79)["status"] == "draft"
    # 403 before 409
    assert_error(app.post("/api/claims/79/submit", {}, user="omar", now=NOW), 403, "forbidden")
    r = app.patch("/api/category_policies/2", {"max_amount": 600}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert r.json["max_amount"] == 600 and r.json["category"] == "meals" and r.json["submit_within_days"] == 30
    r = app.post("/api/claims/79/submit", {}, user="victor", now=NOW)
    assert r.status == 200 and r.json["status"] == "submitted"
    # lowering a maximum blocks submission of an existing draft
    r = new_claim(app, "sam", 300, "meals", "2026-02-28")
    assert r.status == 201
    cid = r.json["id"]
    assert app.patch("/api/category_policies/2", {"max_amount": 250}, user="fiona", now=NOW).status == 200
    assert_error(app.post(f"/api/claims/{cid}/submit", {}, user="sam", now=NOW), 409, "conflict")


def test_submit_deadline_per_category():
    app = fresh_app()
    assert app.patch("/api/claims/20", {"incurred_on": "2026-01-01"}, user="sam", now=NOW).status == 200
    # travel: 60 days. 2026-01-01 -> 2026-03-02 is 60 days (allowed), 2026-03-03 is 61 (late)
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now="2026-03-03T08:00:00"), 409, "conflict")
    assert claim(app, 20)["status"] == "draft"
    r = app.post("/api/claims/20/submit", {}, user="sam", now="2026-03-02T23:59:59")
    assert r.status == 200 and r.json["submitted_at"] == "2026-03-02T23:59:59"
    # meals: 30 days
    late = new_claim(app, "sam", 50, "meals", "2026-01-29").json["id"]
    ok = new_claim(app, "sam", 50, "meals", "2026-01-30").json["id"]
    assert_error(app.post(f"/api/claims/{late}/submit", {}, user="sam", now=NOW), 409, "conflict")
    assert app.post(f"/api/claims/{ok}/submit", {}, user="sam", now=NOW).status == 200
    # the deadline follows the current policy
    assert app.patch("/api/category_policies/2", {"submit_within_days": 31}, user="fiona", now=NOW).status == 200
    assert app.post(f"/api/claims/{late}/submit", {}, user="sam", now=NOW).status == 200
    # a missing incurred_on is still 409 (F01)
    assert_error(app.post("/api/claims/8/submit", {}, user="tariq", now=NOW), 409, "conflict")


def test_only_finance_writes_policies():
    app = fresh_app()
    body = {"category": "training", "max_amount": 750, "submit_within_days": 45}
    for user in ("sam", "omar", "marco"):
        assert_error(app.post("/api/category_policies", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/category_policies", {}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/category_policies/2", {"max_amount": 9000}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/category_policies/2", {"max_amount": -1}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/category_policies/2", user=user, now=NOW), 403, "forbidden")
    assert app.get("/api/category_policies/2", user="sam", now=NOW).json["max_amount"] == 400
    assert ids(app.get("/api/category_policies", user="sam", now=NOW)) == [1, 2, 3, 4, 5]


def test_finance_creates_policy_and_new_category_is_usable():
    app = fresh_app()
    r = app.post("/api/category_policies", {"category": "training", "max_amount": 750, "submit_within_days": 45},
                 user="fiona", now=NOW)
    assert r.status == 201, r
    pid = r.json["id"]
    assert pid not in (1, 2, 3, 4, 5)
    assert r.json["category"] == "training" and r.json["max_amount"] == 750 and r.json["submit_within_days"] == 45
    r = new_claim(app, "priya", 700, "training", "2026-02-20")
    assert r.status == 201 and r.json["category"] == "training"
    cid = r.json["id"]
    assert_error(new_claim(app, "priya", 750.01, "training"), 400, "validation")
    assert app.post(f"/api/claims/{cid}/submit", {}, user="priya", now=NOW).status == 200
    assert app.post(f"/api/claims/{cid}/approve", {}, user="omar", now=NOW).status == 200
    assert ids(app.get("/api/claims?category=training", user="fiona", now=NOW)) == [cid]


def test_policy_validation():
    app = fresh_app()
    full = {"category": "training", "max_amount": 750, "submit_within_days": 45}
    for missing in ("category", "max_amount", "submit_within_days"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/category_policies", body, user="fiona", now=NOW), 400, "validation")
    for bad in ({"category": "meals"}, {"category": ""}, {"max_amount": 0}, {"max_amount": -5},
                {"max_amount": "750"}, {"max_amount": True}, {"submit_within_days": 0}, {"submit_within_days": 1.5},
                {"submit_within_days": "30"}, {"submit_within_days": True}, {"colour": "red"}):
        assert_error(app.post("/api/category_policies", dict(full, **bad), user="fiona", now=NOW), 400, "validation")
    for bad in ({"category": "food"}, {"max_amount": 0}, {"submit_within_days": 0}):
        assert_error(app.patch("/api/category_policies/2", bad, user="fiona", now=NOW), 400, "validation")
    p = app.get("/api/category_policies/2", user="fiona", now=NOW).json
    assert p["category"] == "meals" and p["max_amount"] == 400 and p["submit_within_days"] == 30
    assert ids(app.get("/api/category_policies", user="fiona", now=NOW)) == [1, 2, 3, 4, 5]


def test_policy_delete_rules():
    app = fresh_app()
    assert_error(app.delete("/api/category_policies/2", user="fiona", now=NOW), 409, "conflict")
    assert_error(app.delete("/api/category_policies/5", user="fiona", now=NOW), 409, "conflict")
    pid = app.post("/api/category_policies", {"category": "training", "max_amount": 750, "submit_within_days": 45},
                   user="fiona", now=NOW).json["id"]
    assert app.delete(f"/api/category_policies/{pid}", user="fiona", now=NOW).status == 204
    assert_error(app.get(f"/api/category_policies/{pid}", user="fiona", now=NOW), 404, "not_found")
    assert_error(new_claim(app, "priya", 10, "training"), 400, "validation")
    assert ids(app.get("/api/category_policies", user="fiona", now=NOW)) == [1, 2, 3, 4, 5]


def test_approval_and_payment_unaffected_by_maximums():
    app = fresh_app()
    # claim 2 (meals 734.81, submitted) is above the meals maximum but can still be approved
    r = app.post("/api/claims/2/approve", {}, user="omar", now=NOW)
    assert r.status == 200 and r.json["status"] == "approved"
    before = len(outbox(app))
    r = app.post("/api/claims/21/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["status"] == "paid"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": 21, "employee": 11, "amount": 1644.21}


def test_ui_policies():
    app = fresh_app()
    r = app.get("/ui/category_policies", user="sam", now=NOW)
    assert r.status == 200 and parse_ui(r.text).rows == [1, 2, 3, 4, 5]
    ui = parse_ui(app.get("/ui/category_policies/5", user="sam", now=NOW).text)
    assert ui.fields["category"] == "lodging" and ui.fields["submit_within_days"] == "60"
    assert "max_amount" in ui.fields
    r = app.get("/ui/category_policies/new", user="fiona", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["category_policies"]
    assert {"category", "max_amount", "submit_within_days"} <= set(ui.inputs)
    assert app.get("/ui/category_policies/new", user="sam", now=NOW).status == 403
    assert app.get("/ui/category_policies/new", user="omar", now=NOW).status == 403
    # the submit form follows the policy rules too
    assert app.patch("/api/claims/79", {"incurred_on": "2026-02-27"}, user="victor", now=NOW).status == 200
    assert "submit" not in parse_ui(app.get("/ui/claims/79", user="victor", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/claims/7", user="yusuf", now=NOW).text)
    assert ui.fields["category"] == "lodging"
