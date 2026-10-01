"""Claims: creation, visibility, editing rules and validation."""

NEW = {"amount": 42.5, "category": "meals", "description": "Team lunch"}


def test_any_employee_creates_draft_claim_for_themselves(app):
    for user, employee_id in (("priya", 5), ("marco", 2), ("fiona", 1)):
        r = app.post("/api/claims", NEW, user=user)
        assert r.status == 201
        assert r.json == {"id": r.json["id"], **NEW, "employee": employee_id, "status": "draft",
                          "submitted_at": None, "decided_at": None, "decided_by": None, "rejection_reason": None}


def test_workflow_fields_cannot_be_set(app):
    for field, value in (("employee", 6), ("status", "approved"), ("submitted_at", "2026-01-01T00:00:00"),
                         ("decided_at", None), ("decided_by", 2), ("rejection_reason", "x")):
        r = app.post("/api/claims", dict(NEW, **{field: value}), user="priya")
        assert r.status == 400 and field in r.json["fields"], field
        assert app.patch("/api/claims/1", {field: value}, user="wen").status == 400


def test_claim_validation(app):
    assert app.post("/api/claims", dict(NEW, amount=0), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, amount=-5), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, amount=5000.01), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, amount="12"), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, amount=True), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, amount=5000), user="priya").status == 201
    assert app.post("/api/claims", dict(NEW, amount=0.01), user="priya").status == 201
    assert app.post("/api/claims", dict(NEW, category="fun"), user="priya").status == 400
    assert app.post("/api/claims", dict(NEW, description="  "), user="priya").status == 400
    r = app.post("/api/claims", {}, user="priya")
    assert r.status == 400 and set(r.json["fields"]) == {"amount", "category", "description"}


def test_claim_visibility(app):
    def ids(user):
        return {c["id"] for c in app.get("/api/claims", user=user).json["items"]}

    all_claims = app.get("/api/claims", user="fiona").json["items"]
    assert len(all_claims) == 80
    by_employee = lambda *emps: {c["id"] for c in all_claims if c["employee"] in emps}  # noqa: E731
    assert ids("priya") == by_employee(5)
    assert ids("omar") == by_employee(4, 5, 8, 11, 14)  # own + direct reports
    assert ids("marco") == by_employee(2, 4, 6, 9, 12, 15)  # not omar's reports
    assert app.get("/api/claims/2", user="omar").status == 200  # victor's claim, omar manages victor
    assert app.get("/api/claims/2", user="marco").status == 403  # indirect manager
    assert app.get("/api/claims/2", user="sam").status == 403
    assert app.get("/api/claims/2", user="victor").status == 200


def test_owner_edits_draft_claim(app):
    r = app.patch("/api/claims/1", {"amount": 99, "description": "Changed"}, user="wen")
    assert r.status == 200 and r.json["amount"] == 99 and r.json["description"] == "Changed"
    assert r.json["category"] == "other" and r.json["status"] == "draft"


def test_edit_rules(app):
    assert app.patch("/api/claims/1", {"amount": 1}, user="marco").status == 403  # manager, not owner
    assert app.patch("/api/claims/1", {"amount": 1}, user="fiona").status == 403
    assert app.patch("/api/claims/2", {"amount": 1}, user="victor").status == 409  # submitted
    assert app.patch("/api/claims/2", {"status": "draft"}, user="victor").status == 409  # 409 beats 400
    assert app.patch("/api/claims/1", {"amount": 6000}, user="wen").status == 400
    assert app.patch("/api/claims/999", {"amount": 1}, user="wen").status == 404


def test_delete_rules(app):
    assert app.delete("/api/claims/1", user="marco").status == 403
    assert app.delete("/api/claims/2", user="victor").status == 409
    assert app.delete("/api/claims/1", user="wen").status == 204
    assert app.get("/api/claims/1", user="wen").status == 404
