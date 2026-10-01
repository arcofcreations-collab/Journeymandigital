"""JSON API (``/api``). Handlers are thin: read the request, call a service, respond."""
from flask import Blueprint, request

from . import services
from .auth import current_context

bp = Blueprint("api", __name__, url_prefix="/api")

_INVALID_JSON = object()


def _body():
    """The request's JSON body: ``{}`` when empty, a non-dict marker when malformed.

    Services validate the shape themselves, after the 404/403/409 checks, so that
    error precedence holds even for malformed bodies.
    """
    if not request.get_data():
        return {}
    data = request.get_json(force=True, silent=True)
    return _INVALID_JSON if data is None else data


def _filters():
    return request.args.to_dict()


def _items(records):
    return {"items": records}


# --- staff ----------------------------------------------------------------------------

@bp.get("/staff")
def list_staff():
    return _items(services.list_staff(current_context(), _filters()))


@bp.post("/staff")
def create_staff():
    return services.create_staff(current_context(), _body()), 201


@bp.get("/staff/<int:staff_id>")
def get_staff(staff_id):
    return services.get_staff(current_context(), staff_id)


@bp.patch("/staff/<int:staff_id>")
def update_staff(staff_id):
    return services.update_staff(current_context(), staff_id, _body())


@bp.delete("/staff/<int:staff_id>")
def delete_staff(staff_id):
    services.delete_staff(current_context(), staff_id)
    return "", 204


# --- assets ---------------------------------------------------------------------------

@bp.get("/assets")
def list_assets():
    return _items(services.list_assets(current_context(), _filters()))


@bp.post("/assets")
def create_asset():
    return services.create_asset(current_context(), _body()), 201


@bp.get("/assets/<int:asset_id>")
def get_asset(asset_id):
    return services.get_asset(current_context(), asset_id)


@bp.patch("/assets/<int:asset_id>")
def update_asset(asset_id):
    return services.update_asset(current_context(), asset_id, _body())


@bp.delete("/assets/<int:asset_id>")
def delete_asset(asset_id):
    services.delete_asset(current_context(), asset_id)
    return "", 204


# --- work orders ----------------------------------------------------------------------

@bp.get("/work_orders")
def list_work_orders():
    return _items(services.list_work_orders(current_context(), _filters()))


@bp.post("/work_orders")
def create_work_order():
    return services.create_work_order(current_context(), _body()), 201


@bp.get("/work_orders/<int:work_order_id>")
def get_work_order(work_order_id):
    return services.get_work_order(current_context(), work_order_id)


@bp.patch("/work_orders/<int:work_order_id>")
def update_work_order(work_order_id):
    return services.update_work_order(current_context(), work_order_id, _body())


@bp.delete("/work_orders/<int:work_order_id>")
def delete_work_order(work_order_id):
    services.delete_work_order(current_context(), work_order_id)
    return "", 204


@bp.post("/work_orders/<int:work_order_id>/assign")
def assign_work_order(work_order_id):
    return services.assign_work_order(current_context(), work_order_id, _body())


@bp.post("/work_orders/<int:work_order_id>/start")
def start_work_order(work_order_id):
    return services.start_work_order(current_context(), work_order_id, _body())


@bp.post("/work_orders/<int:work_order_id>/complete")
def complete_work_order(work_order_id):
    return services.complete_work_order(current_context(), work_order_id, _body())


@bp.post("/work_orders/<int:work_order_id>/cancel")
def cancel_work_order(work_order_id):
    return services.cancel_work_order(current_context(), work_order_id, _body())


# --- outbox ---------------------------------------------------------------------------

@bp.get("/_outbox")
def list_outbox():
    return _items(services.list_outbox(current_context(), _filters()))
