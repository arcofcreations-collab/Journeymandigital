"""Strict acceptance tests for the `expenses` application (spec/apps/expenses.md + CONTRACT.md).

All expected values are derived from spec/apps/expenses_seed.json and hard-coded here.

Seed facts used below (verified against the seed file):
  employees: 1 fiona (finance), 2 marco (manager), 3 nadia (manager), 4 omar (manager, mgr 2),
             5 priya (mgr 4), 6 quinn (mgr 2), 7 rosa (mgr 3), 8 sam (mgr 4), 9 tariq (mgr 2),
             10 uma (mgr 3), 11 victor (mgr 4), 12 wen (mgr 2), 13 xena (mgr 3),
             14 yusuf (mgr 4), 15 zoe (mgr 2)
  claim 2  : victor, 734.81, meals, submitted (2026-01-25T12:00:00)
  claim 7  : yusuf, 613.88, equipment, rejected, decided 2026-01-30T09:00:00 by 4, "Missing receipt"
  claim 20 : sam, 1553.42, travel, "Keyboard #20", draft
  claim 22 : sam, 1455.12, meals, approved (submitted 2026-01-09T15:00:00, decided 2026-01-11T13:00:00 by 4)
  claim 43 : omar, submitted
  claim 6  : victor, paid
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

SAM_CLAIMS = [20, 22, 42, 48, 54, 61, 73]
PRIYA_CLAIMS = [14, 33, 44, 45, 51]
MARCO_READABLE = [1, 3, 8, 10, 11, 12, 18, 19, 24, 25, 29, 34, 35, 43, 46, 50, 52, 53, 55, 56,
                  59, 66, 68, 71, 74]
NADIA_READABLE = [4, 9, 13, 16, 26, 27, 30, 32, 37, 38, 39, 47, 57, 58, 62, 63, 65, 67, 69, 70,
                  72, 76, 77, 78]
OMAR_READABLE = [2, 5, 6, 7, 14, 15, 17, 18, 19, 20, 21, 22, 23, 28, 31, 33, 36, 40, 41, 42, 43,
                 44, 45, 48, 49, 50, 51, 52, 54, 59, 60, 61, 64, 73, 75, 79, 80]
DRAFT_CLAIMS = [1, 8, 9, 19, 20, 29, 39, 46, 54, 73, 75, 79]
MEALS_CLAIMS = [2, 21, 22, 53, 62, 72, 79]

PROTECTED = {
    "employee": 5,
    "status": "approved",
    "submitted_at": "2026-03-01T12:00:00",
    "decided_at": "2026-03-01T12:00:00",
    "decided_by": 4,
    "rejection_reason": "x",
}


def assert_error(r, status, code):
    assert r.status == status, r
    body = r.json
    assert isinstance(body, dict), r
    assert body.get("error") == code, r
    assert isinstance(body.get("message"), str), r
    assert isinstance(body.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def claim(app, cid, user="fiona", now=NOW):
    r = app.get(f"/api/claims/{cid}", user=user, now=now)
    assert r.status == 200, r
    return r.json


def new_claim(app, user, amount=120.5, category="meals", description="Client dinner"):
    r = app.post("/api/claims", {"amount": amount, "category": category, "description": description},
                 user=user, now=NOW)
    assert r.status == 201, r
    return r.json


# --------------------------------------------------------------------------- identity / errors

def test_missing_and_unknown_user_are_401():
    app = fresh_app()
    assert_error(app.get("/api/claims", user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/employees", user="nobody", now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/claims", {"amount": 10, "category": "meals", "description": "d"},
                          user=None, now=NOW), 401, "unauthenticated")
    assert_error(app.post("/api/claims/22/pay", {}, user="ghost", now=NOW), 401, "unauthenticated")
    assert_error(app.get("/api/claims/999", user=None, now=NOW), 401, "unauthenticated")


def test_not_found_errors():
    app = fresh_app()
    assert_error(app.get("/api/invoices", user="sam", now=NOW), 404, "not_found")
    assert_error(app.get("/api/claims/999", user="fiona", now=NOW), 404, "not_found")
    assert_error(app.get("/api/claims/999", user="sam", now=NOW), 404, "not_found")
    assert_error(app.get("/api/employees/999", user="sam", now=NOW), 404, "not_found")
    assert_error(app.post("/api/claims/999/approve", {}, user="omar", now=NOW), 404, "not_found")
    assert_error(app.post("/api/claims/20/archive", {}, user="sam", now=NOW), 404, "not_found")
    assert_error(app.patch("/api/claims/999", {"amount": 1}, user="sam", now=NOW), 404, "not_found")
    assert_error(app.delete("/api/claims/999", user="sam", now=NOW), 404, "not_found")


# --------------------------------------------------------------------------- employees: reads

def test_any_user_reads_all_employees():
    app = fresh_app()
    for user in ("sam", "marco", "fiona"):
        assert ids(app.get("/api/employees", user=user, now=NOW)) == list(range(1, 16))
    r = app.get("/api/employees/4", user="priya", now=NOW)
    assert r.status == 200, r
    e = r.json
    assert e["username"] == "omar" and e["name"] == "Omar Haddad"
    assert e["role"] == "manager" and e["manager"] == 2 and e["department"] == "Engineering"
    f = app.get("/api/employees/1", user="priya", now=NOW).json
    assert "manager" in f and f["manager"] is None


def test_employee_list_filters():
    app = fresh_app()
    assert ids(app.get("/api/employees?department=Sales", user="sam", now=NOW)) == [3, 7, 10, 13]
    assert ids(app.get("/api/employees?manager=4", user="sam", now=NOW)) == [5, 8, 11, 14]
    assert ids(app.get("/api/employees?role=manager", user="sam", now=NOW)) == [2, 3, 4]
    assert ids(app.get("/api/employees?username=zoe", user="sam", now=NOW)) == [15]


# --------------------------------------------------------------------------- employees: writes

def test_finance_creates_employee():
    app = fresh_app()
    body = {"username": "anna", "name": "Anna Berg", "role": "employee", "manager": 2,
            "department": "Engineering"}
    r = app.post("/api/employees", body, user="fiona", now=NOW)
    assert r.status == 201, r
    for k, v in body.items():
        assert r.json[k] == v, k
    assert isinstance(r.json["id"], int) and r.json["id"] not in range(1, 16)
    assert r.json["id"] in ids(app.get("/api/employees", user="sam", now=NOW))


def test_employee_manager_is_optional():
    app = fresh_app()
    r = app.post("/api/employees", {"username": "bo", "name": "Bo", "role": "finance",
                                    "department": "Finance"}, user="fiona", now=NOW)
    assert r.status == 201, r
    assert "manager" in r.json and r.json["manager"] is None


def test_employee_create_validation():
    app = fresh_app()
    full = {"username": "anna", "name": "Anna", "role": "employee", "manager": 2, "department": "Ops"}
    for missing in ("username", "name", "role", "department"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/employees", body, user="fiona", now=NOW), 400, "validation")
    assert_error(app.post("/api/employees", dict(full, username="sam"), user="fiona", now=NOW), 400, "validation")
    assert_error(app.post("/api/employees", dict(full, role="boss"), user="fiona", now=NOW), 400, "validation")
    assert ids(app.get("/api/employees", user="fiona", now=NOW)) == list(range(1, 16))


def test_non_finance_cannot_write_employees():
    app = fresh_app()
    body = {"username": "anna", "name": "Anna", "role": "employee", "department": "Ops"}
    for user in ("marco", "sam"):
        assert_error(app.post("/api/employees", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/employees", {}, user=user, now=NOW), 403, "forbidden")  # 403 before 400
        assert_error(app.patch("/api/employees/8", {"department": "Sales"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/employees/15", user=user, now=NOW), 403, "forbidden")
    assert app.get("/api/employees/8", user="sam", now=NOW).json["department"] == "Engineering"


def test_finance_updates_and_deletes_employee():
    app = fresh_app()
    r = app.patch("/api/employees/5", {"department": "Sales"}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert r.json["department"] == "Sales" and r.json["username"] == "priya" and r.json["manager"] == 4
    assert_error(app.patch("/api/employees/5", {"role": "boss"}, user="fiona", now=NOW), 400, "validation")
    assert_error(app.patch("/api/employees/5", {"username": "sam"}, user="fiona", now=NOW), 400, "validation")
    new = app.post("/api/employees", {"username": "temp", "name": "Temp", "role": "employee",
                                      "department": "Ops"}, user="fiona", now=NOW).json
    assert app.delete(f"/api/employees/{new['id']}", user="fiona", now=NOW).status == 204
    assert_error(app.get(f"/api/employees/{new['id']}", user="fiona", now=NOW), 404, "not_found")


# --------------------------------------------------------------------------- claims: reads

def test_claim_lists_per_role():
    app = fresh_app()
    assert ids(app.get("/api/claims", user="sam", now=NOW)) == SAM_CLAIMS
    assert ids(app.get("/api/claims", user="priya", now=NOW)) == PRIYA_CLAIMS
    assert ids(app.get("/api/claims", user="omar", now=NOW)) == OMAR_READABLE
    assert ids(app.get("/api/claims", user="marco", now=NOW)) == MARCO_READABLE
    assert ids(app.get("/api/claims", user="nadia", now=NOW)) == NADIA_READABLE
    assert ids(app.get("/api/claims", user="fiona", now=NOW)) == list(range(1, 81))


def test_claim_list_filters():
    app = fresh_app()
    assert ids(app.get("/api/claims?status=draft", user="fiona", now=NOW)) == DRAFT_CLAIMS
    assert ids(app.get("/api/claims?status=draft", user="sam", now=NOW)) == [20, 54, 73]
    assert ids(app.get("/api/claims?category=meals", user="fiona", now=NOW)) == MEALS_CLAIMS
    assert ids(app.get("/api/claims?employee=5", user="omar", now=NOW)) == PRIYA_CLAIMS
    # marco is priya's skip-level manager, not her manager
    assert ids(app.get("/api/claims?employee=5", user="marco", now=NOW)) == []
    assert ids(app.get("/api/claims?decided_by=4&status=approved", user="fiona", now=NOW)) == [21, 22, 33, 41, 44, 61]


def test_claim_read_permissions():
    app = fresh_app()
    for user in ("sam", "omar", "fiona"):
        assert app.get("/api/claims/20", user=user, now=NOW).status == 200, user
    for user in ("priya", "marco", "nadia", "rosa"):
        assert_error(app.get("/api/claims/20", user=user, now=NOW), 403, "forbidden")


def test_claim_fields_match_seed():
    app = fresh_app()
    c = claim(app, 7, user="yusuf")
    expected = {"id": 7, "employee": 14, "amount": 613.88, "category": "equipment",
                "description": "Hotel night #7", "status": "rejected",
                "submitted_at": "2026-01-28T11:00:00", "decided_at": "2026-01-30T09:00:00",
                "decided_by": 4, "rejection_reason": "Missing receipt"}
    for k, v in expected.items():
        assert c[k] == v, (k, c.get(k))
    d = claim(app, 20, user="sam")
    for k in ("submitted_at", "decided_at", "decided_by", "rejection_reason"):
        assert k in d and d[k] is None, k
    assert d["amount"] == 1553.42 and d["status"] == "draft"


# --------------------------------------------------------------------------- claims: create

def test_create_claim_defaults():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 120.5, "category": "meals", "description": "Client dinner"},
                 user="priya", now=NOW)
    assert r.status == 201, r
    c = r.json
    assert isinstance(c["id"], int) and c["id"] not in range(1, 81)
    assert c["employee"] == 5
    assert c["amount"] == 120.5 and c["category"] == "meals" and c["description"] == "Client dinner"
    assert c["status"] == "draft"
    for k in ("submitted_at", "decided_at", "decided_by", "rejection_reason"):
        assert k in c and c[k] is None, k
    # readable by creator, her manager and finance; not by others
    assert app.get(f"/api/claims/{c['id']}", user="priya", now=NOW).status == 200
    assert app.get(f"/api/claims/{c['id']}", user="omar", now=NOW).status == 200
    assert app.get(f"/api/claims/{c['id']}", user="fiona", now=NOW).status == 200
    assert_error(app.get(f"/api/claims/{c['id']}", user="sam", now=NOW), 403, "forbidden")


def test_any_role_can_create_claims():
    app = fresh_app()
    assert new_claim(app, "fiona")["employee"] == 1
    assert new_claim(app, "marco")["employee"] == 2
    assert new_claim(app, "omar")["employee"] == 4


def test_create_claim_amount_bounds():
    app = fresh_app()
    assert new_claim(app, "sam", amount=5000)["amount"] == 5000
    assert new_claim(app, "sam", amount=0.01)["amount"] == 0.01
    for bad in (0, -5, 5000.01, 10000):
        r = app.post("/api/claims", {"amount": bad, "category": "meals", "description": "d"}, user="sam", now=NOW)
        assert_error(r, 400, "validation")


def test_create_claim_required_fields_and_category():
    app = fresh_app()
    full = {"amount": 50, "category": "travel", "description": "Taxi"}
    for missing in ("amount", "category", "description"):
        body = {k: v for k, v in full.items() if k != missing}
        assert_error(app.post("/api/claims", body, user="sam", now=NOW), 400, "validation")
    assert_error(app.post("/api/claims", dict(full, category="food"), user="sam", now=NOW), 400, "validation")
    for cat in ("travel", "meals", "equipment", "other"):
        assert new_claim(app, "sam", category=cat)["category"] == cat
    assert ids(app.get("/api/claims", user="sam", now=NOW))[:7] == SAM_CLAIMS


def test_create_claim_with_protected_field_is_400():
    app = fresh_app()
    base = {"amount": 50, "category": "travel", "description": "Taxi"}
    for field, value in PROTECTED.items():
        r = app.post("/api/claims", dict(base, **{field: value}), user="priya", now=NOW)
        assert_error(r, 400, "validation")
    # even sending one's own id as employee is refused
    assert_error(app.post("/api/claims", dict(base, employee=5), user="priya", now=NOW), 400, "validation")
    assert ids(app.get("/api/claims", user="priya", now=NOW)) == PRIYA_CLAIMS


# --------------------------------------------------------------------------- claims: patch / delete

def test_employee_patches_own_draft():
    app = fresh_app()
    r = app.patch("/api/claims/20", {"amount": 200, "category": "other", "description": "Updated"},
                  user="sam", now=NOW)
    assert r.status == 200, r
    assert r.json["amount"] == 200 and r.json["category"] == "other" and r.json["description"] == "Updated"
    assert r.json["status"] == "draft" and r.json["employee"] == 8
    r = app.patch("/api/claims/20", {"amount": 99.99}, user="sam", now=NOW)
    assert r.status == 200 and r.json["amount"] == 99.99 and r.json["description"] == "Updated"


def test_patch_non_draft_is_409():
    app = fresh_app()
    for cid in (22, 42):  # approved, paid (both sam's)
        assert_error(app.patch(f"/api/claims/{cid}", {"amount": 10}, user="sam", now=NOW), 409, "conflict")
    # 409 wins over 400
    assert_error(app.patch("/api/claims/22", {"amount": 6000}, user="sam", now=NOW), 409, "conflict")
    assert claim(app, 22)["amount"] == 1455.12


def test_patch_by_others_is_403():
    app = fresh_app()
    for user in ("omar", "fiona", "priya", "marco"):
        assert_error(app.patch("/api/claims/20", {"amount": 10}, user=user, now=NOW), 403, "forbidden")
    # 403 wins over 409 and 400
    assert_error(app.patch("/api/claims/22", {"amount": 6000}, user="omar", now=NOW), 403, "forbidden")
    assert claim(app, 20)["amount"] == 1553.42


def test_patch_validation():
    app = fresh_app()
    for body in ({"amount": 0}, {"amount": 5000.01}, {"category": "food"}):
        assert_error(app.patch("/api/claims/20", body, user="sam", now=NOW), 400, "validation")
    for field, value in PROTECTED.items():
        assert_error(app.patch("/api/claims/20", {field: value}, user="sam", now=NOW), 400, "validation")
    c = claim(app, 20)
    assert c["amount"] == 1553.42 and c["category"] == "travel" and c["status"] == "draft"
    assert c["employee"] == 8 and c["decided_by"] is None


def test_delete_own_draft():
    app = fresh_app()
    assert app.delete("/api/claims/20", user="sam", now=NOW).status == 204
    assert_error(app.get("/api/claims/20", user="fiona", now=NOW), 404, "not_found")
    assert ids(app.get("/api/claims", user="sam", now=NOW)) == [22, 42, 48, 54, 61, 73]


def test_delete_rules():
    app = fresh_app()
    assert_error(app.delete("/api/claims/22", user="sam", now=NOW), 409, "conflict")
    for user in ("omar", "fiona", "priya"):
        assert_error(app.delete("/api/claims/20", user=user, now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/claims/22", user="omar", now=NOW), 403, "forbidden")  # 403 before 409
    assert claim(app, 20)["status"] == "draft"
    assert claim(app, 22)["status"] == "approved"


# --------------------------------------------------------------------------- submit

def test_submit_own_draft():
    app = fresh_app()
    r = app.post("/api/claims/20/submit", {}, user="sam", now=T2)
    assert r.status == 200, r
    assert r.json["id"] == 20
    assert r.json["status"] == "submitted"
    assert r.json["submitted_at"] == T2
    assert r.json["decided_at"] is None and r.json["decided_by"] is None
    assert r.json["amount"] == 1553.42
    # no longer editable / deletable
    assert_error(app.patch("/api/claims/20", {"amount": 10}, user="sam", now=T2), 409, "conflict")
    assert_error(app.delete("/api/claims/20", user="sam", now=T2), 409, "conflict")


def test_submit_from_wrong_state_is_409():
    app = fresh_app()
    assert_error(app.post("/api/claims/22/submit", {}, user="sam", now=NOW), 409, "conflict")  # approved
    assert_error(app.post("/api/claims/42/submit", {}, user="sam", now=NOW), 409, "conflict")  # paid
    assert_error(app.post("/api/claims/7/submit", {}, user="yusuf", now=NOW), 409, "conflict")  # rejected
    assert_error(app.post("/api/claims/2/submit", {}, user="victor", now=NOW), 409, "conflict")  # submitted
    assert claim(app, 2)["submitted_at"] == "2026-01-25T12:00:00"


def test_submit_by_non_owner_is_403():
    app = fresh_app()
    for user in ("omar", "fiona", "priya"):
        assert_error(app.post("/api/claims/20/submit", {}, user=user, now=NOW), 403, "forbidden")
    assert claim(app, 20)["status"] == "draft"


# --------------------------------------------------------------------------- approve

def test_manager_approves_submitted_claim():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {}, user="omar", now=T2)
    assert r.status == 200, r
    c = r.json
    assert c["id"] == 2 and c["status"] == "approved"
    assert c["decided_at"] == T2 and c["decided_by"] == 4
    assert c["submitted_at"] == "2026-01-25T12:00:00"
    assert c["rejection_reason"] is None


def test_approve_permissions():
    app = fresh_app()
    # skip-level manager, other manager, finance, the employee themself
    for user in ("marco", "nadia", "fiona", "victor", "sam"):
        assert_error(app.post("/api/claims/2/approve", {}, user=user, now=NOW), 403, "forbidden")
    assert claim(app, 2)["status"] == "submitted"


def test_manager_claims_are_approved_by_their_own_manager():
    app = fresh_app()
    assert_error(app.post("/api/claims/43/approve", {}, user="omar", now=NOW), 403, "forbidden")
    r = app.post("/api/claims/43/approve", {}, user="marco", now=NOW)
    assert r.status == 200, r
    assert r.json["decided_by"] == 2 and r.json["status"] == "approved"


def test_approve_wrong_state_is_409():
    app = fresh_app()
    for cid in (20, 22, 42, 7):  # draft, approved, paid, rejected; all omar's reports
        assert_error(app.post(f"/api/claims/{cid}/approve", {}, user="omar", now=NOW), 409, "conflict")
    # 403 wins over 409
    assert_error(app.post("/api/claims/22/approve", {}, user="marco", now=NOW), 403, "forbidden")
    assert claim(app, 22)["decided_at"] == "2026-01-11T13:00:00"


# --------------------------------------------------------------------------- reject

def test_manager_rejects_submitted_claim():
    app = fresh_app()
    r = app.post("/api/claims/58/reject", {"reason": "Duplicate"}, user="nadia", now=T2)
    assert r.status == 200, r
    c = r.json
    assert c["id"] == 58 and c["status"] == "rejected"
    assert c["rejection_reason"] == "Duplicate"
    assert c["decided_at"] == T2 and c["decided_by"] == 3
    assert c["employee"] == 7


def test_reject_requires_reason():
    app = fresh_app()
    assert_error(app.post("/api/claims/2/reject", {}, user="omar", now=NOW), 400, "validation")
    assert_error(app.post("/api/claims/2/reject", {"reason": ""}, user="omar", now=NOW), 400, "validation")
    c = claim(app, 2)
    assert c["status"] == "submitted" and c["rejection_reason"] is None


def test_reject_permission_and_state_precedence():
    app = fresh_app()
    for user in ("marco", "fiona", "victor"):
        assert_error(app.post("/api/claims/2/reject", {"reason": "no"}, user=user, now=NOW), 403, "forbidden")
    # 403 wins over 400
    assert_error(app.post("/api/claims/2/reject", {}, user="fiona", now=NOW), 403, "forbidden")
    # wrong state: 409, and 409 wins over 400
    assert_error(app.post("/api/claims/22/reject", {"reason": "no"}, user="omar", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/22/reject", {}, user="omar", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/20/reject", {"reason": "no"}, user="omar", now=NOW), 409, "conflict")
    assert claim(app, 2)["status"] == "submitted"


# --------------------------------------------------------------------------- pay

def test_finance_pays_approved_claim_and_emits_payment():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=T2)
    assert r.status == 200, r
    c = r.json
    assert c["id"] == 22 and c["status"] == "paid"
    assert c["decided_by"] == 4 and c["decided_at"] == "2026-01-11T13:00:00"
    assert c["submitted_at"] == "2026-01-09T15:00:00"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    m = msgs[-1]
    assert m["channel"] == "payment"
    assert m["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}
    assert set(m) >= {"id", "channel", "payload", "created_at"}


def test_pay_permissions_and_state():
    app = fresh_app()
    before = outbox(app)
    for user in ("omar", "sam", "marco"):
        assert_error(app.post("/api/claims/22/pay", {}, user=user, now=NOW), 403, "forbidden")
    for cid in (20, 2, 6, 7):  # draft, submitted, paid, rejected
        assert_error(app.post(f"/api/claims/{cid}/pay", {}, user="fiona", now=NOW), 409, "conflict")
    # 403 wins over 409
    assert_error(app.post("/api/claims/2/pay", {}, user="omar", now=NOW), 403, "forbidden")
    assert outbox(app) == before
    assert claim(app, 22)["status"] == "approved"


def test_pay_twice_is_409():
    app = fresh_app()
    assert app.post("/api/claims/4/pay", {}, user="fiona", now=NOW).status == 200
    n = len(outbox(app))
    assert_error(app.post("/api/claims/4/pay", {}, user="fiona", now=NOW), 409, "conflict")
    assert len(outbox(app)) == n


def test_full_claim_lifecycle():
    app = fresh_app()
    c = new_claim(app, "rosa", amount=321.25, category="travel", description="Bus")
    cid = c["id"]
    assert app.post(f"/api/claims/{cid}/submit", {}, user="rosa", now="2026-03-03T10:00:00").status == 200
    r = app.post(f"/api/claims/{cid}/approve", {}, user="nadia", now="2026-03-04T11:00:00")
    assert r.status == 200 and r.json["decided_by"] == 3
    before = len(outbox(app))
    r = app.post(f"/api/claims/{cid}/pay", {}, user="fiona", now="2026-03-05T12:00:00")
    assert r.status == 200, r
    final = claim(app, cid, user="rosa")
    assert final["status"] == "paid"
    assert final["submitted_at"] == "2026-03-03T10:00:00"
    assert final["decided_at"] == "2026-03-04T11:00:00"
    assert final["employee"] == 7
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": cid, "employee": 7, "amount": 321.25}


def test_outbox_readable_by_any_user():
    app = fresh_app()
    assert app.post("/api/claims/22/pay", {}, user="fiona", now=NOW).status == 200
    r = app.get("/api/_outbox", user="sam", now=NOW)
    assert r.status == 200, r
    items = r.json["items"]
    assert [m["id"] for m in items] == sorted(m["id"] for m in items)
    assert any(m["channel"] == "payment" and m["payload"]["claim"] == 22 for m in items)
    assert_error(app.get("/api/_outbox", user=None, now=NOW), 401, "unauthenticated")


# --------------------------------------------------------------------------- UI

def test_ui_lists():
    app = fresh_app()
    r = app.get("/ui/claims", user="sam", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == SAM_CLAIMS
    assert parse_ui(app.get("/ui/claims", user="nadia", now=NOW).text).rows == NADIA_READABLE
    assert parse_ui(app.get("/ui/claims", user="fiona", now=NOW).text).rows == list(range(1, 81))
    assert parse_ui(app.get("/ui/employees", user="sam", now=NOW).text).rows == list(range(1, 16))


def test_ui_claim_detail_draft_owner():
    app = fresh_app()
    r = app.get("/ui/claims/20", user="sam", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["status"] == "draft"
    assert ui.fields["category"] == "travel"
    assert ui.fields["description"] == "Keyboard #20"
    assert "submit" in ui.actions
    for a in ("approve", "reject", "pay"):
        assert a not in ui.actions, a
    # the manager can read it but has no action on a draft
    ui = parse_ui(app.get("/ui/claims/20", user="omar", now=NOW).text)
    for a in ("submit", "approve", "reject", "pay"):
        assert a not in ui.actions, a


def test_ui_claim_detail_manager_and_finance_actions():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/claims/2", user="omar", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions
    assert "submit" not in ui.actions and "pay" not in ui.actions

    ui = parse_ui(app.get("/ui/claims/2", user="fiona", now=NOW).text)
    for a in ("submit", "approve", "reject", "pay"):
        assert a not in ui.actions, a

    ui = parse_ui(app.get("/ui/claims/22", user="fiona", now=NOW).text)
    assert "pay" in ui.actions
    assert "approve" not in ui.actions and "reject" not in ui.actions

    ui = parse_ui(app.get("/ui/claims/22", user="sam", now=NOW).text)
    for a in ("submit", "approve", "reject", "pay"):
        assert a not in ui.actions, a


def test_ui_claim_detail_rejected_fields():
    app = fresh_app()
    r = app.get("/ui/claims/7", user="yusuf", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["status"] == "rejected"
    assert ui.fields["rejection_reason"] == "Missing receipt"
    assert ui.fields["description"] == "Hotel night #7"
    assert {"employee", "amount", "category", "submitted_at", "decided_at", "decided_by"} <= set(ui.fields)
    for a in ("submit", "approve", "reject", "pay"):
        assert a not in ui.actions, a


def test_ui_detail_errors():
    app = fresh_app()
    assert app.get("/ui/claims/20", user="priya", now=NOW).status == 403
    assert app.get("/ui/claims/20", user="marco", now=NOW).status == 403
    assert app.get("/ui/claims/999", user="fiona", now=NOW).status == 404
    assert app.get("/ui/invoices", user="fiona", now=NOW).status == 404
    assert app.get("/ui/claims", user=None, now=NOW).status == 401
    assert app.get("/ui/claims/20", user="ghost", now=NOW).status == 401


def test_ui_employee_detail():
    app = fresh_app()
    r = app.get("/ui/employees/2", user="sam", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.fields["username"] == "marco"
    assert ui.fields["name"] == "Marco Diaz"
    assert ui.fields["role"] == "manager"
    assert ui.fields["department"] == "Engineering"


def test_ui_claim_create_form():
    app = fresh_app()
    for user in ("sam", "fiona", "marco"):
        r = app.get("/ui/claims/new", user=user, now=NOW)
        assert r.status == 200, (user, r)
        ui = parse_ui(r.text)
        assert ui.creates == ["claims"]
        assert {"amount", "category", "description"} <= set(ui.inputs)
        for f in ("employee", "status", "submitted_at", "decided_at", "decided_by", "rejection_reason"):
            assert f not in ui.inputs, f


def test_ui_employee_create_form():
    app = fresh_app()
    r = app.get("/ui/employees/new", user="fiona", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["employees"]
    assert {"username", "name", "role", "manager", "department"} <= set(ui.inputs)
    assert app.get("/ui/employees/new", user="sam", now=NOW).status == 403
    assert app.get("/ui/employees/new", user="marco", now=NOW).status == 403
    assert app.get("/ui/employees/new", user=None, now=NOW).status == 401
