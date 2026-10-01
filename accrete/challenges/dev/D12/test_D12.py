"""D12 (expenses): itemised claims (`claim_lines`); claim amount becomes the total of its lines.

Seed facts used:
  80 claims; claim 20: sam (8), draft, 1553.42, "Keyboard #20"; claim 22: sam, approved, 1455.12
  claim 7: yusuf, 613.88, "Hotel night #7"; claim 39: uma, draft, 1748.0, "Hotel night #39"
  sam's claims: 20 22 42 48 54 61 73
  1553.42 + 46.58 = 1600.00 ; 1553.42 + 3446.58 = 5000.00 ; 1553.42 + 3446.59 = 5000.01
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
SAM_CLAIMS = [20, 22, 42, 48, 54, 61, 73]


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def claim(app, cid, user="fiona"):
    r = app.get(f"/api/claims/{cid}", user=user, now=NOW)
    assert r.status == 200, r
    return r.json


def add_line(app, cid, amount, description="Extra", user="sam"):
    r = app.post("/api/claim_lines", {"claim": cid, "amount": amount, "description": description}, user=user, now=NOW)
    assert r.status == 201, r
    return r.json


def test_each_existing_claim_has_one_line_with_same_id():
    app = fresh_app()
    lines = app.get("/api/claim_lines", user="fiona", now=NOW).json["items"]
    claims = app.get("/api/claims", user="fiona", now=NOW).json["items"]
    assert [l["id"] for l in lines] == list(range(1, 81))
    for l, c in zip(lines, claims):
        assert l["claim"] == c["id"] == l["id"]
        assert l["amount"] == c["amount"] and l["description"] == c["description"], (l, c)
    assert lines[6]["amount"] == 613.88 and lines[6]["description"] == "Hotel night #7"
    assert claim(app, 39)["amount"] == 1748.0 and claim(app, 20)["amount"] == 1553.42


def test_adding_line_updates_claim_total():
    app = fresh_app()
    l = add_line(app, 20, 46.58, "Mouse")
    assert l["claim"] == 20 and l["amount"] == 46.58 and l["description"] == "Mouse" and l["id"] > 80
    c = claim(app, 20, user="sam")
    assert c["amount"] == 1600.0 and c["description"] == "Keyboard #20" and c["status"] == "draft"
    assert ids(app.get("/api/claim_lines?claim=20", user="sam", now=NOW)) == [20, l["id"]]


def test_claim_total_may_not_exceed_5000():
    app = fresh_app()
    assert_error(app.post("/api/claim_lines", {"claim": 20, "amount": 3446.59, "description": "x"}, user="sam", now=NOW),
                 400, "validation")
    assert claim(app, 20)["amount"] == 1553.42
    l = add_line(app, 20, 3446.58)
    assert claim(app, 20)["amount"] == 5000.0
    assert_error(app.patch(f"/api/claim_lines/{l['id']}", {"amount": 3446.59}, user="sam", now=NOW), 400, "validation")
    assert claim(app, 20)["amount"] == 5000.0


def test_line_validation():
    app = fresh_app()
    for body in ({"claim": 20, "amount": 0, "description": "x"}, {"claim": 20, "amount": -1, "description": "x"},
                 {"claim": 20, "amount": 10}, {"claim": 20, "description": "x"},
                 {"amount": 10, "description": "x"}, {"claim": 999, "amount": 10, "description": "x"}):
        assert_error(app.post("/api/claim_lines", body, user="sam", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claim_lines/20", {"claim": 54}, user="sam", now=NOW), 400, "validation")
    assert_error(app.patch("/api/claim_lines/20", {"amount": 0}, user="sam", now=NOW), 400, "validation")
    assert ids(app.get("/api/claim_lines?claim=20", user="sam", now=NOW)) == [20]
    assert ids(app.get("/api/claim_lines?claim=54", user="sam", now=NOW)) == [54]


def test_only_owner_edits_lines():
    app = fresh_app()
    for user in ("omar", "fiona", "priya"):
        assert_error(app.post("/api/claim_lines", {"claim": 20, "amount": 5, "description": "x"}, user=user, now=NOW),
                     403, "forbidden")
        assert_error(app.patch("/api/claim_lines/20", {"amount": 5}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete("/api/claim_lines/20", user=user, now=NOW), 403, "forbidden")
    assert claim(app, 20)["amount"] == 1553.42


def test_lines_only_editable_on_draft_claims():
    app = fresh_app()
    assert_error(app.post("/api/claim_lines", {"claim": 22, "amount": 5, "description": "x"}, user="sam", now=NOW),
                 409, "conflict")
    assert_error(app.patch("/api/claim_lines/22", {"amount": 5}, user="sam", now=NOW), 409, "conflict")
    assert_error(app.delete("/api/claim_lines/22", user="sam", now=NOW), 409, "conflict")
    l = add_line(app, 20, 10)
    assert app.post("/api/claims/20/submit", {}, user="sam", now=NOW).status == 200
    assert_error(app.patch(f"/api/claim_lines/{l['id']}", {"amount": 20}, user="sam", now=NOW), 409, "conflict")
    assert claim(app, 22)["amount"] == 1455.12 and claim(app, 20)["amount"] == 1563.42


def test_patch_and_delete_lines():
    app = fresh_app()
    l = add_line(app, 20, 46.58)
    r = app.patch(f"/api/claim_lines/{l['id']}", {"amount": 100, "description": "Dock"}, user="sam", now=NOW)
    assert r.status == 200 and r.json["amount"] == 100 and r.json["description"] == "Dock"
    assert claim(app, 20)["amount"] == 1653.42
    assert app.delete("/api/claim_lines/20", user="sam", now=NOW).status == 204
    assert claim(app, 20)["amount"] == 100
    assert_error(app.delete(f"/api/claim_lines/{l['id']}", user="sam", now=NOW), 409, "conflict")  # last line
    assert ids(app.get("/api/claim_lines?claim=20", user="sam", now=NOW)) == [l["id"]]


def test_patching_claim_amount_single_vs_multiple_lines():
    app = fresh_app()
    r = app.patch("/api/claims/20", {"amount": 200}, user="sam", now=NOW)
    assert r.status == 200 and r.json["amount"] == 200
    assert app.get("/api/claim_lines/20", user="sam", now=NOW).json["amount"] == 200
    assert_error(app.patch("/api/claims/20", {"amount": 5000.01}, user="sam", now=NOW), 400, "validation")
    add_line(app, 20, 50)
    assert_error(app.patch("/api/claims/20", {"amount": 300}, user="sam", now=NOW), 409, "conflict")
    assert claim(app, 20)["amount"] == 250
    r = app.patch("/api/claims/20", {"description": "Desk setup", "category": "equipment"}, user="sam", now=NOW)
    assert r.status == 200 and r.json["amount"] == 250 and r.json["description"] == "Desk setup"


def test_line_read_permissions():
    app = fresh_app()
    assert ids(app.get("/api/claim_lines", user="sam", now=NOW)) == SAM_CLAIMS
    assert_error(app.get("/api/claim_lines/2", user="sam", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/claim_lines?claim=2", user="sam", now=NOW)) == []
    assert ids(app.get("/api/claim_lines?claim=20", user="omar", now=NOW)) == [20]
    assert_error(app.get("/api/claim_lines/20", user="marco", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/claim_lines/999", user="fiona", now=NOW), 404, "not_found")


def test_creating_claim_creates_first_line():
    app = fresh_app()
    r = app.post("/api/claims", {"amount": 120.5, "category": "meals", "description": "Client dinner"}, user="priya", now=NOW)
    assert r.status == 201 and r.json["amount"] == 120.5
    lines = app.get(f"/api/claim_lines?claim={r.json['id']}", user="priya", now=NOW).json["items"]
    assert len(lines) == 1
    assert lines[0]["amount"] == 120.5 and lines[0]["description"] == "Client dinner" and lines[0]["id"] > 80
    for bad in (0, 5000.01):
        assert_error(app.post("/api/claims", {"amount": bad, "category": "meals", "description": "d"}, user="priya", now=NOW),
                     400, "validation")


def test_payment_uses_total_of_lines():
    app = fresh_app()
    c = app.post("/api/claims", {"amount": 100, "category": "travel", "description": "Bus"}, user="rosa", now=NOW).json
    add_line(app, c["id"], 50.25, "Taxi", user="rosa")
    assert app.post(f"/api/claims/{c['id']}/submit", {}, user="rosa", now=NOW).status == 200
    assert app.post(f"/api/claims/{c['id']}/approve", {}, user="nadia", now=NOW).status == 200
    assert app.post(f"/api/claims/{c['id']}/pay", {}, user="fiona", now=NOW).status == 200
    msgs = app.get("/api/_outbox", user="fiona", now=NOW).json["items"]
    assert msgs[-1]["channel"] == "payment"
    assert msgs[-1]["payload"] == {"claim": c["id"], "employee": 7, "amount": 150.25}


def test_deleting_draft_claim_deletes_its_lines():
    app = fresh_app()
    l = add_line(app, 20, 10)
    assert app.delete("/api/claims/20", user="sam", now=NOW).status == 204
    assert_error(app.get("/api/claim_lines/20", user="fiona", now=NOW), 404, "not_found")
    assert_error(app.get(f"/api/claim_lines/{l['id']}", user="fiona", now=NOW), 404, "not_found")
    assert 20 not in ids(app.get("/api/claim_lines", user="fiona", now=NOW))


def test_ui_lines():
    app = fresh_app()
    assert parse_ui(app.get("/ui/claim_lines", user="sam", now=NOW).text).rows == SAM_CLAIMS
    r = app.get("/ui/claim_lines/new", user="sam", now=NOW)
    assert r.status == 200 and {"claim", "amount", "description"} <= set(parse_ui(r.text).inputs)
