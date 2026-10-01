"""HTML user interface (``/ui``).

Pages follow the contract's markup conventions: list rows carry ``data-id``, detail pages
mark each field with ``data-field`` and offer one ``<form data-action>`` per action the
caller can run right now, and create pages hold a ``<form data-create>`` with inputs only
for fields the caller may set. Forms post back here; the handlers convert form strings to
JSON-like values and call the same services as the API.
"""
from flask import Blueprint, redirect, render_template, request, url_for

from . import services, validation
from .auth import current_context

bp = Blueprint("ui", __name__, url_prefix="/ui")


@bp.get("")
@bp.get("/")
def index():
    return redirect(url_for("ui.list_books"))


# --- form value conversion ------------------------------------------------------------
# Form fields arrive as strings. Convert what we can; anything unconvertible is passed
# through unchanged so the service's validation reports it as a 400.

def _form_values(converters):
    return {name: convert(request.form[name]) for name, convert in converters.items() if name in request.form}


def _text(value):
    return value


def _optional_int(value):
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _boolean(value):
    return {"true": True, "false": False}.get(value, value)


# --- members --------------------------------------------------------------------------

@bp.get("/members")
def list_members():
    members = services.list_members(current_context(), request.args.to_dict())
    return render_template("members/list.html", members=members)


@bp.get("/members/new")
def new_member():
    services.ensure_can_create_member(current_context())
    return render_template("members/new.html", roles=validation.MEMBER_ROLES)


@bp.post("/members")
def create_member():
    data = _form_values({"username": _text, "name": _text, "role": _text, "active": _boolean})
    member = services.create_member(current_context(), data)
    return redirect(url_for("ui.show_member", member_id=member["id"]), 303)


@bp.get("/members/<int:member_id>")
def show_member(member_id):
    member = services.get_member(current_context(), member_id)
    return render_template("members/detail.html", member=member)


# --- books ----------------------------------------------------------------------------

@bp.get("/books")
def list_books():
    books = services.list_books(current_context(), request.args.to_dict())
    return render_template("books/list.html", books=books)


@bp.get("/books/new")
def new_book():
    services.ensure_can_create_book(current_context())
    return render_template("books/new.html")


@bp.post("/books")
def create_book():
    data = _form_values({"title": _text, "author": _text, "isbn": _text, "year": _optional_int})
    book = services.create_book(current_context(), data)
    return redirect(url_for("ui.show_book", book_id=book["id"]), 303)


@bp.get("/books/<int:book_id>")
def show_book(book_id):
    ctx = current_context()
    book = services.get_book(ctx, book_id)
    actions = services.book_actions(ctx, book)
    # Librarians lend to a chosen member; members always borrow for themselves.
    borrowers = services.list_members(ctx, {"active": "true"}) if ctx.is_librarian else []
    return render_template("books/detail.html", book=book, actions=actions, borrowers=borrowers)


@bp.post("/books/<int:book_id>/borrow")
def borrow_book(book_id):
    params = {k: v for k, v in _form_values({"member": _optional_int}).items() if v is not None}
    services.borrow_book(current_context(), book_id, params)
    return redirect(url_for("ui.show_book", book_id=book_id), 303)


# --- loans ----------------------------------------------------------------------------

@bp.get("/loans")
def list_loans():
    loans = services.list_loans(current_context(), request.args.to_dict())
    return render_template("loans/list.html", loans=loans)


@bp.get("/loans/new")
def new_loan():
    # Nobody may create loans directly (they come from borrowing), so this is always 403.
    services.ensure_can_create_loan(current_context())


@bp.get("/loans/<int:loan_id>")
def show_loan(loan_id):
    ctx = current_context()
    loan = services.get_loan(ctx, loan_id)
    return render_template("loans/detail.html", loan=loan, actions=services.loan_actions(ctx, loan))


@bp.post("/loans/<int:loan_id>/return")
def return_loan(loan_id):
    services.return_loan(current_context(), loan_id, {})
    return redirect(url_for("ui.show_loan", loan_id=loan_id), 303)
