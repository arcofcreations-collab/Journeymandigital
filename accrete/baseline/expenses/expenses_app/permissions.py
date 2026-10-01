"""Who may do what. Pure functions of the calling employee and the records involved.

``claimant`` is the employee record a claim belongs to (needed to find their manager).
These answer only "is this user allowed?"; state rules (409) live in ``services``.
"""


def is_finance(user):
    return user["role"] == "finance"


def is_manager_of(user, employee):
    """Direct manager only: the employee's ``manager`` reference points at ``user``."""
    return employee["manager"] == user["id"]


# --- employees ------------------------------------------------------------------------

def can_read_employee(user, employee):
    return True


def can_manage_employees(user):
    """Create, update and delete employees."""
    return is_finance(user)


# --- claims ---------------------------------------------------------------------------

def can_create_claim(user):
    return True


def can_read_claim(user, claim, claimant):
    return claim["employee"] == user["id"] or is_manager_of(user, claimant) or is_finance(user)


def can_edit_claim(user, claim):
    """PATCH and DELETE: only the claim's own employee."""
    return claim["employee"] == user["id"]


def can_submit_claim(user, claim):
    return claim["employee"] == user["id"]


def can_decide_claim(user, claimant):
    """Approve or reject: the claimant's manager."""
    return is_manager_of(user, claimant)


def can_pay_claim(user, claim):
    return is_finance(user)
