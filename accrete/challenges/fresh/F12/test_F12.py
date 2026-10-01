"""Hidden acceptance tests for F12 (library): members suggest purchases, librarians accept them into
the catalogue atomically or decline them.

Seed facts: the three suggestions from the brief (1 chen pending, 2 hana pending, 3 chen declined);
library_seed.json: books 1-40 (isbn of book 1: 978-0-1007-001-1); members chen 3, hana 8, gus 7,
librarians ada 1 and ben 2. Book 3 has no loans; chen has one open loan.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
SEEDED = [
    {"id": 1, "title": "Salt and Stars", "author": "N. Adeyemi", "isbn": "978-1-2000-001-5",
     "note": "For the book club", "suggested_by": 3, "created_at": "2026-02-10T10:00:00",
     "status": "pending", "book": None, "decline_reason": None},
    {"id": 2, "title": "The Quiet Engine", "author": "P. Varga", "isbn": "978-1-2000-002-2",
     "note": None, "suggested_by": 8, "created_at": "2026-02-12T15:30:00",
     "status": "pending", "book": None, "decline_reason": None},
    {"id": 3, "title": "Old Maps", "author": "R. Ito", "isbn": "978-1-2000-003-9",
     "note": None, "suggested_by": 3, "created_at": "2026-01-20T09:00:00",
     "status": "declined", "book": None, "decline_reason": "Out of print"},
]


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


def sug(app, sid):
    r = app.get(f"/api/suggestions/{sid}", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json


def snapshot(app):
    return (app.get("/api/books", user="ada", now=NOW).json["items"],
            app.get("/api/suggestions", user="ada", now=NOW).json["items"], outbox(app))


def test_seeded_suggestions_and_read_rules():
    app = fresh_app()
    for user in ("ada", "ben"):
        items = app.get("/api/suggestions", user=user, now=NOW).json["items"]
        assert [s["id"] for s in items] == [1, 2, 3]
        for got, exp in zip(items, SEEDED):
            for k, v in exp.items():
                assert got[k] == v, (exp["id"], k, got.get(k))
    assert ids(app.get("/api/suggestions", user="chen", now=NOW)) == [1, 3]
    assert ids(app.get("/api/suggestions", user="hana", now=NOW)) == [2]
    assert ids(app.get("/api/suggestions", user="gus", now=NOW)) == []
    assert ids(app.get("/api/suggestions?status=pending", user="chen", now=NOW)) == [1]
    assert_error(app.get("/api/suggestions/2", user="chen", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/suggestions/99", user="chen", now=NOW), 404, "not_found")
    assert_error(app.get("/api/suggestions", user=None, now=NOW), 401, "unauthenticated")


def test_member_creates_suggestion():
    app = fresh_app()
    r = app.post("/api/suggestions", {"title": "River Tales", "author": "M. Okafor", "isbn": "978-1-2000-010-1"},
                 user="gus", now="2026-03-02T09:15:00")
    assert r.status == 201, r
    s = r.json
    assert s["id"] not in (1, 2, 3)
    expected = {"title": "River Tales", "author": "M. Okafor", "isbn": "978-1-2000-010-1", "note": None,
                "suggested_by": 7, "created_at": "2026-03-02T09:15:00", "status": "pending", "book": None,
                "decline_reason": None}
    for k, v in expected.items():
        assert s[k] == v, (k, s.get(k))
    assert ids(app.get("/api/suggestions", user="gus", now=NOW)) == [s["id"]]
    assert_error(app.get(f"/api/suggestions/{s['id']}", user="chen", now=NOW), 403, "forbidden")
    r = app.post("/api/suggestions", {"title": "Index", "author": "B. Lee", "isbn": "isbn-idx", "note": "Staff pick"},
                 user="ada", now=NOW)
    assert r.status == 201 and r.json["suggested_by"] == 1 and r.json["note"] == "Staff pick"


def test_suggestion_validation():
    app = fresh_app()
    full = {"title": "River Tales", "author": "M. Okafor", "isbn": "978-1-2000-010-1"}
    for missing in ("title", "author", "isbn"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/suggestions", body, user="gus", now=NOW), 400, "validation")
    for bad in ({"isbn": "978-0-1007-001-1"}, {"isbn": "978-1-2000-001-5"}, {"title": "  "}, {"note": 5},
                {"status": "accepted"}, {"suggested_by": 7}, {"book": 1}):
        assert_error(app.post("/api/suggestions", dict(full, **bad), user="gus", now=NOW), 400, "validation")
    assert ids(app.get("/api/suggestions", user="ada", now=NOW)) == [1, 2, 3]
    # the isbn of a declined suggestion may be suggested again
    r = app.post("/api/suggestions", dict(full, isbn="978-1-2000-003-9"), user="gus", now=NOW)
    assert r.status == 201


def test_suggester_edits_and_withdraws_pending_suggestion():
    app = fresh_app()
    r = app.patch("/api/suggestions/1", {"note": "Two copies please"}, user="chen", now=NOW)
    assert r.status == 200 and r.json["note"] == "Two copies please" and r.json["title"] == "Salt and Stars"
    for user in ("hana", "ada"):
        assert_error(app.patch("/api/suggestions/1", {"note": "x"}, user=user, now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/suggestions/3", {"note": "x"}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.patch("/api/suggestions/3", {"note": "x"}, user="hana", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/suggestions/1", {"isbn": "978-0-1007-001-1"}, user="chen", now=NOW), 400, "validation")
    assert_error(app.patch("/api/suggestions/1", {"status": "accepted"}, user="chen", now=NOW), 400, "validation")
    assert sug(app, 1)["isbn"] == "978-1-2000-001-5" and sug(app, 1)["status"] == "pending"
    assert_error(app.delete("/api/suggestions/1", user="ada", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/suggestions/3", user="chen", now=NOW), 409, "conflict")
    assert app.delete("/api/suggestions/1", user="chen", now=NOW).status == 204
    assert_error(app.get("/api/suggestions/1", user="ada", now=NOW), 404, "not_found")
    assert ids(app.get("/api/suggestions", user="chen", now=NOW)) == [3]


def test_accept_adds_book_to_catalogue():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/suggestions/1/accept", {"year": 2025}, user="ada", now=NOW)
    assert r.status == 200, r
    s = r.json
    assert s["id"] == 1 and s["status"] == "accepted" and isinstance(s["book"], int)
    bid = s["book"]
    assert bid not in range(1, 41)
    b = app.get(f"/api/books/{bid}", user="chen", now=NOW).json
    assert b["title"] == "Salt and Stars" and b["author"] == "N. Adeyemi" and b["isbn"] == "978-1-2000-001-5"
    assert b["year"] == 2025 and b["status"] == "available"
    assert ids(app.get("/api/books", user="chen", now=NOW)) == list(range(1, 41)) + [bid]
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "book_added"
    assert msgs[-1]["payload"] == {"book": bid, "suggestion": 1, "suggested_by": 3}
    assert app.get("/api/suggestions/1", user="chen", now=NOW).json["book"] == bid
    r = app.post(f"/api/books/{bid}/borrow", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"
    # without a year the book has none
    r = app.post("/api/suggestions/2/accept", {}, user="ben", now=NOW)
    assert r.status == 200
    assert app.get(f"/api/books/{r.json['book']}", user="chen", now=NOW).json["year"] is None


def test_refused_accepts_leave_no_trace():
    app = fresh_app()
    # a librarian catalogued suggestion 2's book directly in the meantime
    assert app.post("/api/books", {"title": "The Quiet Engine", "author": "P. Varga", "isbn": "978-1-2000-002-2"},
                    user="ben", now=NOW).status == 201
    before = snapshot(app)
    assert_error(app.post("/api/suggestions/1/accept", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/suggestions/3/accept", {"year": "x"}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/suggestions/3/accept", {}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/suggestions/3/accept", {"year": "x"}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/suggestions/2/accept", {}, user="ada", now=NOW), 409, "conflict")
    for year in ("2025", 2025.5, True):
        assert_error(app.post("/api/suggestions/1/accept", {"year": year}, user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/suggestions/99/accept", {}, user="ada", now=NOW), 404, "not_found")
    assert snapshot(app) == before
    assert sug(app, 1)["status"] == "pending" and sug(app, 2)["status"] == "pending"
    # accepting twice is a conflict
    assert app.post("/api/suggestions/1/accept", {}, user="ada", now=NOW).status == 200
    n = len(outbox(app))
    assert_error(app.post("/api/suggestions/1/accept", {}, user="ada", now=NOW), 409, "conflict")
    assert len(outbox(app)) == n and len(ids(app.get("/api/books", user="ada", now=NOW))) == 42


def test_decline():
    app = fresh_app()
    before = outbox(app)
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        assert_error(app.post("/api/suggestions/2/decline", body, user="ben", now=NOW), 400, "validation")
    assert_error(app.post("/api/suggestions/2/decline", {"reason": "x"}, user="hana", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/suggestions/3/decline", {"reason": "x"}, user="ada", now=NOW), 409, "conflict")
    r = app.post("/api/suggestions/2/decline", {"reason": "Over budget"}, user="ben", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "declined" and r.json["decline_reason"] == "Over budget" and r.json["book"] is None
    assert outbox(app) == before
    assert ids(app.get("/api/books", user="ada", now=NOW)) == list(range(1, 41))
    assert_error(app.post("/api/suggestions/2/accept", {}, user="ada", now=NOW), 409, "conflict")


def test_book_from_suggestion_cannot_be_deleted():
    app = fresh_app()
    bid = app.post("/api/suggestions/1/accept", {}, user="ada", now=NOW).json["book"]
    assert_error(app.delete(f"/api/books/{bid}", user="ada", now=NOW), 409, "conflict")
    assert app.get(f"/api/books/{bid}", user="ada", now=NOW).status == 200
    assert app.delete("/api/books/3", user="ada", now=NOW).status == 204
    assert_error(app.delete("/api/books/2", user="ada", now=NOW), 409, "conflict")


def test_ui_suggestions():
    app = fresh_app()
    assert parse_ui(app.get("/ui/suggestions", user="chen", now=NOW).text).rows == [1, 3]
    assert parse_ui(app.get("/ui/suggestions", user="ada", now=NOW).text).rows == [1, 2, 3]
    ui = parse_ui(app.get("/ui/suggestions/1", user="ada", now=NOW).text)
    assert ui.fields["title"] == "Salt and Stars" and ui.fields["status"] == "pending"
    assert "accept" in ui.actions and "decline" in ui.actions
    ui = parse_ui(app.get("/ui/suggestions/1", user="chen", now=NOW).text)
    assert "accept" not in ui.actions and "decline" not in ui.actions
    ui = parse_ui(app.get("/ui/suggestions/3", user="ada", now=NOW).text)
    assert ui.fields["decline_reason"] == "Out of print"
    assert "accept" not in ui.actions and "decline" not in ui.actions
    assert app.get("/ui/suggestions/2", user="chen", now=NOW).status == 403
    r = app.get("/ui/suggestions/new", user="chen", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["suggestions"] and {"title", "author", "isbn", "note"} <= set(ui.inputs)
    for f in ("status", "suggested_by", "book", "created_at", "decline_reason"):
        assert f not in ui.inputs
