"""Hidden acceptance tests for F11 (library): annual memberships with an expiry date.

Seed facts (computed from spec/apps/library_seed.json; member_until = date of the member's
earliest borrowed_at + 365 days, null for librarians and for members without loans):
  1 ada null | 2 ben null | 3 chen 2026-10-27 | 4 dara 2026-09-02 | 5 eli 2026-09-07 | 6 fatima 2026-09-19
  7 gus 2026-11-15 | 8 hana 2026-09-05 | 9 ivan 2026-09-10 | 10 jo 2026-09-18 | 11 kemal 2026-09-02 | 12 lena null
  dara has one open loan (59), chen one (52); books 3, 13, 14 have no loans.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
UNTIL = {1: None, 2: None, 3: "2026-10-27", 4: "2026-09-02", 5: "2026-09-07", 6: "2026-09-19",
         7: "2026-11-15", 8: "2026-09-05", 9: "2026-09-10", 10: "2026-09-18", 11: "2026-09-02", 12: None}


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def member(app, mid):
    r = app.get(f"/api/members/{mid}", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json


def test_membership_dates_migrated():
    app = fresh_app()
    items = app.get("/api/members", user="ada", now=NOW).json["items"]
    assert {m["id"]: m["member_until"] for m in items} == UNTIL
    m = app.get("/api/members/3", user="chen", now=NOW).json
    assert m["member_until"] == "2026-10-27" and m["name"] == "Chen Li" and m["active"] is True
    assert ids(app.get("/api/members?member_until=2026-09-02", user="ada", now=NOW)) == [4, 11]
    assert ids(app.get("/api/members?member_until=null", user="ben", now=NOW)) == [1, 2, 12]


def test_expired_member_cannot_borrow():
    app = fresh_app()
    before = outbox(app)
    # valid through 2026-09-02 inclusive
    assert_error(app.post("/api/books/3/borrow", {}, user="dara", now="2026-09-03T00:00:00"), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="ada", now="2026-09-03T00:00:00"), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {}, user="kemal", now="2026-12-01T10:00:00"), 409, "conflict")
    assert outbox(app) == before
    assert app.get("/api/books/3", user="ada", now=NOW).json["status"] == "available"
    r = app.post("/api/books/3/borrow", {}, user="dara", now="2026-09-02T23:00:00")
    assert r.status == 200 and r.json["status"] == "on_loan"
    r = app.post("/api/books/13/borrow", {}, user="chen", now="2026-09-03T00:00:00")
    assert r.status == 200


def test_expired_member_can_still_return_and_read():
    app = fresh_app()
    later = "2026-09-10T10:00:00"
    r = app.post("/api/loans/59/return", {}, user="dara", now=later)
    assert r.status == 200 and r.json["returned_at"] == later
    assert ids(app.get("/api/loans", user="dara", now=later)) == [1, 23, 26, 29, 41, 59]
    r = app.patch("/api/members/4", {"name": "Dara N."}, user="dara", now=later)
    assert r.status == 200 and r.json["name"] == "Dara N." and r.json["member_until"] == "2026-09-02"


def test_extend_membership():
    app = fresh_app()
    later = "2026-09-10T10:00:00"
    before = len(outbox(app))
    r = app.post("/api/members/4/extend", {}, user="ada", now=later)
    assert r.status == 200, r
    assert r.json["id"] == 4 and r.json["member_until"] == "2027-09-10" and r.json["username"] == "dara"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "membership_extended"
    assert msgs[-1]["payload"] == {"member": 4, "member_until": "2027-09-10"}
    assert app.post("/api/books/3/borrow", {}, user="dara", now=later).status == 200
    # not yet expired: extended from the current end date
    r = app.post("/api/members/3/extend", {}, user="ben", now=NOW)
    assert r.status == 200 and r.json["member_until"] == "2027-10-27"
    r = app.post("/api/members/3/extend", {}, user="ben", now=NOW)
    assert r.status == 200 and r.json["member_until"] == "2028-10-26"


def test_extend_refusals():
    app = fresh_app()
    before = outbox(app)
    assert_error(app.post("/api/members/3/extend", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/members/1/extend", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/members/1/extend", {}, user="ada", now=NOW), 409, "conflict")   # no expiry
    assert_error(app.post("/api/members/12/extend", {}, user="ada", now=NOW), 409, "conflict")  # inactive
    assert app.patch("/api/members/5", {"active": False}, user="ada", now=NOW).status == 200
    assert_error(app.post("/api/members/5/extend", {}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/members/99/extend", {}, user="ada", now=NOW), 404, "not_found")
    assert outbox(app) == before
    assert member(app, 5)["member_until"] == "2026-09-07"
    assert member(app, 3)["member_until"] == "2026-10-27"


def test_librarian_sets_member_until():
    app = fresh_app()
    r = app.patch("/api/members/4", {"member_until": "2026-12-31"}, user="ada", now=NOW)
    assert r.status == 200 and r.json["member_until"] == "2026-12-31"
    assert app.post("/api/books/3/borrow", {}, user="dara", now="2026-12-31T20:00:00").status == 200
    r = app.patch("/api/members/11", {"member_until": None}, user="ben", now=NOW)
    assert r.status == 200 and r.json["member_until"] is None
    assert app.post("/api/books/13/borrow", {}, user="kemal", now="2030-01-01T10:00:00").status == 200
    for bad in ("2026-02-30", "soon", 20261231, "31/12/2026"):
        assert_error(app.patch("/api/members/6", {"member_until": bad}, user="ada", now=NOW), 400, "validation")
    assert member(app, 6)["member_until"] == "2026-09-19"


def test_members_cannot_change_their_expiry():
    app = fresh_app()
    for body in ({"member_until": "2030-01-01"}, {"name": "Chen", "member_until": None}):
        assert_error(app.patch("/api/members/3", body, user="chen", now=NOW), 403, "forbidden")
    m = member(app, 3)
    assert m["member_until"] == "2026-10-27" and m["name"] == "Chen Li"


def test_create_member_with_and_without_expiry():
    app = fresh_app()
    r = app.post("/api/members", {"username": "zed", "name": "Zed Zed", "role": "member", "member_until": "2027-03-01"},
                 user="ada", now=NOW)
    assert r.status == 201 and r.json["member_until"] == "2027-03-01" and r.json["active"] is True
    r = app.post("/api/members", {"username": "yan", "name": "Yan", "role": "member"}, user="ada", now=NOW)
    assert r.status == 201 and r.json["member_until"] is None
    assert_error(app.post("/api/members", {"username": "xo", "name": "Xo", "role": "member", "member_until": "never"},
                          user="ada", now=NOW), 400, "validation")


def test_ui_membership():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/members/4", user="ada", now=NOW).text)
    assert ui.fields["member_until"] == "2026-09-02"
    assert "extend" in ui.actions
    ui = parse_ui(app.get("/ui/members/3", user="chen", now=NOW).text)
    assert ui.fields["member_until"] == "2026-10-27" and "extend" not in ui.actions
    assert "extend" not in parse_ui(app.get("/ui/members/1", user="ada", now=NOW).text).actions
    assert "extend" not in parse_ui(app.get("/ui/members/12", user="ada", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/members/new", user="ada", now=NOW).text)
    assert {"username", "name", "role", "member_until"} <= set(ui.inputs)


def test_borrow_rules_unchanged_today():
    app = fresh_app()
    assert app.post("/api/books/3/borrow", {}, user="chen", now=NOW).status == 200
    assert_error(app.post("/api/books/13/borrow", {}, user="hana", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/13/borrow", {"member": 12}, user="ada", now=NOW), 409, "conflict")
