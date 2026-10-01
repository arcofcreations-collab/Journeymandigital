"""Hidden acceptance tests for E07 (maintenance, after E01-E06): preventive maintenance schedules.

Schedules 1-5 come from the brief:
  1 asset 3  (N-BLR-01, North, high)   p2 365 next 2026-03-05 active
  2 asset 16 (S-CNV-01, South, high)   p3  30 next 2026-03-20 active   (too early before 2026-03-13)
  3 asset 30 (E-GEN-01, East, retired) p3  90 next 2026-02-01 inactive
  4 asset 25 (E-AHU-01, East, medium)  p4  60 next 2026-02-15 active   (asset 25 has unfinished order 66)
  5 asset 21 (S-GEN-01, South, high)   p2  30 next 2026-03-03 active
Roles after E06: sofia manager; tomas supervisor South; yara supervisor East.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

SCHEDULES = {
    1: (3, "Boiler annual service", "p2", 365, "2026-03-05", True),
    2: (16, "Conveyor belt inspection", "p3", 30, "2026-03-20", True),
    3: (30, "Generator load test", "p3", 90, "2026-02-01", False),
    4: (25, "Filter replacement", "p4", 60, "2026-02-15", True),
    5: (21, "Generator monthly run", "p2", 30, "2026-03-03", True),
}


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


def get(app, path, user="sofia", now=NOW):
    r = app.get(path, user=user, now=now)
    assert r.status == 200, r
    return r.json


def gen(app, sid, user, now=NOW):
    return app.post(f"/api/schedules/{sid}/generate", {}, user=user, now=now)


def snapshot(app):
    return (get(app, "/api/schedules")["items"], get(app, "/api/work_orders")["items"], outbox(app))


# --------------------------------------------------------------------------- data

def test_schedules_seeded_and_readable_by_everyone():
    app = fresh_app()
    for user in ("ruth", "nils", "tomas", "mei"):
        assert ids(app.get("/api/schedules", user=user, now=NOW)) == [1, 2, 3, 4, 5]
    for sid, (asset, title, prio, interval, nxt, active) in SCHEDULES.items():
        s = get(app, f"/api/schedules/{sid}", user="kofi")
        expected = {"id": sid, "asset": asset, "title": title, "priority": prio, "interval_days": interval,
                    "next_due": nxt, "active": active}
        for k, v in expected.items():
            assert s[k] == v, (sid, k, s.get(k))
    items = get(app, "/api/work_orders")["items"]
    assert len(items) == 82 and all(o["schedule"] is None for o in items)
    assert ids(app.get("/api/work_orders?schedule=null", user="sofia", now=NOW)) == list(range(1, 83))
    assert ids(app.get("/api/schedules?active=false", user="ruth", now=NOW)) == [3]


# --------------------------------------------------------------------------- generate

def test_generate_creates_order_and_advances_schedule():
    app = fresh_app()
    before = len(outbox(app))
    r = gen(app, 1, "sofia")
    assert r.status == 200, r
    s = r.json
    assert s["id"] == 1 and s["next_due"] == "2027-03-05" and s["active"] is True and s["asset"] == 3
    new = get(app, "/api/work_orders?schedule=1")["items"]
    assert len(new) == 1
    o = new[0]
    assert o["id"] > 82
    expected = {"asset": 3, "title": "Boiler annual service", "description": "Preventive maintenance",
                "priority": "p2", "status": "open", "requested_by": 1, "created_at": NOW, "assignee": None,
                "started_at": None, "completed_at": None, "schedule": 1, "due_date": "2026-03-04",
                "overdue": False, "labor_minutes": None, "parts_cost": 0}
    for k, v in expected.items():
        assert o[k] == v, (k, o.get(k))
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["preventive_generated"]
    assert msgs[0]["payload"] == {"schedule": 1, "work_order": o["id"], "next_due": "2027-03-05"}
    assert get(app, "/api/assets/3", user="ruth")["open_orders"] == 2
    # North technicians see it; the South supervisor does not
    assert o["id"] in ids(app.get("/api/work_orders", user="olga", now=NOW))
    assert_error(app.get(f"/api/work_orders/{o['id']}", user="tomas", now=NOW), 403, "forbidden")


def test_late_schedule_advances_once_from_previous_due_date():
    app = fresh_app()
    r = gen(app, 4, "yara")
    assert r.status == 200 and r.json["next_due"] == "2026-04-16"
    o = get(app, "/api/work_orders?schedule=4")["items"][0]
    assert o["priority"] == "p4" and o["due_date"] == "2026-03-31" and o["requested_by"] == 16


def test_generate_conflicts():
    app = fresh_app()
    assert_error(gen(app, 3, "sofia"), 409, "conflict")                           # inactive / retired asset
    assert_error(gen(app, 2, "tomas"), 409, "conflict")                           # too early (before 03-13)
    assert_error(gen(app, 2, "tomas", now="2026-03-12T23:59:59"), 409, "conflict")
    r = gen(app, 2, "tomas", now="2026-03-13T00:00:00")
    assert r.status == 200 and r.json["next_due"] == "2026-04-19"
    # an unfinished generated order blocks the next one, even when the date would allow it
    assert gen(app, 4, "yara").status == 200                                      # next 2026-04-16
    assert_error(gen(app, 4, "yara", now="2026-04-10T08:00:00"), 409, "conflict")
    oid = get(app, "/api/work_orders?schedule=4")["items"][0]["id"]
    assert app.post(f"/api/work_orders/{oid}/cancel", {"reason": "Rescheduled"}, user="yara",
                    now="2026-04-10T08:00:00").status == 200
    r = gen(app, 4, "yara", now="2026-04-10T08:00:00")
    assert r.status == 200 and r.json["next_due"] == "2026-06-15"
    generated = ids(app.get("/api/work_orders?schedule=4", user="sofia", now=NOW))
    assert len(generated) == 2 and generated[0] == oid and generated[1] > oid


def test_generate_permissions():
    app = fresh_app()
    snap = snapshot(app)
    assert_error(gen(app, 1, "tomas"), 403, "forbidden")      # North schedule, South supervisor
    assert_error(gen(app, 2, "yara"), 403, "forbidden")
    assert_error(gen(app, 3, "tomas"), 403, "forbidden")      # 403 before 409
    for user in ("ruth", "nils", "olga", "mei"):
        assert_error(gen(app, 1, user), 403, "forbidden")
    assert_error(gen(app, 99, "sofia"), 404, "not_found")
    assert_error(app.post("/api/schedules/1/run", {}, user="sofia", now=NOW), 404, "not_found")
    assert snapshot(app) == snap


def test_failed_generate_leaves_no_trace():
    app = fresh_app()
    snap = snapshot(app)
    for sid, user in ((3, "sofia"), (2, "sofia"), (2, "tomas")):
        assert_error(gen(app, sid, user), 409, "conflict")
    assert snapshot(app) == snap


def test_generated_order_lifecycle_and_next_cycle():
    app = fresh_app()
    r = gen(app, 5, "tomas")
    assert r.status == 200 and r.json["next_due"] == "2026-04-02"
    o = get(app, "/api/work_orders?schedule=5", user="tomas")["items"][0]
    oid = o["id"]
    assert o["priority"] == "p2" and o["due_date"] == "2026-03-04" and o["requested_by"] == 2
    assert app.post(f"/api/work_orders/{oid}/assign", {"technician": 15}, user="tomas", now=NOW).status == 200
    assert app.post(f"/api/work_orders/{oid}/start", {}, user="wade", now=NOW).status == 200
    assert app.post(f"/api/work_orders/{oid}/use_parts", {"items": [{"part": 4, "quantity": 1}]},
                    user="wade", now=NOW).status == 200
    assert app.post(f"/api/work_orders/{oid}/log_time", {"minutes": 60}, user="wade", now=NOW).status == 200
    before = len(outbox(app))
    r = app.post(f"/api/work_orders/{oid}/complete", {"resolution": "Ran 1h on load"}, user="wade", now=NOW)
    assert r.status == 200 and r.json["schedule"] == 5
    p = outbox(app)[before]["payload"]
    assert (p["work_order"], p["asset"], p["technician"], p["labor_minutes"]) == (oid, 21, 15, 60)
    assert round(p["parts_cost"], 2) == 9.8
    # finished: the next cycle is only blocked by the date now
    assert_error(gen(app, 5, "tomas"), 409, "conflict")
    r = gen(app, 5, "tomas", now="2026-03-26T07:00:00")
    assert r.status == 200 and r.json["next_due"] == "2026-05-02"


# --------------------------------------------------------------------------- schedule CRUD

def test_schedule_create_permissions_and_validation():
    app = fresh_app()
    body = {"asset": 16, "title": "Belt tension", "priority": "p3", "interval_days": 14, "next_due": "2026-03-10"}
    assert_error(app.post("/api/schedules", dict(body, asset=1), user="tomas", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/schedules", {"asset": 1, "priority": "p9"}, user="tomas", now=NOW), 403, "forbidden")
    for user in ("ruth", "nils"):
        assert_error(app.post("/api/schedules", body, user=user, now=NOW), 403, "forbidden")
    for bad in ({"priority": "p4"}, {"priority": "low"}, {"interval_days": 0}, {"interval_days": 366},
                {"interval_days": 1.5}, {"next_due": "2026-02-30"}, {"next_due": "10/03/2026"}, {"asset": 24},
                {"asset": 999}, {"title": " "}, {"active": "yes"}, {"colour": "red"}):
        assert_error(app.post("/api/schedules", dict(body, **bad), user="tomas", now=NOW), 400, "validation")
    for missing in ("asset", "title", "priority", "interval_days", "next_due"):
        b = {k: v for k, v in body.items() if k != missing}
        assert_error(app.post("/api/schedules", b, user="sofia", now=NOW), 400, "validation")
    assert ids(app.get("/api/schedules", user="sofia", now=NOW)) == [1, 2, 3, 4, 5]
    r = app.post("/api/schedules", body, user="tomas", now=NOW)
    assert r.status == 201, r
    s = r.json
    assert s["id"] > 5 and s["active"] is True and s["asset"] == 16 and s["next_due"] == "2026-03-10"
    r = app.post("/api/schedules", dict(body, asset=19, priority="p4"), user="sofia", now=NOW)   # medium asset
    assert r.status == 201


def test_schedule_patch_and_delete_rules():
    app = fresh_app()
    r = app.patch("/api/schedules/2", {"interval_days": 14, "title": "Belt check"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["interval_days"] == 14 and r.json["asset"] == 16
    assert_error(app.patch("/api/schedules/2", {"asset": 19}, user="tomas", now=NOW), 400, "validation")
    assert_error(app.patch("/api/schedules/2", {"priority": "p4"}, user="tomas", now=NOW), 400, "validation")
    assert_error(app.patch("/api/schedules/2", {"title": "x"}, user="yara", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/schedules/2", user="ruth", now=NOW), 403, "forbidden")
    assert gen(app, 1, "sofia").status == 200
    assert_error(app.delete("/api/schedules/1", user="sofia", now=NOW), 409, "conflict")
    assert app.delete("/api/schedules/2", user="tomas", now=NOW).status == 204
    assert ids(app.get("/api/schedules", user="ruth", now=NOW)) == [1, 3, 4, 5]
    # an asset with a schedule cannot be deleted
    r = app.post("/api/schedules", {"asset": 31, "title": "Panel test", "priority": "p2", "interval_days": 90,
                                    "next_due": "2026-06-01"}, user="yara", now=NOW)
    assert r.status == 201
    assert_error(app.delete("/api/assets/31", user="yara", now=NOW), 409, "conflict")


def test_retiring_asset_deactivates_its_schedules():
    app = fresh_app()
    assert_error(app.patch("/api/assets/25", {"retired": True}, user="yara", now=NOW), 409, "conflict")  # order 66
    assert get(app, "/api/schedules/4")["active"] is True
    assert app.post("/api/work_orders/66/cancel", {"reason": "Merged"}, user="yara", now=NOW).status == 200
    r = app.patch("/api/assets/25", {"retired": True}, user="yara", now=NOW)
    assert r.status == 200 and r.json["retired"] is True
    assert get(app, "/api/schedules/4")["active"] is False
    assert_error(gen(app, 4, "yara"), 409, "conflict")
    r = app.patch("/api/assets/25", {"retired": False}, user="yara", now=NOW)
    assert r.status == 200
    assert get(app, "/api/schedules/4")["active"] is False          # not reactivated
    assert app.patch("/api/schedules/4", {"active": True}, user="yara", now=NOW).status == 200
    assert gen(app, 4, "yara").status == 200
    assert get(app, "/api/schedules/1")["active"] is True           # other assets untouched


def test_schedule_field_is_read_only():
    app = fresh_app()
    assert_error(app.post("/api/work_orders", {"asset": 2, "title": "x", "priority": "p3", "schedule": 1},
                          user="ruth", now=NOW), 400, "validation")
    assert_error(app.patch("/api/work_orders/74", {"schedule": 1}, user="sofia", now=NOW), 400, "validation")
    r = app.post("/api/work_orders", {"asset": 2, "title": "Noise", "priority": "p3"}, user="ruth", now=NOW)
    assert r.status == 201 and r.json["schedule"] is None


def test_ui_schedules():
    app = fresh_app()
    assert parse_ui(app.get("/ui/schedules", user="ruth", now=NOW).text).rows == [1, 2, 3, 4, 5]
    ui = parse_ui(app.get("/ui/schedules/1", user="sofia", now=NOW).text)
    assert ui.fields["title"] == "Boiler annual service" and ui.fields["next_due"] == "2026-03-05"
    assert ui.fields["interval_days"] == "365" and ui.fields["priority"] == "p2"
    assert "generate" in ui.actions
    assert "generate" not in parse_ui(app.get("/ui/schedules/1", user="tomas", now=NOW).text).actions
    assert "generate" not in parse_ui(app.get("/ui/schedules/3", user="sofia", now=NOW).text).actions
    assert "generate" not in parse_ui(app.get("/ui/schedules/2", user="tomas", now=NOW).text).actions
    assert "generate" in parse_ui(app.get("/ui/schedules/2", user="tomas", now="2026-03-13T09:00:00").text).actions
    assert app.get("/ui/schedules/new", user="tomas", now=NOW).status == 200
    assert app.get("/ui/schedules/new", user="ruth", now=NOW).status == 403
    r = app.get("/ui/schedules/new", user="sofia", now=NOW)
    assert {"asset", "title", "priority", "interval_days", "next_due"} <= set(parse_ui(r.text).inputs)
