"""Business rules and actions for the lending library.

Every function takes the ``RequestContext`` (caller + clock) first and returns API-shaped
records. Checks run in the contract's precedence order: the record exists (404), the
caller is allowed (403), the record's state allows it (409), the input is valid (400).
"""
from datetime import timedelta

from . import permissions, repository, validation
from .db import transaction
from .errors import Conflict, Forbidden, NotFound, ValidationError
from .filters import apply_filters

LOAN_PERIOD = timedelta(days=14)
MAX_OPEN_LOANS = 3

MEMBER_FIELDS = ("id", "username", "name", "role", "active")
BOOK_FIELDS = ("id", "title", "author", "isbn", "year", "status")
LOAN_FIELDS = ("id", "book", "member", "borrowed_at", "due_at", "returned_at", "overdue")
OUTBOX_FIELDS = ("id", "channel", "created_at")


# --- members --------------------------------------------------------------------------

def list_members(ctx, filters=None):
    members = [m for m in repository.list_members() if permissions.can_read_member(ctx.user, m)]
    return apply_filters(members, filters or {}, MEMBER_FIELDS)


def get_member(ctx, member_id):
    member = _load_member(member_id)
    if not permissions.can_read_member(ctx.user, member):
        raise Forbidden()
    return member


def ensure_can_create_member(ctx):
    if not permissions.can_create_member(ctx.user):
        raise Forbidden("Only librarians can create members.")


def create_member(ctx, data):
    ensure_can_create_member(ctx)
    with transaction():
        values = validation.clean_member(data, partial=False)
        _ensure_username_free(values["username"])
        member_id = repository.insert_member(values)
    return repository.get_member(member_id)


def update_member(ctx, member_id, data):
    with transaction():
        member = _load_member(member_id)
        fields = data.keys() if isinstance(data, dict) else ()
        if not permissions.can_update_member(ctx.user, member, fields):
            raise Forbidden("Members may only change their own name.")
        values = validation.clean_member(data, partial=True)
        if "username" in values:
            _ensure_username_free(values["username"], exclude_id=member_id)
        repository.update_member(member_id, values)
    return repository.get_member(member_id)


def delete_member(ctx, member_id):
    with transaction():
        member = _load_member(member_id)
        if not permissions.can_delete_member(ctx.user, member):
            raise Forbidden("Only librarians can delete members.")
        if repository.member_has_loans(member_id):
            raise Conflict("A member with loans cannot be deleted.")
        repository.delete_member(member_id)


def _load_member(member_id):
    member = repository.get_member(member_id)
    if member is None:
        raise NotFound("No such member.")
    return member


def _ensure_username_free(username, exclude_id=None):
    if repository.username_taken(username, exclude_id):
        raise ValidationError("Username already in use.", {"username": "already in use"})


# --- books ----------------------------------------------------------------------------

def list_books(ctx, filters=None):
    books = [b for b in repository.list_books() if permissions.can_read_book(ctx.user, b)]
    return apply_filters(books, filters or {}, BOOK_FIELDS)


def get_book(ctx, book_id):
    book = _load_book(book_id)
    if not permissions.can_read_book(ctx.user, book):
        raise Forbidden()
    return book


def ensure_can_create_book(ctx):
    if not permissions.can_manage_books(ctx.user):
        raise Forbidden("Only librarians can create books.")


def create_book(ctx, data):
    ensure_can_create_book(ctx)
    with transaction():
        values = validation.clean_book(data, partial=False)
        _ensure_isbn_free(values["isbn"])
        book_id = repository.insert_book(values)
    return repository.get_book(book_id)


def update_book(ctx, book_id, data):
    with transaction():
        _load_book(book_id)
        if not permissions.can_manage_books(ctx.user):
            raise Forbidden("Only librarians can update books.")
        values = validation.clean_book(data, partial=True)
        if "isbn" in values:
            _ensure_isbn_free(values["isbn"], exclude_id=book_id)
        repository.update_book(book_id, values)
    return repository.get_book(book_id)


def delete_book(ctx, book_id):
    with transaction():
        _load_book(book_id)
        if not permissions.can_manage_books(ctx.user):
            raise Forbidden("Only librarians can delete books.")
        if repository.book_has_loans(book_id):
            raise Conflict("A book with loans cannot be deleted.")
        repository.delete_book(book_id)


def borrow_book(ctx, book_id, params):
    """Lend the book to the caller (or, for librarians, to ``params["member"]``)."""
    with transaction():
        book = _load_book(book_id)
        requested = params.get("member") if isinstance(params, dict) else None
        if not permissions.can_borrow_for(ctx.user, requested):
            raise Forbidden("Members can only borrow for themselves.")
        if book["status"] == "on_loan":
            raise Conflict("The book is already on loan.")
        member_id = validation.clean_borrow_params(params)
        borrower = ctx.user if member_id is None else repository.get_member(member_id)
        if borrower is None:
            raise ValidationError("No such member.", {"member": "no such member"})
        _ensure_may_borrow(borrower)
        loan_id = repository.insert_loan(
            book_id, borrower["id"], borrowed_at=ctx.now_text, due_at=(ctx.today + LOAN_PERIOD).isoformat()
        )
        repository.add_outbox_message(
            "loan_created", {"loan": loan_id, "book": book_id, "member": borrower["id"]}, ctx.now_text
        )
    return repository.get_book(book_id)


def book_actions(ctx, book):
    """Names of the actions the caller could successfully start on ``book`` right now."""
    if book["status"] != "available":
        return []
    if permissions.is_librarian(ctx.user):
        return ["borrow"]  # librarians can lend to any eligible member
    return ["borrow"] if _may_borrow(ctx.user) else []


def _load_book(book_id):
    book = repository.get_book(book_id)
    if book is None:
        raise NotFound("No such book.")
    return book


def _ensure_isbn_free(isbn, exclude_id=None):
    if repository.isbn_taken(isbn, exclude_id):
        raise ValidationError("ISBN already in use.", {"isbn": "already in use"})


def _may_borrow(member):
    return member["active"] and repository.count_open_loans(member["id"]) < MAX_OPEN_LOANS


def _ensure_may_borrow(member):
    if not member["active"]:
        raise Conflict("Inactive members cannot borrow.")
    if repository.count_open_loans(member["id"]) >= MAX_OPEN_LOANS:
        raise Conflict(f"Members may have at most {MAX_OPEN_LOANS} unreturned loans.")


# --- loans ----------------------------------------------------------------------------

def present_loan(ctx, loan):
    """Add the derived ``overdue`` field, which depends on the request's clock."""
    overdue = loan["returned_at"] is None and ctx.today.isoformat() > loan["due_at"]
    return {**loan, "overdue": overdue}


def list_loans(ctx, filters=None):
    loans = [present_loan(ctx, l) for l in repository.list_loans() if permissions.can_read_loan(ctx.user, l)]
    return apply_filters(loans, filters or {}, LOAN_FIELDS)


def get_loan(ctx, loan_id):
    loan = _load_loan(loan_id)
    if not permissions.can_read_loan(ctx.user, loan):
        raise Forbidden()
    return present_loan(ctx, loan)


# Loans are created only by borrowing a book and changed only by returning it: nobody may
# create, update or delete them directly (an unknown loan id is still a 404 first).

def ensure_can_create_loan(ctx):
    """Always refuses (403): loans are created by ``borrow_book``."""
    raise Forbidden("Loans are created by borrowing a book.")


def create_loan(ctx, data):
    """``POST /api/loans``: always 403, see ``ensure_can_create_loan``."""
    ensure_can_create_loan(ctx)


def update_loan(ctx, loan_id, data):
    _load_loan(loan_id)
    raise Forbidden("Loans change only through the return action.")


def delete_loan(ctx, loan_id):
    _load_loan(loan_id)
    raise Forbidden("Loans cannot be deleted.")


def return_loan(ctx, loan_id, params):
    with transaction():
        loan = _load_loan(loan_id)
        if not permissions.can_return_loan(ctx.user, loan):
            raise Forbidden("Only the borrower or a librarian can return a loan.")
        if loan["returned_at"] is not None:
            raise Conflict("The loan has already been returned.")
        validation.clean_no_params(params)
        repository.mark_loan_returned(loan_id, ctx.now_text)
    return present_loan(ctx, repository.get_loan(loan_id))


def loan_actions(ctx, loan):
    if loan["returned_at"] is None and permissions.can_return_loan(ctx.user, loan):
        return ["return"]
    return []


def _load_loan(loan_id):
    loan = repository.get_loan(loan_id)
    if loan is None:
        raise NotFound("No such loan.")
    return loan


# --- outbox ---------------------------------------------------------------------------

def list_outbox(ctx, filters=None):
    """Any authenticated user may read the outbox."""
    return apply_filters(repository.list_outbox_messages(), filters or {}, OUTBOX_FIELDS)
