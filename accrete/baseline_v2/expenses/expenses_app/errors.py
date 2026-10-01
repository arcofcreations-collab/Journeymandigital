"""Application errors and their HTTP rendering.

Services raise these exceptions; the handlers below turn them into the contract's error
shape ``{"error", "message", "fields"}`` for the API, or an HTML error page for the UI.
When several problems apply, services check in contract order: 404, 403, 409, 400
(401 is handled before routing, in ``auth``).
"""
from flask import render_template, request
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status_code = 500
    code = "internal"
    default_message = "Internal error."

    def __init__(self, message=None, fields=None):
        self.message = message or self.default_message
        self.fields = dict(fields or {})
        super().__init__(self.message)

    def to_dict(self):
        return {"error": self.code, "message": self.message, "fields": self.fields}


class ValidationError(AppError):
    status_code = 400
    code = "validation"
    default_message = "Invalid input."


class Unauthenticated(AppError):
    status_code = 401
    code = "unauthenticated"
    default_message = "Missing or unknown X-User."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "You are not allowed to do this."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Not found."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Not allowed in the record's current state."


# Werkzeug errors raised by routing/request parsing, mapped onto contract error codes.
_HTTP_ERRORS = {
    400: ("validation", "Malformed request."),
    404: ("not_found", "Unknown collection, record or action."),
    405: ("method_not_allowed", "Method not allowed for this URL."),
}


def _render(error):
    if request.path.startswith("/ui"):
        html = render_template("error.html", error=error)
        return html, error.status_code
    return error.to_dict(), error.status_code


def init_app(app):
    @app.errorhandler(AppError)
    def handle_app_error(error):
        return _render(error)

    @app.errorhandler(HTTPException)
    def handle_http_exception(exc):
        code, message = _HTTP_ERRORS.get(exc.code, ("error", exc.description))
        error = AppError(message)
        error.status_code = exc.code
        error.code = code
        return _render(error)
