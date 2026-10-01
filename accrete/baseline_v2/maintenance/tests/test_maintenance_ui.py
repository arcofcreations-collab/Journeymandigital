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


def _actions(app, order_id, user):
    return parse_ui(app.get(f"/ui/work_orders/{order_id}", user=user).text).actions


def test_list_rows_match_readable_records(app):
    for user in ("ruth", "nils", "mei", "sofia"):
        api_ids = [o["id"] for o in app.get("/api/work_orders", user=user).json["items"]]
        assert parse_ui(app.get("/ui/work_orders", user=user).text).rows == api_ids
    assert parse_ui(app.get("/ui/staff", user="ruth").text).rows == list(range(1, 17))
    assert parse_ui(app.get("/ui/assets", user="ruth").text).rows == list(range(1, 32))
    assert parse_ui(app.get("/ui/work_orders?status=open&asset=22", user="sofia").text).rows == [78]
    assert app.get("/ui/work_orders").status == 401


def test_work_order_detail_fields(app):
    page = parse_ui(app.get("/ui/work_orders/79", user="olga").text)
    assert page.fields == {
        "asset": "13", "title": "Zone 3 fault", "description": "", "priority": "urgent", "status": "in_progress",
        "requested_by": "1", "created_at": "2026-02-28T15:00:00", "assignee": "9",
        "started_at": "2026-02-28T16:00:00", "completed_at": "", "resolution": "", "labor_minutes": "",
        "cancel_reason": "", "due_date": "2026-03-01", "overdue": "false",
    }
    assert page.actions == ["complete"]
    assert app.get("/ui/work_orders/79", user="ruth").status == 403
    assert app.get("/ui/work_orders/999", user="ruth").status == 404


def test_staff_and_asset_detail(app):
    assert parse_ui(app.get("/ui/staff/13", user="ruth").text).fields == {
        "username": "umar", "name": "Umar Farouk", "role": "technician", "site": "North", "active": "false"}
    assert parse_ui(app.get("/ui/assets/16", user="ruth").text).fields == {
        "tag": "S-CNV-01", "name": "Conveyor line A", "site": "South", "criticality": "high",
        "retired": "false", "open_orders": "2"}
    assert app.get("/ui/assets/99", user="ruth").status == 404


def test_actions_depend_on_role_and_state(app):
    assert _actions(app, 74, "sofia") == ["assign", "cancel"]  # open
    assert _actions(app, 74, "ruth") == ["cancel"]  # requester, open
    assert _actions(app, 74, "olga") == []  # technician at the site
    assert _actions(app, 77, "sofia") == ["assign", "cancel"]  # assigned: re-assign
    assert _actions(app, 77, "ruth") == []  # requester, no longer open
    assert _actions(app, 77, "nils") == ["start"]
    assert _actions(app, 79, "sofia") == ["cancel"]  # in progress
    assert _actions(app, 79, "olga") == ["complete"]
    assert _actions(app, 2, "sofia") == []  # completed
    assign = parse_ui(app.get("/ui/work_orders/74", user="sofia").text)
    assert {"technician", "reason"} <= set(assign.inputs)


def test_create_forms(app):
    for user in ("ruth", "nils", "sofia"):
        page = parse_ui(app.get("/ui/work_orders/new", user=user).text)
        assert page.creates == ["work_orders"]
        assert sorted(page.inputs) == ["asset", "description", "priority", "title"]
    staff = parse_ui(app.get("/ui/staff/new", user="sofia").text)
    assert staff.creates == ["staff"] and sorted(staff.inputs) == ["active", "name", "role", "site", "username"]
    assets = parse_ui(app.get("/ui/assets/new", user="yara").text)
    assert assets.creates == ["assets"]
    assert sorted(assets.inputs) == ["criticality", "name", "retired", "site", "tag"]
    for user in ("ruth", "nils"):
        assert app.get("/ui/staff/new", user=user).status == 403
        assert app.get("/ui/assets/new", user=user).status == 403
    assert app.get("/ui/work_orders/new").status == 401


def test_ui_forms_post_through_services(app):
    status, headers, _ = _post_form(app, "/ui/work_orders",
                                    {"asset": "2", "title": "Drip", "description": "", "priority": "low"}, "ruth")
    assert status == 303 and headers["Location"].endswith("/ui/work_orders/83")
    created = app.get("/api/work_orders/83", user="ruth").json
    assert (created["asset"], created["description"], created["priority"]) == (2, None, "low")
    assert _post_form(app, "/ui/work_orders", {"asset": "14", "title": "x", "priority": "low"}, "ruth")[0] == 403
    assert _post_form(app, "/ui/work_orders/83/assign", {"technician": "8"}, "sofia")[0] == 303
    assert _post_form(app, "/ui/work_orders/83/start", {}, "nils")[0] == 303
    assert _post_form(app, "/ui/work_orders/83/complete", {"resolution": "Fixed", "labor_minutes": "x"}, "nils")[0] == 400
    assert _post_form(app, "/ui/work_orders/83/complete", {"resolution": "Fixed", "labor_minutes": "20"}, "nils")[0] == 303
    assert app.get("/api/work_orders/83", user="ruth").json["labor_minutes"] == 20
    assert _post_form(app, "/ui/work_orders/74/cancel", {"reason": ""}, "ruth")[0] == 400
    assert _post_form(app, "/ui/work_orders/74/cancel", {"reason": "Gone"}, "ruth")[0] == 303
    status, _, _ = _post_form(app, "/ui/staff", {"username": "ann", "name": "Ann", "role": "technician",
                                                 "site": "East", "active": "false"}, "yara")
    assert status == 303 and app.get("/api/staff/17", user="ann").json["active"] is False
    status, _, _ = _post_form(app, "/ui/assets", {"tag": "E-X-1", "name": "X", "site": "East",
                                                  "criticality": "low", "retired": "false"}, "yara")
    assert status == 303 and app.get("/api/assets/32", user="ann").json["retired"] is False
