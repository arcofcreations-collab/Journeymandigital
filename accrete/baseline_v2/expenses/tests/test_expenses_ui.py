"""HTML UI conventions: data-id rows, data-field values, data-action and data-create forms."""
import io
import sys
from urllib.parse import urlencode

from accept_client import parse_ui


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


def test_list_rows_match_readable_records(app):
    for user in ("priya", "omar", "fiona"):
        api_ids = [c["id"] for c in app.get("/api/claims", user=user).json["items"]]
        assert parse_ui(app.get("/ui/claims", user=user).text).rows == api_ids
    assert parse_ui(app.get("/ui/employees", user="priya").text).rows == list(range(1, 16))
    assert app.get("/ui/claims").status == 401


def test_claim_detail_fields(app):
    page = parse_ui(app.get("/ui/claims/7", user="yusuf").text)
    assert page.fields == {"employee": "14", "amount": "613.88", "category": "equipment",
                           "description": "Hotel night #7", "status": "rejected",
                           "submitted_at": "2026-01-28T11:00:00", "decided_at": "2026-01-30T09:00:00",
                           "decided_by": "4", "rejection_reason": "Missing receipt"}
    assert page.actions == []
    assert app.get("/ui/claims/7", user="priya").status == 403
    assert app.get("/ui/claims/999", user="priya").status == 404


def test_claim_actions_depend_on_role_and_state(app):
    def actions(claim_id, user):
        return parse_ui(app.get(f"/ui/claims/{claim_id}", user=user).text).actions

    assert actions(1, "wen") == ["submit"]  # owner, draft
    assert actions(1, "marco") == []  # manager, draft
    assert actions(2, "omar") == ["approve", "reject"]
    assert actions(2, "victor") == []
    assert actions(2, "fiona") == []
    assert actions(4, "fiona") == ["pay"]
    assert actions(4, "nadia") == []
    reject = parse_ui(app.get("/ui/claims/2", user="omar").text)
    assert "reason" in reject.inputs


def test_employee_detail(app):
    page = parse_ui(app.get("/ui/employees/5", user="zoe").text)
    assert page.fields == {"username": "priya", "name": "Priya Kim", "role": "employee", "manager": "4",
                           "department": "Engineering"}
    assert parse_ui(app.get("/ui/employees/1", user="zoe").text).fields["manager"] == ""


def test_create_forms(app):
    claims = parse_ui(app.get("/ui/claims/new", user="priya").text)
    assert claims.creates == ["claims"] and sorted(claims.inputs) == ["amount", "category", "description"]
    employees = parse_ui(app.get("/ui/employees/new", user="fiona").text)
    assert employees.creates == ["employees"]
    assert sorted(employees.inputs) == ["department", "manager", "name", "role", "username"]
    assert app.get("/ui/employees/new", user="marco").status == 403


def test_ui_forms_post_through_services(app):
    status, headers, _ = _post_form(app, "/ui/claims", {"amount": "18.40", "category": "meals", "description": "Taxi"}, "sam")
    assert status == 303 and headers["Location"].endswith("/ui/claims/81")
    assert app.get("/api/claims/81", user="sam").json["amount"] == 18.4
    assert _post_form(app, "/ui/claims/81/submit", {}, "sam")[0] == 303
    assert _post_form(app, "/ui/claims/81/reject", {"reason": ""}, "omar")[0] == 400
    assert _post_form(app, "/ui/claims/81/reject", {"reason": "Duplicate"}, "omar")[0] == 303
    assert app.get("/api/claims/81", user="sam").json["rejection_reason"] == "Duplicate"
    assert _post_form(app, "/ui/claims", {"amount": "lots", "category": "meals", "description": "x"}, "sam")[0] == 400
    status, _, _ = _post_form(app, "/ui/employees", {"username": "ann", "name": "Ann", "role": "employee",
                                                     "manager": "", "department": "Ops"}, "fiona")
    assert status == 303 and app.get("/api/employees/16", user="ann").json["manager"] is None
