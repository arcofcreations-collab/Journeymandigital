"""Business rules and the work order workflow.

Every function takes the ``RequestContext`` (caller + clock) first and returns API-shaped
records. Checks run in the contract's precedence order: the record exists (404), the
caller is allowed (403), the record's state allows it (409), the input is valid (400).

Work order workflow::

    open --assign--> assigned --start--> in_progress --complete--> completed
                     assigned --assign--> assigned               (re-assignment)
    open | assigned | in_progress --cancel--> cancelled          (requester: only from open)
"""
from datetime import date, timedelta

from . import permissions, repository, validation
from .db import transaction
from .errors import Conflict, Forbidden, NotFound, ValidationError
from .filters import apply_filters
from .validation import UNFINISHED_STATUSES

# Days from the creation date to ``due_date``, by priority.
DUE_DAYS = {"urgent": 1, "normal": 7, "low": 30}

# Statuses from which each state-dependent operation may start.
ASSIGNABLE_STATUSES = ("open", "assigned")
STARTABLE_STATUSES = ("assigned",)
COMPLETABLE_STATUSES = ("in_progress",)
REQUESTER_EDITABLE_STATUSES = ("open",)
REQUESTER_CANCELLABLE_STATUSES = ("open",)
SUPERVISOR_EDITABLE_STATUSES = UNFINISHED_STATUSES
SUPERVISOR_CANCELLABLE_STATUSES = UNFINISHED_STATUSES

STAFF_FIELDS = ("id", "username", "name", "role", "site", "active")
ASSET_FIELDS = ("id", "tag", "name", "site", "criticality", "retired", "open_orders")
WORK_ORDER_FIELDS = ("id", "asset", "title", "description", "priority", "status", "requested_by",
                     "created_at", "assignee", "started_at", "completed_at", "resolution",
                     "labor_minutes", "cancel_reason", "due_date", "overdue")
OUTBOX_FIELDS = ("id", "channel", "created_at")


# --- staff ----------------------------------------------------------------------------

def list_staff(ctx, filters=None):
    staff = [s for s in repository.list_staff() if permissions.can_read_staff(ctx.user, s)]
    return apply_filters(staff, filters or {}, STAFF_FIELDS)


def get_staff(ctx, staff_id):
    staff = _load_staff(staff_id)
    if not permissions.can_read_staff(ctx.user, staff):
        raise Forbidden()
    return staff


def ensure_can_create_staff(ctx):
    if not permissions.can_manage_staff(ctx.user):
        raise Forbidden("Only supervisors can create staff.")


def create_staff(ctx, data):
    ensure_can_create_staff(ctx)
    with transaction():
        values = validation.clean_staff(data, partial=False)
        _ensure_username_free(values["username"])
        staff_id = repository.insert_staff(values)
    return repository.get_staff(staff_id)


def update_staff(ctx, staff_id, data):
    with transaction():
        _load_staff(staff_id)
        if not permissions.can_manage_staff(ctx.user):
            raise Forbidden("Only supervisors can update staff.")
        values = validation.clean_staff(data, partial=True)
        if "username" in values:
            _ensure_username_free(values["username"], exclude_id=staff_id)
        repository.update_staff(staff_id, values)
    return repository.get_staff(staff_id)


def delete_staff(ctx, staff_id):
    with transaction():
        _load_staff(staff_id)
        if not permissions.can_manage_staff(ctx.user):
            raise Forbidden("Only supervisors can delete staff.")
        if repository.staff_has_work_orders(staff_id):
            raise Conflict("Staff who requested or are assigned to work orders cannot be deleted.")
        repository.delete_staff(staff_id)


def _load_staff(staff_id):
    staff = repository.get_staff(staff_id)
    if staff is None:
        raise NotFound("No such staff member.")
    return staff


def _ensure_username_free(username, exclude_id=None):
    if repository.username_taken(username, exclude_id):
        raise ValidationError("Username already in use.", {"username": "already in use"})


# --- assets ---------------------------------------------------------------------------

def list_assets(ctx, filters=None):
    assets = [a for a in repository.list_assets() if permissions.can_read_asset(ctx.user, a)]
    return apply_filters(assets, filters or {}, ASSET_FIELDS)


def get_asset(ctx, asset_id):
    asset = _load_asset(asset_id)
    if not permissions.can_read_asset(ctx.user, asset):
        raise Forbidden()
    return asset


def ensure_can_create_asset(ctx):
    if not permissions.can_manage_assets(ctx.user):
        raise Forbidden("Only supervisors can create assets.")


def create_asset(ctx, data):
    ensure_can_create_asset(ctx)
    with transaction():
        values = validation.clean_asset(data, partial=False)
        _ensure_tag_free(values["tag"])
        asset_id = repository.insert_asset(values)
    return repository.get_asset(asset_id)


def update_asset(ctx, asset_id, data):
    with transaction():
        asset = _load_asset(asset_id)
        if not permissions.can_manage_assets(ctx.user):
            raise Forbidden("Only supervisors can update assets.")
        if isinstance(data, dict) and data.get("retired") is True and asset["open_orders"] > 0:
            raise Conflict("An asset with unfinished work orders cannot be retired.")
        values = validation.clean_asset(data, partial=True)
        if "tag" in values:
            _ensure_tag_free(values["tag"], exclude_id=asset_id)
        repository.update_asset(asset_id, values)
    return repository.get_asset(asset_id)


def delete_asset(ctx, asset_id):
    with transaction():
        _load_asset(asset_id)
        if not permissions.can_manage_assets(ctx.user):
            raise Forbidden("Only supervisors can delete assets.")
        if repository.asset_has_work_orders(asset_id):
            raise Conflict("An asset with work orders cannot be deleted.")
        repository.delete_asset(asset_id)


def _load_asset(asset_id):
    asset = repository.get_asset(asset_id)
    if asset is None:
        raise NotFound("No such asset.")
    return asset


def _ensure_tag_free(tag, exclude_id=None):
    if repository.tag_taken(tag, exclude_id):
        raise ValidationError("Tag already in use.", {"tag": "already in use"})


# --- work orders: reading -------------------------------------------------------------

def due_date(order):
    created = date.fromisoformat(order["created_at"][:10])
    return created + timedelta(days=DUE_DAYS[order["priority"]])


def present_work_order(ctx, order):
    """Add the derived ``due_date`` and ``overdue`` fields (``overdue`` depends on the clock)."""
    due = due_date(order)
    overdue = order["status"] in UNFINISHED_STATUSES and ctx.today > due
    return {**order, "due_date": due.isoformat(), "overdue": overdue}


def list_work_orders(ctx, filters=None):
    assets = {a["id"]: a for a in repository.list_assets()}
    orders = [
        present_work_order(ctx, o) for o in repository.list_work_orders()
        if permissions.can_read_work_order(ctx.user, o, assets[o["asset"]])
    ]
    return apply_filters(orders, filters or {}, WORK_ORDER_FIELDS)


def get_work_order(ctx, work_order_id):
    order = _load_work_order(work_order_id)
    _ensure_can_read(ctx, order)
    return present_work_order(ctx, order)


# --- work orders: create, update, delete ----------------------------------------------

def ensure_can_create_work_order(ctx):
    if not permissions.can_create_work_order(ctx.user):
        raise Forbidden()


def create_work_order(ctx, data):
    """Create an ``open`` work order requested by the caller."""
    ensure_can_create_work_order(ctx)
    with transaction():
        # The own-site rule is a 403 and so wins over any 400 in the same body.
        asset = _existing_asset_in(data)
        if asset is not None and not permissions.can_create_work_order_for(ctx.user, asset):
            raise Forbidden("You can only raise work orders for assets at your own site.")
        values = validation.clean_work_order(data, partial=False)
        asset = repository.get_asset(values["asset"])
        if asset is None:
            raise ValidationError("No such asset.", {"asset": "no such asset"})
        if asset["retired"]:
            raise ValidationError("The asset is retired.", {"asset": "asset is retired"})
        work_order_id = repository.insert_work_order(values, requested_by=ctx.user["id"], created_at=ctx.now_text)
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def update_work_order(ctx, work_order_id, data):
    with transaction():
        order = _load_work_order(work_order_id)
        fields = data.keys() if isinstance(data, dict) else ()
        _authorize_edit(ctx.user, order, fields)
        values = validation.clean_work_order(data, partial=True)
        repository.update_work_order(work_order_id, values)
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def delete_work_order(ctx, work_order_id):
    order = _load_work_order(work_order_id)
    if not permissions.can_delete_work_order(ctx.user, order):
        raise Forbidden("Work orders cannot be deleted.")


def _authorize_edit(user, order, fields):
    if not permissions.can_edit_work_order(user, order, fields):
        raise Forbidden("Only supervisors, or the requester for title and description, can edit this order.")
    if permissions.is_supervisor(user):
        _require_status(order, SUPERVISOR_EDITABLE_STATUSES, "Only unfinished work orders can be edited.")
    else:
        _require_status(order, REQUESTER_EDITABLE_STATUSES, "Requesters can only edit open work orders.")


# --- work orders: actions -------------------------------------------------------------
# Each ``_authorize_<action>`` raises Forbidden (403) or Conflict (409) when the caller may
# not run the action on the order right now. The API actions and ``work_order_actions``
# (the forms shown on the detail page) both use them, so the two always agree.

def _authorize_assign(user, order):
    if not permissions.can_assign_work_order(user, order):
        raise Forbidden("Only supervisors can assign work orders.")
    _require_status(order, ASSIGNABLE_STATUSES, "Only open or assigned work orders can be assigned.")


def _authorize_start(user, order):
    if not permissions.can_work_on_work_order(user, order):
        raise Forbidden("Only the assignee can start the work order.")
    _require_status(order, STARTABLE_STATUSES, "Only assigned work orders can be started.")


def _authorize_complete(user, order):
    if not permissions.can_work_on_work_order(user, order):
        raise Forbidden("Only the assignee can complete the work order.")
    _require_status(order, COMPLETABLE_STATUSES, "Only work orders in progress can be completed.")


def _authorize_cancel(user, order):
    if not permissions.can_cancel_work_order(user, order):
        raise Forbidden("Only supervisors or the requester can cancel the work order.")
    if permissions.is_supervisor(user):
        _require_status(order, SUPERVISOR_CANCELLABLE_STATUSES, "Only unfinished work orders can be cancelled.")
    else:
        _require_status(order, REQUESTER_CANCELLABLE_STATUSES, "Requesters can only cancel open work orders.")


WORK_ORDER_ACTIONS = {
    "assign": _authorize_assign,
    "start": _authorize_start,
    "complete": _authorize_complete,
    "cancel": _authorize_cancel,
}


def work_order_actions(ctx, order):
    """Names of the actions the caller may run on ``order`` right now (permission and state)."""
    allowed = []
    for name, authorize in WORK_ORDER_ACTIONS.items():
        try:
            authorize(ctx.user, order)
        except (Forbidden, Conflict):
            continue
        allowed.append(name)
    return allowed


def assign_work_order(ctx, work_order_id, params):
    with transaction():
        order = _load_work_order(work_order_id)
        _authorize_assign(ctx.user, order)
        technician_id = validation.clean_assign_params(params)
        asset = repository.get_asset(order["asset"])
        _ensure_can_be_assigned(repository.get_staff(technician_id), asset)
        repository.mark_work_order_assigned(work_order_id, technician_id)
        repository.add_outbox_message(
            "assignment", {"work_order": work_order_id, "asset": asset["id"], "technician": technician_id},
            ctx.now_text,
        )
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def start_work_order(ctx, work_order_id, params):
    with transaction():
        order = _load_work_order(work_order_id)
        _authorize_start(ctx.user, order)
        validation.clean_no_params(params)
        repository.mark_work_order_started(work_order_id, ctx.now_text)
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def complete_work_order(ctx, work_order_id, params):
    with transaction():
        order = _load_work_order(work_order_id)
        _authorize_complete(ctx.user, order)
        values = validation.clean_complete_params(params)
        repository.mark_work_order_completed(
            work_order_id, ctx.now_text, values["resolution"], values["labor_minutes"]
        )
        repository.add_outbox_message(
            "work_completed",
            {"work_order": work_order_id, "asset": order["asset"], "technician": order["assignee"],
             "labor_minutes": values["labor_minutes"]},
            ctx.now_text,
        )
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def cancel_work_order(ctx, work_order_id, params):
    with transaction():
        order = _load_work_order(work_order_id)
        _authorize_cancel(ctx.user, order)
        reason = validation.clean_cancel_params(params)
        repository.mark_work_order_cancelled(work_order_id, reason)
    return present_work_order(ctx, repository.get_work_order(work_order_id))


def eligible_technicians(asset):
    """Staff ``assign`` accepts for orders on ``asset``: active technicians at its site."""
    return [s for s in repository.list_staff() if _assignment_problem(s, asset) is None]


def _ensure_can_be_assigned(staff, asset):
    problem = _assignment_problem(staff, asset)
    if problem is not None:
        raise ValidationError("This technician cannot be assigned.", {"technician": problem})


def _assignment_problem(staff, asset):
    if staff is None:
        return "no such staff member"
    if staff["role"] != "technician":
        return "not a technician"
    if not staff["active"]:
        return "technician is inactive"
    if staff["site"] != asset["site"]:
        return "technician works at another site"
    return None


# --- work orders: helpers -------------------------------------------------------------

def _load_work_order(work_order_id):
    order = repository.get_work_order(work_order_id)
    if order is None:
        raise NotFound("No such work order.")
    return order


def _ensure_can_read(ctx, order):
    if not permissions.can_read_work_order(ctx.user, order, repository.get_asset(order["asset"])):
        raise Forbidden()


def _existing_asset_in(data):
    """The asset a create body refers to, if it names an existing one; otherwise None."""
    asset_id = data.get("asset") if isinstance(data, dict) else None
    return repository.get_asset(asset_id) if validation.is_integer(asset_id) else None


def _require_status(order, statuses, message):
    if order["status"] not in statuses:
        raise Conflict(message)


# --- outbox ---------------------------------------------------------------------------

def list_outbox(ctx, filters=None):
    """Any authenticated user may read the outbox."""
    return apply_filters(repository.list_outbox_messages(), filters or {}, OUTBOX_FIELDS)
