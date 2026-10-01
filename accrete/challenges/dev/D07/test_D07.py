"""D07 (library): borrowing blocked by overdue loans; 7-day loans for new releases.

Seed facts used (at 2026-03-01):
  overdue loans (due 2026-02-15): 46 & 50 jo (10), 47 gus (7), 48 ivan (9), 49 kemal (11)
  chen (3): loan 52 due 2026-03-04; dara (4): loan 59 due 2026-03-04; fatima (6): loan 54 due 2026-03-04
  available books: 3 (2005), 13 (2021), 14 (1999), 19 (year null), 25 (year null), 32 (2024), 40 (2024)
"""
from accept_client import fresh_app

NOW = "2026-03-01T12:00:00"


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


def new_loan(app, book, now=NOW):
    items = app.get(f"/api/loans?book={book}", user="ada", now=now).json["items"]
    open_ = [l for l in items if l["returned_at"] is None]
    assert len(open_) == 1, items
    return open_[0]


def borrow_ok(app, book, user, now=NOW, body=None):
    r = app.post(f"/api/books/{book}/borrow", body or {}, user=user, now=now)
    assert r.status == 200, r
    return new_loan(app, book, now)


def test_member_with_overdue_loan_cannot_borrow():
    app = fresh_app()
    n = len(outbox(app))
    for user in ("gus", "ivan", "kemal"):
        assert_error(app.post("/api/books/3/borrow", {}, user=user, now=NOW), 409, "conflict")
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))
    assert len(outbox(app)) == n
    assert app.get("/api/books/3", user="ada", now=NOW).json["status"] == "available"


def test_librarian_cannot_lend_to_member_with_overdue_loan():
    app = fresh_app()
    assert_error(app.post("/api/books/3/borrow", {"member": 7}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {"member": 9}, user="ben", now=NOW), 409, "conflict")
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))


def test_members_without_overdue_loans_still_borrow():
    app = fresh_app()
    l = borrow_ok(app, 3, "chen")
    assert l["member"] == 3 and l["due_at"] == "2026-03-15"
    l = borrow_ok(app, 14, "ada", body={"member": 6})
    assert l["member"] == 6 and l["due_at"] == "2026-03-15"


def test_loan_due_today_does_not_block_but_tomorrow_does():
    app = fresh_app()
    l = borrow_ok(app, 3, "chen", now="2026-03-04T20:00:00")
    assert l["due_at"] == "2026-03-18"
    assert_error(app.post("/api/books/13/borrow", {}, user="dara", now="2026-03-05T00:00:00"), 409, "conflict")


def test_returning_overdue_loan_lifts_block():
    app = fresh_app()
    assert app.post("/api/loans/47/return", {}, user="gus", now=NOW).status == 200
    l = borrow_ok(app, 3, "gus")
    assert l["member"] == 7 and l["due_at"] == "2026-03-15"
    # ivan returns only one of his loans; the overdue one remains -> still blocked
    assert app.post("/api/loans/55/return", {}, user="ivan", now=NOW).status == 200
    assert_error(app.post("/api/books/13/borrow", {}, user="ivan", now=NOW), 409, "conflict")


def test_returns_are_never_blocked():
    app = fresh_app()
    r = app.post("/api/loans/46/return", {}, user="jo", now=NOW)
    assert r.status == 200 and r.json["returned_at"] == NOW
    r = app.post("/api/loans/50/return", {}, user="ada", now=NOW)
    assert r.status == 200


def test_new_releases_are_lent_for_seven_days():
    app = fresh_app()
    b26 = app.post("/api/books", {"title": "Fresh", "author": "A", "isbn": "isbn-2026", "year": 2026},
                   user="ada", now=NOW).json
    b25 = app.post("/api/books", {"title": "Recent", "author": "A", "isbn": "isbn-2025", "year": 2025},
                   user="ada", now=NOW).json
    n = len(outbox(app))
    l = borrow_ok(app, b26["id"], "chen")
    assert l["due_at"] == "2026-03-08" and l["borrowed_at"] == NOW
    l = borrow_ok(app, b25["id"], "ada", body={"member": 4})
    assert l["due_at"] == "2026-03-08"
    msgs = outbox(app)
    assert len(msgs) == n + 2 and msgs[-1]["channel"] == "loan_created"


def test_older_and_undated_books_keep_fourteen_days():
    app = fresh_app()
    assert borrow_ok(app, 32, "chen")["due_at"] == "2026-03-15"       # 2024
    assert borrow_ok(app, 19, "dara")["due_at"] == "2026-03-15"       # year null
    assert borrow_ok(app, 13, "fatima")["due_at"] == "2026-03-15"     # 2021


def test_new_release_window_follows_request_year():
    app = fresh_app()
    # on 2025-12-31 a 2024 book is from the previous year -> 7 days
    assert borrow_ok(app, 40, "chen", now="2025-12-31T10:00:00")["due_at"] == "2026-01-07"
    b = app.post("/api/books", {"title": "Old News", "author": "A", "isbn": "isbn-2024b", "year": 2024},
                 user="ada", now=NOW).json
    # on 2026-03-01 a 2024 book is two years old -> 14 days
    assert borrow_ok(app, b["id"], "dara")["due_at"] == "2026-03-15"


def test_existing_loans_are_not_recalculated():
    app = fresh_app()
    items = {l["id"]: l for l in app.get("/api/loans", user="ada", now=NOW).json["items"]}
    assert items[55]["due_at"] == "2026-03-04" and items[60]["due_at"] == "2026-03-05"
    assert items[46]["due_at"] == "2026-02-15" and items[46]["overdue"] is True
    assert items[52]["overdue"] is False


def test_other_borrow_rules_still_apply():
    app = fresh_app()
    assert_error(app.post("/api/books/3/borrow", {}, user="hana", now=NOW), 409, "conflict")                 # limit
    assert_error(app.post("/api/books/3/borrow", {"member": 12}, user="ada", now=NOW), 409, "conflict")      # inactive
    assert_error(app.post("/api/books/1/borrow", {}, user="chen", now=NOW), 409, "conflict")                 # on loan
    assert_error(app.post("/api/books/3/borrow", {"member": 7}, user="chen", now=NOW), 403, "forbidden")     # 403 first
    assert app.get("/api/books/3", user="ada", now=NOW).json["status"] == "available"
