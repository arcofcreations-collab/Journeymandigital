"""D04 (library, depends on D03 renewals -> D02 holds): late-return fines.

Seed facts (computed from library_seed.json; fine = 0.50/day, cap 5.00):
  historic loans returned late (loan: days late -> fine):
    2: 4 -> 2.0   4: 1 -> 0.5   14: 1 -> 0.5   17: 5 -> 2.5   19: 2 -> 1.0   26: 2 -> 1.0
    28: 1 -> 0.5  29: 4 -> 2.0  35: 4 -> 2.0   36: 6 -> 3.0   41: 4 -> 2.0   44: 6 -> 3.0
  loan 38 due 2026-01-05, returned 2026-01-05T15:00 -> 0 (same day); loan 11 likewise -> 0
  open loans due 2026-02-15: 46 (jo), 47 (gus, book 8), 48 (ivan, book 7), 49 (kemal), 50 (jo)
  ivan (9) also has loan 55 (book 1, due 2026-03-04); chen (3) has 52 (due 2026-03-04)
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

HISTORIC_FINES = {2: 2.0, 4: 0.5, 14: 0.5, 17: 2.5, 19: 1.0, 26: 1.0, 28: 0.5, 29: 2.0,
                  35: 2.0, 36: 3.0, 41: 2.0, 44: 3.0}


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def loan(app, lid, now=NOW):
    r = app.get(f"/api/loans/{lid}", user="ada", now=now)
    assert r.status == 200, r
    return r.json


def fines_due(app, mid, now=NOW):
    r = app.get(f"/api/members/{mid}", user="ada", now=now)
    assert r.status == 200, r
    return r.json["fines_due"]


def new_msgs(app, before, channel):
    return [m for m in outbox(app)[before:] if m["channel"] == channel]


def gus_returns_late(app, now="2026-02-18T10:00:00"):
    r = app.post("/api/loans/47/return", {}, user="gus", now=now)
    assert r.status == 200, r
    return r


def test_historic_fines_computed_and_settled():
    app = fresh_app()
    items = {l["id"]: l for l in app.get("/api/loans", user="ada", now=NOW).json["items"]}
    for lid in range(1, 46):  # all returned seed loans
        l = items[lid]
        if lid in HISTORIC_FINES:
            assert l["fine"] == HISTORIC_FINES[lid], (lid, l["fine"])
            assert l["fine_paid"] is True, lid
        else:
            assert l["fine"] == 0, (lid, l["fine"])
            assert l["fine_paid"] is False, lid
    assert items[38]["fine"] == 0 and items[11]["fine"] == 0


def test_no_member_owes_anything_initially():
    app = fresh_app()
    members = app.get("/api/members", user="ada", now=NOW).json["items"]
    assert [m["id"] for m in members] == list(range(1, 13))
    for m in members:
        assert m["fines_due"] == 0, m
    # jo has two overdue, unreturned loans: they accrue but do not count yet
    assert fines_due(app, 10) == 0
    r = app.get("/api/members/10", user="jo", now=NOW)
    assert r.status == 200 and r.json["fines_due"] == 0


def test_open_loan_fine_accrues_and_is_capped():
    app = fresh_app()
    assert loan(app, 46, now="2026-02-15T23:00:00")["fine"] == 0
    assert loan(app, 46, now="2026-02-16T00:00:00")["fine"] == 0.5
    assert loan(app, 46, now="2026-02-20T12:00:00")["fine"] == 2.5
    assert loan(app, 46, now=NOW)["fine"] == 5.0          # 14 days late, capped
    assert loan(app, 52, now=NOW)["fine"] == 0
    for lid in range(46, 61):
        assert loan(app, lid)["fine_paid"] is False


def test_late_return_charges_fine_and_blocks_member():
    app = fresh_app()
    n = len(outbox(app))
    r = gus_returns_late(app)
    assert r.json["fine"] == 1.5 and r.json["fine_paid"] is False
    msgs = new_msgs(app, n, "fine_charged")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == {"loan": 47, "member": 7, "amount": 1.5}
    assert fines_due(app, 7, now="2026-02-18T10:00:00") == 1.5
    r = app.get("/api/members/7", user="gus", now=NOW)
    assert r.status == 200 and r.json["fines_due"] == 1.5
    # the fine is fixed once returned
    assert loan(app, 47, now="2026-06-01T00:00:00")["fine"] == 1.5
    n = len(outbox(app))
    assert_error(app.post("/api/books/3/borrow", {}, user="gus", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/3/borrow", {"member": 7}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/1/hold", {}, user="gus", now=NOW), 409, "conflict")
    assert len(outbox(app)) == n
    assert app.get("/api/books/3", user="ada", now=NOW).json["status"] == "available"
    assert app.get("/api/holds?member=7", user="ada", now=NOW).json["items"] == []


def test_pay_fine_unblocks_member():
    app = fresh_app()
    gus_returns_late(app)
    n = len(outbox(app))
    r = app.post("/api/loans/47/pay_fine", {}, user="ben", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 47 and r.json["fine_paid"] is True and r.json["fine"] == 1.5
    msgs = outbox(app)[n:]
    assert [m["channel"] for m in msgs] == ["fine_paid"]
    assert msgs[0]["payload"] == {"loan": 47, "member": 7, "amount": 1.5}
    assert fines_due(app, 7) == 0
    assert app.post("/api/books/3/borrow", {}, user="gus", now=NOW).status == 200


def test_pay_fine_permissions_and_state():
    app = fresh_app()
    gus_returns_late(app)
    assert_error(app.post("/api/loans/47/pay_fine", {}, user="gus", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/46/pay_fine", {}, user="chen", now=NOW), 403, "forbidden")  # 403 before 409
    n = len(outbox(app))
    assert_error(app.post("/api/loans/46/pay_fine", {}, user="ada", now=NOW), 409, "conflict")   # not returned
    assert_error(app.post("/api/loans/36/pay_fine", {}, user="ada", now=NOW), 409, "conflict")   # historic, settled
    assert_error(app.post("/api/loans/13/pay_fine", {}, user="ada", now=NOW), 409, "conflict")   # fine 0
    assert len(outbox(app)) == n
    assert loan(app, 47)["fine_paid"] is False
    assert app.post("/api/loans/47/pay_fine", {}, user="ada", now=NOW).status == 200
    assert_error(app.post("/api/loans/47/pay_fine", {}, user="ada", now=NOW), 409, "conflict")   # twice


def test_unpaid_fine_blocks_renewal():
    app = fresh_app()
    r = app.post("/api/loans/48/return", {}, user="ivan", now=NOW)
    assert r.status == 200 and r.json["fine"] == 5.0
    assert fines_due(app, 9) == 5.0
    assert_error(app.post("/api/loans/55/renew", {}, user="ivan", now=NOW), 409, "conflict")
    assert loan(app, 55)["due_at"] == "2026-03-04" and loan(app, 55)["renewals"] == 0
    assert app.post("/api/loans/48/pay_fine", {}, user="ada", now=NOW).status == 200
    r = app.post("/api/loans/55/renew", {}, user="ivan", now=NOW)
    assert r.status == 200 and r.json["due_at"] == "2026-03-18"


def test_fine_uses_renewed_due_date():
    app = fresh_app()
    assert app.post("/api/loans/52/renew", {}, user="chen", now=NOW).status == 200  # due 2026-03-18
    assert loan(app, 52, now="2026-03-10T12:00:00")["fine"] == 0
    r = app.post("/api/loans/52/return", {}, user="chen", now="2026-03-20T09:00:00")
    assert r.status == 200, r
    assert r.json["fine"] == 1.0
    assert fines_due(app, 3, now="2026-03-20T09:00:00") == 1.0


def test_on_time_return_charges_nothing():
    app = fresh_app()
    n = len(outbox(app))
    r = app.post("/api/loans/52/return", {}, user="chen", now="2026-03-04T22:00:00")
    assert r.status == 200 and r.json["fine"] == 0 and r.json["fine_paid"] is False
    assert new_msgs(app, n, "fine_charged") == []
    assert fines_due(app, 3) == 0
    assert app.post("/api/books/3/borrow", {}, user="chen", now="2026-03-04T22:00:00").status == 200


def test_ready_hold_member_with_fine_cannot_borrow_until_paid():
    app = fresh_app()
    # gus has no fine yet (his overdue loan is still out), so he may place a hold
    assert app.post("/api/books/1/hold", {}, user="gus", now="2026-02-19T09:00:00").status == 200
    r = gus_returns_late(app, now="2026-02-19T10:00:00")
    assert r.json["fine"] == 2.0
    assert app.post("/api/loans/55/return", {}, user="ivan", now="2026-02-19T11:00:00").status == 200
    h = app.get("/api/holds?book=1", user="ada", now=NOW).json["items"][0]
    assert h["member"] == 7 and h["status"] == "ready"
    assert_error(app.post("/api/books/1/borrow", {}, user="gus", now="2026-02-19T12:00:00"), 409, "conflict")
    assert app.get("/api/holds?book=1", user="ada", now=NOW).json["items"][0]["status"] == "ready"
    assert app.post("/api/loans/47/pay_fine", {}, user="ada", now="2026-02-19T13:00:00").status == 200
    assert app.post("/api/books/1/borrow", {}, user="gus", now="2026-02-19T14:00:00").status == 200
    assert app.get("/api/holds?book=1", user="ada", now=NOW).json["items"][0]["status"] == "fulfilled"


def test_ui_pay_fine_form():
    app = fresh_app()
    gus_returns_late(app)
    ui = parse_ui(app.get("/ui/loans/47", user="ada", now=NOW).text)
    assert "pay_fine" in ui.actions and "fine" in ui.fields
    assert "pay_fine" not in parse_ui(app.get("/ui/loans/47", user="gus", now=NOW).text).actions
    assert "pay_fine" not in parse_ui(app.get("/ui/loans/36", user="ada", now=NOW).text).actions
    assert "pay_fine" not in parse_ui(app.get("/ui/loans/46", user="ada", now=NOW).text).actions
