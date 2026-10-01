"""Who may do what. Pure functions of the calling member and the records involved.

These answer only "is this user allowed?"; state rules (409) live in ``services``.
"""

MEMBER_SELF_EDITABLE = {"name"}


def is_librarian(user):
    return user["role"] == "librarian"


# --- members --------------------------------------------------------------------------

def can_read_member(user, member):
    return is_librarian(user) or member["id"] == user["id"]


def can_create_member(user):
    return is_librarian(user)


def can_update_member(user, member, fields):
    """Librarians may change anything; members only the ``name`` of their own record."""
    if is_librarian(user):
        return True
    return member["id"] == user["id"] and set(fields) <= MEMBER_SELF_EDITABLE


def can_delete_member(user, member):
    return is_librarian(user)


# --- books ----------------------------------------------------------------------------

def can_read_book(user, book):
    return True


def can_manage_books(user):
    """Create, update and delete books."""
    return is_librarian(user)


def can_borrow_for(user, member_id):
    """May ``user`` borrow a book on behalf of ``member_id`` (None means themselves)?"""
    return member_id is None or member_id == user["id"] or is_librarian(user)


# --- loans ----------------------------------------------------------------------------

def can_read_loan(user, loan):
    return is_librarian(user) or loan["member"] == user["id"]


def can_return_loan(user, loan):
    return is_librarian(user) or loan["member"] == user["id"]

