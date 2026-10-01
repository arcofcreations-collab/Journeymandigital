"""Hidden acceptance tests for E14 (library, after E08): lost copies.

State: E08 applied (copy i = book i, plus copies 41 (book 1) and 42 (book 22)); E14 migration marks loans 46
(book/copy 4) and 50 (book/copy 16), both of jo (10), lost at 2026-02-28T10:00:00, and copies 4 and 16 lost.
Seed facts: unreturned loans 46-60; overdue at 2026-03-01 were 46-50; jo's open loans 46 50 57; loan 52 = chen's
book 22 (copy 22); loan 55 = ivan's book 1 (copy 1).
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T2 = "2026-03-02T09:30:00"
LOST_AT = "2026-02-28T10:00:00"


def assert_error(r, status, code):
    assert r.status == status, r
    assert isinstance(r.json, dict) and r.json.get("error") == code, r
    assert isinstance(r.json.get("message"), str) and isinstance(r.json.get("fields"), dict), r


def ids(r):
    assert r.status == 200, r
    return [x["id"] for x in r.json["items"]]


def outbox(app):
    r = app.get("/api/_outbox", user="ada", now=NOW)
    assert r.status == 200, r
    return r.json["items"]


def get(app, path, user="ada", now=NOW):
    r = app.get(path, user=user, now=now)
    assert r.status == 200, r
    return r.json


def snapshot(app):
    return (get(app, "/api/loans")["items"], get(app, "/api/copies")["items"], get(app, "/api/books")["items"],
            outbox(app))


def test_lost_loans_and_copies_migrated():
    app = fresh_app()
    loans = {l["id"]: l for l in get(app, "/api/loans")["items"]}
    assert sorted(loans) == list(range(1, 61))
    for lid, l in loans.items():
        assert l["lost_at"] == (LOST_AT if lid in (46, 50) else None), l
        assert l["copy"] == l["book"]
    assert loans[46]["returned_at"] is None
    copies = {c["id"]: c for c in get(app, "/api/copies", user="chen")["items"]}
    assert sorted(copies) == list(range(1, 43))
    for cid, c in copies.items():
        assert c["lost"] is (cid in (4, 16)), c
    assert copies[4]["status"] == "lost" and copies[16]["status"] == "lost"
    assert copies[41]["status"] == "available" and copies[1]["status"] == "on_loan"
    for bid in (4, 16):
        b = get(app, f"/api/books/{bid}", user="chen")
        assert b["status"] == "unavailable" and b["available_copies"] == 0
    assert get(app, "/api/books/1", user="chen")["status"] == "available"
    assert ids(app.get("/api/copies?lost=true", user="chen", now=NOW)) == [4, 16]


def test_lost_loans_are_closed():
    app = fresh_app()
    items = get(app, "/api/loans")["items"]
    assert [l["id"] for l in items if l["overdue"]] == [47, 48, 49]
    assert_error(app.post("/api/loans/46/return", {}, user="ben", now=NOW), 409, "conflict")
    assert_error(app.post("/api/loans/50/return", {}, user="jo", now=NOW), 409, "conflict")
    # jo now has a single open loan (57)
    assert app.post("/api/books/3/borrow", {}, user="jo", now=NOW).status == 200
    assert app.post("/api/books/13/borrow", {}, user="jo", now=NOW).status == 200
    assert_error(app.post("/api/books/14/borrow", {}, user="jo", now=NOW), 409, "conflict")
    assert_error(app.post("/api/books/4/borrow", {}, user="chen", now=NOW), 409, "conflict")   # only copy lost


def test_declare_lost():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/loans/52/declare_lost", {}, user="ada", now=T2)
    assert r.status == 200, r
    l = r.json
    assert (l["id"], l["lost_at"], l["returned_at"], l["overdue"], l["copy"]) == (52, T2, None, False, 22)
    assert get(app, "/api/loans/52", user="chen", now="2026-03-20T00:00:00")["overdue"] is False
    c = get(app, "/api/copies/22")
    assert c["lost"] is True and c["status"] == "lost"
    b = get(app, "/api/books/22")
    assert b["status"] == "available" and b["available_copies"] == 1     # copy 42 remains
    msgs = outbox(app)[before:]
    assert [m["channel"] for m in msgs] == ["copy_lost"]
    assert msgs[0]["payload"] == {"loan": 52, "copy": 22, "book": 22, "member": 3}
    assert_error(app.post("/api/loans/52/return", {}, user="chen", now=T2), 409, "conflict")
    # book 1: copy 1 lost, copy 41 still lendable
    assert app.post("/api/loans/55/declare_lost", {}, user="ben", now=T2).status == 200
    assert get(app, "/api/books/1")["status"] == "available"
    assert app.post("/api/books/1/borrow", {}, user="chen", now=T2).status == 200
    assert get(app, "/api/loans?book=1")["items"][-1]["copy"] == 41
    b = get(app, "/api/books/1")
    assert b["status"] == "on_loan" and b["available_copies"] == 0


def test_declare_lost_refusals_change_nothing():
    app = fresh_app()
    snap = snapshot(app)
    assert_error(app.post("/api/loans/52/declare_lost", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/46/declare_lost", {}, user="jo", now=NOW), 403, "forbidden")   # 403 before 409
    assert_error(app.post("/api/loans/1/declare_lost", {}, user="ada", now=NOW), 409, "conflict")    # returned
    assert_error(app.post("/api/loans/46/declare_lost", {}, user="ada", now=NOW), 409, "conflict")   # already lost
    assert_error(app.post("/api/loans/999/declare_lost", {}, user="ada", now=NOW), 404, "not_found")
    assert snapshot(app) == snap


def test_found_copy():
    app = fresh_app()
    assert_error(app.post("/api/copies/4/found", {}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/copies/3/found", {}, user="ada", now=NOW), 409, "conflict")
    assert_error(app.post("/api/copies/3/found", {}, user="chen", now=NOW), 403, "forbidden")        # 403 before 409
    r = app.post("/api/copies/4/found", {}, user="ada", now=NOW)
    assert r.status == 200, r
    assert r.json["id"] == 4 and r.json["lost"] is False and r.json["status"] == "available"
    assert get(app, "/api/books/4")["status"] == "available"
    assert get(app, "/api/loans/46")["lost_at"] == LOST_AT
    assert_error(app.post("/api/loans/46/return", {}, user="ada", now=NOW), 409, "conflict")
    assert app.post("/api/books/4/borrow", {"member": 4}, user="ada", now=NOW).status == 200
    assert get(app, "/api/loans?book=4")["items"][-1]["copy"] == 4
    assert_error(app.post("/api/copies/4/found", {}, user="ada", now=NOW), 409, "conflict")


def test_copies_and_loans_still_protected():
    app = fresh_app()
    assert_error(app.delete("/api/copies/4", user="ada", now=NOW), 409, "conflict")
    assert_error(app.patch("/api/copies/4", {"lost": False}, user="ada", now=NOW), 400, "validation")
    assert_error(app.post("/api/copies", {"book": 4, "barcode": "C0004-2", "lost": False}, user="ada", now=NOW),
                 400, "validation")
    assert_error(app.patch("/api/loans/52", {"lost_at": NOW}, user="ada", now=NOW), 403, "forbidden")
    r = app.post("/api/copies", {"book": 4, "barcode": "C0004-2"}, user="ada", now=NOW)
    assert r.status == 201 and r.json["lost"] is False and r.json["status"] == "available"
    assert get(app, "/api/books/4")["available_copies"] == 1


def test_ui_lost_flow():
    app = fresh_app()
    acts = parse_ui(app.get("/ui/loans/52", user="ada", now=NOW).text).actions
    assert "declare_lost" in acts and "return" in acts
    acts = parse_ui(app.get("/ui/loans/52", user="chen", now=NOW).text).actions
    assert "return" in acts and "declare_lost" not in acts
    acts = parse_ui(app.get("/ui/loans/46", user="ada", now=NOW).text).actions
    assert "return" not in acts and "declare_lost" not in acts
    ui = parse_ui(app.get("/ui/loans/46", user="jo", now=NOW).text)
    assert ui.fields["lost_at"] == LOST_AT
    assert "found" in parse_ui(app.get("/ui/copies/4", user="ada", now=NOW).text).actions
    assert "found" not in parse_ui(app.get("/ui/copies/4", user="chen", now=NOW).text).actions
    assert "found" not in parse_ui(app.get("/ui/copies/3", user="ada", now=NOW).text).actions
    ui = parse_ui(app.get("/ui/books/4", user="chen", now=NOW).text)
    assert ui.fields["status"] == "unavailable" and "borrow" not in ui.actions
