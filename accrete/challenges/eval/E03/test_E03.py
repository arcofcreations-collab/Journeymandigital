"""Hidden acceptance tests for E03 (maintenance, after E01-E02): priority scale p1-p4.

Migration computed from spec/apps/maintenance_seed.json:
  urgent -> p1; normal -> p2 on high-criticality assets (1 3 4 5 13 14 15 16 21 26 31), else p3; low -> p4.
  Low orders on high-criticality assets keep p4: 6 26 42 64 67 (64 is unfinished: S-GEN-01, assigned to sara).
  New overdue set at 2026-03-01 (offsets p1 1, p2 3, p3 7, p4 30): adds 65 and 68.
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

P1 = [27, 32, 35, 39, 40, 41, 51, 58, 70, 73, 76, 77, 79, 80, 81, 82]
P2 = [4, 14, 17, 18, 21, 29, 34, 54, 61, 65, 68, 74]
P3 = [1, 2, 3, 7, 10, 11, 12, 13, 19, 25, 28, 31, 36, 43, 44, 48, 50, 52, 55, 56, 57, 62, 66, 69, 72, 75, 78]
P4 = [5, 6, 8, 9, 15, 16, 20, 22, 23, 24, 26, 30, 33, 37, 38, 42, 45, 46, 47, 49, 53, 59, 60, 63, 64, 67, 71]
OVERDUE = [30, 37, 38, 47, 52, 54, 56, 61, 62, 65, 68, 73, 76]


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


def create(app, user, asset, priority, now=NOW, title="Check"):
    return app.post("/api/work_orders", {"asset": asset, "title": title, "priority": priority}, user=user, now=now)


# --------------------------------------------------------------------------- migration

def test_priorities_migrated():
    app = fresh_app()
    got = {o["id"]: o["priority"] for o in app.get("/api/work_orders", user="sofia", now=NOW).json["items"]}
    assert len(got) == 82
    for code, lst in (("p1", P1), ("p2", P2), ("p3", P3), ("p4", P4)):
        for oid in lst:
            assert got[oid] == code, (oid, got[oid])
        assert ids(app.get(f"/api/work_orders?priority={code}", user="sofia", now=NOW)) == lst
    for old in ("urgent", "normal", "low"):
        assert ids(app.get(f"/api/work_orders?priority={old}", user="sofia", now=NOW)) == []


def test_due_dates_and_overdue_follow_new_offsets():
    app = fresh_app()
    items = app.get("/api/work_orders", user="sofia", now=NOW).json["items"]
    assert [o["id"] for o in items if o["overdue"]] == OVERDUE
    due = {o["id"]: o["due_date"] for o in items}
    assert due[74] == "2026-03-01"     # p2 (was normal, +7)
    assert due[65] == "2026-02-25"
    assert due[54] == "2026-02-17"
    assert due[78] == "2026-03-07"     # p3 keeps +7
    assert due[82] == "2026-03-02"     # p1 keeps +1
    assert due[30] == "2026-02-04"     # p4 keeps +30
    assert due[4] == "2025-10-12"      # finished orders follow the new offsets too
    assert wo(app, 74, now="2026-03-01T23:59:59")["overdue"] is False
    assert wo(app, 74, now="2026-03-02T00:00:00")["overdue"] is True


def test_low_orders_on_high_assets_keep_p4():
    app = fresh_app()
    o = wo(app, 64)
    assert o["priority"] == "p4" and o["due_date"] == "2026-03-23" and o["assignee"] == 11
    assert wo(app, 6)["priority"] == "p4" and wo(app, 42)["priority"] == "p4"
    r = app.patch("/api/work_orders/64", {"title": "Battery check (bank B)"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["priority"] == "p4"
    # setting p4 on a high-criticality asset is refused, even if the order already has it
    assert_error(app.patch("/api/work_orders/64", {"priority": "p4"}, user="tomas", now=NOW), 400, "validation")
    r = app.patch("/api/work_orders/64", {"priority": "p3"}, user="tomas", now=NOW)
    assert r.status == 200 and r.json["due_date"] == "2026-02-28" and r.json["overdue"] is True
    assert_error(app.patch("/api/work_orders/64", {"priority": "p4"}, user="tomas", now=NOW), 400, "validation")
    assert wo(app, 64)["priority"] == "p3"


# --------------------------------------------------------------------------- create / patch

def test_create_with_new_priority_codes():
    app = fresh_app()
    late = "2026-02-25T23:30:00"
    expected = {"p1": "2026-02-26", "p2": "2026-02-28", "p3": "2026-03-04", "p4": "2026-03-27"}
    for code, due in expected.items():
        r = create(app, "tomas", 19, code, now=late)        # S-PMP-01, medium
        assert r.status == 201, r
        assert r.json["priority"] == code and r.json["due_date"] == due
    for bad in ("urgent", "normal", "low", "P1", "p5", "", None, 1):
        assert_error(create(app, "ruth", 2, bad), 400, "validation")
    assert_error(create(app, "ruth", 1, "p4"), 400, "validation")       # N-AHU-01 is high
    assert_error(create(app, "sofia", 21, "p4"), 400, "validation")     # S-GEN-01 is high
    assert create(app, "ruth", 1, "p3").status == 201
    assert create(app, "ruth", 9, "p4").status == 201                   # N-CMP-01 is low
    # site rule still wins over the new validation
    assert_error(create(app, "ruth", 21, "p4"), 403, "forbidden")


def test_patch_priority_codes():
    app = fresh_app()
    r = app.patch("/api/work_orders/74", {"priority": "p1"}, user="sofia", now=NOW)
    assert r.status == 200 and r.json["due_date"] == "2026-02-27" and r.json["overdue"] is True
    for bad in ("urgent", "normal", "p0", "p4"):          # p4 refused: asset 1 is high
        assert_error(app.patch("/api/work_orders/74", {"priority": bad}, user="sofia", now=NOW), 400, "validation")
    r = app.patch("/api/work_orders/38", {"priority": "p4"}, user="sofia", now=NOW)   # N-DCK-01 low
    assert r.status == 200
    assert_error(app.patch("/api/work_orders/74", {"priority": "p3"}, user="ruth", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/work_orders/2", {"priority": "urgent"}, user="sofia", now=NOW), 409, "conflict")
    assert wo(app, 74)["priority"] == "p1"


# --------------------------------------------------------------------------- claim interaction (E02)

def test_claim_limited_to_p3_and_p4():
    app = fresh_app()
    assert_error(app.post("/api/work_orders/76/claim", {}, user="wade", now=NOW), 403, "forbidden")   # p1
    assert_error(app.post("/api/work_orders/54/claim", {}, user="wade", now=NOW), 403, "forbidden")   # p2
    r = app.post("/api/work_orders/78/claim", {}, user="wade", now=NOW)                               # p3
    assert r.status == 200 and r.json["dispatch"] == "self"
    # the rule uses the current priority
    assert app.patch("/api/work_orders/54", {"priority": "p3"}, user="tomas", now=NOW).status == 200
    assert app.post("/api/work_orders/54/claim", {}, user="wade", now=NOW).status == 200
    assert_error(app.post("/api/work_orders/60/claim", {}, user="wade", now=NOW), 409, "conflict")    # wade at 3
    # 403 for the priority wins over 409 (state or workload)
    assert_error(app.post("/api/work_orders/73/claim", {}, user="wade", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders/82/claim", {}, user="nils", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/work_orders/38/claim", {}, user="nils", now=NOW), 409, "conflict")    # p4, nils at 3
    # supervisors still dispatch any priority
    r = app.post("/api/work_orders/76/assign", {"technician": 15}, user="tomas", now=NOW)
    assert_error(r, 409, "conflict")       # wade is now at the cap
    r = app.post("/api/work_orders/81/assign", {"technician": 12}, user="yara", now=NOW)
    assert r.status == 200 and r.json["priority"] == "p1"


def test_ui_shows_codes_and_claim_rule():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/work_orders/74", user="ruth", now=NOW).text)
    assert ui.fields["priority"] == "p2" and ui.fields["due_date"] == "2026-03-01"
    assert "claim" in parse_ui(app.get("/ui/work_orders/78", user="wade", now=NOW).text).actions
    assert "claim" not in parse_ui(app.get("/ui/work_orders/76", user="wade", now=NOW).text).actions
    assert "claim" in parse_ui(app.get("/ui/work_orders/30", user="tess", now=NOW).text).actions
    assert "claim" not in parse_ui(app.get("/ui/work_orders/81", user="tess", now=NOW).text).actions


def test_earlier_changes_preserved():
    app = fresh_app()
    assert_error(app.post("/api/work_orders/74/assign", {"technician": 8}, user="sofia", now=NOW), 409, "conflict")
    assert wo(app, 75)["dispatch"] == "self"
    r = app.post("/api/work_orders/79/use_parts", {"items": [{"part": 3, "quantity": 2}]}, user="olga", now=NOW)
    assert r.status == 200 and round(r.json["parts_cost"], 2) == 2.5
    before = len(outbox(app))
    r = app.post("/api/work_orders/79/complete", {"resolution": "Fixed", "labor_minutes": 50}, user="olga", now=NOW)
    assert r.status == 200 and r.json["priority"] == "p1"
    p = outbox(app)[before]["payload"]
    assert set(p) == {"work_order", "asset", "technician", "labor_minutes", "parts_cost"}
    assert p["labor_minutes"] == 50 and round(p["parts_cost"], 2) == 2.5
