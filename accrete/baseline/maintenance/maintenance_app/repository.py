"""Data access: all SQL lives here.

Functions return plain dicts shaped like API records (references as ids under the API
field name, booleans as ``bool``). Values passed to insert/update functions have already
been validated by ``services``.

Derived values that depend only on stored data (``assets.open_orders``) are computed in
SQL here; those that depend on the request's clock (``work_orders.due_date``/``overdue``)
are added by ``services.present_work_order``.
"""
import json

from .db import get_db
from .validation import UNFINISHED_STATUSES

_UNFINISHED_SQL = "(" + ", ".join(f"'{status}'" for status in UNFINISHED_STATUSES) + ")"

# --- staff ----------------------------------------------------------------------------

_STAFF_SELECT = "SELECT id, username, name, role, site, active FROM staff"


def _staff(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "site": row["site"],
        "active": bool(row["active"]),
    }


def list_staff():
    return [_staff(row) for row in get_db().execute(f"{_STAFF_SELECT} ORDER BY id")]


def get_staff(staff_id):
    return _staff(get_db().execute(f"{_STAFF_SELECT} WHERE id = ?", (staff_id,)).fetchone())


def get_staff_by_username(username):
    return _staff(get_db().execute(f"{_STAFF_SELECT} WHERE username = ?", (username,)).fetchone())


def username_taken(username, exclude_id=None):
    row = get_db().execute(
        "SELECT 1 FROM staff WHERE username = ? AND id IS NOT ?", (username, exclude_id)
    ).fetchone()
    return row is not None


def insert_staff(values):
    cur = get_db().execute(
        "INSERT INTO staff (username, name, role, site, active) VALUES (?, ?, ?, ?, ?)",
        (values["username"], values["name"], values["role"], values["site"], int(values["active"])),
    )
    return cur.lastrowid


def update_staff(staff_id, values):
    columns = {"username": "username", "name": "name", "role": "role", "site": "site", "active": "active"}
    _update("staff", columns, staff_id, values)


def delete_staff(staff_id):
    get_db().execute("DELETE FROM staff WHERE id = ?", (staff_id,))


def staff_has_work_orders(staff_id):
    """True if the staff member requested or is assigned to any work order."""
    row = get_db().execute(
        "SELECT 1 FROM work_orders WHERE requested_by_id = :id OR assignee_id = :id LIMIT 1", {"id": staff_id}
    ).fetchone()
    return row is not None


# --- assets ---------------------------------------------------------------------------

_ASSET_SELECT = f"""
    SELECT a.id, a.tag, a.name, a.site, a.criticality, a.retired,
           (SELECT COUNT(*) FROM work_orders w
             WHERE w.asset_id = a.id AND w.status IN {_UNFINISHED_SQL}) AS open_orders
    FROM assets a
"""


def _asset(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "tag": row["tag"],
        "name": row["name"],
        "site": row["site"],
        "criticality": row["criticality"],
        "retired": bool(row["retired"]),
        "open_orders": row["open_orders"],
    }


def list_assets():
    return [_asset(row) for row in get_db().execute(f"{_ASSET_SELECT} ORDER BY a.id")]


def get_asset(asset_id):
    return _asset(get_db().execute(f"{_ASSET_SELECT} WHERE a.id = ?", (asset_id,)).fetchone())


def tag_taken(tag, exclude_id=None):
    row = get_db().execute("SELECT 1 FROM assets WHERE tag = ? AND id IS NOT ?", (tag, exclude_id)).fetchone()
    return row is not None


def insert_asset(values):
    cur = get_db().execute(
        "INSERT INTO assets (tag, name, site, criticality, retired) VALUES (?, ?, ?, ?, ?)",
        (values["tag"], values["name"], values["site"], values["criticality"], int(values["retired"])),
    )
    return cur.lastrowid


def update_asset(asset_id, values):
    columns = {"tag": "tag", "name": "name", "site": "site", "criticality": "criticality", "retired": "retired"}
    _update("assets", columns, asset_id, values)


def delete_asset(asset_id):
    get_db().execute("DELETE FROM assets WHERE id = ?", (asset_id,))


def asset_has_work_orders(asset_id):
    return get_db().execute("SELECT 1 FROM work_orders WHERE asset_id = ? LIMIT 1", (asset_id,)).fetchone() is not None


# --- work orders ----------------------------------------------------------------------

_WORK_ORDER_SELECT = """
    SELECT id, asset_id, title, description, priority, status, requested_by_id, created_at,
           assignee_id, started_at, completed_at, resolution, labor_minutes, cancel_reason
    FROM work_orders
"""


def _work_order(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "asset": row["asset_id"],
        "title": row["title"],
        "description": row["description"],
        "priority": row["priority"],
        "status": row["status"],
        "requested_by": row["requested_by_id"],
        "created_at": row["created_at"],
        "assignee": row["assignee_id"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "resolution": row["resolution"],
        "labor_minutes": row["labor_minutes"],
        "cancel_reason": row["cancel_reason"],
    }


def list_work_orders():
    return [_work_order(row) for row in get_db().execute(f"{_WORK_ORDER_SELECT} ORDER BY id")]


def get_work_order(work_order_id):
    return _work_order(get_db().execute(f"{_WORK_ORDER_SELECT} WHERE id = ?", (work_order_id,)).fetchone())


def insert_work_order(values, requested_by, created_at):
    """Insert a new work order in ``open`` status."""
    cur = get_db().execute(
        "INSERT INTO work_orders (asset_id, title, description, priority, status, requested_by_id, created_at)"
        " VALUES (?, ?, ?, ?, 'open', ?, ?)",
        (values["asset"], values["title"], values["description"], values["priority"], requested_by, created_at),
    )
    return cur.lastrowid


def update_work_order(work_order_id, values):
    columns = {"title": "title", "description": "description", "priority": "priority"}
    _update("work_orders", columns, work_order_id, values)


def mark_work_order_assigned(work_order_id, technician_id):
    get_db().execute(
        "UPDATE work_orders SET status = 'assigned', assignee_id = ? WHERE id = ?", (technician_id, work_order_id)
    )


def mark_work_order_started(work_order_id, started_at):
    get_db().execute(
        "UPDATE work_orders SET status = 'in_progress', started_at = ? WHERE id = ?", (started_at, work_order_id)
    )


def mark_work_order_completed(work_order_id, completed_at, resolution, labor_minutes):
    get_db().execute(
        "UPDATE work_orders SET status = 'completed', completed_at = ?, resolution = ?, labor_minutes = ?"
        " WHERE id = ?",
        (completed_at, resolution, labor_minutes, work_order_id),
    )


def mark_work_order_cancelled(work_order_id, reason):
    get_db().execute(
        "UPDATE work_orders SET status = 'cancelled', cancel_reason = ? WHERE id = ?", (reason, work_order_id)
    )


# --- outbox ---------------------------------------------------------------------------

def add_outbox_message(channel, payload, created_at):
    cur = get_db().execute(
        "INSERT INTO outbox (channel, payload, created_at) VALUES (?, ?, ?)",
        (channel, json.dumps(payload), created_at),
    )
    return cur.lastrowid


def list_outbox_messages():
    rows = get_db().execute("SELECT id, channel, payload, created_at FROM outbox ORDER BY id")
    return [
        {"id": r["id"], "channel": r["channel"], "payload": json.loads(r["payload"]), "created_at": r["created_at"]}
        for r in rows
    ]


# --- helpers --------------------------------------------------------------------------

def _update(table, columns, record_id, values):
    """UPDATE ``table`` setting the API fields in ``values`` (mapped through ``columns``)."""
    if not values:
        return
    assignments = ", ".join(f"{columns[field]} = ?" for field in values)
    get_db().execute(f"UPDATE {table} SET {assignments} WHERE id = ?", [*values.values(), record_id])
