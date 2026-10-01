"""JSON API (``/api``). Handlers are thin: read the request, call a service, respond."""
from flask import Blueprint, request

from . import services
from .auth import current_context

bp = Blueprint("api", __name__, url_prefix="/api")

_INVALID_JSON = object()


def _body():
    """The request's JSON body: ``{}`` when empty, a non-dict marker when malformed.

    Services validate the shape themselves, after the 404/403/409 checks, so that
    error precedence holds even for malformed bodies.
    """
    if not request.get_data():
        return {}
    data = request.get_json(force=True, silent=True)
    return _INVALID_JSON if data is None else data


def _filters():
    return request.args.to_dict()


def _items(records):
    return {"items": records}


# --- members --------------------------------------------------------------------------

@bp.get("/members")
def list_members():
    return _items(services.list_members(current_context(), _filters()))


@bp.post("/members")
def create_member():
    return services.create_member(current_context(), _body()), 201


@bp.get("/members/<int:member_id>")
def get_member(member_id):
    return services.get_member(current_context(), member_id)


@bp.patch("/members/<int:member_id>")
def update_member(member_id):
    return services.update_member(current_context(), member_id, _body())


@bp.delete("/members/<int:member_id>")
def delete_member(member_id):
    services.delete_member(current_context(), member_id)
    return "", 204


# --- books ----------------------------------------------------------------------------

@bp.get("/books")
def list_books():
    return _items(services.list_books(current_context(), _filters()))


@bp.post("/books")
def create_book():
    return services.create_book(current_context(), _body()), 201


@bp.get("/books/<int:book_id>")
def get_book(book_id):
    return services.get_book(current_context(), book_id)


@bp.patch("/books/<int:book_id>")
def update_book(book_id):
    return services.update_book(current_context(), book_id, _body())


@bp.delete("/books/<int:book_id>")
def delete_book(book_id):
    services.delete_book(current_context(), book_id)
    return "", 204


@bp.post("/books/<int:book_id>/borrow")
def borrow_book(book_id):
    return services.borrow_book(current_context(), book_id, _body())


# --- loans ----------------------------------------------------------------------------

@bp.get("/loans")
def list_loans():
    return _items(services.list_loans(current_context(), _filters()))


@bp.post("/loans")
def create_loan():
    return services.create_loan(current_context(), _body()), 201


@bp.get("/loans/<int:loan_id>")
def get_loan(loan_id):
    return services.get_loan(current_context(), loan_id)


@bp.patch("/loans/<int:loan_id>")
def update_loan(loan_id):
    return services.update_loan(current_context(), loan_id, _body())


@bp.delete("/loans/<int:loan_id>")
def delete_loan(loan_id):
    services.delete_loan(current_context(), loan_id)
    return "", 204


@bp.post("/loans/<int:loan_id>/return")
def return_loan(loan_id):
    return services.return_loan(current_context(), loan_id, _body())


# --- outbox ---------------------------------------------------------------------------

@bp.get("/_outbox")
def list_outbox():
    return _items(services.list_outbox(current_context(), _filters()))
