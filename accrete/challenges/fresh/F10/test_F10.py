"""Hidden acceptance tests for F10 (library): reference-only books.

Seed facts (computed from spec/apps/library_seed.json):
  reference collection (per the brief): books 9, 33, 36, 40.
  book 9 is on loan to fatima (6) via loan 54 (due 2026-03-04); 33, 36, 40 have no loans.
  book 3 has no loans; chen (3) has one open loan (52), dara (4) one (59).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
REFERENCE = [9, 33, 36, 40]


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


def test_reference_flag_migrated():
    app = fresh_app()
    items = app.get("/api/books", user="chen", now=NOW).json["items"]
    assert [b["id"] for b in items] == list(range(1, 41))
    for b in items:
        assert b["reference_only"] is (b["id"] in REFERENCE), b["id"]
    assert ids(app.get("/api/books?reference_only=true", user="chen", now=NOW)) == REFERENCE
    b = app.get("/api/books/33", user="chen", now=NOW).json
    assert b["title"] == "The Lantern Song 33" and b["author"] == "T. Okoye" and b["year"] == 2024
    assert b["status"] == "available"
    assert app.get("/api/books/9", user="chen", now=NOW).json["status"] == "on_loan"


def test_reference_books_cannot_be_borrowed():
    app = fresh_app()
    before = outbox(app)
    assert_error(app.post("/api/books/33/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/36/borrow", {"member": 4}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/40/borrow", {"member": 3}, user="chen", now=NOW), 409, "conflict")
    # 403 still wins for a member borrowing for someone else
    assert_error(app.post("/api/books/33/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    assert outbox(app) == before
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))
    assert app.get("/api/books/33", user="chen", now=NOW).json["status"] == "available"


def test_book_on_loan_stays_until_returned():
    app = fresh_app()
    r = app.get("/api/loans/54", user="fatima", now=NOW)
    assert r.status == 200 and r.json["returned_at"] is None
    r = app.post("/api/loans/54/return", {}, user="fatima", now=NOW)
    assert r.status == 200 and r.json["returned_at"] == NOW
    assert app.get("/api/books/9", user="chen", now=NOW).json["status"] == "available"
    assert_error(app.post("/api/books/9/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/9/borrow", {"member": 6}, user="ben", now=NOW), 409, "conflict")


def test_librarian_toggles_reference_flag():
    app = fresh_app()
    r = app.patch("/api/books/33", {"reference_only": False}, user="ada", now=NOW)
    assert r.status == 200 and r.json["reference_only"] is False and r.json["title"] == "The Lantern Song 33"
    r = app.post("/api/books/33/borrow", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"
    r = app.patch("/api/books/3", {"reference_only": True}, user="ben", now=NOW)
    assert r.status == 200 and r.json["reference_only"] is True
    assert_error(app.post("/api/books/3/borrow", {}, user="dara", now=NOW), 409, "conflict")
    # flagging a book that is on loan is allowed; the loan continues and can be returned
    r = app.patch("/api/books/1", {"reference_only": True}, user="ada", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"
    assert app.post("/api/loans/55/return", {}, user="ivan", now=NOW).status == 200
    assert_error(app.post("/api/books/1/borrow", {}, user="chen", now=NOW), 409, "conflict")


def test_reference_flag_validation_and_permissions():
    app = fresh_app()
    for bad in ("yes", 1, None, "true"):
        assert_error(app.patch("/api/books/3", {"reference_only": bad}, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/books/33", {"reference_only": False}, user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/books/3", user="ada", now=NOW).json["reference_only"] is False
    assert app.get("/api/books/33", user="ada", now=NOW).json["reference_only"] is True


def test_create_book_reference_flag():
    app = fresh_app()
    r = app.post("/api/books", {"title": "Atlas of the World", "author": "Various", "isbn": "isbn-atlas",
                                "reference_only": True}, user="ada", now=NOW)
    assert r.status == 201, r
    assert r.json["reference_only"] is True and r.json["status"] == "available"
    assert_error(app.post(f"/api/books/{r.json['id']}/borrow", {}, user="chen", now=NOW), 409, "conflict")
    r = app.post("/api/books", {"title": "Novel", "author": "A. Writer", "isbn": "isbn-novel"}, user="ada", now=NOW)
    assert r.status == 201 and r.json["reference_only"] is False
    assert app.post(f"/api/books/{r.json['id']}/borrow", {}, user="chen", now=NOW).status == 200
    assert_error(app.post("/api/books", {"title": "T", "author": "A", "isbn": "isbn-z", "reference_only": "no"},
                          user="ada", now=NOW), 400, "validation")


def test_ui_reference_books():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/books/33", user="chen", now=NOW).text)
    assert "reference_only" in ui.fields and ui.fields["status"] == "available"
    assert "borrow" not in ui.actions
    assert "borrow" in parse_ui(app.get("/ui/books/3", user="chen", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/books/new", user="ada", now=NOW).text)
    assert {"title", "author", "isbn", "year", "reference_only"} <= set(ui.inputs)


def test_other_borrow_rules_unchanged():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/books/3/borrow", {}, user="chen", now=NOW)
    assert r.status == 200
    assert outbox(app)[before]["channel"] == "loan_created"
    assert_error(app.post("/api/books/13/borrow", {}, user="hana", now=NOW), 409, "conflict")
    assert app.delete("/api/books/33", user="ada", now=NOW).status == 204
