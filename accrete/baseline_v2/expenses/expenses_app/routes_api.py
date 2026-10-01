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


# --- employees ------------------------------------------------------------------------

@bp.get("/employees")
def list_employees():
    return _items(services.list_employees(current_context(), _filters()))


@bp.post("/employees")
def create_employee():
    return services.create_employee(current_context(), _body()), 201


@bp.get("/employees/<int:employee_id>")
def get_employee(employee_id):
    return services.get_employee(current_context(), employee_id)


@bp.patch("/employees/<int:employee_id>")
def update_employee(employee_id):
    return services.update_employee(current_context(), employee_id, _body())


@bp.delete("/employees/<int:employee_id>")
def delete_employee(employee_id):
    services.delete_employee(current_context(), employee_id)
    return "", 204


# --- claims ---------------------------------------------------------------------------

@bp.get("/claims")
def list_claims():
    return _items(services.list_claims(current_context(), _filters()))


@bp.post("/claims")
def create_claim():
    return services.create_claim(current_context(), _body()), 201


@bp.get("/claims/<int:claim_id>")
def get_claim(claim_id):
    return services.get_claim(current_context(), claim_id)


@bp.patch("/claims/<int:claim_id>")
def update_claim(claim_id):
    return services.update_claim(current_context(), claim_id, _body())


@bp.delete("/claims/<int:claim_id>")
def delete_claim(claim_id):
    services.delete_claim(current_context(), claim_id)
    return "", 204


@bp.post("/claims/<int:claim_id>/submit")
def submit_claim(claim_id):
    return services.submit_claim(current_context(), claim_id, _body())


@bp.post("/claims/<int:claim_id>/approve")
def approve_claim(claim_id):
    return services.approve_claim(current_context(), claim_id, _body())


@bp.post("/claims/<int:claim_id>/reject")
def reject_claim(claim_id):
    return services.reject_claim(current_context(), claim_id, _body())


@bp.post("/claims/<int:claim_id>/pay")
def pay_claim(claim_id):
    return services.pay_claim(current_context(), claim_id, _body())


# --- outbox ---------------------------------------------------------------------------

@bp.get("/_outbox")
def list_outbox():
    return _items(services.list_outbox(current_context(), _filters()))
