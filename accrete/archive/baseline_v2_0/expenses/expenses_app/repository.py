"""Data access: all SQL lives here.

Functions return plain dicts shaped like API records (references as ids under the API
field name). Values passed to insert/update functions have already been validated by
``services``.
"""
import json

from .db import get_db

# --- employees ------------------------------------------------------------------------

_EMPLOYEE_SELECT = "SELECT id, username, name, role, manager_id, department FROM employees"


def _employee(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "role": row["role"],
        "manager": row["manager_id"],
        "department": row["department"],
    }


def list_employees():
    return [_employee(row) for row in get_db().execute(f"{_EMPLOYEE_SELECT} ORDER BY id")]


def get_employee(employee_id):
    return _employee(get_db().execute(f"{_EMPLOYEE_SELECT} WHERE id = ?", (employee_id,)).fetchone())


def get_employee_by_username(username):
    return _employee(get_db().execute(f"{_EMPLOYEE_SELECT} WHERE username = ?", (username,)).fetchone())


def username_taken(username, exclude_id=None):
    row = get_db().execute(
        "SELECT 1 FROM employees WHERE username = ? AND id IS NOT ?", (username, exclude_id)
    ).fetchone()
    return row is not None


def insert_employee(values):
    cur = get_db().execute(
        "INSERT INTO employees (username, name, role, manager_id, department) VALUES (?, ?, ?, ?, ?)",
        (values["username"], values["name"], values["role"], values["manager"], values["department"]),
    )
    return cur.lastrowid


def update_employee(employee_id, values):
    columns = {"username": "username", "name": "name", "role": "role", "manager": "manager_id",
               "department": "department"}
    _update("employees", columns, employee_id, values)


def delete_employee(employee_id):
    get_db().execute("DELETE FROM employees WHERE id = ?", (employee_id,))


def employee_is_referenced(employee_id):
    """True if the employee has claims, decided claims or reports (rows that point at them)."""
    row = get_db().execute(
        """
        SELECT EXISTS (SELECT 1 FROM claims WHERE employee_id = :id OR decided_by_id = :id)
            OR EXISTS (SELECT 1 FROM employees WHERE manager_id = :id)
        """,
        {"id": employee_id},
    ).fetchone()
    return bool(row[0])


# --- claims ---------------------------------------------------------------------------

_CLAIM_SELECT = """
    SELECT id, employee_id, amount, category, description, status,
           submitted_at, decided_at, decided_by_id, rejection_reason
    FROM claims
"""


def _claim(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "employee": row["employee_id"],
        "amount": row["amount"],
        "category": row["category"],
        "description": row["description"],
        "status": row["status"],
        "submitted_at": row["submitted_at"],
        "decided_at": row["decided_at"],
        "decided_by": row["decided_by_id"],
        "rejection_reason": row["rejection_reason"],
    }


def list_claims():
    return [_claim(row) for row in get_db().execute(f"{_CLAIM_SELECT} ORDER BY id")]


def get_claim(claim_id):
    return _claim(get_db().execute(f"{_CLAIM_SELECT} WHERE id = ?", (claim_id,)).fetchone())


def insert_claim(employee_id, values):
    """Insert a new claim in ``draft`` status."""
    cur = get_db().execute(
        "INSERT INTO claims (employee_id, amount, category, description, status) VALUES (?, ?, ?, ?, 'draft')",
        (employee_id, values["amount"], values["category"], values["description"]),
    )
    return cur.lastrowid


def update_claim(claim_id, values):
    columns = {"amount": "amount", "category": "category", "description": "description"}
    _update("claims", columns, claim_id, values)


def delete_claim(claim_id):
    get_db().execute("DELETE FROM claims WHERE id = ?", (claim_id,))


def mark_claim_submitted(claim_id, submitted_at):
    get_db().execute(
        "UPDATE claims SET status = 'submitted', submitted_at = ? WHERE id = ?", (submitted_at, claim_id)
    )


def mark_claim_decided(claim_id, status, decided_at, decided_by, rejection_reason=None):
    """Record a manager's decision; ``status`` is 'approved' or 'rejected'."""
    get_db().execute(
        "UPDATE claims SET status = ?, decided_at = ?, decided_by_id = ?, rejection_reason = ? WHERE id = ?",
        (status, decided_at, decided_by, rejection_reason, claim_id),
    )


def mark_claim_paid(claim_id):
    get_db().execute("UPDATE claims SET status = 'paid' WHERE id = ?", (claim_id,))


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
