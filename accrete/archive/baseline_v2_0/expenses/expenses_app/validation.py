"""Input validation helpers.

Each ``clean_*`` function takes the raw JSON body and returns a dict holding only
validated values, or raises ``ValidationError`` listing every bad field. Checks that
need the database (uniqueness, references) live in ``services``.

Field checkers raise ``FieldInvalid``; ``collect`` records that message against a field.
"""
import math
from contextlib import contextmanager

from .errors import ValidationError

EMPLOYEE_ROLES = ("employee", "manager", "finance")
CLAIM_CATEGORIES = ("travel", "meals", "equipment", "other")
MAX_CLAIM_AMOUNT = 5000


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


def unknown_field_errors(data, allowed, read_only=()):
    errors = {}
    for name in data:
        if name in read_only:
            errors[name] = "cannot be set directly"
        elif name not in allowed:
            errors[name] = "unknown field"
    return errors


# --- field checkers -------------------------------------------------------------------

def required_text(value):
    if not isinstance(value, str) or not value.strip():
        raise FieldInvalid("required")
    return value


def choice(value, options):
    if value not in options:
        raise FieldInvalid("must be one of: " + ", ".join(options))
    return value


def optional_record_id(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FieldInvalid("must be a record id")
    return value


def claim_amount(value):
    if value is None:
        raise FieldInvalid("required")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FieldInvalid("must be a number")
    if not 0 < value <= MAX_CLAIM_AMOUNT:
        raise FieldInvalid(f"must be greater than 0 and at most {MAX_CLAIM_AMOUNT}")
    return value


# --- per-collection cleaning ----------------------------------------------------------

EMPLOYEE_WRITABLE = ("username", "name", "role", "manager", "department")

CLAIM_WRITABLE = ("amount", "category", "description")
# Maintained by the workflow actions; clients sending them get a 400.
CLAIM_READ_ONLY = ("id", "employee", "status", "submitted_at", "decided_at", "decided_by", "rejection_reason")


def clean_employee(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, EMPLOYEE_WRITABLE, read_only=("id",))
    values = {}
    for name in ("username", "name", "department"):
        if name in data or not partial:
            with collect(errors, name):
                values[name] = required_text(data.get(name))
    if "role" in data or not partial:
        with collect(errors, "role"):
            values["role"] = choice(data.get("role"), EMPLOYEE_ROLES)
    if "manager" in data or not partial:
        with collect(errors, "manager"):
            values["manager"] = optional_record_id(data.get("manager"))
    raise_if_errors(errors)
    return values


def clean_claim(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, CLAIM_WRITABLE, read_only=CLAIM_READ_ONLY)
    values = {}
    if "amount" in data or not partial:
        with collect(errors, "amount"):
            values["amount"] = claim_amount(data.get("amount"))
    if "category" in data or not partial:
        with collect(errors, "category"):
            values["category"] = choice(data.get("category"), CLAIM_CATEGORIES)
    if "description" in data or not partial:
        with collect(errors, "description"):
            values["description"] = required_text(data.get("description"))
    raise_if_errors(errors)
    return values


def clean_reject_params(data):
    data = require_object(data)
    errors = unknown_field_errors(data, ("reason",))
    reason = None
    with collect(errors, "reason"):
        reason = required_text(data.get("reason"))
    raise_if_errors(errors)
    return reason


def clean_no_params(data):
    data = require_object(data)
    raise_if_errors(unknown_field_errors(data, ()))
