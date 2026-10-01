"""Data access: all SQL lives here.

Functions return plain dicts shaped like API records (references as ids under the API
field name, booleans as ``bool``). Values passed to insert/update functions have already
been validated by ``services``.
"""
import json

from .db import get_db

# --- members --------------------------------------------------------------------------

_MEMBER_SELECT = "SELECT id, username, name, role, active FROM members"


def _member(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "active": bool(row["active"]),
    }


def list_members():
    return [_member(row) for row in get_db().execute(f"{_MEMBER_SELECT} ORDER BY id")]


def get_member(member_id):
    return _member(get_db().execute(f"{_MEMBER_SELECT} WHERE id = ?", (member_id,)).fetchone())


def get_member_by_username(username):
    return _member(get_db().execute(f"{_MEMBER_SELECT} WHERE username = ?", (username,)).fetchone())


def username_taken(username, exclude_id=None):
    row = get_db().execute(
        "SELECT 1 FROM members WHERE username = ? AND id IS NOT ?", (username, exclude_id)
    ).fetchone()
    return row is not None


def insert_member(values):
    cur = get_db().execute(
        "INSERT INTO members (username, name, role, active) VALUES (?, ?, ?, ?)",
        (values["username"], values["name"], values["role"], int(values["active"])),
    )
    return cur.lastrowid


def update_member(member_id, values):
    columns = {"username": "username", "name": "name", "role": "role", "active": "active"}
    _update("members", columns, member_id, values)


def delete_member(member_id):
    get_db().execute("DELETE FROM members WHERE id = ?", (member_id,))


def member_has_loans(member_id):
    return get_db().execute("SELECT 1 FROM loans WHERE member_id = ?", (member_id,)).fetchone() is not None


def count_open_loans(member_id):
    return get_db().execute(
        "SELECT COUNT(*) FROM loans WHERE member_id = ? AND returned_at IS NULL", (member_id,)
    ).fetchone()[0]


# --- books ----------------------------------------------------------------------------

_BOOK_SELECT = """
    SELECT b.id, b.title, b.author, b.isbn, b.year,
           EXISTS (SELECT 1 FROM loans l WHERE l.book_id = b.id AND l.returned_at IS NULL) AS on_loan
    FROM books b
"""


def _book(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "isbn": row["isbn"],
        "year": row["year"],
        "status": "on_loan" if row["on_loan"] else "available",
    }


def list_books():
    return [_book(row) for row in get_db().execute(f"{_BOOK_SELECT} ORDER BY b.id")]


def get_book(book_id):
    return _book(get_db().execute(f"{_BOOK_SELECT} WHERE b.id = ?", (book_id,)).fetchone())


def isbn_taken(isbn, exclude_id=None):
    row = get_db().execute("SELECT 1 FROM books WHERE isbn = ? AND id IS NOT ?", (isbn, exclude_id)).fetchone()
    return row is not None


def insert_book(values):
    cur = get_db().execute(
        "INSERT INTO books (title, author, isbn, year) VALUES (?, ?, ?, ?)",
        (values["title"], values["author"], values["isbn"], values["year"]),
    )
    return cur.lastrowid


def update_book(book_id, values):
    columns = {"title": "title", "author": "author", "isbn": "isbn", "year": "year"}
    _update("books", columns, book_id, values)


def delete_book(book_id):
    get_db().execute("DELETE FROM books WHERE id = ?", (book_id,))


def book_has_loans(book_id):
    return get_db().execute("SELECT 1 FROM loans WHERE book_id = ?", (book_id,)).fetchone() is not None


# --- loans ----------------------------------------------------------------------------
# ``overdue`` depends on the request's clock, so services add it (see services.present_loan).

_LOAN_SELECT = "SELECT id, book_id, member_id, borrowed_at, due_at, returned_at FROM loans"


def _loan(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "book": row["book_id"],
        "member": row["member_id"],
        "borrowed_at": row["borrowed_at"],
        "due_at": row["due_at"],
        "returned_at": row["returned_at"],
    }


def list_loans():
    return [_loan(row) for row in get_db().execute(f"{_LOAN_SELECT} ORDER BY id")]


def get_loan(loan_id):
    return _loan(get_db().execute(f"{_LOAN_SELECT} WHERE id = ?", (loan_id,)).fetchone())


def insert_loan(book_id, member_id, borrowed_at, due_at):
    cur = get_db().execute(
        "INSERT INTO loans (book_id, member_id, borrowed_at, due_at) VALUES (?, ?, ?, ?)",
        (book_id, member_id, borrowed_at, due_at),
    )
    return cur.lastrowid


def mark_loan_returned(loan_id, returned_at):
    get_db().execute("UPDATE loans SET returned_at = ? WHERE id = ?", (returned_at, loan_id))


# --- outbox ---------------------------------------------------------------------------

def add_outbox_message(channel, payload, created_at):
    cur = get_db().execute(
        "INSERT INTO outbox (channel, payload, created_at) VALUES (?, ?, ?)",
        (channel, json.dumps(payload), created_at),
    )
    return cur.lastrowid


def list_outbox_messages():
    rows = get_db().execute("SELECT id, channel, payload, created_at FROM outbox ORDER BY id")
    return [
        {"id": r["id"], "channel": r["channel"], "payload": json.loads(r["payload"]), "created_at": r["created_at"]}
        for r in rows
    ]


# --- helpers --------------------------------------------------------------------------

def _update(table, columns, record_id, values):
    """UPDATE ``table`` setting the API fields in ``values`` (mapped through ``columns``)."""
    if not values:
        return
    assignments = ", ".join(f"{columns[field]} = ?" for field in values)
    params = [_to_db(value) for value in values.values()] + [record_id]
    get_db().execute(f"UPDATE {table} SET {assignments} WHERE id = ?", params)


def _to_db(value):
    return int(value) if isinstance(value, bool) else value
