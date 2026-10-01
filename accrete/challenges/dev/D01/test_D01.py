"""D01 (library): authors become records; books.author becomes a reference (data migration).

Seed facts (computed from spec/apps/library_seed.json, books in ascending id order):
  first appearance -> author id:
    1 M. Reyes     (8 books) 1 9 12 18 24 32 36 38
    2 T. Okoye     (8 books) 2 5 10 16 27 28 33 37
    3 S. Lindqvist (5 books) 3 4 11 21 29
    4 R. Banerjee  (5 books) 6 8 13 14 26
    5 J. Moreau    (8 books) 7 15 17 25 31 35 39 40
    6 K. Tanaka    (6 books) 19 20 22 23 30 34
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

AUTHORS = {
    1: ("M. Reyes", [1, 9, 12, 18, 24, 32, 36, 38]),
    2: ("T. Okoye", [2, 5, 10, 16, 27, 28, 33, 37]),
    3: ("S. Lindqvist", [3, 4, 11, 21, 29]),
    4: ("R. Banerjee", [6, 8, 13, 14, 26]),
    5: ("J. Moreau", [7, 15, 17, 25, 31, 35, 39, 40]),
    6: ("K. Tanaka", [19, 20, 22, 23, 30, 34]),
}
BOOK_AUTHOR = {b: aid for aid, (_, books) in AUTHORS.items() for b in books}


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def test_authors_migrated_in_first_appearance_order():
    app = fresh_app()
    r = app.get("/api/authors", user="chen", now=NOW)
    assert r.status == 200, r
    items = r.json["items"]
    assert [a["id"] for a in items] == [1, 2, 3, 4, 5, 6]
    for a in items:
        assert a["name"] == AUTHORS[a["id"]][0], a


def test_author_book_counts_after_migration():
    app = fresh_app()
    for aid, (name, books) in AUTHORS.items():
        r = app.get(f"/api/authors/{aid}", user="gus", now=NOW)
        assert r.status == 200, r
        assert r.json["name"] == name
        assert r.json["book_count"] == len(books), (aid, r.json)


def test_every_existing_book_references_its_migrated_author():
    app = fresh_app()
    r = app.get("/api/books", user="eli", now=NOW)
    assert r.status == 200, r
    books = {b["id"]: b for b in r.json["items"]}
    assert sorted(books) == list(range(1, 41))
    for bid, b in books.items():
        aid = BOOK_AUTHOR[bid]
        assert b["author"] == aid, (bid, b["author"])
        assert b["author_name"] == AUTHORS[aid][0], (bid, b.get("author_name"))
    # other fields untouched
    b4 = books[4]
    assert b4["title"] == "The Harbor Year 4" and b4["isbn"] == "978-0-1028-004-4"
    assert b4["year"] is None and b4["status"] == "on_loan"
    assert books[3]["status"] == "available" and books[3]["year"] == 2005


def test_filter_books_by_author_id():
    app = fresh_app()
    assert ids(app.get("/api/books?author=6", user="chen", now=NOW)) == AUTHORS[6][1]
    assert ids(app.get("/api/books?author=3", user="chen", now=NOW)) == AUTHORS[3][1]
    assert ids(app.get("/api/books?author=6&year=2018", user="chen", now=NOW)) == [22, 30]


def test_create_book_with_author_reference():
    app = fresh_app()
    body = {"title": "New Book", "author": 4, "isbn": "978-9-9999-999-9", "year": 2020}
    r = app.post("/api/books", body, user="ada", now=NOW)
    assert r.status == 201, r
    b = r.json
    assert b["author"] == 4 and b["author_name"] == "R. Banerjee"
    assert b["status"] == "available" and b["id"] not in range(1, 41)
    assert app.get("/api/authors/4", user="chen", now=NOW).json["book_count"] == 6
    assert ids(app.get("/api/books?author=4", user="chen", now=NOW)) == AUTHORS[4][1] + [b["id"]]


def test_book_author_must_be_existing_author_id():
    app = fresh_app()
    base = {"title": "T", "isbn": "isbn-new-1", "year": 2000}
    for bad in ("M. Reyes", 999, None):
        assert_error(app.post("/api/books", dict(base, author=bad), user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/books", base, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/books/3", {"author": "Someone Else"}, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/books/3", {"author": 999}, user="ada", now=NOW), 400, "validation")
    assert ids(app.get("/api/books", user="ada", now=NOW)) == list(range(1, 41))
    assert app.get("/api/books/3", user="ada", now=NOW).json["author"] == 3


def test_reassigning_book_author_updates_counts():
    app = fresh_app()
    r = app.patch("/api/books/3", {"author": 1}, user="ben", now=NOW)
    assert r.status == 200, r
    assert r.json["author"] == 1 and r.json["author_name"] == "M. Reyes"
    assert r.json["title"] == "The Atlas House 3"
    assert app.get("/api/authors/1", user="chen", now=NOW).json["book_count"] == 9
    assert app.get("/api/authors/3", user="chen", now=NOW).json["book_count"] == 4


def test_librarian_manages_authors_and_names_are_unique():
    app = fresh_app()
    r = app.post("/api/authors", {"name": "N. Adichie"}, user="ada", now=NOW)
    assert r.status == 201, r
    assert r.json["name"] == "N. Adichie" and r.json["book_count"] == 0
    assert r.json["id"] not in range(1, 7)
    assert_error(app.post("/api/authors", {"name": "M. Reyes"}, user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/authors", {}, user="ada", now=NOW), 400, "validation")
    assert_error(app.patch("/api/authors/2", {"name": "K. Tanaka"}, user="ada", now=NOW), 400, "validation")
    # rename propagates to the derived author_name of the books
    r = app.patch("/api/authors/6", {"name": "Kenji Tanaka"}, user="ben", now=NOW)
    assert r.status == 200 and r.json["name"] == "Kenji Tanaka"
    b = app.get("/api/books/19", user="chen", now=NOW).json
    assert b["author"] == 6 and b["author_name"] == "Kenji Tanaka"


def test_members_cannot_write_authors():
    app = fresh_app()
    assert_error(app.post("/api/authors", {"name": "X"}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/authors", {}, user="chen", now=NOW), 403, "forbidden")  # 403 before 400
    assert_error(app.patch("/api/authors/1", {"name": "X"}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/authors/1", user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/authors/1", user="chen", now=NOW).json["name"] == "M. Reyes"


def test_delete_author_rules():
    app = fresh_app()
    assert_error(app.delete("/api/authors/3", user="ada", now=NOW), 409, "conflict")
    assert app.get("/api/authors/3", user="ada", now=NOW).status == 200
    new = app.post("/api/authors", {"name": "Temp Author"}, user="ada", now=NOW).json
    assert app.delete(f"/api/authors/{new['id']}", user="ada", now=NOW).status == 204
    assert_error(app.get(f"/api/authors/{new['id']}", user="ada", now=NOW), 404, "not_found")
    # an author whose last book was deleted can be deleted
    a = app.post("/api/authors", {"name": "One Book"}, user="ada", now=NOW).json
    b = app.post("/api/books", {"title": "Solo", "author": a["id"], "isbn": "isbn-solo"}, user="ada", now=NOW).json
    assert_error(app.delete(f"/api/authors/{a['id']}", user="ada", now=NOW), 409, "conflict")
    assert app.delete(f"/api/books/{b['id']}", user="ada", now=NOW).status == 204
    assert app.delete(f"/api/authors/{a['id']}", user="ada", now=NOW).status == 204


def test_ui_shows_author_name_and_authors_list():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/books/19", user="chen", now=NOW).text)
    assert ui.fields["author"] == "K. Tanaka"
    assert ui.fields["title"] == "The Signal House 19"
    r = app.get("/ui/authors", user="chen", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == [1, 2, 3, 4, 5, 6]
    r = app.get("/ui/books/new", user="ada", now=NOW)
    assert r.status == 200 and "author" in parse_ui(r.text).inputs
    assert app.get("/ui/authors/new", user="chen", now=NOW).status == 403


def test_borrowing_and_loans_unaffected():
    app = fresh_app()
    r = app.post("/api/books/3/borrow", {}, user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["status"] == "on_loan" and r.json["author"] == 3
    assert ids(app.get("/api/loans", user="ada", now=NOW))[:60] == list(range(1, 61))
    assert app.get("/api/loans/52", user="chen", now=NOW).json["book"] == 22
