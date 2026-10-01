"""Members: visibility, librarian-only management, self-service name changes, validation."""


def test_member_sees_only_own_record(app):
    r = app.get("/api/members", user="chen")
    assert [m["id"] for m in r.json["items"]] == [3]
    assert app.get("/api/members/3", user="chen").json["username"] == "chen"
    assert app.get("/api/members/4", user="chen").status == 403


def test_librarian_sees_everyone(app):
    assert len(app.get("/api/members", user="ada").json["items"]) == 12
    assert app.get("/api/members/12", user="ada").json["active"] is False


def test_librarian_creates_member_with_default_active(app):
    r = app.post("/api/members", {"username": "zed", "name": "Zed Z", "role": "member"}, user="ada")
    assert r.status == 201
    assert r.json == {"id": 13, "username": "zed", "name": "Zed Z", "role": "member", "active": True}
    assert app.get("/api/members/13", user="ben").json["username"] == "zed"
    assert app.get("/api/members", user="zed").json["items"][0]["id"] == 13


def test_member_cannot_create_members(app):
    assert app.post("/api/members", {"username": "x", "name": "X", "role": "member"}, user="chen").status == 403
    # 403 wins over 400
    assert app.post("/api/members", {}, user="chen").status == 403


def test_member_validation(app):
    r = app.post("/api/members", {"name": "No Username"}, user="ada")
    assert r.status == 400 and set(r.json["fields"]) == {"username", "role"}
    assert app.post("/api/members", {"username": "chen", "name": "C", "role": "member"}, user="ada").status == 400
    assert app.post("/api/members", {"username": "q", "name": "Q", "role": "admin"}, user="ada").status == 400
    assert app.post("/api/members", {"username": "q", "name": "Q", "role": "member", "active": "yes"}, user="ada").status == 400
    assert app.post("/api/members", {"username": "", "name": "Q", "role": "member"}, user="ada").status == 400


def test_member_updates_own_name_only(app):
    r = app.patch("/api/members/3", {"name": "Chen Q. Li"}, user="chen")
    assert r.status == 200 and r.json["name"] == "Chen Q. Li" and r.json["role"] == "member"
    assert app.patch("/api/members/3", {"role": "librarian"}, user="chen").status == 403
    assert app.patch("/api/members/3", {"name": "x", "active": False}, user="chen").status == 403
    assert app.patch("/api/members/4", {"name": "Dara"}, user="chen").status == 403
    assert app.patch("/api/members/3", {"name": ""}, user="chen").status == 400


def test_librarian_updates_any_field(app):
    r = app.patch("/api/members/4", {"role": "librarian", "active": False}, user="ada")
    assert r.status == 200 and r.json["role"] == "librarian" and r.json["active"] is False
    assert app.patch("/api/members/4", {"username": "chen"}, user="ada").status == 400
    assert app.patch("/api/members/4", {"username": "dara"}, user="ada").status == 200  # unchanged is fine
    assert app.patch("/api/members/99", {"name": "x"}, user="ada").status == 404


def test_404_beats_403_for_members(app):
    assert app.patch("/api/members/99", {"role": "librarian"}, user="chen").status == 404
    assert app.delete("/api/members/99", user="chen").status == 404


def test_delete_member(app):
    assert app.delete("/api/members/3", user="chen").status == 403
    assert app.delete("/api/members/3", user="ada").status == 409  # has loans
    created = app.post("/api/members", {"username": "tmp", "name": "Tmp", "role": "member"}, user="ada").json
    assert app.delete(f"/api/members/{created['id']}", user="ada").status == 204
    assert app.get(f"/api/members/{created['id']}", user="ada").status == 404
