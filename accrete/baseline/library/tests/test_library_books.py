"""Books: readable by all, librarian-only management, derived status, validation."""

NEW_BOOK = {"title": "Dune", "author": "F. Herbert", "isbn": "978-0441013593", "year": 1965}


def test_any_user_reads_books_with_status(app):
    books = app.get("/api/books", user="lena").json["items"]
    assert len(books) == 40
    by_id = {b["id"]: b for b in books}
    assert by_id[4]["status"] == "on_loan"  # open loan 46
    assert by_id[2]["status"] == "available"
    assert app.get("/api/books/4", user="chen").json["status"] == "on_loan"


def test_librarian_creates_book(app):
    r = app.post("/api/books", NEW_BOOK, user="ada")
    assert r.status == 201
    assert r.json == {"id": 41, **NEW_BOOK, "status": "available"}


def test_year_is_optional(app):
    r = app.post("/api/books", {k: v for k, v in NEW_BOOK.items() if k != "year"}, user="ada")
    assert r.status == 201 and r.json["year"] is None


def test_member_cannot_manage_books(app):
    assert app.post("/api/books", NEW_BOOK, user="chen").status == 403
    assert app.post("/api/books", {"bogus": 1}, user="chen").status == 403  # 403 before 400
    assert app.patch("/api/books/2", {"title": "x"}, user="chen").status == 403
    assert app.delete("/api/books/2", user="chen").status == 403
    assert app.patch("/api/books/999", {"title": "x"}, user="chen").status == 404


def test_book_validation(app):
    r = app.post("/api/books", {"title": "Only title"}, user="ada")
    assert r.status == 400 and set(r.json["fields"]) == {"author", "isbn"}
    dup = dict(NEW_BOOK, isbn="978-0-1007-001-1")
    assert app.post("/api/books", dup, user="ada").json["fields"] == {"isbn": "already in use"}
    assert app.post("/api/books", dict(NEW_BOOK, year="1965"), user="ada").status == 400
    assert app.post("/api/books", dict(NEW_BOOK, status="on_loan"), user="ada").status == 400
    assert app.patch("/api/books/2", {"isbn": "978-0-1007-001-1"}, user="ada").status == 400
    assert app.patch("/api/books/2", {"title": None}, user="ada").status == 400


def test_librarian_updates_book(app):
    r = app.patch("/api/books/2", {"title": "New Title", "year": None}, user="ada")
    assert r.status == 200 and r.json["title"] == "New Title" and r.json["year"] is None
    assert r.json["author"] == "T. Okoye"


def test_delete_book(app):
    assert app.delete("/api/books/1", user="ada").status == 409  # has loans
    created = app.post("/api/books", NEW_BOOK, user="ada").json
    assert app.delete(f"/api/books/{created['id']}", user="ada").status == 204
    assert app.get(f"/api/books/{created['id']}", user="ada").status == 404
