"""Strict acceptance tests for the `library` application (spec/apps/library.md + CONTRACT.md).

All expected values are derived from spec/apps/library_seed.json and hard-coded here.

Seed facts used below (verified against the seed file):
  members: 1 ada (librarian), 2 ben (librarian), 3 chen, 4 dara, 5 eli, 6 fatima, 7 gus,
           8 hana, 9 ivan, 10 jo, 11 kemal (members, active), 12 lena (member, INACTIVE)
  unreturned loans (id, book, member, due_at):
    46 b4  m10 2026-02-15 | 47 b8  m7  2026-02-15 | 48 b7  m9  2026-02-15
    49 b29 m11 2026-02-15 | 50 b16 m10 2026-02-15 | 51 b23 m8  2026-03-04
    52 b22 m3  2026-03-04 | 53 b10 m8  2026-03-04 | 54 b9  m6  2026-03-04
    55 b1  m9  2026-03-04 | 56 b11 m11 2026-03-04 | 57 b28 m10 2026-03-04
    58 b27 m8  2026-03-04 | 59 b5  m4  2026-03-04 | 60 b39 m5  2026-03-05
  -> jo (10) and hana (8) each hold exactly 3 unreturned loans.
  books on loan: 1 4 5 7 8 9 10 11 16 22 23 27 28 29 39
  books with no loans at all: 3 13 14 15 33 34 36 40
  book 2 has only a returned loan (39).
  chen's loans: 13 15 43 52.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

LIBRARIANS = ("ada", "ben")
ON_LOAN_BOOKS = [1, 4, 5, 7, 8, 9, 10, 11, 16, 22, 23, 27, 28, 29, 39]
CHEN_LOANS = [13, 15, 43, 52]
HANA_LOANS = [4, 6, 11, 19, 22, 24, 28, 30, 36, 38, 51, 53, 58]


def assert_error(r, status, code):
    assert r.status == status, r
    body = r.json
    assert isinstance(body, dict), r
    assert body.get("error") == code, r
    assert isinstance(body.get("message"), str), r
    assert isinstance(body.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    items = r.json["items"]
    return [x["id"] for x in items]


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


# --------------------------------------------------------------------------- identity / errors

def test_missing_user_is_401_with_error_shape():
    app = fresh_app()
    assert_error(app.get("/api/books", user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/books/3/borrow", {}, user=None, now=NOW), 401, "unauthenticated")


def test_unknown_user_is_401():
    app = fresh_app()
    assert_error(app.get("/api/books", user="nobody", now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/members/3", user="mallory", now=NOW), 401, "unauthenticated")


def test_401_takes_precedence_over_404():
    app = fresh_app()
    assert_error(app.get("/api/books/999", user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/widgets", user="nobody", now=NOW), 401, "unauthenticated")


def test_unknown_collection_record_and_action_are_404():
    app = fresh_app()
    assert_error(app.get("/api/widgets", user="ada", now=NOW), 404, "not_found")
    assert_error(app.get("/api/books/999", user="chen", now=NOW), 404, "not_found")
    assert_error(app.get("/api/loans/999", user="ada", now=NOW), 404, "not_found")
    assert_error(app.post("/api/books/999/borrow", {}, user="chen", now=NOW), 404, "not_found")
    assert_error(app.post("/api/books/3/frobnicate", {}, user="chen", now=NOW), 404, "not_found")
    assert_error(app.post("/api/loans/52/renew", {}, user="chen", now=NOW), 404, "not_found")


def test_404_takes_precedence_over_403():
    app = fresh_app()
    # chen may not read other members, but an unknown id is 404 not 403
    assert_error(app.get("/api/members/999", user="chen", now=NOW), 404, "not_found")
    # nobody may delete loans, but an unknown loan is 404
    assert_error(app.delete("/api/loans/999", user="ada", now=NOW), 404, "not_found")
    assert_error(app.patch("/api/loans/999", {"due_at": "2026-04-01"}, user="ada", now=NOW), 404, "not_found")


# --------------------------------------------------------------------------- reads: books

def test_any_user_reads_all_books_ascending():
    app = fresh_app()
    for user in ("chen", "gus", "ada"):
        assert ids(app.get("/api/books", user=user, now=NOW)) == list(range(1, 41))


def test_book_fields_and_derived_status():
    app = fresh_app()
    r = app.get("/api/books/4", user="chen", now=NOW)
    assert r.status == 200, r
    b = r.json
    assert b["id"] == 4
    assert b["title"] == "The Harbor Year 4"
    assert b["author"] == "S. Lindqvist"
    assert b["isbn"] == "978-0-1028-004-4"
    assert "year" in b and b["year"] is None
    assert b["status"] == "on_loan"

    r = app.get("/api/books/3", user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["year"] == 2005
    assert r.json["status"] == "available"
    # book 2 has only a returned loan -> available
    assert app.get("/api/books/2", user="chen", now=NOW).json["status"] == "available"


def test_book_status_for_whole_catalogue():
    app = fresh_app()
    r = app.get("/api/books", user="eli", now=NOW)
    assert r.status == 200, r
    status = {b["id"]: b["status"] for b in r.json["items"]}
    for bid in range(1, 41):
        expected = "on_loan" if bid in ON_LOAN_BOOKS else "available"
        assert status[bid] == expected, (bid, status[bid])


def test_books_filter_by_text_and_integer():
    app = fresh_app()
    assert ids(app.get("/api/books?author=K.%20Tanaka", user="chen", now=NOW)) == [19, 20, 22, 23, 30, 34]
    assert ids(app.get("/api/books?year=2024", user="chen", now=NOW)) == [9, 29, 32, 33, 40]
    assert ids(app.get("/api/books?isbn=978-0-1007-001-1", user="chen", now=NOW)) == [1]
    assert ids(app.get("/api/books?author=Nobody", user="chen", now=NOW)) == []


# --------------------------------------------------------------------------- reads: members

def test_member_sees_only_own_member_record():
    app = fresh_app()
    assert ids(app.get("/api/members", user="chen", now=NOW)) == [3]
    r = app.get("/api/members/3", user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["username"] == "chen"
    assert r.json["name"] == "Chen Li"
    assert r.json["role"] == "member"
    assert r.json["active"] is True
    assert_error(app.get("/api/members/4", user="chen", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/members/1", user="chen", now=NOW), 403, "forbidden")


def test_librarian_sees_all_members_and_boolean_filter():
    app = fresh_app()
    assert ids(app.get("/api/members", user="ben", now=NOW)) == list(range(1, 13))
    assert ids(app.get("/api/members?active=false", user="ben", now=NOW)) == [12]
    assert ids(app.get("/api/members?role=librarian", user="ben", now=NOW)) == [1, 2]
    r = app.get("/api/members/12", user="ada", now=NOW)
    assert r.status == 200 and r.json["active"] is False


# --------------------------------------------------------------------------- reads: loans

def test_member_sees_only_own_loans():
    app = fresh_app()
    assert ids(app.get("/api/loans", user="chen", now=NOW)) == CHEN_LOANS
    assert ids(app.get("/api/loans", user="hana", now=NOW)) == HANA_LOANS
    assert ids(app.get("/api/loans", user="gus", now=NOW)) == [7, 14, 25, 47]


def test_librarian_sees_all_loans_and_reference_filter():
    app = fresh_app()
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))
    assert ids(app.get("/api/loans?member=8", user="ada", now=NOW)) == HANA_LOANS
    assert ids(app.get("/api/loans?book=26", user="ada", now=NOW)) == [3, 13]


def test_list_filter_respects_read_permission():
    app = fresh_app()
    # loan 3 (book 26) belongs to fatima; chen only sees his own loan 13
    assert ids(app.get("/api/loans?book=26", user="chen", now=NOW)) == [13]
    assert ids(app.get("/api/loans?member=8", user="chen", now=NOW)) == []


def test_member_cannot_read_other_members_loan():
    app = fresh_app()
    assert_error(app.get("/api/loans/1", user="chen", now=NOW), 403, "forbidden")
    r = app.get("/api/loans/52", user="chen", now=NOW)
    assert r.status == 200, r
    expected = {
        "id": 52, "book": 22, "member": 3, "borrowed_at": "2026-02-18T16:00:00",
        "due_at": "2026-03-04", "returned_at": None, "overdue": False,
    }
    for k, v in expected.items():
        assert k in r.json, k
        assert r.json[k] == v, (k, r.json[k])
    assert r.json["overdue"] is False


def test_overdue_derived_field():
    app = fresh_app()
    r = app.get("/api/loans", user="ada", now=NOW)
    overdue = {l["id"]: l["overdue"] for l in r.json["items"]}
    for lid in range(1, 61):
        expected = lid in (46, 47, 48, 49, 50)
        assert overdue[lid] is expected, (lid, overdue[lid])
    # loan 4 was returned late but is returned -> not overdue
    assert app.get("/api/loans/4", user="ada", now=NOW).json["overdue"] is False


def test_overdue_uses_now_date_boundary():
    app = fresh_app()
    # due 2026-03-04: not overdue on that date, overdue from 2026-03-05
    assert app.get("/api/loans/51", user="ada", now="2026-03-04T23:59:59").json["overdue"] is False
    assert app.get("/api/loans/51", user="ada", now="2026-03-05T00:00:00").json["overdue"] is True
    # due 2026-03-05: not yet overdue on 2026-03-05
    assert app.get("/api/loans/60", user="ada", now="2026-03-05T00:00:00").json["overdue"] is False
    # an early "now" makes the February loans not overdue
    assert app.get("/api/loans/46", user="ada", now="2026-02-15T23:00:00").json["overdue"] is False


# --------------------------------------------------------------------------- borrow

def test_member_borrows_for_self():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/books/3/borrow", {}, user="chen", now="2026-03-10T08:15:00")
    assert r.status == 200, r
    assert r.json["id"] == 3
    assert r.json["title"] == "The Atlas House 3"
    assert r.json["status"] == "on_loan"

    loans = app.get("/api/loans?book=3", user="ada", now="2026-03-10T08:15:00").json["items"]
    assert len(loans) == 1
    loan = loans[0]
    assert loan["book"] == 3
    assert loan["member"] == 3
    assert loan["borrowed_at"] == "2026-03-10T08:15:00"
    assert loan["due_at"] == "2026-03-24"
    assert loan["returned_at"] is None
    assert loan["overdue"] is False
    # chen can now see the loan in his list
    assert loan["id"] in ids(app.get("/api/loans", user="chen", now="2026-03-10T08:15:00"))

    msgs = outbox(app)
    assert len(msgs) == before + 1
    m = msgs[-1]
    assert m["channel"] == "loan_created"
    assert m["payload"] == {"loan": loan["id"], "book": 3, "member": 3}
    assert isinstance(m["id"], int)
    assert "created_at" in m


def test_borrow_due_date_crosses_month_end():
    app = fresh_app()
    r = app.post("/api/books/13/borrow", {}, user="dara", now="2026-02-20T23:30:00")
    assert r.status == 200, r
    loan = app.get("/api/loans?book=13", user="ada", now="2026-02-20T23:30:00").json["items"][0]
    assert loan["due_at"] == "2026-03-06"
    assert loan["borrowed_at"] == "2026-02-20T23:30:00"


def test_borrow_book_on_loan_is_409():
    app = fresh_app()
    assert_error(app.post("/api/books/1/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/22/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/1/borrow", {"member": 4}, user="ada", now=NOW), 409, "conflict")


def test_borrow_member_with_three_open_loans_is_409():
    app = fresh_app()
    assert_error(app.post("/api/books/3/borrow", {}, user="hana", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {}, user="jo", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {"member": 10}, user="ada", now=NOW), 409, "conflict")
    assert app.get("/api/books/3", user="ada", now=NOW).json["status"] == "available"


def test_borrow_allowed_again_after_return_drops_below_limit():
    app = fresh_app()
    r = app.post("/api/loans/51/return", {}, user="hana", now=NOW)
    assert r.status == 200, r
    r = app.post("/api/books/3/borrow", {}, user="hana", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "on_loan"
    # back at 3 open loans -> next borrow refused
    assert_error(app.post("/api/books/13/borrow", {}, user="hana", now=NOW), 409, "conflict")


def test_member_with_two_open_loans_may_borrow_third():
    app = fresh_app()
    # ivan has two unreturned loans (48, 55)
    r = app.post("/api/books/14/borrow", {}, user="ivan", now=NOW)
    assert r.status == 200, r
    assert_error(app.post("/api/books/15/borrow", {}, user="ivan", now=NOW), 409, "conflict")


def test_librarian_lends_to_member():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/books/3/borrow", {"member": 4}, user="ada", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 3 and r.json["status"] == "on_loan"
    loan = app.get("/api/loans?book=3", user="ada", now=NOW).json["items"][0]
    assert loan["member"] == 4
    assert loan["borrowed_at"] == NOW
    assert loan["due_at"] == "2026-03-15"
    # the borrowing member can read it, others cannot
    assert app.get(f"/api/loans/{loan['id']}", user="dara", now=NOW).status == 200
    assert_error(app.get(f"/api/loans/{loan['id']}", user="chen", now=NOW), 403, "forbidden")
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "loan_created"
    assert msgs[-1]["payload"] == {"loan": loan["id"], "book": 3, "member": 4}


def test_lending_to_inactive_member_is_409():
    app = fresh_app()
    assert_error(app.post("/api/books/3/borrow", {"member": 12}, user="ben", now=NOW), 409, "conflict")
    assert app.get("/api/books/3", user="ben", now=NOW).json["status"] == "available"


def test_lending_to_reactivated_member_succeeds():
    app = fresh_app()
    r = app.patch("/api/members/12", {"active": True}, user="ada", now=NOW)
    assert r.status == 200, r
    assert r.json["active"] is True
    r = app.post("/api/books/3/borrow", {"member": 12}, user="ada", now=NOW)
    assert r.status == 200, r


def test_lending_to_deactivated_member_is_409():
    app = fresh_app()
    r = app.patch("/api/members/4", {"active": False}, user="ada", now=NOW)
    assert r.status == 200 and r.json["active"] is False
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="ada", now=NOW), 409, "conflict")


def test_member_borrowing_for_someone_else_is_403():
    app = fresh_app()
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    # 403 wins over 409 (book 1 is on loan)
    assert_error(app.post("/api/books/1/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/books/3", user="chen", now=NOW).json["status"] == "available"


def test_member_passing_own_id_may_borrow():
    app = fresh_app()
    r = app.post("/api/books/3/borrow", {"member": 3}, user="chen", now=NOW)
    assert r.status == 200, r
    loan = app.get("/api/loans?book=3", user="ada", now=NOW).json["items"][0]
    assert loan["member"] == 3


def test_failed_borrows_emit_no_outbox_message():
    app = fresh_app()
    before = outbox(app)
    app.post("/api/books/1/borrow", {}, user="chen", now=NOW)               # 409 on loan
    app.post("/api/books/3/borrow", {}, user="hana", now=NOW)               # 409 limit
    app.post("/api/books/3/borrow", {"member": 12}, user="ada", now=NOW)    # 409 inactive
    app.post("/api/books/3/borrow", {"member": 4}, user="chen", now=NOW)    # 403
    assert outbox(app) == before
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))


def test_outbox_readable_by_any_authenticated_user():
    app = fresh_app()
    assert app.post("/api/books/3/borrow", {}, user="chen", now=NOW).status == 200
    r = app.get("/api/_outbox", user="eli", now=NOW)
    assert r.status == 200, r
    items = r.json["items"]
    assert [m["id"] for m in items] == sorted(m["id"] for m in items)
    assert any(m["channel"] == "loan_created" and m["payload"]["book"] == 3 for m in items)
    for m in items:
        assert set(m) >= {"id", "channel", "payload", "created_at"}
    assert_error(app.get("/api/_outbox", user=None, now=NOW), 401, "unauthenticated")


# --------------------------------------------------------------------------- return

def test_borrower_returns_loan():
    app = fresh_app()
    r = app.post("/api/loans/52/return", {}, user="chen", now="2026-03-02T09:45:00")
    assert r.status == 200, r
    assert r.json["id"] == 52
    assert r.json["returned_at"] == "2026-03-02T09:45:00"
    assert r.json["overdue"] is False
    assert r.json["book"] == 22 and r.json["member"] == 3
    assert r.json["due_at"] == "2026-03-04"
    assert app.get("/api/books/22", user="chen", now=NOW).json["status"] == "available"


def test_librarian_returns_overdue_loan():
    app = fresh_app()
    r = app.post("/api/loans/46/return", {}, user="ben", now=NOW)
    assert r.status == 200, r
    assert r.json["returned_at"] == NOW
    assert r.json["overdue"] is False
    assert app.get("/api/books/4", user="ben", now=NOW).json["status"] == "available"


def test_returned_book_can_be_borrowed_again():
    app = fresh_app()
    assert app.post("/api/loans/55/return", {}, user="ivan", now=NOW).status == 200
    r = app.post("/api/books/1/borrow", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"


def test_return_already_returned_is_409():
    app = fresh_app()
    assert_error(app.post("/api/loans/1/return", {}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/13/return", {}, user="chen", now=NOW), 409, "conflict")
    assert app.post("/api/loans/52/return", {}, user="chen", now=NOW).status == 200
    assert_error(app.post("/api/loans/52/return", {}, user="chen", now=NOW), 409, "conflict")
    assert app.get("/api/loans/1", user="ada", now=NOW).json["returned_at"] == "2025-11-15T18:00:00"


def test_return_by_other_member_is_403():
    app = fresh_app()
    assert_error(app.post("/api/loans/52/return", {}, user="dara", now=NOW), 403, "forbidden")
    # 403 wins over 409 for an already-returned loan of someone else
    assert_error(app.post("/api/loans/1/return", {}, user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/loans/52", user="ada", now=NOW).json["returned_at"] is None


# --------------------------------------------------------------------------- loans: no direct writes

def test_loans_cannot_be_created_patched_or_deleted():
    app = fresh_app()
    body = {"book": 3, "member": 3, "borrowed_at": NOW, "due_at": "2026-03-15"}
    for user in ("ada", "chen"):
        assert_error(app.post("/api/loans", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/loans/52", {"due_at": "2026-04-01"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/loans/52", user=user, now=NOW), 403, "forbidden")
    r = app.get("/api/loans/52", user="ada", now=NOW)
    assert r.status == 200 and r.json["due_at"] == "2026-03-04"
    assert ids(app.get("/api/loans", user="ada", now=NOW)) == list(range(1, 61))


# --------------------------------------------------------------------------- books CRUD

def test_librarian_creates_book():
    app = fresh_app()
    body = {"title": "New Book", "author": "A. Writer", "isbn": "978-9-9999-999-9", "year": 2020}
    r = app.post("/api/books", body, user="ada", now=NOW)
    assert r.status == 201, r
    b = r.json
    assert isinstance(b["id"], int) and b["id"] not in range(1, 41)
    assert b["title"] == "New Book" and b["author"] == "A. Writer"
    assert b["isbn"] == "978-9-9999-999-9" and b["year"] == 2020
    assert b["status"] == "available"
    g = app.get(f"/api/books/{b['id']}", user="chen", now=NOW)
    assert g.status == 200 and g.json["title"] == "New Book"
    assert ids(app.get("/api/books", user="chen", now=NOW))[-1] == b["id"]


def test_book_year_is_optional():
    app = fresh_app()
    r = app.post("/api/books", {"title": "T", "author": "A", "isbn": "isbn-no-year"}, user="ben", now=NOW)
    assert r.status == 201, r
    assert "year" in r.json and r.json["year"] is None


def test_book_create_validation():
    app = fresh_app()
    full = {"title": "T", "author": "A", "isbn": "isbn-x", "year": 2000}
    for missing in ("title", "author", "isbn"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/books", body, user="ada", now=NOW), 400, "validation")
    dup = dict(full, isbn="978-0-1007-001-1")
    assert_error(app.post("/api/books", dup, user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/books", dict(full, year="abc"), user="ada", now=NOW), 400, "validation")
    assert ids(app.get("/api/books", user="ada", now=NOW)) == list(range(1, 41))


def test_member_cannot_write_books():
    app = fresh_app()
    body = {"title": "T", "author": "A", "isbn": "isbn-y"}
    assert_error(app.post("/api/books", body, user="chen", now=NOW), 403, "forbidden")
    # 403 wins over 400
    assert_error(app.post("/api/books", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/books/3", {"title": "X"}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/books/3", user="chen", now=NOW), 403, "forbidden")
    r = app.get("/api/books/3", user="chen", now=NOW)
    assert r.status == 200 and r.json["title"] == "The Atlas House 3"


def test_librarian_updates_book():
    app = fresh_app()
    r = app.patch("/api/books/3", {"title": "Renamed", "year": 2001}, user="ben", now=NOW)
    assert r.status == 200, r
    assert r.json["title"] == "Renamed" and r.json["year"] == 2001
    assert r.json["author"] == "S. Lindqvist"
    assert r.json["isbn"] == "978-0-1021-003-3"
    assert app.get("/api/books/3", user="chen", now=NOW).json["title"] == "Renamed"


def test_book_update_duplicate_isbn_is_400():
    app = fresh_app()
    assert_error(app.patch("/api/books/3", {"isbn": "978-0-1007-001-1"}, user="ada", now=NOW), 400, "validation")
    assert app.get("/api/books/3", user="ada", now=NOW).json["isbn"] == "978-0-1021-003-3"


def test_delete_book_without_loans():
    app = fresh_app()
    r = app.delete("/api/books/3", user="ada", now=NOW)
    assert r.status == 204, r
    assert_error(app.get("/api/books/3", user="ada", now=NOW), 404, "not_found")
    assert 3 not in ids(app.get("/api/books", user="ada", now=NOW))


def test_delete_book_with_loans_is_409():
    app = fresh_app()
    assert_error(app.delete("/api/books/2", user="ada", now=NOW), 409, "conflict")   # returned loan only
    assert_error(app.delete("/api/books/1", user="ada", now=NOW), 409, "conflict")   # on loan
    assert app.get("/api/books/2", user="ada", now=NOW).status == 200


# --------------------------------------------------------------------------- members CRUD

def test_librarian_creates_member_with_default_active():
    app = fresh_app()
    r = app.post("/api/members", {"username": "zed", "name": "Zed Zed", "role": "member"}, user="ada", now=NOW)
    assert r.status == 201, r
    assert r.json["username"] == "zed" and r.json["name"] == "Zed Zed"
    assert r.json["role"] == "member" and r.json["active"] is True
    assert isinstance(r.json["id"], int) and r.json["id"] not in range(1, 13)


def test_member_create_validation():
    app = fresh_app()
    full = {"username": "zed", "name": "Zed", "role": "member"}
    for missing in ("username", "name", "role"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/members", body, user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/members", dict(full, username="chen"), user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/members", dict(full, role="admin"), user="ada", now=NOW), 400, "validation")
    assert ids(app.get("/api/members", user="ada", now=NOW)) == list(range(1, 13))


def test_member_cannot_create_or_delete_members():
    app = fresh_app()
    body = {"username": "zed", "name": "Zed", "role": "member"}
    assert_error(app.post("/api/members", body, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/members/3", user="chen", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/members/4", user="chen", now=NOW), 403, "forbidden")


def test_librarian_deletes_member_without_loans():
    app = fresh_app()
    r = app.delete("/api/members/12", user="ada", now=NOW)
    assert r.status == 204, r
    assert_error(app.get("/api/members/12", user="ada", now=NOW), 404, "not_found")


def test_member_updates_own_name_only():
    app = fresh_app()
    r = app.patch("/api/members/3", {"name": "Chen Lee"}, user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["name"] == "Chen Lee" and r.json["username"] == "chen"
    assert r.json["role"] == "member" and r.json["active"] is True
    for body in ({"role": "librarian"}, {"active": False}, {"username": "chen2"},
                 {"name": "X", "role": "librarian"}):
        assert_error(app.patch("/api/members/3", body, user="chen", now=NOW), 403, "forbidden")
    m = app.get("/api/members/3", user="ada", now=NOW).json
    assert m["name"] == "Chen Lee" and m["role"] == "member" and m["active"] is True


def test_member_cannot_update_other_member():
    app = fresh_app()
    assert_error(app.patch("/api/members/4", {"name": "Hacked"}, user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/members/4", user="ada", now=NOW).json["name"] == "Dara Novak"


def test_librarian_updates_member_and_role_validation():
    app = fresh_app()
    r = app.patch("/api/members/3", {"role": "librarian"}, user="ada", now=NOW)
    assert r.status == 200 and r.json["role"] == "librarian"
    assert_error(app.patch("/api/members/4", {"role": "admin"}, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/members/4", {"username": "chen"}, user="ada", now=NOW), 400, "validation")
    m = app.get("/api/members/4", user="ada", now=NOW).json
    assert m["role"] == "member" and m["username"] == "dara"


# --------------------------------------------------------------------------- UI

def test_ui_lists_follow_read_permissions():
    app = fresh_app()
    r = app.get("/ui/books", user="chen", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == list(range(1, 41))
    assert parse_ui(app.get("/ui/loans", user="chen", now=NOW).text).rows == CHEN_LOANS
    assert parse_ui(app.get("/ui/members", user="chen", now=NOW).text).rows == [3]
    assert parse_ui(app.get("/ui/members", user="ada", now=NOW).text).rows == list(range(1, 13))
    assert parse_ui(app.get("/ui/loans", user="ada", now=NOW).text).rows == list(range(1, 61))


def test_ui_book_detail_fields_and_borrow_action():
    app = fresh_app()
    r = app.get("/ui/books/3", user="chen", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["title"] == "The Atlas House 3"
    assert ui.fields["author"] == "S. Lindqvist"
    assert ui.fields["isbn"] == "978-0-1021-003-3"
    assert ui.fields["year"] == "2005"
    assert ui.fields["status"] == "available"
    assert "borrow" in ui.actions

    ui = parse_ui(app.get("/ui/books/1", user="chen", now=NOW).text)
    assert ui.fields["status"] == "on_loan"
    assert "borrow" not in ui.actions


def test_ui_loan_detail_return_action():
    app = fresh_app()
    r = app.get("/ui/loans/52", user="chen", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert set(ui.fields) >= {"book", "member", "borrowed_at", "due_at", "returned_at", "overdue"}
    assert ui.fields["due_at"] == "2026-03-04"
    assert "return" in ui.actions
    # a librarian may also return it
    assert "return" in parse_ui(app.get("/ui/loans/52", user="ada", now=NOW).text).actions
    # returned loan: no return action
    ui = parse_ui(app.get("/ui/loans/13", user="chen", now=NOW).text)
    assert "return" not in ui.actions


def test_ui_detail_permissions_and_404():
    app = fresh_app()
    assert app.get("/ui/loans/52", user="dara", now=NOW).status == 403
    assert app.get("/ui/members/4", user="chen", now=NOW).status == 403
    assert app.get("/ui/books/999", user="chen", now=NOW).status == 404
    assert app.get("/ui/widgets", user="chen", now=NOW).status == 404
    assert app.get("/ui/books", user=None, now=NOW).status == 401
    assert app.get("/ui/books/3", user="nobody", now=NOW).status == 401


def test_ui_member_detail():
    app = fresh_app()
    r = app.get("/ui/members/3", user="chen", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["username"] == "chen"
    assert ui.fields["name"] == "Chen Li"
    assert ui.fields["role"] == "member"
    assert "borrow" not in ui.actions and "return" not in ui.actions


def test_ui_create_forms():
    app = fresh_app()
    r = app.get("/ui/books/new", user="ada", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["books"]
    assert {"title", "author", "isbn", "year"} <= set(ui.inputs)
    assert "status" not in ui.inputs and "id" not in ui.inputs

    r = app.get("/ui/members/new", user="ben", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["members"]
    assert {"username", "name", "role"} <= set(ui.inputs)


def test_ui_create_forms_forbidden():
    app = fresh_app()
    assert app.get("/ui/books/new", user="chen", now=NOW).status == 403
    assert app.get("/ui/members/new", user="chen", now=NOW).status == 403
    assert app.get("/ui/loans/new", user="ada", now=NOW).status == 403
    assert app.get("/ui/loans/new", user="chen", now=NOW).status == 403
    assert app.get("/ui/books/new", user=None, now=NOW).status == 401
