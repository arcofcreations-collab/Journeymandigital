"""Claim actions: submit, approve, reject, pay; permissions, states and the outbox."""

NOW = "2026-03-02T09:30:00"


def test_submit(app):
    assert app.post("/api/claims/1/submit", {}, user="marco").status == 403  # not the owner
    r = app.post("/api/claims/1/submit", {}, user="wen", now=NOW)
    assert r.status == 200 and r.json["status"] == "submitted" and r.json["submitted_at"] == NOW
    assert app.post("/api/claims/1/submit", {}, user="wen").status == 409


def test_approve(app):
    assert app.post("/api/claims/2/approve", {}, user="victor").status == 403  # own claim
    assert app.post("/api/claims/2/approve", {}, user="marco").status == 403  # indirect manager
    assert app.post("/api/claims/2/approve", {}, user="fiona").status == 403  # finance
    r = app.post("/api/claims/2/approve", {}, user="omar", now=NOW)
    assert r.status == 200
    assert (r.json["status"], r.json["decided_at"], r.json["decided_by"]) == ("approved", NOW, 4)
    assert app.post("/api/claims/2/approve", {}, user="omar").status == 409
    assert app.post("/api/claims/2/reject", {"reason": "no"}, user="omar").status == 409


def test_approve_requires_submitted(app):
    assert app.post("/api/claims/1/approve", {}, user="marco").status == 409  # draft
    assert app.post("/api/claims/4/approve", {}, user="nadia").status == 409  # already approved


def test_reject(app):
    assert app.post("/api/claims/3/reject", {"reason": "x"}, user="omar").status == 403
    assert app.post("/api/claims/3/reject", {}, user="marco").status == 400
    assert app.post("/api/claims/3/reject", {"reason": "   "}, user="marco").status == 400
    assert app.post("/api/claims/1/reject", {}, user="marco").status == 409  # 409 beats 400
    r = app.post("/api/claims/3/reject", {"reason": "Missing receipt"}, user="marco", now=NOW)
    assert r.status == 200
    assert r.json["status"] == "rejected" and r.json["rejection_reason"] == "Missing receipt"
    assert r.json["decided_by"] == 2 and r.json["decided_at"] == NOW


def test_pay(app):
    assert app.post("/api/claims/4/pay", {}, user="nadia").status == 403
    assert app.post("/api/claims/2/pay", {}, user="fiona").status == 409  # submitted
    r = app.post("/api/claims/4/pay", {}, user="fiona", now=NOW)
    assert r.status == 200 and r.json["status"] == "paid"
    assert r.json["decided_by"] == 3  # unchanged by payment
    assert app.post("/api/claims/4/pay", {}, user="fiona").status == 409
    assert app.get("/api/_outbox", user="uma").json["items"] == [
        {"id": 1, "channel": "payment", "payload": {"claim": 4, "employee": 10, "amount": 558.67}, "created_at": NOW}
    ]


def test_full_lifecycle(app):
    claim = app.post("/api/claims", {"amount": 120, "category": "travel", "description": "Train"}, user="sam").json
    path = f"/api/claims/{claim['id']}"
    assert app.post(f"{path}/submit", {}, user="sam").status == 200
    assert app.post(f"{path}/approve", {}, user="omar").status == 200
    assert app.post(f"{path}/pay", {}, user="fiona").status == 200
    assert app.get(path, user="sam").json["status"] == "paid"
    payload = app.get("/api/_outbox?channel=payment", user="sam").json["items"][-1]["payload"]
    assert payload == {"claim": claim["id"], "employee": 8, "amount": 120}


def test_failed_action_leaves_no_trace(app):
    app.post("/api/claims/2/pay", {}, user="fiona")
    assert app.get("/api/_outbox", user="fiona").json["items"] == []
    assert app.get("/api/claims/2", user="fiona").json["status"] == "submitted"
