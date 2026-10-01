"""HTML UI conventions: data-id rows, data-field values, data-action and data-create forms."""
import io
import sys
from urllib.parse import urlencode

from accept_client import parse_ui


def test_list_pages_show_readable_rows(app):
    assert parse_ui(app.get("/ui/books", user="chen").text).rows == list(range(1, 41))
    assert parse_ui(app.get("/ui/members", user="chen").text).rows == [3]
    loans = parse_ui(app.get("/ui/loans", user="chen").text).rows
    assert loans == [l["id"] for l in app.get("/api/loans", user="chen").json["items"]]


def test_ui_requires_authentication(app):
    assert app.get("/ui/books").status == 401


def test_book_detail_fields_and_actions(app):
    page = parse_ui(app.get("/ui/books/2", user="chen").text)
    assert page.fields == {"title": "The Lantern Song 2", "author": "T. Okoye", "isbn": "978-0-1014-002-2",
                           "year": "2005", "status": "available"}
    assert page.actions == ["borrow"]
    assert parse_ui(app.get("/ui/books/4", user="chen").text).actions == []  # on loan
    assert parse_ui(app.get("/ui/books/2", user="jo").text).actions == []  # 3 open loans
    assert parse_ui(app.get("/ui/books/2", user="lena").text).actions == []  # inactive
    assert parse_ui(app.get("/ui/books/4", user="chen").text).fields["year"] == ""


def test_librarian_borrow_form_offers_member_choice(app):
    page = parse_ui(app.get("/ui/books/2", user="ada").text)
    assert page.actions == ["borrow"] and "member" in page.inputs


def test_loan_detail_shows_return_only_when_allowed(app):
    page = parse_ui(app.get("/ui/loans/52", user="chen").text)
    assert page.fields["member"] == "3" and page.fields["returned_at"] == "" and page.fields["overdue"] == "false"
    assert page.actions == ["return"]
    assert parse_ui(app.get("/ui/loans/1", user="ada").text).actions == []  # already returned
    assert app.get("/ui/loans/46", user="chen").status == 403
    assert app.get("/ui/loans/999", user="chen").status == 404


def test_member_detail(app):
    page = parse_ui(app.get("/ui/members/12", user="ada").text)
    assert page.fields == {"username": "lena", "name": "Lena Okafor", "role": "member", "active": "false"}
    assert page.actions == []
    assert app.get("/ui/members/12", user="chen").status == 403


def test_create_forms(app):
    books = parse_ui(app.get("/ui/books/new", user="ada").text)
    assert books.creates == ["books"] and sorted(books.inputs) == ["author", "isbn", "title", "year"]
    members = parse_ui(app.get("/ui/members/new", user="ada").text)
    assert members.creates == ["members"] and sorted(members.inputs) == ["active", "name", "role", "username"]
    assert app.get("/ui/books/new", user="chen").status == 403
    assert app.get("/ui/members/new", user="chen").status == 403
    assert app.get("/ui/loans/new", user="ada").status == 403


def _post_form(app, path, form, user):
    """POST an HTML form (urlencoded) the way a browser would; returns (status, headers, body)."""
    data = urlencode(form).encode()
    environ = {
        "REQUEST_METHOD": "POST", "PATH_INFO": path, "QUERY_STRING": "", "SERVER_NAME": "test",
        "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.version": (1, 0), "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(data), "wsgi.errors": sys.stderr, "wsgi.multithread": False,
        "wsgi.multiprocess": False, "wsgi.run_once": False, "CONTENT_LENGTH": str(len(data)),
        "CONTENT_TYPE": "application/x-www-form-urlencoded", "HTTP_X_USER": user,
        "HTTP_X_NOW": "2026-03-01T12:00:00",
    }
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured.update(status=int(status.split()[0]), headers=dict(headers))

    body = b"".join(app.wsgi(environ, start_response))
    return captured["status"], captured["headers"], body.decode()


def test_ui_forms_post_through_services(app):
    code, headers, _ = _post_form(app, "/ui/books", {"title": "T", "author": "A", "isbn": "X-1", "year": "2001"}, "ada")
    assert code == 303 and headers["Location"].endswith("/ui/books/41")
    assert app.get("/api/books/41", user="ada").json["year"] == 2001
    code, _, _ = _post_form(app, "/ui/books/41/borrow", {"member": "4"}, "ada")
    assert code == 303 and app.get("/api/books/41", user="ada").json["status"] == "on_loan"
    code, _, _ = _post_form(app, "/ui/books", {"title": "T", "author": "A", "isbn": "X-2", "year": "soon"}, "ada")
    assert code == 400
    code, _, _ = _post_form(app, "/ui/members", {"username": "u1", "name": "U", "role": "member", "active": "false"}, "ada")
    assert code == 303 and app.get("/api/members/13", user="ada").json["active"] is False
