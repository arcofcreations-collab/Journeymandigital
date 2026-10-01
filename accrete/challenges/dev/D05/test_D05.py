"""D05 (library): new staff role `assistant` with a restricted permission set.

Seed facts used: ada/ben librarians (1, 2); chen 3, dara 4 (open loan 59), jo 10 (3 open loans),
lena 12 inactive; loan 46 (jo) and 52 (chen) open; 60 loans; 12 members; book 1 on loan, book 3 available.
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


def make_assistant(app):
    r = app.post("/api/members", {"username": "asha", "name": "Asha Bose", "role": "assistant"}, user="ada", now=NOW)
    assert r.status == 201, r
    assert r.json["role"] == "assistant" and r.json["active"] is True
    return r.json["id"]


def test_librarian_creates_assistant_and_role_validation():
    app = fresh_app()
    aid = make_assistant(app)
    assert ids(app.get("/api/members?role=assistant", user="ada", now=NOW)) == [aid]
    assert_error(app.post("/api/members", {"username": "x1", "name": "X", "role": "admin"}, user="ada", now=NOW),
                 400, "validation")
    assert_error(app.post("/api/members", {"username": "x2", "name": "X", "role": "assistant"}, user="chen", now=NOW),
                 403, "forbidden")
    assert_error(app.post("/api/members", {"username": "x3", "name": "X", "role": "member"}, user="asha", now=NOW),
                 403, "forbidden")


def test_assistant_reads_all_books_members_and_loans():
    app = fresh_app()
    aid = make_assistant(app)
    assert ids(app.get("/api/members", user="asha", now=NOW)) == list(range(1, 13)) + [aid]
    assert ids(app.get("/api/loans", user="asha", now=NOW)) == list(range(1, 61))
    assert ids(app.get("/api/books", user="asha", now=NOW)) == list(range(1, 41))
    r = app.get("/api/members/12", user="asha", now=NOW)
    assert r.status == 200 and r.json["active"] is False
    assert app.get("/api/loans/46", user="asha", now=NOW).json["member"] == 10


def test_assistant_lends_with_all_borrow_rules():
    app = fresh_app()
    make_assistant(app)
    n = len(outbox(app))
    r = app.post("/api/books/3/borrow", {"member": 4}, user="asha", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan", r
    loan = app.get("/api/loans?book=3", user="ada", now=NOW).json["items"][0]
    assert loan["member"] == 4 and loan["due_at"] == "2026-03-15" and loan["borrowed_at"] == NOW
    msgs = outbox(app)
    assert len(msgs) == n + 1 and msgs[-1]["channel"] == "loan_created"
    assert msgs[-1]["payload"] == {"loan": loan["id"], "book": 3, "member": 4}
    assert_error(app.post("/api/books/13/borrow", {"member": 10}, user="asha", now=NOW), 409, "conflict")  # limit
    assert_error(app.post("/api/books/13/borrow", {"member": 12}, user="asha", now=NOW), 409, "conflict")  # inactive
    assert_error(app.post("/api/books/1/borrow", {"member": 3}, user="asha", now=NOW), 409, "conflict")   # on loan
    assert len(outbox(app)) == n + 1


def test_assistant_returns_any_loan():
    app = fresh_app()
    make_assistant(app)
    r = app.post("/api/loans/46/return", {}, user="asha", now=NOW)
    assert r.status == 200 and r.json["returned_at"] == NOW
    assert_error(app.post("/api/loans/1/return", {}, user="asha", now=NOW), 409, "conflict")


def test_assistant_deactivates_and_reactivates_member():
    app = fresh_app()
    make_assistant(app)
    r = app.patch("/api/members/4", {"active": False}, user="asha", now=NOW)
    assert r.status == 200 and r.json["active"] is False and r.json["name"] == "Dara Novak"
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="asha", now=NOW), 409, "conflict")
    r = app.patch("/api/members/12", {"active": True}, user="asha", now=NOW)
    assert r.status == 200 and r.json["active"] is True
    assert app.post("/api/books/3/borrow", {"member": 12}, user="asha", now=NOW).status == 200


def test_assistant_cannot_patch_other_fields_or_staff_records():
    app = fresh_app()
    make_assistant(app)
    for body in ({"name": "X"}, {"role": "librarian"}, {"username": "dd"}, {"active": False, "name": "X"}):
        assert_error(app.patch("/api/members/4", body, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/members/1", {"active": False}, user="asha", now=NOW), 403, "forbidden")
    other = app.post("/api/members", {"username": "bob", "name": "Bob", "role": "assistant"}, user="ada", now=NOW).json
    assert_error(app.patch(f"/api/members/{other['id']}", {"active": False}, user="asha", now=NOW), 403, "forbidden")
    m = app.get("/api/members/4", user="ada", now=NOW).json
    assert m["name"] == "Dara Novak" and m["active"] is True and m["role"] == "member"
    assert app.get("/api/members/1", user="ada", now=NOW).json["active"] is True


def test_assistant_own_record_name_only():
    app = fresh_app()
    aid = make_assistant(app)
    r = app.patch(f"/api/members/{aid}", {"name": "Asha B."}, user="asha", now=NOW)
    assert r.status == 200 and r.json["name"] == "Asha B."
    assert_error(app.patch(f"/api/members/{aid}", {"active": False}, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.patch(f"/api/members/{aid}", {"role": "librarian"}, user="asha", now=NOW), 403, "forbidden")
    assert app.get(f"/api/members/{aid}", user="ada", now=NOW).json["role"] == "assistant"


def test_assistant_cannot_write_books_members_or_loans():
    app = fresh_app()
    make_assistant(app)
    book = {"title": "T", "author": "A", "isbn": "isbn-asst"}
    assert_error(app.post("/api/books", book, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books", {}, user="asha", now=NOW), 403, "forbidden")  # 403 before 400
    assert_error(app.patch("/api/books/3", {"title": "X"}, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/books/3", user="asha", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/members/12", user="asha", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans", {"book": 3, "member": 3}, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/loans/52", {"due_at": "2026-04-01"}, user="asha", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/loans/52", user="asha", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/books", user="ada", now=NOW)) == list(range(1, 41))
    assert app.get("/api/members/12", user="ada", now=NOW).status == 200


def test_promoting_member_to_assistant_grants_rights():
    app = fresh_app()
    assert_error(app.patch("/api/members/3", {"role": "assistant"}, user="chen", now=NOW), 403, "forbidden")
    r = app.patch("/api/members/3", {"role": "assistant"}, user="ada", now=NOW)
    assert r.status == 200 and r.json["role"] == "assistant"
    assert ids(app.get("/api/loans", user="chen", now=NOW)) == list(range(1, 61))
    assert app.post("/api/books/3/borrow", {"member": 4}, user="chen", now=NOW).status == 200


def test_member_and_librarian_rights_unchanged():
    app = fresh_app()
    make_assistant(app)
    assert ids(app.get("/api/members", user="chen", now=NOW)) == [3]
    assert_error(app.patch("/api/members/4", {"active": False}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    r = app.post("/api/books", {"title": "T", "author": "A", "isbn": "isbn-lib"}, user="ben", now=NOW)
    assert r.status == 201, r
    r = app.patch("/api/members/4", {"name": "Dara N."}, user="ada", now=NOW)
    assert r.status == 200 and r.json["name"] == "Dara N."


def test_ui_for_assistant():
    app = fresh_app()
    aid = make_assistant(app)
    assert app.get("/ui/books/new", user="asha", now=NOW).status == 403
    assert app.get("/ui/members/new", user="asha", now=NOW).status == 403
    assert app.get("/ui/loans/new", user="asha", now=NOW).status == 403
    assert parse_ui(app.get("/ui/members", user="asha", now=NOW).text).rows == list(range(1, 13)) + [aid]
    assert "return" in parse_ui(app.get("/ui/loans/52", user="asha", now=NOW).text).actions
    assert "return" not in parse_ui(app.get("/ui/loans/1", user="asha", now=NOW).text).actions
    assert "borrow" in parse_ui(app.get("/ui/books/3", user="asha", now=NOW).text).actions
    r = app.get("/ui/members/new", user="ada", now=NOW)
    assert r.status == 200 and "role" in parse_ui(r.text).inputs
