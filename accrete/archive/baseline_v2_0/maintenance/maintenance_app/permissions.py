"""Who may do what. Pure functions of the calling staff member and the records involved.

``asset`` is the asset record a work order is raised against (its ``site`` decides which
technicians may read the order and where requesters/technicians may raise orders).
These answer only "is this user allowed?"; state rules (409) live in ``services``.
Inactive staff keep all the rights of their role (``active`` only matters for ``assign``).
"""

# Work order fields only a supervisor may change; the requester sending one gets a 403.
# (Other non-editable fields are a 400, reported by validation.)
WORK_ORDER_SUPERVISOR_ONLY = {"priority"}


def is_supervisor(user):
    return user["role"] == "supervisor"


def is_technician(user):
    return user["role"] == "technician"


def is_requester_of(user, order):
    return order["requested_by"] == user["id"]


def is_assignee_of(user, order):
    return order["assignee"] == user["id"]


# --- staff and assets -----------------------------------------------------------------

def can_read_staff(user, staff):
    return True


def can_manage_staff(user):
    """Create, update and delete staff."""
    return is_supervisor(user)


def can_read_asset(user, asset):
    return True


def can_manage_assets(user):
    """Create, update and delete assets."""
    return is_supervisor(user)


# --- work orders ----------------------------------------------------------------------

def can_read_work_order(user, order, asset):
    return (
        is_supervisor(user)
        or is_requester_of(user, order)
        or is_assignee_of(user, order)
        or (is_technician(user) and user["site"] == asset["site"])
    )


def can_create_work_order(user):
    return True


def can_create_work_order_for(user, asset):
    """Requesters and technicians only at their own site; supervisors anywhere."""
    return is_supervisor(user) or asset["site"] == user["site"]


def can_edit_work_order(user, order, fields):
    """PATCH: supervisors; or the requester, unless they send a supervisor-only field."""
    if is_supervisor(user):
        return True
    return is_requester_of(user, order) and not WORK_ORDER_SUPERVISOR_ONLY.intersection(fields)


def can_delete_work_order(user, order):
    return False


def can_assign_work_order(user, order):
    return is_supervisor(user)


def can_work_on_work_order(user, order):
    """``start`` and ``complete``: only the current assignee."""
    return is_assignee_of(user, order)


def can_cancel_work_order(user, order):
    return is_supervisor(user) or is_requester_of(user, order)
