"""Business rules and the claim workflow for expense claims.

Every function takes the ``RequestContext`` (caller + clock) first and returns API-shaped
records. Checks run in the contract's precedence order: the record exists (404), the
caller is allowed (403), the record's state allows it (409), the input is valid (400).

Claim workflow::

    draft --submit--> submitted --approve--> approved --pay--> paid
                                \\--reject--> rejected
"""
from . import permissions, repository, validation
from .db import transaction
from .errors import Conflict, Forbidden, NotFound, ValidationError
from .filters import apply_filters

EMPLOYEE_FIELDS = ("id", "username", "name", "role", "manager", "department")
CLAIM_FIELDS = ("id", "employee", "amount", "category", "description", "status",
                "submitted_at", "decided_at", "decided_by", "rejection_reason")
OUTBOX_FIELDS = ("id", "channel", "created_at")


# --- employees ------------------------------------------------------------------------

def list_employees(ctx, filters=None):
    employees = [e for e in repository.list_employees() if permissions.can_read_employee(ctx.user, e)]
    return apply_filters(employees, filters or {}, EMPLOYEE_FIELDS)


def get_employee(ctx, employee_id):
    employee = _load_employee(employee_id)
    if not permissions.can_read_employee(ctx.user, employee):
        raise Forbidden()
    return employee


def ensure_can_create_employee(ctx):
    if not permissions.can_manage_employees(ctx.user):
        raise Forbidden("Only finance can create employees.")


def create_employee(ctx, data):
    ensure_can_create_employee(ctx)
    with transaction():
        values = validation.clean_employee(data, partial=False)
        _check_employee_references(values)
        employee_id = repository.insert_employee(values)
    return repository.get_employee(employee_id)


def update_employee(ctx, employee_id, data):
    with transaction():
        _load_employee(employee_id)
        if not permissions.can_manage_employees(ctx.user):
            raise Forbidden("Only finance can update employees.")
        values = validation.clean_employee(data, partial=True)
        _check_employee_references(values, employee_id)
        repository.update_employee(employee_id, values)
    return repository.get_employee(employee_id)


def delete_employee(ctx, employee_id):
    with transaction():
        _load_employee(employee_id)
        if not permissions.can_manage_employees(ctx.user):
            raise Forbidden("Only finance can delete employees.")
        if repository.employee_is_referenced(employee_id):
            raise Conflict("An employee with claims or reports cannot be deleted.")
        repository.delete_employee(employee_id)


def _load_employee(employee_id):
    employee = repository.get_employee(employee_id)
    if employee is None:
        raise NotFound("No such employee.")
    return employee


def _check_employee_references(values, employee_id=None):
    """Username must be unique; ``manager`` must exist and not create a reporting loop."""
    errors = {}
    if "username" in values and repository.username_taken(values["username"], employee_id):
        errors["username"] = "already in use"
    manager_id = values.get("manager")
    if manager_id is not None:
        if repository.get_employee(manager_id) is None:
            errors["manager"] = "no such employee"
        elif employee_id is not None and _is_same_or_reports_to(manager_id, employee_id):
            errors["manager"] = "would make the employee their own manager"
    if errors:
        raise ValidationError("Invalid input.", errors)


def _is_same_or_reports_to(employee_id, boss_id):
    """True if ``employee_id`` is ``boss_id`` or reports to them, directly or indirectly."""
    seen = set()
    while employee_id is not None and employee_id not in seen:
        if employee_id == boss_id:
            return True
        seen.add(employee_id)
        employee_id = repository.get_employee(employee_id)["manager"]
    return False


# --- claims ---------------------------------------------------------------------------

def list_claims(ctx, filters=None):
    employees = {e["id"]: e for e in repository.list_employees()}
    claims = [
        c for c in repository.list_claims()
        if permissions.can_read_claim(ctx.user, c, employees[c["employee"]])
    ]
    return apply_filters(claims, filters or {}, CLAIM_FIELDS)


def get_claim(ctx, claim_id):
    claim = _load_claim(claim_id)
    if not permissions.can_read_claim(ctx.user, claim, _claimant(claim)):
        raise Forbidden()
    return claim


def ensure_can_create_claim(ctx):
    if not permissions.can_create_claim(ctx.user):
        raise Forbidden()


def create_claim(ctx, data):
    """Create a draft claim owned by the caller."""
    ensure_can_create_claim(ctx)
    with transaction():
        values = validation.clean_claim(data, partial=False)
        claim_id = repository.insert_claim(ctx.user["id"], values)
    return repository.get_claim(claim_id)


def update_claim(ctx, claim_id, data):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_edit_claim(ctx.user, claim):
            raise Forbidden("Only the claim's employee can edit it.")
        _require_status(claim, "draft", "Only draft claims can be edited.")
        values = validation.clean_claim(data, partial=True)
        repository.update_claim(claim_id, values)
    return repository.get_claim(claim_id)


def delete_claim(ctx, claim_id):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_edit_claim(ctx.user, claim):
            raise Forbidden("Only the claim's employee can delete it.")
        _require_status(claim, "draft", "Only draft claims can be deleted.")
        repository.delete_claim(claim_id)


def submit_claim(ctx, claim_id, params):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_submit_claim(ctx.user, claim):
            raise Forbidden("Only the claim's employee can submit it.")
        _require_status(claim, "draft", "Only draft claims can be submitted.")
        validation.clean_no_params(params)
        repository.mark_claim_submitted(claim_id, ctx.now_text)
    return repository.get_claim(claim_id)


def approve_claim(ctx, claim_id, params):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_decide_claim(ctx.user, _claimant(claim)):
            raise Forbidden("Only the employee's manager can approve the claim.")
        _require_status(claim, "submitted", "Only submitted claims can be approved.")
        validation.clean_no_params(params)
        repository.mark_claim_decided(claim_id, "approved", ctx.now_text, ctx.user["id"])
    return repository.get_claim(claim_id)


def reject_claim(ctx, claim_id, params):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_decide_claim(ctx.user, _claimant(claim)):
            raise Forbidden("Only the employee's manager can reject the claim.")
        _require_status(claim, "submitted", "Only submitted claims can be rejected.")
        reason = validation.clean_reject_params(params)
        repository.mark_claim_decided(claim_id, "rejected", ctx.now_text, ctx.user["id"], reason)
    return repository.get_claim(claim_id)


def pay_claim(ctx, claim_id, params):
    with transaction():
        claim = _load_claim(claim_id)
        if not permissions.can_pay_claim(ctx.user, claim):
            raise Forbidden("Only finance can pay claims.")
        _require_status(claim, "approved", "Only approved claims can be paid.")
        validation.clean_no_params(params)
        repository.mark_claim_paid(claim_id)
        repository.add_outbox_message(
            "payment", {"claim": claim_id, "employee": claim["employee"], "amount": claim["amount"]}, ctx.now_text
        )
    return repository.get_claim(claim_id)


def claim_actions(ctx, claim):
    """Names of the actions the caller could successfully start on ``claim`` right now."""
    user, status = ctx.user, claim["status"]
    actions = []
    if status == "draft" and permissions.can_submit_claim(user, claim):
        actions.append("submit")
    if status == "submitted" and permissions.can_decide_claim(user, _claimant(claim)):
        actions += ["approve", "reject"]
    if status == "approved" and permissions.can_pay_claim(user, claim):
        actions.append("pay")
    return actions


def _load_claim(claim_id):
    claim = repository.get_claim(claim_id)
    if claim is None:
        raise NotFound("No such claim.")
    return claim


def _claimant(claim):
    return repository.get_employee(claim["employee"])


def _require_status(claim, status, message):
    if claim["status"] != status:
        raise Conflict(message)


# --- outbox ---------------------------------------------------------------------------

def list_outbox(ctx, filters=None):
    """Any authenticated user may read the outbox."""
    return apply_filters(repository.list_outbox_messages(), filters or {}, OUTBOX_FIELDS)
