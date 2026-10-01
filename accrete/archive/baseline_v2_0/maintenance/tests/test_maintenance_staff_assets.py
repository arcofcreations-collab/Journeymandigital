"""Staff and assets: supervisor-only writes, validation, uniqueness, delete and retire rules."""

NEW_STAFF = {"username": "ada", "name": "Ada Byrne", "role": "technician", "site": "East"}
NEW_ASSET = {"tag": "E-CMP-01", "name": "Compressor East", "site": "East", "criticality": "medium"}


# --- staff ----------------------------------------------------------------------------

def test_everyone_reads_all_staff(app):
    for user in ("ruth", "nils", "tomas"):
        assert [s["id"] for s in app.get("/api/staff", user=user).json["items"]] == list(range(1, 17))
    assert app.get("/api/staff/16", user="mei").json == {
        "id": 16, "username": "yara", "name": "Yara Haddad", "role": "supervisor", "site": "East", "active": True
    }


def test_create_staff(app):
    r = app.post("/api/staff", NEW_STAFF, user="yara")
    assert r.status == 201
    assert r.json == {"id": 17, **NEW_STAFF, "active": True}
    # New staff are valid identities immediately.
    assert app.get("/api/staff/17", user="ada").status == 200
    inactive = app.post("/api/staff", {**NEW_STAFF, "username": "bea", "active": False}, user="yara")
    assert inactive.status == 201 and inactive.json["active"] is False


def test_only_supervisors_manage_staff(app):
    for user in ("ruth", "nils"):
        assert app.post("/api/staff", NEW_STAFF, user=user).status == 403
        assert app.post("/api/staff", {"bogus": 1}, user=user).status == 403  # 403 beats 400
        assert app.patch("/api/staff/3", {"name": "R"}, user=user).status == 403
        assert app.delete("/api/staff/3", user=user).status == 403


def test_staff_validation(app):
    def create(**changes):
        return app.post("/api/staff", {**NEW_STAFF, **changes}, user="sofia")

    assert create(username="ruth").status == 400  # duplicate
    assert create(username="   ").status == 400
    assert create(name=None).status == 400
    assert create(role="manager").status == 400
    assert create(active="yes").status == 400
    assert create(active=None).status == 400
    assert create(id=99).status == 400
    assert create(colour="red").status == 400
    body = dict(NEW_STAFF)
    del body["site"]
    assert app.post("/api/staff", body, user="sofia").status == 400
    assert app.post("/api/staff", [1, 2], user="sofia").status == 400
    assert app.get("/api/staff?username=ada", user="sofia").json["items"] == []  # nothing created


def test_update_staff(app):
    r = app.patch("/api/staff/7", {"site": "North", "active": False}, user="tomas")
    assert r.status == 200 and (r.json["site"], r.json["active"]) == ("North", False)
    assert app.patch("/api/staff/7", {"username": "mei"}, user="tomas").status == 200  # own name is fine
    assert app.patch("/api/staff/7", {"username": "ruth"}, user="tomas").status == 400
    assert app.patch("/api/staff/7", {"role": "boss"}, user="tomas").status == 400
    assert app.patch("/api/staff/7", {"id": 7}, user="tomas").status == 400


def test_delete_staff(app):
    assert app.delete("/api/staff/3", user="sofia").status == 409  # requested orders
    assert app.delete("/api/staff/15", user="sofia").status == 409  # assigned to order 80
    new_id = app.post("/api/staff", NEW_STAFF, user="sofia").json["id"]
    assert app.delete(f"/api/staff/{new_id}", user="sofia").status == 204
    assert app.get(f"/api/staff/{new_id}", user="sofia").status == 404
    assert app.get("/api/staff", user="ada").status == 401


# --- assets ---------------------------------------------------------------------------

def test_assets_have_open_orders(app):
    assert app.get("/api/assets/16", user="mei").json == {
        "id": 16, "tag": "S-CNV-01", "name": "Conveyor line A", "site": "South", "criticality": "high",
        "retired": False, "open_orders": 2,
    }
    assert app.get("/api/assets/7", user="mei").json["open_orders"] == 0  # only finished orders


def test_open_orders_follow_work_orders(app):
    order = app.post("/api/work_orders", {"asset": 31, "title": "Test", "priority": "low"}, user="yara").json
    assert app.get("/api/assets/31", user="yara").json["open_orders"] == 1
    app.post(f"/api/work_orders/{order['id']}/cancel", {"reason": "dup"}, user="yara")
    assert app.get("/api/assets/31", user="yara").json["open_orders"] == 0


def test_create_asset(app):
    r = app.post("/api/assets", NEW_ASSET, user="sofia")
    assert r.status == 201 and r.json == {"id": 32, **NEW_ASSET, "retired": False, "open_orders": 0}
    assert app.post("/api/assets", {**NEW_ASSET, "tag": "X-1", "retired": True}, user="sofia").json["retired"] is True


def test_only_supervisors_manage_assets(app):
    for user in ("ruth", "nils"):
        assert app.post("/api/assets", NEW_ASSET, user=user).status == 403
        assert app.patch("/api/assets/31", {"name": "x"}, user=user).status == 403
        assert app.patch("/api/assets/1", {"retired": True}, user=user).status == 403  # 403 beats 409
        assert app.delete("/api/assets/31", user=user).status == 403


def test_asset_validation(app):
    def create(**changes):
        return app.post("/api/assets", {**NEW_ASSET, **changes}, user="sofia")

    assert create(tag="N-AHU-01").status == 400
    assert create(criticality="extreme").status == 400
    assert create(retired=1).status == 400
    assert create(open_orders=0).status == 400
    assert create(site="").status == 400
    assert app.patch("/api/assets/2", {"tag": "N-AHU-01"}, user="sofia").status == 400
    assert app.patch("/api/assets/2", {"open_orders": 0}, user="sofia").status == 400


def test_retire_asset(app):
    assert app.patch("/api/assets/1", {"retired": True}, user="sofia").status == 409  # open order 74
    assert app.patch("/api/assets/1", {"retired": True, "colour": "x"}, user="sofia").status == 409  # 409 beats 400
    assert app.get("/api/assets/1", user="sofia").json["retired"] is False
    r = app.patch("/api/assets/31", {"retired": True}, user="sofia")
    assert r.status == 200 and r.json["retired"] is True
    r = app.patch("/api/assets/7", {"retired": False, "criticality": "low"}, user="sofia")
    assert r.status == 200 and (r.json["retired"], r.json["criticality"]) == (False, "low")


def test_delete_asset(app):
    assert app.delete("/api/assets/7", user="sofia").status == 409  # finished orders still count
    assert app.delete("/api/assets/24", user="sofia").status == 204
    assert app.get("/api/assets/24", user="sofia").status == 404
