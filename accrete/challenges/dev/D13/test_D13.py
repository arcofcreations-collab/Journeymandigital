"""D13 (expenses): approval delegation between managers.

Seed facts used:
  managers: marco 2 (reports omar 4, quinn 6, tariq 9, wen 12, zoe 15), nadia 3 (reports rosa 7, uma 10, xena 13),
            omar 4 (manager marco; reports priya, sam, victor, yusuf)
  submitted: 25 zoe, 53 zoe, 43 omar (omar's own claim, manager marco), 58 rosa, 72 rosa, 2 victor
  claim 1: wen draft; claim 24: wen paid
  nadia's normal reading set + marco's reading set (union) = NADIA_PLUS_MARCO
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
NADIA_READABLE = [4, 9, 13, 16, 26, 27, 30, 32, 37, 38, 39, 47, 57, 58, 62, 63, 65, 67, 69, 70,
                  72, 76, 77, 78]
NADIA_PLUS_MARCO = [1, 3, 4, 8, 9, 10, 11, 12, 13, 16, 18, 19, 24, 25, 26, 27, 29, 30, 32, 34, 35, 37, 38,
                    39, 43, 46, 47, 50, 52, 53, 55, 56, 57, 58, 59, 62, 63, 65, 66, 67, 68, 69, 70, 71, 72,
                    74, 76, 77, 78]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def delegate(app, delegator, delegate_id, starts="2026-03-01", ends="2026-03-10"):
    r = app.post("/api/delegations", {"delegate": delegate_id, "starts_on": starts, "ends_on": ends},
                 user=delegator, now=NOW)
    assert r.status == 201, r
    return r.json


def test_manager_creates_delegation():
    app = fresh_app()
    d = delegate(app, "marco", 3)
    assert d["delegator"] == 2 and d["delegate"] == 3
    assert d["starts_on"] == "2026-03-01" and d["ends_on"] == "2026-03-10"
    assert ids(app.get("/api/delegations", user="marco", now=NOW)) == [d["id"]]
    assert ids(app.get("/api/delegations", user="fiona", now=NOW)) == [d["id"]]


def test_delegation_validation():
    app = fresh_app()
    base = {"delegate": 3, "starts_on": "2026-03-01", "ends_on": "2026-03-10"}
    bad = [dict(base, delegate=2), dict(base, delegate=8), dict(base, delegate=1), dict(base, delegate=999),
           dict(base, ends_on="2026-02-28"), {k: v for k, v in base.items() if k != "delegate"},
           {k: v for k, v in base.items() if k != "starts_on"}, {k: v for k, v in base.items() if k != "ends_on"},
           dict(base, delegator=4)]
    for body in bad:
        assert_error(app.post("/api/delegations", body, user="marco", now=NOW), 400, "validation")
    assert ids(app.get("/api/delegations", user="fiona", now=NOW)) == []
    r = app.post("/api/delegations", dict(base, ends_on="2026-03-01"), user="marco", now=NOW)  # one-day
    assert r.status == 201, r


def test_only_managers_create_delegations():
    app = fresh_app()
    body = {"delegate": 3, "starts_on": "2026-03-01", "ends_on": "2026-03-10"}
    for user in ("sam", "fiona"):
        assert_error(app.post("/api/delegations", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/delegations", {}, user=user, now=NOW), 403, "forbidden")  # 403 before 400
    assert ids(app.get("/api/delegations", user="fiona", now=NOW)) == []


def test_active_delegate_reads_and_approves():
    app = fresh_app()
    delegate(app, "marco", 3)
    assert ids(app.get("/api/claims", user="nadia", now=NOW)) == NADIA_PLUS_MARCO
    assert app.get("/api/claims/25", user="nadia", now=NOW).status == 200
    r = app.post("/api/claims/25/approve", {}, user="nadia", now="2026-03-02T09:00:00")
    assert r.status == 200, r
    assert r.json["status"] == "approved" and r.json["decided_by"] == 3 and r.json["decided_at"] == "2026-03-02T09:00:00"
    r = app.post("/api/claims/53/reject", {"reason": "Duplicate"}, user="nadia", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 3 and r.json["rejection_reason"] == "Duplicate"
    # her own reports still work as before
    assert app.post("/api/claims/58/approve", {}, user="nadia", now=NOW).status == 200


def test_delegation_respects_date_window():
    app = fresh_app()
    delegate(app, "marco", 3)
    assert_error(app.post("/api/claims/25/approve", {}, user="nadia", now="2026-02-28T23:59:59"), 403, "forbidden")
    assert_error(app.get("/api/claims/25", user="nadia", now="2026-03-11T00:00:00"), 403, "forbidden")
    assert_error(app.post("/api/claims/25/approve", {}, user="nadia", now="2026-03-11T00:00:00"), 403, "forbidden")
    assert ids(app.get("/api/claims", user="nadia", now="2026-03-11T00:00:00")) == NADIA_READABLE
    r = app.post("/api/claims/25/approve", {}, user="nadia", now="2026-03-10T23:00:00")  # last day inclusive
    assert r.status == 200 and r.json["decided_by"] == 3


def test_deleting_delegation_revokes_rights():
    app = fresh_app()
    d = delegate(app, "marco", 3)
    assert_error(app.delete(f"/api/delegations/{d['id']}", user="nadia", now=NOW), 403, "forbidden")
    assert_error(app.delete(f"/api/delegations/{d['id']}", user="fiona", now=NOW), 403, "forbidden")
    assert app.delete(f"/api/delegations/{d['id']}", user="marco", now=NOW).status == 204
    assert_error(app.post("/api/claims/25/approve", {}, user="nadia", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/claims", user="nadia", now=NOW)) == NADIA_READABLE


def test_delegate_cannot_decide_own_claim():
    app = fresh_app()
    delegate(app, "marco", 4)   # omar is himself one of marco's reports
    assert_error(app.post("/api/claims/43/approve", {}, user="omar", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/43/reject", {"reason": "x"}, user="omar", now=NOW), 403, "forbidden")
    assert app.get("/api/claims/43", user="fiona", now=NOW).json["status"] == "submitted"
    r = app.post("/api/claims/25/approve", {}, user="omar", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 4
    r = app.post("/api/claims/43/approve", {}, user="marco", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 2


def test_delegator_keeps_rights_and_state_rules_apply():
    app = fresh_app()
    delegate(app, "marco", 3)
    r = app.post("/api/claims/53/approve", {}, user="marco", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 2
    assert_error(app.post("/api/claims/53/approve", {}, user="nadia", now=NOW), 409, "conflict")
    assert_error(app.post("/api/claims/1/approve", {}, user="nadia", now=NOW), 409, "conflict")   # draft
    assert_error(app.post("/api/claims/24/approve", {}, user="nadia", now=NOW), 409, "conflict")  # paid
    assert_error(app.post("/api/claims/25/reject", {}, user="nadia", now=NOW), 400, "validation")
    assert_error(app.post("/api/claims/2/approve", {}, user="nadia", now=NOW), 403, "forbidden")  # omar's report


def test_delegations_do_not_chain():
    app = fresh_app()
    delegate(app, "nadia", 2)   # nadia -> marco
    delegate(app, "marco", 4)   # marco -> omar
    assert_error(app.post("/api/claims/58/approve", {}, user="omar", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/claims/58", user="omar", now=NOW), 403, "forbidden")
    assert app.post("/api/claims/25/approve", {}, user="omar", now=NOW).status == 200
    r = app.post("/api/claims/58/approve", {}, user="marco", now=NOW)
    assert r.status == 200 and r.json["decided_by"] == 2


def test_delegation_read_and_write_permissions():
    app = fresh_app()
    d = delegate(app, "marco", 3)
    for user in ("marco", "nadia", "fiona"):
        assert app.get(f"/api/delegations/{d['id']}", user=user, now=NOW).status == 200, user
    assert_error(app.get(f"/api/delegations/{d['id']}", user="omar", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/delegations", user="omar", now=NOW)) == []
    assert ids(app.get("/api/delegations", user="sam", now=NOW)) == []
    for user in ("marco", "fiona"):
        assert_error(app.patch(f"/api/delegations/{d['id']}", {"ends_on": "2026-12-31"}, user=user, now=NOW),
                     403, "forbidden")
    assert app.get(f"/api/delegations/{d['id']}", user="marco", now=NOW).json["ends_on"] == "2026-03-10"


def test_ui_delegate_actions():
    app = fresh_app()
    delegate(app, "marco", 3)
    ui = parse_ui(app.get("/ui/claims/25", user="nadia", now=NOW).text)
    assert "approve" in ui.actions and "reject" in ui.actions
    assert app.get("/ui/claims/25", user="nadia", now="2026-03-11T00:00:00").status == 403
    delegate(app, "marco", 4)
    ui = parse_ui(app.get("/ui/claims/43", user="omar", now=NOW).text)
    assert "approve" not in ui.actions and "reject" not in ui.actions
