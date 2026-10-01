"""D06 (library): atomic bulk checkout `POST /api/members/{id}/checkout`.

Seed facts used: chen (3) has 1 open loan (52); hana (8) has 3; lena (12) inactive;
available books include 3, 13, 14, 15, 33, 34, 36, 40; book 1 and 22 are on loan.
"""
from accept_client import fresh_app, parse_ui

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


def snapshot(app):
    loans = app.get("/api/loans", user="ada", now=NOW).json["items"]
    books = {b["id"]: b["status"] for b in app.get("/api/books", user="ada", now=NOW).json["items"]}
    return loans, books, outbox(app)


def new_member(app, username="zed"):
    r = app.post("/api/members", {"username": username, "name": "Zed Zed", "role": "member"}, user="ada", now=NOW)
    assert r.status == 201, r
    return r.json["id"]


def test_checkout_creates_loans_and_messages_in_order():
    app = fresh_app()
    n = len(outbox(app))
    r = app.post("/api/members/3/checkout", {"books": [13, 3]}, user="ada", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 3 and r.json["username"] == "chen"
    new = [l for l in app.get("/api/loans?member=3", user="ada", now=NOW).json["items"] if l["id"] > 60]
    assert [l["book"] for l in new] == [13, 3]
    assert new[0]["id"] < new[1]["id"]
    for l in new:
        assert l["borrowed_at"] == NOW and l["due_at"] == "2026-03-15" and l["returned_at"] is None
    assert app.get("/api/books/13", user="chen", now=NOW).json["status"] == "on_loan"
    assert app.get("/api/books/3", user="chen", now=NOW).json["status"] == "on_loan"
    msgs = outbox(app)[n:]
    assert [m["channel"] for m in msgs] == ["loan_created", "loan_created"]
    assert msgs[0]["payload"] == {"loan": new[0]["id"], "book": 13, "member": 3}
    assert msgs[1]["payload"] == {"loan": new[1]["id"], "book": 3, "member": 3}


def test_checkout_three_books_for_member_without_loans():
    app = fresh_app()
    mid = new_member(app)
    r = app.post(f"/api/members/{mid}/checkout", {"books": [14, 15, 33]}, user="ben", now=NOW)
    assert r.status == 200, r
    assert len(app.get(f"/api/loans?member={mid}", user="ada", now=NOW).json["items"]) == 3
    assert_error(app.post("/api/books/34/borrow", {}, user="zed", now=NOW), 409, "conflict")


def test_checkout_over_limit_leaves_no_trace():
    app = fresh_app()
    before = snapshot(app)
    assert_error(app.post("/api/members/3/checkout", {"books": [3, 13, 14]}, user="ada", now=NOW), 409, "conflict")
    assert snapshot(app) == before
    mid = new_member(app)
    before = snapshot(app)
    assert_error(app.post(f"/api/members/{mid}/checkout", {"books": [3, 13, 14, 15]}, user="ada", now=NOW),
                 409, "conflict")
    assert snapshot(app) == before


def test_checkout_with_unavailable_book_anywhere_leaves_no_trace():
    app = fresh_app()
    mid = new_member(app)
    before = snapshot(app)
    # the unavailable book is last: nothing before it may be lent
    assert_error(app.post(f"/api/members/{mid}/checkout", {"books": [3, 13, 1]}, user="ada", now=NOW),
                 409, "conflict")
    assert snapshot(app) == before
    assert_error(app.post(f"/api/members/{mid}/checkout", {"books": [22, 3]}, user="ada", now=NOW),
                 409, "conflict")
    assert snapshot(app) == before
    assert app.post(f"/api/members/{mid}/checkout", {"books": [3, 13]}, user="ada", now=NOW).status == 200


def test_checkout_for_inactive_member_is_409():
    app = fresh_app()
    before = snapshot(app)
    assert_error(app.post("/api/members/12/checkout", {"books": [3]}, user="ada", now=NOW), 409, "conflict")
    assert snapshot(app) == before


def test_checkout_validation_leaves_no_trace():
    app = fresh_app()
    before = snapshot(app)
    for body in ({}, {"books": []}, {"books": 3}, {"books": [3, 3]}, {"books": [3, 999]}):
        assert_error(app.post("/api/members/3/checkout", body, user="ada", now=NOW), 400, "validation")
    assert snapshot(app) == before


def test_conflict_wins_over_validation():
    app = fresh_app()
    before = snapshot(app)
    assert_error(app.post("/api/members/3/checkout", {"books": [1, 999]}, user="ada", now=NOW), 409, "conflict")
    assert snapshot(app) == before


def test_members_cannot_checkout():
    app = fresh_app()
    before = snapshot(app)
    assert_error(app.post("/api/members/3/checkout", {"books": [3]}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/members/4/checkout", {"books": [3]}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/members/3/checkout", {"books": []}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/members/3/checkout", {"books": [3]}, user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/members/999/checkout", {"books": [3]}, user="ada", now=NOW), 404, "not_found")
    assert snapshot(app) == before


def test_checked_out_loans_behave_like_normal_loans():
    app = fresh_app()
    assert app.post("/api/members/3/checkout", {"books": [3, 13]}, user="ada", now=NOW).status == 200
    assert_error(app.post("/api/books/14/borrow", {}, user="chen", now=NOW), 409, "conflict")  # now at 3
    lid = app.get("/api/loans?book=3", user="chen", now=NOW).json["items"][0]["id"]
    r = app.post(f"/api/loans/{lid}/return", {}, user="chen", now="2026-03-02T10:00:00")
    assert r.status == 200 and r.json["returned_at"] == "2026-03-02T10:00:00"
    assert app.get(f"/api/loans/{lid}", user="chen", now=NOW).json["overdue"] is False
    assert app.post("/api/books/14/borrow", {}, user="chen", now=NOW).status == 200


def test_single_borrow_unchanged():
    app = fresh_app()
    n = len(outbox(app))
    r = app.post("/api/books/3/borrow", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"
    assert len(outbox(app)) == n + 1
    assert_error(app.post("/api/books/3/borrow", {}, user="dara", now=NOW), 409, "conflict")


def test_ui_checkout_form_for_librarians_only():
    app = fresh_app()
    assert "checkout" in parse_ui(app.get("/ui/members/3", user="ada", now=NOW).text).actions
    assert "checkout" not in parse_ui(app.get("/ui/members/3", user="chen", now=NOW).text).actions
