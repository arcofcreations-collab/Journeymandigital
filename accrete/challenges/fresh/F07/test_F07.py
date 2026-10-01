"""Hidden acceptance tests for F07 (maintenance): moving an asset to another site.

Seed facts (computed from spec/apps/maintenance_seed.json):
  asset 21 S-GEN-01 (South, high): order 54 open (requested by tomas), order 64 assigned to sara (11),
           requested by tomas (2).
  asset 17 S-CNV-02 (South): order 12 completed (assignee sara), order 72 assigned to sara, requested by sara.
  asset 16 S-CNV-01 (South): order 61 in_progress -> cannot move.  asset 1 N-AHU-01 (North): order 74 open.
  asset 31 E-FIR-01 (East): no orders. retired assets: 7 (North), 24 (South), 30 (East).
  East orders (visible to tess): 1 2 7 15 19 22 27 29 30 33 47 66 69 81.
  sites with staff: North, South, East.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
EAST_ORDERS = [1, 2, 7, 15, 19, 22, 27, 29, 30, 33, 47, 66, 69, 81]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="sofia", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def wo(app, oid, user="sofia"):
    r = app.get(f"/api/work_orders/{oid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def snapshot(app):
    return tuple(app.get(f"/api/{c}", user="sofia", now=NOW).json["items"]
                 for c in ("staff", "assets", "work_orders", "_outbox"))


def test_transfer_unassigns_assigned_orders():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/assets/21/transfer", {"site": "East"}, user="tomas", now="2026-03-02T09:30:00")
    assert r.status == 200, r
    a = r.json
    assert a["id"] == 21 and a["site"] == "East" and a["tag"] == "S-GEN-01" and a["criticality"] == "high"
    assert a["retired"] is False and a["open_orders"] == 2
    o64 = wo(app, 64)
    assert o64["status"] == "open" and o64["assignee"] is None and o64["started_at"] is None
    assert o64["requested_by"] == 2 and o64["asset"] == 21 and o64["title"] == "Battery check"
    o54 = wo(app, 54)
    assert o54["status"] == "open" and o54["assignee"] is None
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "asset_transferred"
    assert msgs[-1]["payload"] == {"asset": 21, "from_site": "South", "to_site": "East", "unassigned": [64]}
    assert app.get("/api/assets/21", user="mei", now=NOW).json["site"] == "East"


def test_visibility_and_creation_follow_new_site():
    app = fresh_app()
    assert app.post("/api/assets/21/transfer", {"site": "East"}, user="yara", now=NOW).status == 200
    assert ids(app.get("/api/work_orders", user="tess", now=NOW)) == sorted(EAST_ORDERS + [54, 64])
    assert ids(app.get("/api/work_orders?asset=21", user="tess", now=NOW)) == [54, 64]
    assert_error(app.get("/api/work_orders/64", user="sara", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/work_orders/54", user="ravi", now=NOW), 403, "forbidden")
    assert app.get("/api/work_orders/64", user="tomas", now=NOW).status == 200
    r = app.post("/api/work_orders", {"asset": 21, "title": "Fuel smell", "priority": "urgent"}, user="mei", now=NOW)
    assert r.status == 201 and r.json["requested_by"] == 7
    assert_error(app.post("/api/work_orders", {"asset": 21, "title": "x", "priority": "low"}, user="lina", now=NOW),
                 403, "forbidden")
    assert_error(app.post("/api/work_orders/64/assign", {"technician": 10}, user="tomas", now=NOW), 400, "validation")
    r = app.post("/api/work_orders/64/assign", {"technician": 12}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["assignee"] == 12 and r.json["status"] == "assigned"
    assert app.get("/api/assets/21", user="mei", now=NOW).json["open_orders"] == 3


def test_transfer_keeps_history_and_requester_access():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/assets/17/transfer", {"site": "North"}, user="sofia", now=NOW)
    assert r.status == 200, r
    assert r.json["site"] == "North" and r.json["open_orders"] == 1
    o72 = wo(app, 72)
    assert o72["status"] == "open" and o72["assignee"] is None and o72["requested_by"] == 11
    o12 = wo(app, 12)
    assert o12["status"] == "completed" and o12["assignee"] == 11 and o12["labor_minutes"] == 150
    # sara raised 72 (still readable) and was the assignee of the finished order 12
    assert app.get("/api/work_orders/72", user="sara", now=NOW).status == 200
    assert app.get("/api/work_orders/12", user="sara", now=NOW).status == 200
    assert app.get("/api/work_orders/72", user="nils", now=NOW).status == 200
    assert_error(app.get("/api/work_orders/72", user="wade", now=NOW), 403, "forbidden")
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["asset_transferred"]
    assert msgs[0]["payload"] == {"asset": 17, "from_site": "South", "to_site": "North", "unassigned": [72]}


def test_transfer_without_assigned_orders():
    app = fresh_app()
    r = app.post("/api/assets/31/transfer", {"site": "North"}, user="yara", now=NOW)
    assert r.status == 200 and r.json["site"] == "North" and r.json["open_orders"] == 0
    assert outbox(app)[-1]["payload"] == {"asset": 31, "from_site": "East", "to_site": "North", "unassigned": []}
    r = app.post("/api/assets/1/transfer", {"site": "South"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["site"] == "South"
    assert wo(app, 74)["status"] == "open"
    assert outbox(app)[-1]["payload"] == {"asset": 1, "from_site": "North", "to_site": "South", "unassigned": []}
    assert ids(app.get("/api/assets?site=South", user="ruth", now=NOW)) == [1] + list(range(14, 25))


def test_refused_transfers_change_nothing():
    app = fresh_app()
    before = snapshot(app)
    # not a supervisor: 403, also before 409 and 400
    for user in ("ruth", "nils", "umar", "lina"):
        assert_error(app.post("/api/assets/21/transfer", {"site": "East"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/assets/16/transfer", {"site": "West"}, user=user, now=NOW), 403, "forbidden")
    # in-progress order or retired asset: 409, before 400
    assert_error(app.post("/api/assets/16/transfer", {"site": "North"}, user="sofia", now=NOW), 409, "conflict")
    assert_error(app.post("/api/assets/16/transfer", {"site": "West"}, user="sofia", now=NOW), 409, "conflict")
    for aid in (7, 24, 30):
        assert_error(app.post(f"/api/assets/{aid}/transfer", {"site": "South"}, user="sofia", now=NOW), 409, "conflict")
    # invalid site
    for body in ({}, {"site": ""}, {"site": "  "}, {"site": "West"}, {"site": "South"}, {"site": 5},
                 {"site": None}, {"site": "East", "reason": "move"}):
        assert_error(app.post("/api/assets/21/transfer", body, user="tomas", now=NOW), 400, "validation")
    assert_error(app.post("/api/assets/999/transfer", {"site": "East"}, user="sofia", now=NOW), 404, "not_found")
    assert_error(app.post("/api/work_orders/64/transfer", {"site": "East"}, user="sofia", now=NOW), 404, "not_found")
    assert snapshot(app) == before


def test_site_cannot_be_patched_directly():
    app = fresh_app()
    assert_error(app.patch("/api/assets/1", {"site": "South"}, user="sofia", now=NOW), 400, "validation")
    assert_error(app.patch("/api/assets/31", {"site": "North", "name": "Panel"}, user="yara", now=NOW), 400, "validation")
    assert app.get("/api/assets/1", user="sofia", now=NOW).json["site"] == "North"
    assert app.get("/api/assets/31", user="sofia", now=NOW).json["name"] == "Fire panel East"
    r = app.patch("/api/assets/1", {"name": "AHU 1", "criticality": "medium"}, user="yara", now=NOW)
    assert r.status == 200 and r.json["name"] == "AHU 1" and r.json["site"] == "North"
    # creating assets with a site is unchanged
    r = app.post("/api/assets", {"tag": "E-NEW-01", "name": "New", "site": "East", "criticality": "low"},
                 user="yara", now=NOW)
    assert r.status == 201 and r.json["site"] == "East"
    # a non-supervisor still gets 403 first
    assert_error(app.patch("/api/assets/1", {"site": "South"}, user="ruth", now=NOW), 403, "forbidden")


def test_ui_transfer_form():
    app = fresh_app()
    assert "transfer" in parse_ui(app.get("/ui/assets/21", user="sofia", now=NOW).text).actions
    assert "transfer" in parse_ui(app.get("/ui/assets/31", user="tomas", now=NOW).text).actions
    assert "transfer" not in parse_ui(app.get("/ui/assets/21", user="ruth", now=NOW).text).actions
    assert "transfer" not in parse_ui(app.get("/ui/assets/21", user="sara", now=NOW).text).actions
    assert "transfer" not in parse_ui(app.get("/ui/assets/16", user="sofia", now=NOW).text).actions
    assert "transfer" not in parse_ui(app.get("/ui/assets/7", user="sofia", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/assets/21", user="mei", now=NOW).text)
    assert ui.fields["site"] == "South" and ui.fields["open_orders"] == "2"


def test_other_operations_unchanged():
    app = fresh_app()
    before = len(outbox(app))
    assert app.post("/api/work_orders/74/assign", {"technician": 9}, user="sofia", now=NOW).status == 200
    assert app.post("/api/work_orders/74/cancel", {"reason": "dup"}, user="sofia", now=NOW).status == 200
    assert [m["channel"] for m in outbox(app)[before:]] == ["assignment"]
    assert_error(app.patch("/api/assets/16", {"retired": True}, user="sofia", now=NOW), 409, "conflict")
    r = app.patch("/api/assets/1", {"retired": True}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["retired"] is True
    assert_error(app.post("/api/assets/1/transfer", {"site": "South"}, user="sofia", now=NOW), 409, "conflict")
