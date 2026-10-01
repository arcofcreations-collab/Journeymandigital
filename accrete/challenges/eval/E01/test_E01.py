"""Hidden acceptance tests for E01 (maintenance): spare parts and atomic part consumption.

Seed facts (spec/apps/maintenance_seed.json) used here:
  in_progress orders: 62 (N-AHU-02, asset 2, North, assignee nils=8), 49 (North, nils), 79 (North, olga=9),
                      53 (S-PMP-01, asset 19, South, ravi=10, requested by tomas), 61 (South, sara=11),
                      47 (East, tess=12)
  77 assigned to nils; 2 completed (tess); 74 open (North).
Parts 1-8 come from the brief.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"

PARTS = {
    1: ("FLT-AHU", "AHU filter", "North", 42.5, 12, 4),
    2: ("BELT-A40", "V-belt A40", "North", 18.0, 3, 2),
    3: ("FUSE-10A", "Fuse 10A", "North", 1.25, 50, 10),
    4: ("BRG-6204", "Bearing 6204", "South", 9.8, 6, 2),
    5: ("BELT-A40-S", "V-belt A40", "South", 18.0, 2, 2),
    6: ("SEAL-KIT", "Pump seal kit", "South", 64.0, 1, 0),
    7: ("LAMP-LED", "LED lamp", "East", 7.4, 20, 5),
    8: ("REMOTE-DK", "Dock door remote", "North", 23.9, 0, 1),
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


def snapshot(app):
    return {
        "parts": get(app, "/api/parts")["items"],
        "part_usages": get(app, "/api/part_usages")["items"],
        "work_orders": get(app, "/api/work_orders")["items"],
        "outbox": outbox(app),
    }


def use(app, oid, items, user, now=NOW):
    return app.post(f"/api/work_orders/{oid}/use_parts", {"items": items}, user=user, now=now)


# --------------------------------------------------------------------------- data

def test_parts_seeded_and_low_stock_derived():
    app = fresh_app()
    for user in ("ruth", "nils", "tess", "sofia"):
        assert ids(app.get("/api/parts", user=user, now=NOW)) == list(range(1, 9))
    for pid, (sku, name, site, cost, qty, rl) in PARTS.items():
        p = get(app, f"/api/parts/{pid}", user="mei")
        expected = {"id": pid, "sku": sku, "name": name, "site": site, "unit_cost": cost, "quantity": qty,
                    "reorder_level": rl, "low_stock": qty <= rl}
        for k, v in expected.items():
            assert p[k] == v, (pid, k, p.get(k))
    assert ids(app.get("/api/parts?low_stock=true", user="ruth", now=NOW)) == [5, 8]
    assert ids(app.get("/api/parts?site=North", user="ruth", now=NOW)) == [1, 2, 3, 8]


def test_existing_orders_have_zero_parts_cost_and_no_usages():
    app = fresh_app()
    assert get(app, "/api/part_usages")["items"] == []
    items = get(app, "/api/work_orders")["items"]
    assert [o["id"] for o in items] == list(range(1, 83))
    assert all(o["parts_cost"] == 0 for o in items)
    o = get(app, "/api/work_orders/2", user="mei")
    assert o["labor_minutes"] == 315 and o["status"] == "completed" and o["priority"] == "normal"


# --------------------------------------------------------------------------- use_parts

def test_use_parts_creates_usages_and_decrements_stock():
    app = fresh_app()
    r = use(app, 62, [{"part": 1, "quantity": 2}, {"part": 3, "quantity": 4}], user="nils", now=T2)
    assert r.status == 200, r
    assert r.json["id"] == 62 and r.json["status"] == "in_progress"
    assert round(r.json["parts_cost"], 2) == 90.0
    usages = get(app, "/api/part_usages")["items"]
    assert len(usages) == 2
    assert usages[0]["id"] < usages[1]["id"]
    for u, (part, qty, cost) in zip(usages, [(1, 2, 42.5), (3, 4, 1.25)]):
        expected = {"work_order": 62, "part": part, "quantity": qty, "unit_cost": cost, "used_by": 8,
                    "used_at": T2}
        for k, v in expected.items():
            assert u[k] == v, (k, u.get(k))
    assert get(app, "/api/parts/1")["quantity"] == 10
    assert get(app, "/api/parts/3")["quantity"] == 46
    assert get(app, "/api/parts/1")["low_stock"] is False
    # a second call adds to the cost
    r = use(app, 62, [{"part": 1, "quantity": 1}], user="nils", now=T2)
    assert r.status == 200 and round(r.json["parts_cost"], 2) == 132.5
    now_ids = ids(app.get("/api/part_usages?work_order=62", user="sofia", now=T2))
    assert len(now_ids) == 3 and now_ids[:2] == [u["id"] for u in usages] and now_ids[2] > now_ids[1]
    assert len(get(app, "/api/part_usages?part=1")["items"]) == 2


def test_low_stock_messages_only_on_crossing():
    app = fresh_app()
    before = len(outbox(app))
    assert use(app, 62, [{"part": 2, "quantity": 1}], user="nils").status == 200   # 3 -> 2 (crosses)
    assert use(app, 62, [{"part": 2, "quantity": 1}], user="nils").status == 200   # 2 -> 1 (already low)
    msgs = [m for m in outbox(app)[before:] if m["channel"] == "low_stock"]
    assert [m["payload"] for m in msgs] == [{"part": 2, "sku": "BELT-A40", "quantity": 2}]
    before = len(outbox(app))
    # South: part 5 already low (no message); 6: 1 -> 0 crosses; 4: 6 -> 2 crosses; messages in list order
    r = use(app, 53, [{"part": 5, "quantity": 1}, {"part": 6, "quantity": 1}, {"part": 4, "quantity": 4}], user="ravi")
    assert r.status == 200, r
    assert round(r.json["parts_cost"], 2) == 121.2
    msgs = [m for m in outbox(app)[before:] if m["channel"] == "low_stock"]
    assert [m["payload"] for m in msgs] == [{"part": 6, "sku": "SEAL-KIT", "quantity": 0},
                                            {"part": 4, "sku": "BRG-6204", "quantity": 2}]
    assert all("created_at" in m and isinstance(m["id"], int) for m in msgs)
    assert [p["quantity"] for p in get(app, "/api/parts")["items"]] == [12, 1, 50, 2, 1, 0, 20, 0]


def test_insufficient_stock_is_409_and_atomic():
    app = fresh_app()
    snap = snapshot(app)
    # the first line alone would be fine; the second asks for 5 of 3 belts
    assert_error(use(app, 62, [{"part": 1, "quantity": 2}, {"part": 2, "quantity": 5}], user="nils"), 409, "conflict")
    assert_error(use(app, 62, [{"part": 8, "quantity": 1}], user="nils"), 409, "conflict")   # out of stock
    assert_error(use(app, 62, [{"part": 3, "quantity": 9}, {"part": 1, "quantity": 13}], user="nils"), 409, "conflict")
    assert snapshot(app) == snap
    # exactly the available quantity is fine
    r = use(app, 62, [{"part": 2, "quantity": 3}], user="nils")
    assert r.status == 200, r
    assert get(app, "/api/parts/2")["quantity"] == 0


def test_stock_conflict_wins_over_invalid_item():
    app = fresh_app()
    snap = snapshot(app)
    # part 4 is a South part (invalid for a North order) but part 2 lacks stock: 409 wins over 400
    assert_error(use(app, 62, [{"part": 2, "quantity": 9}, {"part": 4, "quantity": 1}], user="nils"), 409, "conflict")
    assert_error(use(app, 62, [{"part": 4, "quantity": 1}], user="nils"), 400, "validation")
    assert_error(use(app, 62, [{"part": 1, "quantity": 1}, {"part": 4, "quantity": 1}], user="nils"), 400, "validation")
    assert snapshot(app) == snap


def test_use_parts_validation():
    app = fresh_app()
    snap = snapshot(app)
    bad_bodies = [
        {}, {"items": []}, {"items": "FLT-AHU"}, {"items": [1]},
        {"items": [{"part": 1}]}, {"items": [{"quantity": 1}]},
        {"items": [{"part": 1, "quantity": 1, "note": "x"}]},
        {"items": [{"part": 999, "quantity": 1}]},
        {"items": [{"part": 1, "quantity": 0}]}, {"items": [{"part": 1, "quantity": -1}]},
        {"items": [{"part": 1, "quantity": 1.5}]}, {"items": [{"part": 1, "quantity": "2"}]},
        {"items": [{"part": 1, "quantity": True}]},
        {"items": [{"part": 1, "quantity": 1}, {"part": 1, "quantity": 1}]},
        {"items": [{"part": 7, "quantity": 1}]},            # East part on a North order
    ]
    for body in bad_bodies:
        r = app.post("/api/work_orders/62/use_parts", body, user="nils", now=NOW)
        assert_error(r, 400, "validation")
    assert snapshot(app) == snap


def test_use_parts_permissions_and_state():
    app = fresh_app()
    snap = snapshot(app)
    items = [{"part": 1, "quantity": 1}]
    for user in ("olga", "sofia", "kofi", "umar"):
        assert_error(use(app, 62, items, user=user), 403, "forbidden")
    assert_error(use(app, 77, items, user="nils"), 409, "conflict")          # assigned, not started
    assert_error(use(app, 77, [], user="nils"), 409, "conflict")             # 409 before 400
    assert_error(use(app, 2, [{"part": 7, "quantity": 1}], user="tess"), 409, "conflict")   # completed
    assert_error(use(app, 2, [{"part": 7, "quantity": 1}], user="nils"), 403, "forbidden")  # 403 before 409
    assert_error(use(app, 74, items, user="nils"), 403, "forbidden")         # open, no assignee
    assert_error(use(app, 999, items, user="nils"), 404, "not_found")
    assert snapshot(app) == snap


# --------------------------------------------------------------------------- part_usages reads and writes

def test_part_usages_follow_work_order_read_rules():
    app = fresh_app()
    assert use(app, 53, [{"part": 4, "quantity": 1}], user="ravi").status == 200
    assert use(app, 62, [{"part": 3, "quantity": 2}], user="nils").status == 200
    all_ids = ids(app.get("/api/part_usages", user="sofia", now=NOW))
    assert len(all_ids) == 2
    south, north = all_ids
    assert ids(app.get("/api/part_usages", user="sara", now=NOW)) == [south]
    assert ids(app.get("/api/part_usages", user="ravi", now=NOW)) == [south]
    assert ids(app.get("/api/part_usages", user="tomas", now=NOW)) == all_ids
    assert ids(app.get("/api/part_usages", user="kofi", now=NOW)) == [north]    # kofi requested 62
    assert ids(app.get("/api/part_usages", user="lina", now=NOW)) == []
    assert ids(app.get("/api/part_usages", user="tess", now=NOW)) == []
    assert_error(app.get(f"/api/part_usages/{south}", user="nils", now=NOW), 403, "forbidden")
    assert_error(app.get(f"/api/part_usages/{north}", user="ruth", now=NOW), 403, "forbidden")
    assert app.get(f"/api/part_usages/{north}", user="olga", now=NOW).status == 200
    assert_error(app.get("/api/part_usages/999", user="ruth", now=NOW), 404, "not_found")


def test_part_usages_cannot_be_written_directly():
    app = fresh_app()
    assert use(app, 62, [{"part": 3, "quantity": 2}], user="nils").status == 200
    uid = ids(app.get("/api/part_usages", user="sofia", now=NOW))[0]
    body = {"work_order": 62, "part": 3, "quantity": 1, "unit_cost": 1.25, "used_by": 8, "used_at": NOW}
    for user in ("sofia", "nils"):
        assert_error(app.post("/api/part_usages", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch(f"/api/part_usages/{uid}", {"quantity": 9}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete(f"/api/part_usages/{uid}", user=user, now=NOW), 403, "forbidden")
    assert get(app, f"/api/part_usages/{uid}")["quantity"] == 2


# --------------------------------------------------------------------------- cost, completion, cancel

def test_parts_cost_is_frozen_and_reported_on_completion():
    app = fresh_app()
    assert use(app, 79, [{"part": 3, "quantity": 3}, {"part": 1, "quantity": 1}], user="olga").status == 200
    r = app.patch("/api/parts/3", {"unit_cost": 2.0}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["unit_cost"] == 2.0
    assert round(get(app, "/api/work_orders/79")["parts_cost"], 2) == 46.25
    before = len(outbox(app))
    r = app.post("/api/work_orders/79/complete", {"resolution": "Replaced detector", "labor_minutes": 95},
                 user="olga", now=T2)
    assert r.status == 200, r
    assert round(r.json["parts_cost"], 2) == 46.25
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["work_completed"]
    p = msgs[0]["payload"]
    assert set(p) == {"work_order", "asset", "technician", "labor_minutes", "parts_cost"}
    assert (p["work_order"], p["asset"], p["technician"], p["labor_minutes"]) == (79, 13, 9, 95)
    assert round(p["parts_cost"], 2) == 46.25
    # an order without parts reports 0
    assert app.post("/api/work_orders/62/complete", {"resolution": "ok", "labor_minutes": 10},
                    user="nils", now=T2).status == 200
    assert outbox(app)[-1]["payload"]["parts_cost"] == 0


def test_cancel_keeps_usages_and_stock():
    app = fresh_app()
    assert use(app, 62, [{"part": 1, "quantity": 4}], user="nils").status == 200
    r = app.post("/api/work_orders/62/cancel", {"reason": "Unit replaced"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["status"] == "cancelled"
    assert round(r.json["parts_cost"], 2) == 170.0
    assert get(app, "/api/parts/1")["quantity"] == 8
    assert len(get(app, "/api/part_usages?work_order=62")["items"]) == 1
    assert_error(use(app, 62, [{"part": 1, "quantity": 1}], user="nils"), 409, "conflict")
    assert_error(app.delete("/api/parts/1", user="sofia", now=NOW), 409, "conflict")


# --------------------------------------------------------------------------- parts CRUD

def test_parts_crud_permissions_and_validation():
    app = fresh_app()
    body = {"sku": "GRS-1", "name": "Grease tube", "site": "East", "unit_cost": 3.5, "quantity": 10, "reorder_level": 3}
    for user in ("ruth", "nils", "umar"):
        assert_error(app.post("/api/parts", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/parts", {}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch("/api/parts/1", {"quantity": -5}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/parts/7", user=user, now=NOW), 403, "forbidden")
    for missing in ("sku", "name", "site", "unit_cost", "quantity", "reorder_level"):
        b = {k: v for k, v in body.items() if k != missing}
        assert_error(app.post("/api/parts", b, user="yara", now=NOW), 400, "validation")
    for bad in ({"sku": "FLT-AHU"}, {"quantity": -1}, {"quantity": 1.5}, {"reorder_level": -2},
                {"unit_cost": -0.5}, {"unit_cost": "3.5"}, {"low_stock": False}, {"colour": "red"}):
        assert_error(app.post("/api/parts", dict(body, **bad), user="yara", now=NOW), 400, "validation")
    assert ids(app.get("/api/parts", user="sofia", now=NOW)) == list(range(1, 9))
    r = app.post("/api/parts", body, user="yara", now=NOW)
    assert r.status == 201, r
    new = r.json
    assert isinstance(new["id"], int) and new["id"] not in range(1, 9)
    assert new["low_stock"] is False and new["unit_cost"] == 3.5 and new["quantity"] == 10
    r = app.patch(f"/api/parts/{new['id']}", {"quantity": 3}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["low_stock"] is True
    assert_error(app.patch("/api/parts/2", {"sku": "FUSE-10A"}, user="sofia", now=NOW), 400, "validation")
    assert app.delete(f"/api/parts/{new['id']}", user="sofia", now=NOW).status == 204
    assert_error(app.get(f"/api/parts/{new['id']}", user="sofia", now=NOW), 404, "not_found")


# --------------------------------------------------------------------------- UI and preserved behaviour

def test_ui_parts_and_use_parts_form():
    app = fresh_app()
    r = app.get("/ui/parts", user="ruth", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == list(range(1, 9))
    ui = parse_ui(app.get("/ui/parts/6", user="ruth", now=NOW).text)
    assert ui.fields["sku"] == "SEAL-KIT" and ui.fields["quantity"] == "1" and ui.fields["site"] == "South"
    assert app.get("/ui/parts/new", user="ruth", now=NOW).status == 403
    r = app.get("/ui/parts/new", user="tomas", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["parts"]
    assert {"sku", "name", "site", "unit_cost", "quantity", "reorder_level"} <= set(ui.inputs)
    assert "low_stock" not in ui.inputs
    assert "use_parts" in parse_ui(app.get("/ui/work_orders/62", user="nils", now=NOW).text).actions
    assert "use_parts" not in parse_ui(app.get("/ui/work_orders/62", user="sofia", now=NOW).text).actions
    assert "use_parts" not in parse_ui(app.get("/ui/work_orders/77", user="nils", now=NOW).text).actions
    assert "use_parts" not in parse_ui(app.get("/ui/work_orders/2", user="tess", now=NOW).text).actions
    assert use(app, 62, [{"part": 3, "quantity": 1}], user="nils").status == 200
    assert parse_ui(app.get("/ui/part_usages", user="kofi", now=NOW).text).rows == \
        ids(app.get("/api/part_usages", user="sofia", now=NOW))
    assert parse_ui(app.get("/ui/part_usages", user="mei", now=NOW).text).rows == []


def test_base_behaviour_preserved():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/work_orders/74/assign", {"technician": 9}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["assignee"] == 9
    assert outbox(app)[before]["payload"] == {"work_order": 74, "asset": 1, "technician": 9}
    assert_error(app.post("/api/work_orders/62/complete", {"resolution": "ok", "labor_minutes": 0},
                          user="nils", now=NOW), 400, "validation")
    assert_error(app.post("/api/work_orders", {"asset": 1, "title": "x", "priority": "low", "parts_cost": 0},
                          user="ruth", now=NOW), 400, "validation")
    assert_error(app.delete("/api/work_orders/62", user="sofia", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/work_orders", user="ruth", now=NOW)) == [9, 34, 38, 49, 55, 74, 77]
