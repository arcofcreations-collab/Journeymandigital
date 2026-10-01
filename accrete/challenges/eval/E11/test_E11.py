"""Hidden acceptance tests for E11 (expenses): cost centres with budgets.

Cost centres from the brief: 1 ENG (Engineering, 31000.00), 2 SAL (Sales, 12000.00), 3 FIN (Finance, 2000.00),
4 TRV (no department, 5000.00).
Computed from spec/apps/expenses_seed.json (approved + paid amounts per department):
  Engineering 28886.18 -> remaining 2113.82; Sales 10750.94 -> remaining 1249.06.
  Sales claims (rosa 7, uma 10, xena 13): 4 9 13 16 26 27 30 32 37 38 39 47 57 58 62 63 65 67 69 70 72 76 77 78;
  every other claim is Engineering. Submitted: 58 (rosa 1118.43), 62 (xena 293.2), 72 (rosa 1646.02),
  43 (omar 1663.17, approver marco), 2 (victor 734.81, approver omar), 40 (yusuf 201.82, approver omar).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

SALES = [4, 9, 13, 16, 26, 27, 30, 32, 37, 38, 39, 47, 57, 58, 62, 63, 65, 67, 69, 70, 72, 76, 77, 78]
ENG = [i for i in range(1, 81) if i not in SALES]


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


def cc(app, cid, user="sam"):
    r = app.get(f"/api/cost_centres/{cid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def approve(app, cid, user):
    return app.post(f"/api/claims/{cid}/approve", {}, user=user, now=NOW)


def test_cost_centres_seeded():
    app = fresh_app()
    for user in ("sam", "marco", "fiona"):
        assert ids(app.get("/api/cost_centres", user=user, now=NOW)) == [1, 2, 3, 4]
    expected = {1: ("ENG", "Engineering", "Engineering", 31000, 28886.18, 2113.82),
                2: ("SAL", "Sales", "Sales", 12000, 10750.94, 1249.06),
                3: ("FIN", "Finance", "Finance", 2000, 0, 2000),
                4: ("TRV", "Travel pool", None, 5000, 0, 5000)}
    for cid, (code, name, dep, budget, committed, remaining) in expected.items():
        c = cc(app, cid)
        assert (c["code"], c["name"], c["department"]) == (code, name, dep), c
        assert c["budget"] == budget
        assert round(c["committed"], 2) == committed and round(c["remaining"], 2) == remaining, c


def test_claims_migrated_to_department_centre():
    app = fresh_app()
    claims = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    got = {c["id"]: c["cost_centre"] for c in claims}
    for cid in SALES:
        assert got[cid] == 2, cid
    for cid in ENG:
        assert got[cid] == 1, cid
    assert ids(app.get("/api/claims?cost_centre=2", user="fiona", now=NOW)) == SALES
    assert ids(app.get("/api/claims?cost_centre=4", user="fiona", now=NOW)) == []
    c = app.get("/api/claims/7", user="yusuf", now=NOW).json
    assert (c["amount"], c["status"], c["decided_by"], c["cost_centre"]) == (613.88, "rejected", 4, 1)


def test_approval_respects_budget_sales():
    app = fresh_app()
    r = approve(app, 58, "nadia")
    assert r.status == 200 and r.json["status"] == "approved"
    c = cc(app, 2)
    assert round(c["committed"], 2) == 11869.37 and round(c["remaining"], 2) == 130.63
    assert_error(approve(app, 62, "nadia"), 409, "conflict")              # 293.20 > 130.63
    c62 = app.get("/api/claims/62", user="fiona", now=NOW).json
    assert c62["status"] == "submitted" and c62["decided_by"] is None
    assert "approve" not in parse_ui(app.get("/ui/claims/62", user="nadia", now=NOW).text).actions
    assert "reject" in parse_ui(app.get("/ui/claims/62", user="nadia", now=NOW).text).actions
    r = app.post("/api/claims/62/reject", {"reason": "Budget exhausted"}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["status"] == "rejected"
    assert round(cc(app, 2)["committed"], 2) == 11869.37


def test_approval_respects_budget_engineering():
    app = fresh_app()
    assert_error(approve(app, 2, "marco"), 403, "forbidden")             # 403 before any 409
    r = approve(app, 43, "marco")
    assert r.status == 200
    assert round(cc(app, 1)["remaining"], 2) == 450.65
    assert_error(approve(app, 2, "omar"), 409, "conflict")               # 734.81 > 450.65
    assert approve(app, 40, "omar").status == 200                         # 201.82 fits
    assert round(cc(app, 1)["remaining"], 2) == 248.83
    assert app.get("/api/claims/2", user="fiona", now=NOW).json["status"] == "submitted"
    assert_error(approve(app, 22, "omar"), 409, "conflict")              # wrong state stays 409


def test_payment_payload_and_committed():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["status"] == "paid" and r.json["cost_centre"] == 1
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["payment"]
    assert msgs[0]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12, "cost_centre": 1}
    assert round(cc(app, 1)["committed"], 2) == 28886.18          # approved -> paid: unchanged


def test_claim_cost_centre_on_create_and_patch():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 50, "category": "meals", "description": "Lunch"}, user="priya", now=NOW)
    assert r.status == 201 and r.json["cost_centre"] == 1
    r = app.post("/api/claims", {"amount": 50, "category": "meals", "description": "Lunch"}, user="rosa", now=NOW)
    assert r.status == 201 and r.json["cost_centre"] == 2
    r = app.post("/api/claims", {"amount": 80, "category": "other", "description": "Books"}, user="fiona", now=NOW)
    assert r.status == 201 and r.json["cost_centre"] == 3
    r = app.post("/api/claims", {"amount": 300, "category": "travel", "description": "Train", "cost_centre": 4},
                 user="rosa", now=NOW)
    assert r.status == 201 and r.json["cost_centre"] == 4
    for bad in (999, "TRV", None):
        assert_error(app.post("/api/claims", {"amount": 5, "category": "meals", "description": "x", "cost_centre": bad},
                              user="sam", now=NOW), 400, "validation")
    r = app.patch("/api/claims/20", {"cost_centre": 4}, user="sam", now=NOW)
    assert r.status == 200 and r.json["cost_centre"] == 4
    assert_error(app.patch("/api/claims/20", {"cost_centre": 999}, user="sam", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claims/22", {"cost_centre": 4}, user="sam", now=NOW), 409, "conflict")
    assert_error(app.patch("/api/claims/20", {"cost_centre": 2}, user="omar", now=NOW), 403, "forbidden")
    assert app.post("/api/claims/20/submit", {}, user="sam", now=NOW).status == 200
    assert approve(app, 20, "omar").status == 200                  # 1553.42 against TRV
    assert round(cc(app, 4)["committed"], 2) == 1553.42
    assert round(cc(app, 1)["committed"], 2) == 28886.18


def test_cost_centre_writes():
    app = fresh_app()
    body = {"code": "MKT", "name": "Marketing", "budget": 1000}
    for user in ("sam", "marco"):
        assert_error(app.post("/api/cost_centres", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/cost_centres", {}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/cost_centres/2", {"budget": 99999}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/cost_centres/4", user=user, now=NOW), 403, "forbidden")
    for bad in ({"code": "ENG"}, {"department": "Sales"}, {"budget": -1}, {"budget": "1000"}, {"code": ""},
                {"committed": 0}, {"remaining": 5}):
        assert_error(app.post("/api/cost_centres", dict(body, **bad), user="fiona", now=NOW), 400, "validation")
    for missing in ("code", "name", "budget"):
        b = {k: v for k, v in body.items() if k != missing}
        assert_error(app.post("/api/cost_centres", b, user="fiona", now=NOW), 400, "validation")
    r = app.post("/api/cost_centres", body, user="fiona", now=NOW)
    assert r.status == 201, r
    new = r.json
    assert new["id"] > 4 and new["department"] is None and new["committed"] == 0 and new["remaining"] == 1000
    assert_error(app.patch("/api/cost_centres/1", {"budget": 20000}, user="fiona", now=NOW), 409, "conflict")
    assert_error(app.delete("/api/cost_centres/2", user="fiona", now=NOW), 409, "conflict")
    assert app.delete(f"/api/cost_centres/{new['id']}", user="fiona", now=NOW).status == 204
    assert app.delete("/api/cost_centres/4", user="fiona", now=NOW).status == 204
    assert cc(app, 1)["budget"] == 31000


def test_budget_change_unblocks_approval():
    app = fresh_app()
    assert_error(approve(app, 72, "nadia"), 409, "conflict")       # 1646.02 > 1249.06
    r = app.patch("/api/cost_centres/2", {"budget": 13000}, user="fiona", now=NOW)
    assert r.status == 200 and round(r.json["remaining"], 2) == 2249.06
    assert approve(app, 72, "nadia").status == 200
    assert round(cc(app, 2)["committed"], 2) == 12396.96
    # lowering exactly to the committed amount is allowed
    r = app.patch("/api/cost_centres/2", {"budget": 12396.96}, user="fiona", now=NOW)
    assert r.status == 200 and round(r.json["remaining"], 2) == 0
    assert_error(approve(app, 62, "nadia"), 409, "conflict")


def test_ui_cost_centres():
    app = fresh_app()
    assert parse_ui(app.get("/ui/cost_centres", user="sam", now=NOW).text).rows == [1, 2, 3, 4]
    ui = parse_ui(app.get("/ui/cost_centres/4", user="sam", now=NOW).text)
    assert ui.fields["code"] == "TRV" and ui.fields["name"] == "Travel pool"
    assert app.get("/ui/cost_centres/new", user="sam", now=NOW).status == 403
    r = app.get("/ui/cost_centres/new", user="fiona", now=NOW)
    assert r.status == 200 and {"code", "name", "department", "budget"} <= set(parse_ui(r.text).inputs)
    ui = parse_ui(app.get("/ui/claims/new", user="sam", now=NOW).text)
    assert {"amount", "category", "description", "cost_centre"} <= set(ui.inputs)
    assert "approve" in parse_ui(app.get("/ui/claims/58", user="nadia", now=NOW).text).actions
    assert "approve" not in parse_ui(app.get("/ui/claims/72", user="nadia", now=NOW).text).actions
