"""Employees: readable by everyone, managed by finance only."""

NEW = {"username": "ann", "name": "Ann Lee", "role": "employee", "manager": 3, "department": "Sales"}


def test_everyone_reads_employees(app):
    assert len(app.get("/api/employees", user="priya").json["items"]) == 15
    assert app.get("/api/employees/2", user="priya").json["username"] == "marco"


def test_finance_creates_employee(app):
    r = app.post("/api/employees", NEW, user="fiona")
    assert r.status == 201 and r.json == {"id": 16, **NEW}
    no_manager = dict(NEW, username="bo")
    del no_manager["manager"]
    assert app.post("/api/employees", no_manager, user="fiona").json["manager"] is None
    assert app.get("/api/claims", user="ann").json == {"items": []}  # new user can authenticate


def test_only_finance_manages_employees(app):
    assert app.post("/api/employees", NEW, user="marco").status == 403
    assert app.post("/api/employees", {}, user="marco").status == 403  # 403 beats 400
    assert app.patch("/api/employees/5", {"name": "P"}, user="omar").status == 403
    assert app.delete("/api/employees/5", user="priya").status == 403
    assert app.patch("/api/employees/99", {"name": "P"}, user="omar").status == 404  # 404 beats 403


def test_employee_validation(app):
    r = app.post("/api/employees", {"name": "X"}, user="fiona")
    assert r.status == 400 and set(r.json["fields"]) == {"username", "role", "department"}
    assert app.post("/api/employees", dict(NEW, username="priya"), user="fiona").json["fields"] == {"username": "already in use"}
    assert app.post("/api/employees", dict(NEW, role="boss"), user="fiona").status == 400
    assert app.post("/api/employees", dict(NEW, manager=99), user="fiona").status == 400
    assert app.post("/api/employees", dict(NEW, manager="marco"), user="fiona").status == 400


def test_finance_updates_employee(app):
    r = app.patch("/api/employees/5", {"manager": 2, "department": "Platform"}, user="fiona")
    assert r.status == 200 and r.json["manager"] == 2 and r.json["department"] == "Platform"
    assert app.patch("/api/employees/5", {"manager": None}, user="fiona").json["manager"] is None
    assert app.patch("/api/employees/5", {"manager": 5}, user="fiona").status == 400  # self
    assert app.patch("/api/employees/2", {"manager": 5}, user="fiona").status == 200
    assert app.patch("/api/employees/4", {"manager": 5}, user="fiona").status == 200
    assert app.patch("/api/employees/5", {"manager": 4}, user="fiona").status == 400  # 4 reports to 5: loop
    assert app.patch("/api/employees/5", {"username": "sam"}, user="fiona").status == 400


def test_delete_employee(app):
    assert app.delete("/api/employees/5", user="fiona").status == 409  # has claims
    assert app.delete("/api/employees/3", user="fiona").status == 409  # has reports
    created = app.post("/api/employees", NEW, user="fiona").json
    assert app.delete(f"/api/employees/{created['id']}", user="fiona").status == 204
    assert app.get(f"/api/employees/{created['id']}", user="fiona").status == 404
