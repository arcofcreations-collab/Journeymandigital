"""D10 (expenses): claim history (`claim_events`) with backfill of existing claims.

Seed facts (computed from expenses_seed.json):
  68 claims have submitted_at, 50 have decided_at (44 approved/paid + 6 rejected), 21 are paid
  -> 139 backfilled events: 68 submit, 44 approve, 6 reject, 21 pay
  reject events by omar (4): claims 7, 14, 23, 60
  claim 6 : victor (11) paid; submitted 2026-02-09T13:00:00; decided 2026-02-11T11:00:00 by 4
  claim 7 : yusuf (14) rejected; submitted 2026-01-28T11:00:00; decided 2026-01-30T09:00:00 by 4
  claim 2 : victor submitted 2026-01-25T12:00:00 ; claim 20: sam draft
  events readable by sam (claims 20,22,42,48,54,61,73): 22 -> 2, 42 -> 3, 48 -> 3, 61 -> 2 = 10
  events readable by omar (his reports' + his own claims): 62
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"
T3 = "2026-03-03T10:00:00"
T4 = "2026-03-04T11:00:00"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def events(app, query="", user="fiona"):
    r = app.get("/api/claim_events" + query, user=user, now=NOW)
    assert r.status == 200, r
    items = r.json["items"]
    assert [e["id"] for e in items] == sorted(e["id"] for e in items)
    return items


def shape(e):
    return (e["claim"], e["action"], e["actor"], e["at"], e["from_status"], e["to_status"])


def test_backfill_counts():
    app = fresh_app()
    allev = events(app)
    assert len(allev) == 139
    assert len(events(app, "?action=submit")) == 68
    assert len(events(app, "?action=approve")) == 44
    assert len(events(app, "?action=reject")) == 6
    assert len(events(app, "?action=pay")) == 21
    assert [e["claim"] for e in events(app, "?actor=4&action=reject")] == [7, 14, 23, 60]


def test_backfill_for_paid_claim():
    app = fresh_app()
    evs = events(app, "?claim=6")
    assert [shape(e) for e in evs] == [
        (6, "submit", 11, "2026-02-09T13:00:00", "draft", "submitted"),
        (6, "approve", 4, "2026-02-11T11:00:00", "submitted", "approved"),
        (6, "pay", None, None, "approved", "paid"),
    ]


def test_backfill_for_rejected_submitted_and_draft_claims():
    app = fresh_app()
    assert [shape(e) for e in events(app, "?claim=7")] == [
        (7, "submit", 14, "2026-01-28T11:00:00", "draft", "submitted"),
        (7, "reject", 4, "2026-01-30T09:00:00", "submitted", "rejected"),
    ]
    assert [shape(e) for e in events(app, "?claim=2")] == [
        (2, "submit", 11, "2026-01-25T12:00:00", "draft", "submitted"),
    ]
    assert events(app, "?claim=20") == []


def test_actions_record_events_after_backfill():
    app = fresh_app()
    max_backfill = max(e["id"] for e in events(app))
    assert app.post("/api/claims/20/submit", {}, user="sam", now=T2).status == 200
    assert app.post("/api/claims/20/approve", {}, user="omar", now=T3).status == 200
    assert app.post("/api/claims/20/pay", {}, user="fiona", now=T4).status == 200
    evs = events(app, "?claim=20")
    assert [shape(e) for e in evs] == [
        (20, "submit", 8, T2, "draft", "submitted"),
        (20, "approve", 4, T3, "submitted", "approved"),
        (20, "pay", 1, T4, "approved", "paid"),
    ]
    assert all(e["id"] > max_backfill for e in evs)
    assert len(events(app)) == 142


def test_reject_records_event():
    app = fresh_app()
    assert app.post("/api/claims/58/reject", {"reason": "Duplicate"}, user="nadia", now=T2).status == 200
    evs = events(app, "?claim=58")
    assert [shape(e) for e in evs][-1] == (58, "reject", 3, T2, "submitted", "rejected")
    assert len(evs) == 2


def test_failed_actions_record_nothing():
    app = fresh_app()
    n = len(events(app))
    app.post("/api/claims/2/approve", {}, user="marco", now=NOW)          # 403
    app.post("/api/claims/22/approve", {}, user="omar", now=NOW)          # 409
    app.post("/api/claims/2/reject", {}, user="omar", now=NOW)            # 400
    app.post("/api/claims/2/pay", {}, user="fiona", now=NOW)              # 409
    app.post("/api/claims/22/submit", {}, user="sam", now=NOW)            # 409
    app.post("/api/claims/999/submit", {}, user="sam", now=NOW)           # 404
    assert len(events(app)) == n


def test_draft_edits_record_nothing():
    app = fresh_app()
    n = len(events(app))
    r = app.post("/api/claims", {"amount": 10, "category": "meals", "description": "Coffee"}, user="sam", now=NOW)
    assert r.status == 201
    assert app.patch(f"/api/claims/{r.json['id']}", {"amount": 12}, user="sam", now=NOW).status == 200
    assert app.delete("/api/claims/54", user="sam", now=NOW).status == 204
    assert len(events(app)) == n


def test_events_follow_claim_read_permission():
    app = fresh_app()
    sam = events(app, user="sam")
    assert len(sam) == 10
    assert sorted({e["claim"] for e in sam}) == [22, 42, 48, 61]
    assert events(app, "?claim=2", user="sam") == []
    assert len(events(app, user="omar")) == 62
    ev2 = events(app, "?claim=2")[0]["id"]
    assert_error(app.get(f"/api/claim_events/{ev2}", user="sam", now=NOW), 403, "forbidden")
    r = app.get(f"/api/claim_events/{ev2}", user="omar", now=NOW)
    assert r.status == 200 and r.json["claim"] == 2
    assert_error(app.get("/api/claim_events/99999", user="fiona", now=NOW), 404, "not_found")


def test_events_are_read_only():
    app = fresh_app()
    ev = events(app, "?claim=6")[0]["id"]
    body = {"claim": 20, "action": "approve", "actor": 4, "at": NOW, "from_status": "submitted", "to_status": "approved"}
    for user in ("fiona", "sam", "omar"):
        assert_error(app.post("/api/claim_events", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch(f"/api/claim_events/{ev}", {"actor": 2}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete(f"/api/claim_events/{ev}", user=user, now=NOW), 403, "forbidden")
    assert len(events(app)) == 139
    assert events(app, "?claim=6")[0]["actor"] == 11


def test_ui_claim_events_list():
    app = fresh_app()
    r = app.get("/ui/claim_events", user="sam", now=NOW)
    assert r.status == 200, r
    assert parse_ui(r.text).rows == [e["id"] for e in events(app, user="sam")]
    assert app.get("/ui/claim_events/new", user="fiona", now=NOW).status == 403


def test_claim_actions_unchanged():
    app = fresh_app()
    r = app.post("/api/claims/2/approve", {}, user="omar", now=T2)
    assert r.status == 200 and r.json["status"] == "approved" and r.json["decided_by"] == 4
    r = app.post("/api/claims/22/pay", {}, user="fiona", now=T2)
    assert r.status == 200 and r.json["status"] == "paid"
    msgs = app.get("/api/_outbox", user="fiona", now=NOW).json["items"]
    assert msgs[-1]["channel"] == "payment" and msgs[-1]["payload"] == {"claim": 22, "employee": 8, "amount": 1455.12}
