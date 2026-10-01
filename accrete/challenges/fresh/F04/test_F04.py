"""Hidden acceptance tests for F04 (expenses, after F01-F03): cash advances recovered from payments.

Seed facts (spec/apps/expenses_seed.json after the F01-F04 migrations):
  advances 1 victor (11) 300.00 issued 2026-02-01T09:00:00, 2 victor 250.00 issued 2026-02-20T09:00:00,
           3 rosa (7) 500.00 issued 2026-02-10T09:00:00; all issued by fiona (1), nothing recovered.
  victor's manager is omar (4); rosa's manager is nadia (3).
  claim 41: victor, other, 635.61, approved (approved_amount 635.61).
  claim 21: victor, meals, 1644.21, approved, approved_amount 400 (capped by F03).
  claim 22: sam (8), approved, approved_amount 400.   claim 58: rosa, travel, 1118.43, submitted.
  paid claims: 6 11 16 17 24 26 31 32 42 45 47 48 49 51 55 56 57 64 70 71 77
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
PAID = [6, 11, 16, 17, 24, 26, 31, 32, 42, 45, 47, 48, 49, 51, 55, 56, 57, 64, 70, 71, 77]
SEEDED = [
    {"id": 1, "employee": 11, "amount": 300, "purpose": "Conference travel float",
     "issued_at": "2026-02-01T09:00:00", "issued_by": 1, "recovered": 0, "outstanding": 300},
    {"id": 2, "employee": 11, "amount": 250, "purpose": "Client visit float",
     "issued_at": "2026-02-20T09:00:00", "issued_by": 1, "recovered": 0, "outstanding": 250},
    {"id": 3, "employee": 7, "amount": 500, "purpose": "Trade fair float",
     "issued_at": "2026-02-10T09:00:00", "issued_by": 1, "recovered": 0, "outstanding": 500},
]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def money(x):
    return None if x is None else round(x, 2)


def rounded(d):
    return {k: (money(v) if isinstance(v, float) else v) for k, v in d.items()}


def outbox(app):
    r = app.get("/api/_outbox", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def adv(app, aid):
    r = app.get(f"/api/advances/{aid}", user="fiona", now=NOW)
    assert r.status == 200, r
    return r.json


def claim(app, cid, user="fiona"):
    r = app.get(f"/api/claims/{cid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def snapshot(app):
    return (app.get("/api/advances", user="fiona", now=NOW).json["items"],
            app.get("/api/claims", user="fiona", now=NOW).json["items"], outbox(app))


def test_seeded_advances():
    app = fresh_app()
    r = app.get("/api/advances", user="fiona", now=NOW)
    assert r.status == 200, r
    items = r.json["items"]
    assert [a["id"] for a in items] == [1, 2, 3]
    for got, exp in zip(items, SEEDED):
        for k, v in exp.items():
            assert got[k] == v, (exp["id"], k, got.get(k))


def test_advance_read_permissions():
    app = fresh_app()
    assert ids(app.get("/api/advances", user="victor", now=NOW)) == [1, 2]
    assert ids(app.get("/api/advances", user="rosa", now=NOW)) == [3]
    assert ids(app.get("/api/advances", user="omar", now=NOW)) == [1, 2]
    assert ids(app.get("/api/advances", user="nadia", now=NOW)) == [3]
    for user in ("marco", "sam"):
        assert ids(app.get("/api/advances", user=user, now=NOW)) == []
    assert app.get("/api/advances/1", user="omar", now=NOW).status == 200
    assert_error(app.get("/api/advances/1", user="sam", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/advances/3", user="victor", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/advances/99", user="sam", now=NOW), 404, "not_found")
    assert ids(app.get("/api/advances?employee=11", user="fiona", now=NOW)) == [1, 2]
    assert_error(app.get("/api/advances", user=None, now=NOW), 401, "unauthenticated")


def test_paid_claims_migrated_and_new_fields():
    app = fresh_app()
    items = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert [c["id"] for c in items if c["status"] == "paid"] == PAID
    for c in items:
        if c["status"] == "paid":
            assert c["advance_recovered"] == 0, c["id"]
            assert c["paid_amount"] == c["amount"], c["id"]
        else:
            assert "paid_amount" in c and c["paid_amount"] is None, c["id"]
            assert "advance_recovered" in c and c["advance_recovered"] is None, c["id"]
    c = claim(app, 17, user="victor")
    assert c["paid_amount"] == 1588.92 and c["approved_amount"] == 1588.92 and c["category"] == "lodging"


def test_finance_issues_advance():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/advances", {"employee": 7, "amount": 200, "purpose": "Booth supplies"},
                 user="fiona", now="2026-03-02T10:00:00")
    assert r.status == 201, r
    a = r.json
    assert a["id"] not in (1, 2, 3)
    expected = {"employee": 7, "amount": 200, "purpose": "Booth supplies", "issued_at": "2026-03-02T10:00:00",
                "issued_by": 1, "recovered": 0, "outstanding": 200}
    for k, v in expected.items():
        assert a[k] == v, (k, a.get(k))
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "advance_issued"
    assert msgs[-1]["payload"] == {"advance": a["id"], "employee": 7, "amount": 200}
    assert ids(app.get("/api/advances", user="rosa", now=NOW)) == [3, a["id"]]
    assert ids(app.get("/api/advances", user="nadia", now=NOW)) == [3, a["id"]]


def test_issue_advance_permissions_and_validation():
    app = fresh_app()
    before = outbox(app)
    body = {"employee": 7, "amount": 200, "purpose": "Booth supplies"}
    for user in ("sam", "omar", "rosa"):
        assert_error(app.post("/api/advances", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.post("/api/advances", {}, user=user, now=NOW), 403, "forbidden")
    for bad in ({"employee": 999}, {"employee": "rosa"}, {"employee": None}, {"amount": 0}, {"amount": -5},
                {"amount": 2000.01}, {"amount": "200"}, {"amount": True}, {"purpose": "  "}, {"purpose": None},
                {"recovered": 0}, {"issued_by": 1}, {"issued_at": NOW}, {"outstanding": 200}):
        assert_error(app.post("/api/advances", dict(body, **bad), user="fiona", now=NOW), 400, "validation")
    for missing in ("employee", "amount", "purpose"):
        b = {k: v for k, v in body.items() if k != missing}
        assert_error(app.post("/api/advances", b, user="fiona", now=NOW), 400, "validation")
    assert app.post("/api/advances", dict(body, amount=2000), user="fiona", now=NOW).status == 201
    assert len(outbox(app)) == len(before) + 1
    assert len(ids(app.get("/api/advances", user="fiona", now=NOW))) == 4


def test_advances_cannot_be_changed_or_deleted():
    app = fresh_app()
    for user in ("fiona", "victor", "omar"):
        assert_error(app.patch("/api/advances/1", {"purpose": "x"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/advances/1", user=user, now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/advances/99", {"purpose": "x"}, user="fiona", now=NOW), 404, "not_found")
    assert adv(app, 1)["purpose"] == "Conference travel float"


def test_payment_recovers_oldest_advances_first():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/claims/41/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    c = r.json
    assert c["status"] == "paid" and money(c["advance_recovered"]) == 550 and money(c["paid_amount"]) == 85.61
    assert c["approved_amount"] == 635.61 and c["amount"] == 635.61
    a1, a2 = adv(app, 1), adv(app, 2)
    assert money(a1["recovered"]) == 300 and money(a1["outstanding"]) == 0
    assert money(a2["recovered"]) == 250 and money(a2["outstanding"]) == 0
    assert adv(app, 3)["recovered"] == 0
    msgs = outbox(app)
    assert len(msgs) == before + 1
    assert msgs[-1]["channel"] == "payment"
    assert rounded(msgs[-1]["payload"]) == {"claim": 41, "employee": 11, "amount": 85.61, "advance_recovered": 550}
    # nothing left to recover for victor's next payment
    r = app.post("/api/claims/21/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["advance_recovered"] == 0 and money(r.json["paid_amount"]) == 400
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 21, "employee": 11, "amount": 400, "advance_recovered": 0}


def test_payment_fully_offset_and_partial_advance():
    app = fresh_app()
    # claim 21 approved for 400 (capped): 300 from advance 1, 100 from advance 2, nothing paid out
    r = app.post("/api/claims/21/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert money(r.json["advance_recovered"]) == 400 and money(r.json["paid_amount"]) == 0
    assert money(adv(app, 1)["outstanding"]) == 0
    a2 = adv(app, 2)
    assert money(a2["recovered"]) == 100 and money(a2["outstanding"]) == 150
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 21, "employee": 11, "amount": 0, "advance_recovered": 400}
    r = app.post("/api/claims/41/pay", {}, user="fiona", now=NOW)
    assert r.status == 200
    assert money(r.json["advance_recovered"]) == 150 and money(r.json["paid_amount"]) == 485.61
    assert money(adv(app, 2)["outstanding"]) == 0


def test_partial_approval_then_recovery_across_new_advance():
    app = fresh_app()
    new = app.post("/api/advances", {"employee": 7, "amount": 100, "purpose": "Taxi float"}, user="fiona", now=NOW)
    assert new.status == 201
    nid = new.json["id"]
    assert app.post("/api/claims/58/approve", {"amount": 700, "note": "Economy fare only"},
                    user="nadia", now=NOW).status == 200
    r = app.post("/api/claims/58/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert money(r.json["advance_recovered"]) == 600 and money(r.json["paid_amount"]) == 100
    assert money(adv(app, 3)["outstanding"]) == 0 and money(adv(app, nid)["outstanding"]) == 0
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 58, "employee": 7, "amount": 100, "advance_recovered": 600}
    r = app.get("/api/claims/58", user="rosa", now=NOW)
    assert r.status == 200 and money(r.json["paid_amount"]) == 100


def test_payment_without_advances():
    app = fresh_app()
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=NOW)
    assert r.status == 200, r
    assert r.json["advance_recovered"] == 0 and money(r.json["paid_amount"]) == 400
    assert rounded(outbox(app)[-1]["payload"]) == {"claim": 22, "employee": 8, "amount": 400, "advance_recovered": 0}


def test_failed_payments_change_nothing():
    app = fresh_app()
    before = snapshot(app)
    assert_error(app.post("/api/claims/41/pay", {}, user="omar", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/41/pay", {}, user="victor", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/claims/2/pay", {}, user="fiona", now=NOW), 409, "conflict")    # submitted
    assert_error(app.post("/api/claims/6/pay", {}, user="fiona", now=NOW), 409, "conflict")    # paid
    assert_error(app.post("/api/claims/79/pay", {}, user="fiona", now=NOW), 409, "conflict")   # draft
    assert snapshot(app) == before


def test_payment_fields_are_protected():
    app = fresh_app()
    base = {"amount": 50, "category": "travel", "description": "Taxi"}
    for extra in ({"paid_amount": 50}, {"advance_recovered": 0}):
        assert_error(app.post("/api/claims", dict(base, **extra), user="victor", now=NOW), 400, "validation")
        assert_error(app.patch("/api/claims/79", extra, user="victor", now=NOW), 400, "validation")
    assert claim(app, 79)["paid_amount"] is None


def test_ui_advances():
    app = fresh_app()
    assert parse_ui(app.get("/ui/advances", user="fiona", now=NOW).text).rows == [1, 2, 3]
    assert parse_ui(app.get("/ui/advances", user="omar", now=NOW).text).rows == [1, 2]
    assert parse_ui(app.get("/ui/advances", user="sam", now=NOW).text).rows == []
    ui = parse_ui(app.get("/ui/advances/3", user="rosa", now=NOW).text)
    assert ui.fields["purpose"] == "Trade fair float"
    assert {"employee", "amount", "issued_at", "issued_by", "recovered", "outstanding"} <= set(ui.fields)
    assert app.get("/ui/advances/3", user="victor", now=NOW).status == 403
    r = app.get("/ui/advances/new", user="fiona", now=NOW)
    assert r.status == 200, r
    ui = parse_ui(r.text)
    assert ui.creates == ["advances"] and {"employee", "amount", "purpose"} <= set(ui.inputs)
    for f in ("issued_at", "issued_by", "recovered", "outstanding"):
        assert f not in ui.inputs
    assert app.get("/ui/advances/new", user="victor", now=NOW).status == 403
    ui = parse_ui(app.get("/ui/claims/41", user="victor", now=NOW).text)
    assert {"paid_amount", "advance_recovered"} <= set(ui.fields)


def test_earlier_steps_still_work():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {"amount": 500}, user="omar", now=NOW)
    assert_error(r, 400, "validation")   # F03: partial approval needs a note
    assert app.post("/api/claims/2/approve", {"amount": 500, "note": "Dinner only"}, user="omar", now=NOW).status == 200
    r = app.post("/api/claims/2/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and money(r.json["advance_recovered"]) == 500 and money(r.json["paid_amount"]) == 0
    assert_error(app.post("/api/claims/20/submit", {}, user="sam", now=NOW), 409, "conflict")   # F01
    assert app.get("/api/category_policies/5", user="sam", now=NOW).json["category"] == "lodging"  # F02
