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
    return redirect(url_for("ui.list_claims"))


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


def _number(value):
    value = value.strip()
    if value == "":
        return None
    for convert in (int, float):
        try:
            return convert(value)
        except ValueError:
            pass
    return value


# --- employees ------------------------------------------------------------------------

@bp.get("/employees")
def list_employees():
    employees = services.list_employees(current_context(), request.args.to_dict())
    return render_template("employees/list.html", employees=employees)


@bp.get("/employees/new")
def new_employee():
    ctx = current_context()
    services.ensure_can_create_employee(ctx)
    return render_template("employees/new.html", roles=validation.EMPLOYEE_ROLES,
                           managers=services.list_employees(ctx))


@bp.post("/employees")
def create_employee():
    data = _form_values({"username": _text, "name": _text, "role": _text, "manager": _optional_int,
                         "department": _text})
    employee = services.create_employee(current_context(), data)
    return redirect(url_for("ui.show_employee", employee_id=employee["id"]), 303)


@bp.get("/employees/<int:employee_id>")
def show_employee(employee_id):
    employee = services.get_employee(current_context(), employee_id)
    return render_template("employees/detail.html", employee=employee)


# --- claims ---------------------------------------------------------------------------

@bp.get("/claims")
def list_claims():
    claims = services.list_claims(current_context(), request.args.to_dict())
    return render_template("claims/list.html", claims=claims)


@bp.get("/claims/new")
def new_claim():
    services.ensure_can_create_claim(current_context())
    return render_template("claims/new.html", categories=validation.CLAIM_CATEGORIES)


@bp.post("/claims")
def create_claim():
    data = _form_values({"amount": _number, "category": _text, "description": _text})
    claim = services.create_claim(current_context(), data)
    return redirect(url_for("ui.show_claim", claim_id=claim["id"]), 303)


@bp.get("/claims/<int:claim_id>")
def show_claim(claim_id):
    ctx = current_context()
    claim = services.get_claim(ctx, claim_id)
    return render_template("claims/detail.html", claim=claim, actions=services.claim_actions(ctx, claim))


@bp.post("/claims/<int:claim_id>/submit")
def submit_claim(claim_id):
    services.submit_claim(current_context(), claim_id, {})
    return redirect(url_for("ui.show_claim", claim_id=claim_id), 303)


@bp.post("/claims/<int:claim_id>/approve")
def approve_claim(claim_id):
    services.approve_claim(current_context(), claim_id, {})
    return redirect(url_for("ui.show_claim", claim_id=claim_id), 303)


@bp.post("/claims/<int:claim_id>/reject")
def reject_claim(claim_id):
    services.reject_claim(current_context(), claim_id, _form_values({"reason": _text}))
    return redirect(url_for("ui.show_claim", claim_id=claim_id), 303)


@bp.post("/claims/<int:claim_id>/pay")
def pay_claim(claim_id):
    services.pay_claim(current_context(), claim_id, {})
    return redirect(url_for("ui.show_claim", claim_id=claim_id), 303)
