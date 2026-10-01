"""Hidden acceptance tests for E08 (library): physical copies.

Seed facts (spec/apps/library_seed.json): books on loan 1 4 5 7 8 9 10 11 16 22 23 27 28 29 39 (one open loan
each). After the migration copy i belongs to book i (barcode C%04d), plus copy 41 (book 1, C0001-2) and copy 42
(book 22, C0022-2), both available, so books 1 and 22 become available. Every loan's copy = its book id.
hana (8) and jo (10) hold 3 open loans; lena (12) is inactive; loan 55 = book 1 / ivan; loan 52 = book 22 / chen.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

ON_LOAN = [4, 5, 7, 8, 9, 10, 11, 16, 23, 27, 28, 29, 39]
LOANED_COPIES = [1, 4, 5, 7, 8, 9, 10, 11, 16, 22, 23, 27, 28, 29, 39]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def get(app, path, user="ada", now=NOW):
    r = app.get(path, user=user, now=now)
    assert r.status == 200, r
    return r.json


def test_copies_migrated():
    app = fresh_app()
    for user in ("chen", "ada"):
        assert ids(app.get("/api/copies", user=user, now=NOW)) == list(range(1, 43))
    items = {c["id"]: c for c in get(app, "/api/copies", user="eli")["items"]}
    for i in range(1, 41):
        assert items[i]["book"] == i and items[i]["barcode"] == "C%04d" % i, items[i]
        assert items[i]["status"] == ("on_loan" if i in LOANED_COPIES else "available"), items[i]
    assert (items[41]["book"], items[41]["barcode"], items[41]["status"]) == (1, "C0001-2", "available")
    assert (items[42]["book"], items[42]["barcode"], items[42]["status"]) == (22, "C0022-2", "available")
    assert ids(app.get("/api/copies?book=1", user="chen", now=NOW)) == [1, 41]
    assert ids(app.get("/api/copies?barcode=C0022-2", user="chen", now=NOW)) == [42]


def test_loans_reference_copies():
    app = fresh_app()
    loans = get(app, "/api/loans")["items"]
    assert len(loans) == 60
    for l in loans:
        assert l["copy"] == l["book"], l
    l = get(app, "/api/loans/52", user="chen")
    assert (l["book"], l["copy"], l["member"], l["due_at"], l["returned_at"]) == (22, 22, 3, "2026-03-04", None)
    assert ids(app.get("/api/loans?copy=41", user="ada", now=NOW)) == []


def test_book_status_and_available_copies():
    app = fresh_app()
    books = {b["id"]: b for b in get(app, "/api/books", user="gus")["items"]}
    assert sorted(books) == list(range(1, 41))
    for bid, b in books.items():
        if bid in ON_LOAN:
            assert (b["status"], b["available_copies"]) == ("on_loan", 0), b
        else:
            assert b["status"] == "available", b
            assert b["available_copies"] == 1, b
    assert books[3]["title"] == "The Atlas House 3" and books[3]["isbn"] == "978-0-1021-003-3"


def test_borrow_takes_lowest_available_copy():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/books/1/borrow", {}, user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 1 and r.json["status"] == "on_loan" and r.json["available_copies"] == 0
    loans = get(app, "/api/loans?book=1")["items"]
    new = loans[-1]
    assert new["id"] > 60 and new["copy"] == 41 and new["member"] == 3 and new["due_at"] == "2026-03-15"
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["loan_created"]
    assert msgs[0]["payload"] == {"loan": new["id"], "book": 1, "member": 3, "copy": 41}
    assert get(app, "/api/copies/41")["status"] == "on_loan"
    n = len(outbox(app))
    assert_error(app.post("/api/books/1/borrow", {}, user="dara", now=NOW), 409, "conflict")
    assert len(outbox(app)) == n
    # returning loan 55 frees copy 1, which is then the lowest available copy
    r = app.post("/api/loans/55/return", {}, user="ivan", now=NOW)
    assert r.status == 200
    assert get(app, "/api/copies/1")["status"] == "available"
    assert get(app, "/api/books/1")["status"] == "available"
    assert app.post("/api/books/1/borrow", {}, user="dara", now=NOW).status == 200
    assert get(app, "/api/loans?member=4")["items"][-1]["copy"] == 1


def test_returning_frees_the_copy():
    app = fresh_app()
    r = app.post("/api/loans/52/return", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["copy"] == 22
    b = get(app, "/api/books/22")
    assert b["status"] == "available" and b["available_copies"] == 2
    r = app.post("/api/books/22/borrow", {"member": 4}, user="ben", now=NOW)
    assert r.status == 200 and r.json["available_copies"] == 1
    assert get(app, "/api/loans?member=4")["items"][-1]["copy"] == 22


def test_book_without_copies_is_unavailable():
    app = fresh_app()
    r = app.post("/api/books", {"title": "New Book", "author": "A. Writer", "isbn": "978-9-9999-999-9"},
                 user="ada", now=NOW)
    assert r.status == 201, r
    bid = r.json["id"]
    assert r.json["status"] == "unavailable" and r.json["available_copies"] == 0
    before = outbox(app)
    assert_error(app.post(f"/api/books/{bid}/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert "borrow" not in parse_ui(app.get(f"/ui/books/{bid}", user="chen", now=NOW).text).actions
    r = app.post("/api/copies", {"book": bid, "barcode": "NEW-0001"}, user="ben", now=NOW)
    assert r.status == 201, r
    cid = r.json["id"]
    assert cid > 42 and r.json["book"] == bid and r.json["status"] == "available"
    assert get(app, f"/api/books/{bid}")["status"] == "available"
    assert app.post(f"/api/books/{bid}/borrow", {}, user="chen", now=NOW).status == 200
    assert get(app, f"/api/loans?book={bid}")["items"][0]["copy"] == cid


def test_copies_write_rules():
    app = fresh_app()
    for user in ("chen", "lena"):
        assert_error(app.post("/api/copies", {"book": 3, "barcode": "X1"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/copies", {}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/copies/3", {"barcode": "X2"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/copies/41", user=user, now=NOW), 403, "forbidden")
    for body in ({"book": 3}, {"barcode": "X3"}, {"book": 3, "barcode": "C0001"}, {"book": 999, "barcode": "X4"},
                 {"book": 3, "barcode": ""}, {"book": 3, "barcode": "X5", "status": "available"}):
        assert_error(app.post("/api/copies", body, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/copies/3", {"book": 4}, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/copies/3", {"barcode": "C0004"}, user="ada", now=NOW), 400, "validation")
    r = app.patch("/api/copies/3", {"barcode": "C0003-A"}, user="ada", now=NOW)
    assert r.status == 200 and r.json["barcode"] == "C0003-A" and r.json["book"] == 3
    assert_error(app.delete("/api/copies/2", user="ada", now=NOW), 409, "conflict")    # has (returned) loan 39
    assert ids(app.get("/api/copies", user="ada", now=NOW)) == list(range(1, 43))
    assert app.delete("/api/copies/41", user="ada", now=NOW).status == 204
    assert get(app, "/api/books/1")["status"] == "on_loan"


def test_deleting_a_book_removes_its_copies():
    app = fresh_app()
    assert app.delete("/api/books/3", user="ada", now=NOW).status == 204
    assert_error(app.get("/api/copies/3", user="ada", now=NOW), 404, "not_found")
    assert 3 not in ids(app.get("/api/copies", user="ada", now=NOW))
    assert_error(app.delete("/api/books/2", user="ada", now=NOW), 409, "conflict")
    assert app.get("/api/copies/2", user="ada", now=NOW).status == 200


def test_base_rules_preserved():
    app = fresh_app()
    before = outbox(app)
    assert_error(app.post("/api/books/22/borrow", {}, user="hana", now=NOW), 409, "conflict")      # 3 loans
    assert_error(app.post("/api/books/22/borrow", {"member": 12}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/22/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/4/borrow", {}, user="chen", now=NOW), 409, "conflict")
    assert outbox(app) == before
    assert get(app, "/api/copies/42")["status"] == "available"
    body = {"book": 22, "copy": 42, "member": 3, "borrowed_at": NOW, "due_at": "2026-03-15"}
    assert_error(app.post("/api/loans", body, user="ada", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/loans/52", {"copy": 42}, user="ada", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/loans", user="chen", now=NOW)) == [13, 15, 43, 52]


def test_ui_copies():
    app = fresh_app()
    assert parse_ui(app.get("/ui/copies", user="chen", now=NOW).text).rows == list(range(1, 43))
    ui = parse_ui(app.get("/ui/copies/42", user="chen", now=NOW).text)
    assert ui.fields["barcode"] == "C0022-2" and ui.fields["status"] == "available"
    ui = parse_ui(app.get("/ui/books/1", user="chen", now=NOW).text)
    assert ui.fields["status"] == "available" and ui.fields["available_copies"] == "1"
    assert "borrow" in ui.actions
    assert "borrow" not in parse_ui(app.get("/ui/books/4", user="chen", now=NOW).text).actions
    assert app.get("/ui/copies/new", user="chen", now=NOW).status == 403
    r = app.get("/ui/copies/new", user="ada", now=NOW)
    assert r.status == 200
    ui = parse_ui(r.text)
    assert ui.creates == ["copies"] and {"book", "barcode"} <= set(ui.inputs) and "status" not in ui.inputs
