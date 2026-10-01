"""Input validation helpers.

Each ``clean_*`` function takes the raw JSON body and returns a dict holding only
validated values, or raises ``ValidationError`` listing every bad field. Checks that
need the database (uniqueness, references) live in ``services``.

Field checkers raise ``FieldInvalid``; ``collect`` records that message against a field.
"""
from contextlib import contextmanager

from .errors import ValidationError

MEMBER_ROLES = ("member", "librarian")


class FieldInvalid(Exception):
    pass


@contextmanager
def collect(errors, field):
    try:
        yield
    except FieldInvalid as exc:
        errors[field] = str(exc)


def raise_if_errors(errors, message="Invalid input."):
    if errors:
        raise ValidationError(message, errors)


def require_object(data):
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


def unknown_field_errors(data, allowed):
    return {name: "unknown or read-only field" for name in data if name not in allowed}


# --- field checkers -------------------------------------------------------------------

def required_text(value):
    if not isinstance(value, str) or not value.strip():
        raise FieldInvalid("required")
    return value


def choice(value, options):
    if value not in options:
        raise FieldInvalid("must be one of: " + ", ".join(options))
    return value


def boolean(value):
    if not isinstance(value, bool):
        raise FieldInvalid("must be true or false")
    return value


def optional_integer(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldInvalid("must be an integer")
    return value


def record_id(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldInvalid("must be a record id")
    return value


# --- per-collection cleaning ----------------------------------------------------------

MEMBER_WRITABLE = ("username", "name", "role", "active")
BOOK_WRITABLE = ("title", "author", "isbn", "year")


def clean_member(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, MEMBER_WRITABLE)
    values = {}
    for name in ("username", "name"):
        if name in data or not partial:
            with collect(errors, name):
                values[name] = required_text(data.get(name))
    if "role" in data or not partial:
        with collect(errors, "role"):
            values["role"] = choice(data.get("role"), MEMBER_ROLES)
    if "active" in data:
        with collect(errors, "active"):
            values["active"] = boolean(data["active"])
    elif not partial:
        values["active"] = True
    raise_if_errors(errors)
    return values


def clean_book(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, BOOK_WRITABLE)
    values = {}
    for name in ("title", "author", "isbn"):
        if name in data or not partial:
            with collect(errors, name):
                values[name] = required_text(data.get(name))
    if "year" in data or not partial:
        with collect(errors, "year"):
            values["year"] = optional_integer(data.get("year"))
    raise_if_errors(errors)
    return values


def clean_borrow_params(data):
    """Return the requested borrower's member id, or None to borrow for oneself."""
    data = require_object(data)
    errors = unknown_field_errors(data, ("member",))
    member_id = None
    if data.get("member") is not None:
        with collect(errors, "member"):
            member_id = record_id(data["member"])
    raise_if_errors(errors)
    return member_id


def clean_no_params(data):
    data = require_object(data)
    raise_if_errors(unknown_field_errors(data, ()))
