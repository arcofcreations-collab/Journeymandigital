"""HTML user interface (``/ui``).

Pages follow the contract's markup conventions: list rows carry ``data-id``, detail pages
mark each field with ``data-field`` and offer one ``<form data-action>`` per action the
caller can run right now, and create pages hold a ``<form data-create>`` with inputs only
for fields the caller may set. Forms post back here; the handlers convert form strings to
JSON-like values and call the same services as the API.
"""
from flask import Blueprint, redirect, render_template, request, url_for

from . import permissions, services, validation
from .auth import current_context

bp = Blueprint("ui", __name__, url_prefix="/ui")


@bp.get("")
@bp.get("/")
def index():
    return redirect(url_for("ui.list_work_orders"))


# --- form value conversion ------------------------------------------------------------
# Form fields arrive as strings. Convert what we can; anything unconvertible is passed
# through unchanged so the service's validation reports it as a 400.

def _form_values(converters):
    return {name: convert(request.form[name]) for name, convert in converters.items() if name in request.form}


def _text(value):
    return value


def _optional_text(value):
    return value if value.strip() else None


def _integer(value):
    value = value.strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _boolean(value):
    return {"true": True, "false": False}.get(value.strip().lower(), value)


def _redirect_to_work_order(work_order_id):
    return redirect(url_for("ui.show_work_order", work_order_id=work_order_id), 303)


# --- staff ----------------------------------------------------------------------------

@bp.get("/staff")
def list_staff():
    staff = services.list_staff(current_context(), request.args.to_dict())
    return render_template("staff/list.html", staff=staff)


@bp.get("/staff/new")
def new_staff():
    services.ensure_can_create_staff(current_context())
    return render_template("staff/new.html", roles=validation.STAFF_ROLES)


@bp.post("/staff")
def create_staff():
    data = _form_values({"username": _text, "name": _text, "role": _text, "site": _text, "active": _boolean})
    staff = services.create_staff(current_context(), data)
    return redirect(url_for("ui.show_staff", staff_id=staff["id"]), 303)


@bp.get("/staff/<int:staff_id>")
def show_staff(staff_id):
    staff = services.get_staff(current_context(), staff_id)
    return render_template("staff/detail.html", staff=staff)


# --- assets ---------------------------------------------------------------------------

@bp.get("/assets")
def list_assets():
    assets = services.list_assets(current_context(), request.args.to_dict())
    return render_template("assets/list.html", assets=assets)


@bp.get("/assets/new")
def new_asset():
    services.ensure_can_create_asset(current_context())
    return render_template("assets/new.html", criticalities=validation.ASSET_CRITICALITIES)


@bp.post("/assets")
def create_asset():
    data = _form_values({"tag": _text, "name": _text, "site": _text, "criticality": _text, "retired": _boolean})
    asset = services.create_asset(current_context(), data)
    return redirect(url_for("ui.show_asset", asset_id=asset["id"]), 303)


@bp.get("/assets/<int:asset_id>")
def show_asset(asset_id):
    asset = services.get_asset(current_context(), asset_id)
    return render_template("assets/detail.html", asset=asset)


# --- work orders ----------------------------------------------------------------------

@bp.get("/work_orders")
def list_work_orders():
    orders = services.list_work_orders(current_context(), request.args.to_dict())
    return render_template("work_orders/list.html", work_orders=orders)


@bp.get("/work_orders/new")
def new_work_order():
    ctx = current_context()
    services.ensure_can_create_work_order(ctx)
    assets = [
        a for a in services.list_assets(ctx, {"retired": "false"})
        if permissions.can_create_work_order_for(ctx.user, a)
    ]
    return render_template("work_orders/new.html", assets=assets, priorities=validation.WORK_ORDER_PRIORITIES)


@bp.post("/work_orders")
def create_work_order():
    data = _form_values({"asset": _integer, "title": _text, "description": _optional_text, "priority": _text})
    order = services.create_work_order(current_context(), data)
    return _redirect_to_work_order(order["id"])


@bp.get("/work_orders/<int:work_order_id>")
def show_work_order(work_order_id):
    ctx = current_context()
    order = services.get_work_order(ctx, work_order_id)
    actions = services.work_order_actions(ctx, order)
    technicians = []
    if "assign" in actions:
        technicians = services.eligible_technicians(services.get_asset(ctx, order["asset"]))
    return render_template("work_orders/detail.html", order=order, actions=actions, technicians=technicians)


@bp.post("/work_orders/<int:work_order_id>/assign")
def assign_work_order(work_order_id):
    services.assign_work_order(current_context(), work_order_id, _form_values({"technician": _integer}))
    return _redirect_to_work_order(work_order_id)


@bp.post("/work_orders/<int:work_order_id>/start")
def start_work_order(work_order_id):
    services.start_work_order(current_context(), work_order_id, {})
    return _redirect_to_work_order(work_order_id)


@bp.post("/work_orders/<int:work_order_id>/complete")
def complete_work_order(work_order_id):
    params = _form_values({"resolution": _text, "labor_minutes": _integer})
    services.complete_work_order(current_context(), work_order_id, params)
    return _redirect_to_work_order(work_order_id)


@bp.post("/work_orders/<int:work_order_id>/cancel")
def cancel_work_order(work_order_id):
    services.cancel_work_order(current_context(), work_order_id, _form_values({"reason": _text}))
    return _redirect_to_work_order(work_order_id)
