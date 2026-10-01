"""Loans: borrowing and returning, limits, permissions, derived overdue, outbox."""

NOW = "2026-03-01T10:00:00"


def test_member_borrows_book(app):
    r = app.post("/api/books/3/borrow", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["id"] == 3 and r.json["status"] == "on_loan"
    loan = app.get("/api/loans?book=3&returned_at=null", user="chen").json["items"][0]
    assert loan == {"id": 61, "book": 3, "member": 3, "borrowed_at": NOW, "due_at": "2026-03-15",
                    "returned_at": None, "overdue": False}
    outbox = app.get("/api/_outbox", user="dara").json["items"]
    assert outbox == [{"id": 1, "channel": "loan_created", "payload": {"loan": 61, "book": 3, "member": 3},
                       "created_at": NOW}]


def test_borrowing_a_book_on_loan_is_409(app):
    assert app.post("/api/books/4/borrow", {}, user="chen").status == 409


def test_inactive_member_cannot_borrow(app):
    assert app.post("/api/books/3/borrow", {}, user="lena").status == 409


def test_member_with_three_open_loans_cannot_borrow(app):
    assert app.post("/api/books/3/borrow", {}, user="jo").status == 409
    assert app.post("/api/books/3/borrow", {}, user="ivan").status == 200  # ivan has 2
    assert app.post("/api/books/2/borrow", {}, user="ivan").status == 409


def test_librarian_lends_to_member(app):
    r = app.post("/api/books/3/borrow", {"member": 5}, user="ada")
    assert r.status == 200
    assert app.get("/api/loans/61", user="eli").json["member"] == 5
    assert app.get("/api/_outbox", user="ada").json["items"][0]["payload"] == {"loan": 61, "book": 3, "member": 5}


def test_librarian_lending_rules(app):
    assert app.post("/api/books/3/borrow", {"member": 12}, user="ada").status == 409  # inactive
    assert app.post("/api/books/3/borrow", {"member": 999}, user="ada").status == 400
    assert app.post("/api/books/3/borrow", {"member": "chen"}, user="ada").status == 400
    assert app.post("/api/books/4/borrow", {"member": 999}, user="ada").status == 409  # 409 beats 400


def test_member_cannot_borrow_for_someone_else(app):
    assert app.post("/api/books/3/borrow", {"member": 4}, user="chen").status == 403
    assert app.post("/api/books/4/borrow", {"member": 4}, user="chen").status == 403  # 403 beats 409
    assert app.post("/api/books/3/borrow", {"member": 3}, user="chen").status == 200
    assert app.get("/api/_outbox", user="chen").json["items"][0]["payload"]["member"] == 3


def test_return_by_borrower(app):
    r = app.post("/api/loans/52/return", {}, user="chen", now=NOW)
    assert r.status == 200
    assert r.json["returned_at"] == NOW and r.json["overdue"] is False and r.json["id"] == 52
    assert app.get("/api/books/22", user="chen").json["status"] == "available"
    assert app.post("/api/loans/52/return", {}, user="chen").status == 409


def test_return_permissions(app):
    assert app.post("/api/loans/52/return", {}, user="dara").status == 403
    assert app.post("/api/loans/1/return", {}, user="dara").status == 409  # dara's, already returned
    assert app.post("/api/loans/52/return", {}, user="ben").status == 200
    assert app.post("/api/loans/999/return", {}, user="ben").status == 404


def test_overdue_is_derived_from_x_now(app):
    assert app.get("/api/loans/52", user="chen", now="2026-03-04T23:59:59").json["overdue"] is False
    assert app.get("/api/loans/52", user="chen", now="2026-03-05T00:00:00").json["overdue"] is True
    assert app.get("/api/loans/1", user="ada", now="2027-01-01T00:00:00").json["overdue"] is False  # returned
    overdue = app.get("/api/loans?overdue=true", user="ada", now="2026-03-01T12:00:00").json["items"]
    assert [l["id"] for l in overdue] == [46, 47, 48, 49, 50]


def test_member_reads_only_own_loans(app):
    loans = app.get("/api/loans", user="chen").json["items"]
    assert loans and all(l["member"] == 3 for l in loans)
    assert app.get("/api/loans/46", user="chen").status == 403
    assert app.get("/api/loans/52", user="chen").status == 200
    assert app.get("/api/loans/999", user="chen").status == 404


def test_loans_cannot_be_created_edited_or_deleted_directly(app):
    assert app.post("/api/loans", {"book": 3, "member": 3}, user="ada").status == 403
    assert app.patch("/api/loans/52", {"due_at": "2030-01-01"}, user="ada").status == 403
    assert app.delete("/api/loans/52", user="ada").status == 403
    assert app.patch("/api/loans/999", {}, user="ada").status == 404
    assert app.delete("/api/loans/999", user="ada").status == 404


def test_failed_action_changes_nothing(app):
    app.post("/api/books/4/borrow", {}, user="chen")
    assert app.get("/api/_outbox", user="chen").json["items"] == []
    assert len(app.get("/api/loans", user="ada").json["items"]) == 60
