"""Input validation helpers and the application's vocabulary (roles, statuses, ...).

Each ``clean_*`` function takes the raw JSON body and returns a dict holding only
validated values, or raises ``ValidationError`` listing every bad field. Checks that
need the database (uniqueness, references, technician eligibility) live in ``services``.

Field checkers raise ``FieldInvalid``; ``collect`` records that message against a field.
"""
from contextlib import contextmanager

from .errors import ValidationError

STAFF_ROLES = ("requester", "technician", "supervisor")
ASSET_CRITICALITIES = ("low", "medium", "high")
WORK_ORDER_PRIORITIES = ("low", "normal", "urgent")
WORK_ORDER_STATUSES = ("open", "assigned", "in_progress", "completed", "cancelled")
# Work orders in these states still need work; they count towards an asset's ``open_orders``.
UNFINISHED_STATUSES = ("open", "assigned", "in_progress")


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

def is_integer(value):
    """A JSON integer: ``int`` but not ``bool`` (``True`` is an ``int`` in Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def required_text(value):
    if not isinstance(value, str) or not value.strip():
        raise FieldInvalid("required")
    return value


def optional_text(value):
    if value is not None and not isinstance(value, str):
        raise FieldInvalid("must be text or null")
    return value


def choice(value, options):
    if value not in options:
        raise FieldInvalid("must be one of: " + ", ".join(options))
    return value


def boolean(value):
    if not isinstance(value, bool):
        raise FieldInvalid("must be true or false")
    return value


def record_id(value):
    if value is None:
        raise FieldInvalid("required")
    if not is_integer(value):
        raise FieldInvalid("must be a record id")
    return value


def positive_integer(value):
    if value is None:
        raise FieldInvalid("required")
    if not is_integer(value) or value < 1:
        raise FieldInvalid("must be an integer of at least 1")
    return value


def _clean_boolean_with_default(data, values, errors, name, default, partial):
    if name in data:
        with collect(errors, name):
            values[name] = boolean(data[name])
    elif not partial:
        values[name] = default


# --- per-collection cleaning ----------------------------------------------------------

STAFF_WRITABLE = ("username", "name", "role", "site", "active")
ASSET_WRITABLE = ("tag", "name", "site", "criticality", "retired")
ASSET_READ_ONLY = ("id", "open_orders")

WORK_ORDER_CREATABLE = ("asset", "title", "description", "priority")
WORK_ORDER_EDITABLE = ("title", "description", "priority")
# Maintained by the system and the workflow actions; clients sending them get a 400.
WORK_ORDER_READ_ONLY = ("id", "status", "requested_by", "created_at", "assignee", "started_at",
                        "completed_at", "resolution", "labor_minutes", "cancel_reason",
                        "due_date", "overdue")


def clean_staff(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, STAFF_WRITABLE, read_only=("id",))
    values = {}
    for name in ("username", "name", "site"):
        if name in data or not partial:
            with collect(errors, name):
                values[name] = required_text(data.get(name))
    if "role" in data or not partial:
        with collect(errors, "role"):
            values["role"] = choice(data.get("role"), STAFF_ROLES)
    _clean_boolean_with_default(data, values, errors, "active", True, partial)
    raise_if_errors(errors)
    return values


def clean_asset(data, *, partial):
    data = require_object(data)
    errors = unknown_field_errors(data, ASSET_WRITABLE, read_only=ASSET_READ_ONLY)
    values = {}
    for name in ("tag", "name", "site"):
        if name in data or not partial:
            with collect(errors, name):
                values[name] = required_text(data.get(name))
    if "criticality" in data or not partial:
        with collect(errors, "criticality"):
            values["criticality"] = choice(data.get("criticality"), ASSET_CRITICALITIES)
    _clean_boolean_with_default(data, values, errors, "retired", False, partial)
    raise_if_errors(errors)
    return values


def clean_work_order(data, *, partial):
    """Create (``partial=False``) or PATCH (``partial=True``) body; ``asset`` only on create."""
    data = require_object(data)
    allowed = WORK_ORDER_EDITABLE if partial else WORK_ORDER_CREATABLE
    read_only = WORK_ORDER_READ_ONLY + (("asset",) if partial else ())
    errors = unknown_field_errors(data, allowed, read_only=read_only)
    values = {}
    if not partial:
        with collect(errors, "asset"):
            values["asset"] = record_id(data.get("asset"))
    if "title" in data or not partial:
        with collect(errors, "title"):
            values["title"] = required_text(data.get("title"))
    if "description" in data or not partial:
        with collect(errors, "description"):
            values["description"] = optional_text(data.get("description"))
    if "priority" in data or not partial:
        with collect(errors, "priority"):
            values["priority"] = choice(data.get("priority"), WORK_ORDER_PRIORITIES)
    raise_if_errors(errors)
    return values


# --- action parameters ----------------------------------------------------------------

def clean_assign_params(data):
    """Return the requested technician's staff id (existence/eligibility checked in services)."""
    data = require_object(data)
    errors = unknown_field_errors(data, ("technician",))
    technician = None
    with collect(errors, "technician"):
        technician = record_id(data.get("technician"))
    raise_if_errors(errors)
    return technician


def clean_complete_params(data):
    data = require_object(data)
    errors = unknown_field_errors(data, ("resolution", "labor_minutes"))
    values = {}
    with collect(errors, "resolution"):
        values["resolution"] = required_text(data.get("resolution"))
    with collect(errors, "labor_minutes"):
        values["labor_minutes"] = positive_integer(data.get("labor_minutes"))
    raise_if_errors(errors)
    return values


def clean_cancel_params(data):
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
