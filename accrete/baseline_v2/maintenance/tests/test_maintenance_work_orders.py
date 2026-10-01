"""Work orders: who can read them, creating, editing, deleting and the derived fields."""
from datetime import date, timedelta

NOW = "2026-03-01T12:00:00"
NEW_ORDER = {"asset": 1, "title": "Rattling fan", "priority": "normal"}


def _readable_ids(seed, username):
    """Expected readable work orders, computed from the seed with the spec's rule."""
    user = next(s for s in seed["staff"] if s["username"] == username)
    asset_site = {a["id"]: a["site"] for a in seed["assets"]}
    return [
        o["id"] for o in seed["work_orders"]
        if user["role"] == "supervisor" or user["id"] in (o["requested_by"], o["assignee"])
        or (user["role"] == "technician" and asset_site[o["asset"]] == user["site"])
    ]


# --- reading --------------------------------------------------------------------------

def test_list_shows_only_readable_orders(app, seed):
    for user in ("sofia", "ruth", "mei", "nils", "tess", "umar", "ravi"):
        ids = [o["id"] for o in app.get("/api/work_orders", user=user).json["items"]]
        assert ids == _readable_ids(seed, user), user
    assert len(app.get("/api/work_orders", user="yara").json["items"]) == len(seed["work_orders"])


def test_direct_access_to_unreadable_order_is_403(app):
    assert app.get("/api/work_orders/74", user="ruth").status == 200  # requester
    assert app.get("/api/work_orders/74", user="olga").status == 200  # technician at the asset's site
    assert app.get("/api/work_orders/74", user="tomas").status == 200  # any supervisor
    r = app.get("/api/work_orders/74", user="kofi")  # requester, not theirs
    assert r.status == 403 and r.json["error"] == "forbidden"
    assert app.get("/api/work_orders/74", user="ravi").status == 403  # technician elsewhere
    assert app.get("/api/work_orders/56", user="ravi").status == 200  # requested by ravi


def test_assignee_reads_order_at_another_site(app):
    app.patch("/api/staff/10", {"site": "North"}, user="sofia")  # ravi moves; assignee of 53 (South)
    assert app.get("/api/work_orders/53", user="ravi").status == 200
    assert app.get("/api/work_orders/54", user="ravi").status == 403  # South, not his


def test_derived_fields(app):
    order = app.get("/api/work_orders/30", user="mei").json  # low, created 2026-01-05, open
    assert order["due_date"] == "2026-02-04" and order["overdue"] is True
    order = app.get("/api/work_orders/77", user="ruth").json  # urgent, created 2026-02-28, assigned
    assert order["due_date"] == "2026-03-01" and order["overdue"] is False
    assert app.get("/api/work_orders/77", user="ruth", now="2026-03-02T00:00:00").json["overdue"] is True
    finished = app.get("/api/work_orders/2", user="sofia").json
    assert finished["status"] == "completed" and finished["overdue"] is False


def test_due_date_follows_priority(app):
    r = app.patch("/api/work_orders/74", {"priority": "urgent"}, user="sofia")
    assert r.json["due_date"] == "2026-02-27" and r.json["overdue"] is True
    r = app.patch("/api/work_orders/74", {"priority": "low"}, user="sofia")
    assert r.json["due_date"] == "2026-03-28" and r.json["overdue"] is False


def test_overdue_filter(app, seed):
    today = date(2026, 3, 1)
    days = {"urgent": 1, "normal": 7, "low": 30}
    expected = [
        o["id"] for o in seed["work_orders"]
        if o["status"] in ("open", "assigned", "in_progress")
        and today > date.fromisoformat(o["created_at"][:10]) + timedelta(days=days[o["priority"]])
    ]
    assert expected
    assert [o["id"] for o in app.get("/api/work_orders?overdue=true", user="sofia").json["items"]] == expected


# --- creating -------------------------------------------------------------------------

def test_create(app):
    r = app.post("/api/work_orders", NEW_ORDER, user="ruth", now="2026-03-03T08:15:00")
    assert r.status == 201
    assert r.json == {
        "id": 83, "asset": 1, "title": "Rattling fan", "description": None, "priority": "normal",
        "status": "open", "requested_by": 3, "created_at": "2026-03-03T08:15:00", "assignee": None,
        "started_at": None, "completed_at": None, "resolution": None, "labor_minutes": None,
        "cancel_reason": None, "due_date": "2026-03-10", "overdue": False,
    }
    assert app.get("/api/work_orders/83", user="ruth").json == r.json
    assert app.get("/api/_outbox", user="ruth").json["items"] == []


def test_create_with_description(app):
    r = app.post("/api/work_orders", {**NEW_ORDER, "description": "Since Monday"}, user="nils")
    assert r.status == 201 and r.json["description"] == "Since Monday"


def test_create_only_at_own_site(app):
    south = {**NEW_ORDER, "asset": 14}
    assert app.post("/api/work_orders", south, user="ruth").status == 403
    assert app.post("/api/work_orders", south, user="nils").status == 403
    assert app.post("/api/work_orders", {**south, "title": "", "status": "x"}, user="ruth").status == 403
    assert app.post("/api/work_orders", {"asset": 24}, user="ruth").status == 403  # retired, other site
    assert app.post("/api/work_orders", south, user="sofia").status == 201  # supervisors anywhere


def test_create_validation(app):
    def create(**changes):
        return app.post("/api/work_orders", {**NEW_ORDER, **changes}, user="ruth")

    assert create(asset=999).status == 400
    assert create(asset=7).status == 400  # retired
    assert create(asset=None).status == 400
    assert create(asset="1").status == 400
    assert create(asset=True).status == 400
    assert create(title="  ").status == 400
    assert create(priority="high").status == 400
    assert create(description=5).status == 400
    for field, value in (("status", "open"), ("requested_by", 3), ("id", 1), ("due_date", "2026-03-02"),
                         ("assignee", 8), ("colour", "red")):
        assert create(**{field: value}).status == 400, field
    body = dict(NEW_ORDER)
    del body["priority"]
    assert app.post("/api/work_orders", body, user="ruth").status == 400
    assert len(app.get("/api/work_orders", user="sofia").json["items"]) == 82


# --- editing --------------------------------------------------------------------------

def test_supervisor_edits_unfinished_orders(app):
    r = app.patch("/api/work_orders/79", {"title": "Zone 3", "description": None, "priority": "low"}, user="tomas")
    assert r.status == 200 and (r.json["title"], r.json["priority"]) == ("Zone 3", "low")
    assert app.patch("/api/work_orders/2", {"title": "x"}, user="sofia").status == 409  # completed
    assert app.patch("/api/work_orders/1", {"title": "x"}, user="sofia").status == 409  # cancelled
    assert app.patch("/api/work_orders/2", {"asset": 3}, user="sofia").status == 409  # 409 beats 400


def test_requester_edits_open_orders_without_priority(app):
    r = app.patch("/api/work_orders/74", {"title": "Fan noise", "description": "Loud"}, user="ruth")
    assert r.status == 200 and (r.json["title"], r.json["description"]) == ("Fan noise", "Loud")
    assert app.patch("/api/work_orders/74", {"priority": "urgent"}, user="ruth").status == 403
    assert app.patch("/api/work_orders/77", {"title": "x"}, user="ruth").status == 409  # assigned
    assert app.patch("/api/work_orders/77", {"priority": "low"}, user="ruth").status == 403  # 403 beats 409


def test_others_cannot_edit(app):
    assert app.patch("/api/work_orders/74", {"title": "x"}, user="kofi").status == 403
    assert app.patch("/api/work_orders/77", {"title": "x"}, user="nils").status == 403  # assignee
    assert app.patch("/api/work_orders/74", {"title": "x"}, user="olga").status == 403  # site technician


def test_edit_validation(app):
    assert app.patch("/api/work_orders/74", {"asset": 2}, user="ruth").status == 400
    assert app.patch("/api/work_orders/74", {"asset": 1}, user="sofia").status == 400
    assert app.patch("/api/work_orders/74", {"status": "completed"}, user="sofia").status == 400
    assert app.patch("/api/work_orders/74", {"title": ""}, user="sofia").status == 400
    assert app.patch("/api/work_orders/74", {"priority": "asap"}, user="sofia").status == 400
    assert app.patch("/api/work_orders/74", {"overdue": False}, user="sofia").status == 400
    assert app.patch("/api/work_orders/74", {}, user="ruth").status == 200


def test_nobody_deletes_work_orders(app):
    assert app.delete("/api/work_orders/74", user="sofia").status == 403
    assert app.delete("/api/work_orders/74", user="ruth").status == 403
    assert app.delete("/api/work_orders/999", user="sofia").status == 404
    assert app.get("/api/work_orders/74", user="sofia").status == 200
