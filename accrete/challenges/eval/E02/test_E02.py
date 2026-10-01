"""Hidden acceptance tests for E02 (maintenance, after E01): technician self-dispatch and workload cap.

Seed facts (computed from spec/apps/maintenance_seed.json):
  active workloads (assigned + in_progress): nils(8)=3 [49 62 77], olga(9)=2 [75 79], umar(13, inactive)=1 [37],
      ravi(10)=4 [53 56 68 73], sara(11)=3 [61 64 72], wade(15)=1 [80], tess(12)=2 [47 66]
  open orders: North 38 52 63 65 74 82 | South 54 60 71 76 78 | East 30 69 81
  78: S-DCK-01 (asset 22), requested by lina(5).  30: E-DCK-01 (asset 28), requested by mei.
  migrated dispatch: self = requester == assignee; supervisor = other assigned; null = no assignee.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

SELF = [4, 16, 17, 20, 21, 22, 28, 33, 35, 41, 42, 50, 56, 67, 72, 75]
SUPERVISOR = [2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 23, 24, 26, 29, 31, 32, 34, 36, 37, 39, 40, 43,
              44, 46, 47, 48, 49, 51, 53, 55, 57, 58, 59, 61, 62, 64, 66, 68, 70, 73, 77, 79, 80]
NONE = [1, 6, 15, 25, 27, 30, 38, 45, 52, 54, 60, 63, 65, 69, 71, 74, 76, 78, 81, 82]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="sofia", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def wo(app, oid, user="sofia", now=NOW):
    r = app.get(f"/api/work_orders/{oid}", user=user, now=now)
    assert r.status == 200, r
    return r.json


def claim(app, oid, user, now=NOW):
    return app.post(f"/api/work_orders/{oid}/claim", {}, user=user, now=now)


def assign(app, oid, tech, user="sofia", now=NOW):
    return app.post(f"/api/work_orders/{oid}/assign", {"technician": tech}, user=user, now=now)


# --------------------------------------------------------------------------- data

def test_dispatch_migrated_from_existing_assignments():
    app = fresh_app()
    items = app.get("/api/work_orders", user="sofia", now=NOW).json["items"]
    got = {o["id"]: o["dispatch"] for o in items}
    for oid in SELF:
        assert got[oid] == "self", oid
    for oid in SUPERVISOR:
        assert got[oid] == "supervisor", oid
    for oid in NONE:
        assert got[oid] is None, oid
    assert ids(app.get("/api/work_orders?dispatch=self", user="sofia", now=NOW)) == SELF
    assert ids(app.get("/api/work_orders?dispatch=null", user="sofia", now=NOW)) == NONE
    assert ids(app.get("/api/work_orders?dispatch=self&status=assigned", user="sofia", now=NOW)) == [72, 75]
    # nothing else about the orders changed
    o = wo(app, 75)
    assert o["status"] == "assigned" and o["assignee"] == 9 and o["requested_by"] == 9 and o["priority"] == "normal"


# --------------------------------------------------------------------------- claim

def test_technician_claims_open_order():
    app = fresh_app()
    before = len(outbox(app))
    r = claim(app, 78, "wade", now=T2)
    assert r.status == 200, r
    o = r.json
    assert o["id"] == 78 and o["status"] == "assigned" and o["assignee"] == 15 and o["dispatch"] == "self"
    assert o["requested_by"] == 5 and o["started_at"] is None
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["assignment"]
    assert msgs[0]["payload"] == {"work_order": 78, "asset": 22, "technician": 15}
    r = app.post("/api/work_orders/78/start", {}, user="wade", now=T2)
    assert r.status == 200 and r.json["status"] == "in_progress"
    assert wo(app, 78, user="wade")["dispatch"] == "self"


def test_claim_permissions():
    app = fresh_app()
    before = outbox(app)
    assert_error(claim(app, 78, "lina"), 403, "forbidden")      # requester (even of this order)
    assert_error(claim(app, 78, "tomas"), 403, "forbidden")     # supervisor
    assert_error(claim(app, 78, "nils"), 403, "forbidden")      # North technician, South order
    assert_error(claim(app, 78, "tess"), 403, "forbidden")
    assert_error(claim(app, 74, "umar"), 403, "forbidden")      # inactive technician, own site
    # 403 wins over 409
    assert_error(claim(app, 73, "lina"), 403, "forbidden")
    assert_error(claim(app, 77, "umar"), 403, "forbidden")
    assert_error(claim(app, 999, "wade"), 404, "not_found")
    assert outbox(app) == before
    o = wo(app, 78)
    assert o["status"] == "open" and o["assignee"] is None and o["dispatch"] is None


def test_claim_only_from_open():
    app = fresh_app()
    for oid in (73, 61, 12, 13):   # assigned, in_progress, completed, cancelled (all South)
        assert_error(claim(app, oid, "wade"), 409, "conflict")
    assert wo(app, 73)["assignee"] == 10


def test_claim_respects_workload_cap():
    app = fresh_app()
    before = outbox(app)
    assert_error(claim(app, 74, "nils"), 409, "conflict")       # 3 active
    assert_error(claim(app, 60, "ravi"), 409, "conflict")       # 4 active (ravi raised 60 himself)
    assert_error(claim(app, 71, "sara"), 409, "conflict")       # 3 active
    assert outbox(app) == before
    assert claim(app, 74, "olga").status == 200                 # 2 -> 3
    assert_error(claim(app, 82, "olga"), 409, "conflict")
    assert claim(app, 30, "tess").status == 200                 # 2 -> 3
    assert_error(claim(app, 69, "tess"), 409, "conflict")
    assert wo(app, 82)["status"] == "open" and wo(app, 69)["assignee"] is None


# --------------------------------------------------------------------------- assign with cap

def test_assign_respects_workload_cap():
    app = fresh_app()
    before = outbox(app)
    assert_error(assign(app, 74, 8), 409, "conflict")                  # nils at 3
    assert_error(assign(app, 76, 10, user="tomas"), 409, "conflict")   # ravi at 4
    assert_error(assign(app, 76, 11, user="tomas"), 409, "conflict")   # sara at 3
    assert_error(assign(app, 68, 11, user="tomas"), 409, "conflict")   # re-assign ravi -> sara
    assert outbox(app) == before
    assert wo(app, 74)["assignee"] is None and wo(app, 68)["assignee"] == 10
    r = assign(app, 76, 15, user="tomas")                              # wade 1 -> 2
    assert r.status == 200 and r.json["assignee"] == 15 and r.json["dispatch"] == "supervisor"
    r = assign(app, 73, 10, user="tomas")                              # current assignee: always allowed
    assert r.status == 200 and r.json["assignee"] == 10
    r = assign(app, 68, 15, user="tomas")                              # wade 2 -> 3
    assert r.status == 200 and r.json["assignee"] == 15
    assert_error(assign(app, 71, 15, user="tomas"), 409, "conflict")   # wade now at 3
    assert len(outbox(app)) == len(before) + 3


def test_cap_check_order():
    app = fresh_app()
    assert_error(assign(app, 74, 13), 400, "validation")     # umar inactive -> invalid technician
    assert_error(assign(app, 74, 10), 400, "validation")     # ravi: wrong site, so no cap check
    assert_error(assign(app, 74, 999), 400, "validation")
    assert_error(assign(app, 79, 8), 409, "conflict")        # in_progress: state 409
    assert_error(assign(app, 74, 8, user="ruth"), 403, "forbidden")


def test_workload_frees_up():
    app = fresh_app()
    r = app.post("/api/work_orders/62/complete", {"resolution": "Done", "labor_minutes": 30}, user="nils", now=NOW)
    assert r.status == 200, r
    r = assign(app, 74, 8)                                   # nils 3 -> 2 -> 3
    assert r.status == 200 and r.json["dispatch"] == "supervisor"
    assert app.post("/api/work_orders/53/cancel", {"reason": "x"}, user="tomas", now=NOW).status == 200
    assert_error(assign(app, 76, 10, user="tomas"), 409, "conflict")   # ravi 4 -> 3, still full
    assert app.post("/api/work_orders/56/cancel", {"reason": "x"}, user="tomas", now=NOW).status == 200
    r = assign(app, 76, 10, user="tomas")                              # ravi 2 -> 3
    assert r.status == 200 and r.json["assignee"] == 10


def test_dispatch_is_read_only_and_tracks_last_dispatch():
    app = fresh_app()
    assert_error(app.post("/api/work_orders", {"asset": 28, "title": "x", "priority": "low", "dispatch": "self"},
                          user="mei", now=NOW), 400, "validation")
    assert_error(app.patch("/api/work_orders/74", {"dispatch": "supervisor"}, user="sofia", now=NOW), 400, "validation")
    r = app.post("/api/work_orders", {"asset": 28, "title": "Door sticks", "priority": "low"}, user="mei", now=NOW)
    assert r.status == 201 and r.json["dispatch"] is None
    assert claim(app, 30, "tess").json["dispatch"] == "self"
    r = assign(app, 30, 12, user="yara")                    # re-assignment by a supervisor
    assert r.status == 200 and r.json["dispatch"] == "supervisor" and r.json["assignee"] == 12


def test_claimed_order_follows_existing_rules():
    app = fresh_app()
    assert claim(app, 78, "wade").status == 200
    # the requester can no longer cancel an assigned order; a supervisor can
    assert_error(app.post("/api/work_orders/78/cancel", {"reason": "x"}, user="lina", now=NOW), 409, "conflict")
    assert_error(app.patch("/api/work_orders/78", {"title": "x"}, user="lina", now=NOW), 409, "conflict")
    assert app.post("/api/work_orders/78/start", {}, user="wade", now=NOW).status == 200
    r = app.post("/api/work_orders/78/use_parts", {"items": [{"part": 4, "quantity": 1}]}, user="wade", now=NOW)
    assert r.status == 200 and round(r.json["parts_cost"], 2) == 9.8
    before = len(outbox(app))
    r = app.post("/api/work_orders/78/complete", {"resolution": "Realigned", "labor_minutes": 30}, user="wade", now=T2)
    assert r.status == 200, r
    p = outbox(app)[before]["payload"]
    assert (p["work_order"], p["asset"], p["technician"], p["labor_minutes"]) == (78, 22, 15, 30)
    assert round(p["parts_cost"], 2) == 9.8


# --------------------------------------------------------------------------- UI

def test_ui_claim_form():
    app = fresh_app()

    def acts(oid, user):
        r = app.get(f"/ui/work_orders/{oid}", user=user, now=NOW)
        assert r.status == 200, (oid, user, r)
        return parse_ui(r.text).actions

    assert "claim" in acts(78, "wade")
    assert "claim" in acts(74, "olga")
    assert "claim" not in acts(74, "nils")       # at the cap
    assert "claim" not in acts(74, "umar")       # inactive
    assert "claim" not in acts(78, "lina")
    assert "claim" not in acts(78, "tomas")
    assert "claim" not in acts(73, "wade")       # not open
    assert "assign" in acts(78, "tomas")
    assert claim(app, 74, "olga").status == 200
    assert "claim" not in acts(82, "olga")       # now at the cap
