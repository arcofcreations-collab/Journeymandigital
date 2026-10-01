"""D03 (library, depends on D02 holds): loan renewals.

Seed facts used:
  loan 52: chen (3), book 22, due 2026-03-04, open
  loan 51: hana (8), book 23, due 2026-03-04, open
  loan 46: jo (10), book 4, due 2026-02-15, open (overdue at 2026-03-01)
  loan 13: chen, returned
  loan 1 : dara, returned
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def loan(app, lid, now=NOW):
    r = app.get(f"/api/loans/{lid}", user="ada", now=now)
    assert r.status == 200, r
    return r.json


def test_member_renews_own_loan():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/loans/52/renew", {}, user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 52
    assert r.json["due_at"] == "2026-03-18"
    assert r.json["renewals"] == 1
    assert r.json["returned_at"] is None and r.json["borrowed_at"] == "2026-02-18T16:00:00"
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "loan_renewed"
    assert msgs[-1]["payload"] == {"loan": 52, "due_at": "2026-03-18"}


def test_renewal_counts_from_due_date_and_is_limited_to_two():
    app = fresh_app()
    assert app.post("/api/loans/52/renew", {}, user="chen", now=NOW).status == 200
    r = app.post("/api/loans/52/renew", {}, user="chen", now=NOW)
    assert r.status == 200, r
    assert r.json["due_at"] == "2026-04-01" and r.json["renewals"] == 2
    n = len(outbox(app))
    assert_error(app.post("/api/loans/52/renew", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/52/renew", {}, user="ada", now=NOW), 409, "conflict")
    l = loan(app, 52)
    assert l["due_at"] == "2026-04-01" and l["renewals"] == 2
    assert len(outbox(app)) == n


def test_renew_on_due_date_allowed_but_not_after():
    app = fresh_app()
    r = app.post("/api/loans/52/renew", {}, user="chen", now="2026-03-04T23:59:59")
    assert r.status == 200 and r.json["due_at"] == "2026-03-18", r
    assert_error(app.post("/api/loans/51/renew", {}, user="hana", now="2026-03-05T00:00:00"), 409, "conflict")
    assert loan(app, 51)["due_at"] == "2026-03-04"


def test_overdue_and_returned_loans_cannot_be_renewed():
    app = fresh_app()
    assert_error(app.post("/api/loans/46/renew", {}, user="jo", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/46/renew", {}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/13/renew", {}, user="chen", now=NOW), 409, "conflict")
    l = loan(app, 46)
    assert l["due_at"] == "2026-02-15" and l["renewals"] == 0 and l["overdue"] is True


def test_renew_permissions():
    app = fresh_app()
    assert_error(app.post("/api/loans/52/renew", {}, user="dara", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/1/renew", {}, user="chen", now=NOW), 403, "forbidden")  # 403 before 409
    assert_error(app.post("/api/loans/999/renew", {}, user="chen", now=NOW), 404, "not_found")
    assert loan(app, 52)["renewals"] == 0
    r = app.post("/api/loans/52/renew", {}, user="ben", now=NOW)
    assert r.status == 200 and r.json["renewals"] == 1


def test_waiting_hold_blocks_renewal():
    app = fresh_app()
    assert app.post("/api/books/22/hold", {}, user="dara", now=NOW).status == 200
    n = len(outbox(app))
    assert_error(app.post("/api/loans/52/renew", {}, user="chen", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/52/renew", {}, user="ada", now=NOW), 409, "conflict")
    assert loan(app, 52)["due_at"] == "2026-03-04"
    assert len(outbox(app)) == n
    hid = app.get("/api/holds?book=22", user="ada", now=NOW).json["items"][0]["id"]
    assert app.post(f"/api/holds/{hid}/cancel", {}, user="dara", now=NOW).status == 200
    r = app.post("/api/loans/52/renew", {}, user="chen", now=NOW)
    assert r.status == 200 and r.json["due_at"] == "2026-03-18"


def test_renewal_does_not_disturb_holds_queue():
    app = fresh_app()
    assert app.post("/api/loans/52/renew", {}, user="chen", now=NOW).status == 200
    # a hold may be placed after the renewal; return then serves it
    assert app.post("/api/books/22/hold", {}, user="dara", now=NOW).status == 200
    assert app.post("/api/loans/52/return", {}, user="chen", now="2026-03-10T10:00:00").status == 200
    h = app.get("/api/holds?book=22", user="ada", now=NOW).json["items"][0]
    assert h["status"] == "ready" and h["member"] == 4
    assert app.get("/api/books/22", user="ada", now="2026-03-10T10:00:00").json["status"] == "reserved"


def test_renewed_loan_overdue_follows_new_due_date():
    app = fresh_app()
    assert app.post("/api/loans/52/renew", {}, user="chen", now=NOW).status == 200
    assert loan(app, 52, now="2026-03-10T12:00:00")["overdue"] is False
    assert loan(app, 52, now="2026-03-18T23:00:00")["overdue"] is False
    assert loan(app, 52, now="2026-03-19T00:00:00")["overdue"] is True


def test_existing_and_new_loans_start_with_zero_renewals():
    app = fresh_app()
    items = app.get("/api/loans", user="ada", now=NOW).json["items"]
    assert [l["id"] for l in items] == list(range(1, 61))
    for l in items:
        assert l["renewals"] == 0, l
    assert app.post("/api/books/3/borrow", {}, user="chen", now=NOW).status == 200
    new = app.get("/api/loans?book=3", user="ada", now=NOW).json["items"][0]
    assert new["renewals"] == 0 and new["due_at"] == "2026-03-15"


def test_loans_still_not_directly_writable():
    app = fresh_app()
    for user in ("ada", "chen"):
        assert_error(app.patch("/api/loans/52", {"renewals": 0, "due_at": "2026-05-01"}, user=user, now=NOW),
                     403, "forbidden")
    assert loan(app, 52)["due_at"] == "2026-03-04"


def test_ui_renew_form():
    app = fresh_app()
    assert "renew" in parse_ui(app.get("/ui/loans/52", user="chen", now=NOW).text).actions
    assert "renew" in parse_ui(app.get("/ui/loans/52", user="ada", now=NOW).text).actions
    assert "renew" not in parse_ui(app.get("/ui/loans/46", user="jo", now=NOW).text).actions
    assert "renew" not in parse_ui(app.get("/ui/loans/13", user="chen", now=NOW).text).actions
    assert app.post("/api/books/22/hold", {}, user="dara", now=NOW).status == 200
    ui = parse_ui(app.get("/ui/loans/52", user="chen", now=NOW).text)
    assert "renew" not in ui.actions and "return" in ui.actions
