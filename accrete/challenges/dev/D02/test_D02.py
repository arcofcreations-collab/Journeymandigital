"""D02 (library): holds / reservations queue.

Seed facts used:
  book 1 on loan via loan 55 (ivan, id 9, due 2026-03-04)
  book 22 on loan via loan 52 (chen, id 3)
  book 3 available, no loans
  hana (8) holds 3 open loans: 51 (book 23), 53, 58
  lena (12) inactive
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"
T_EARLY = "2026-03-01T09:00:00"
T_RET = "2026-03-02T10:00:00"
T_LATER = "2026-03-03T11:00:00"


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


def holds(app, query="", user="ada", now=NOW):
    r = app.get("/api/holds" + query, user=user, now=now)
    assert r.status == 200, r
    return r.json["items"]


def new_msgs(app, before, channel):
    return [m for m in outbox(app)[before:] if m["channel"] == channel]


def place(app, book, user, now=NOW, body=None):
    r = app.post(f"/api/books/{book}/hold", body or {}, user=user, now=now)
    assert r.status == 200, r
    return r


def test_seed_has_no_holds_and_no_reserved_books():
    app = fresh_app()
    assert holds(app) == []
    statuses = {b["status"] for b in app.get("/api/books", user="chen", now=NOW).json["items"]}
    assert statuses == {"on_loan", "available"}


def test_member_places_hold_on_loaned_book():
    app = fresh_app()
    before = len(outbox(app))
    r = place(app, 1, "chen")
    assert r.json["id"] == 1 and r.json["status"] == "on_loan"
    hs = holds(app, user="chen")
    assert len(hs) == 1
    h = hs[0]
    assert h["book"] == 1 and h["member"] == 3 and h["status"] == "waiting"
    assert h["placed_at"] == NOW and h["ready_at"] is None
    assert len(outbox(app)) == before  # placing a hold emits nothing


def test_hold_conflicts_and_permissions():
    app = fresh_app()
    assert_error(app.post("/api/books/3/hold", {}, user="chen", now=NOW), 409, "conflict")       # available
    assert_error(app.post("/api/books/22/hold", {}, user="chen", now=NOW), 409, "conflict")      # own loan
    assert_error(app.post("/api/books/1/hold", {"member": 12}, user="ada", now=NOW), 409, "conflict")  # inactive
    assert_error(app.post("/api/books/1/hold", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/999/hold", {}, user="chen", now=NOW), 404, "not_found")
    place(app, 1, "chen")
    assert_error(app.post("/api/books/1/hold", {}, user="chen", now=NOW), 409, "conflict")       # duplicate
    assert len(holds(app)) == 1


def test_librarian_places_hold_for_member():
    app = fresh_app()
    place(app, 1, "ada", body={"member": 4})
    hs = holds(app, "?book=1")
    assert len(hs) == 1 and hs[0]["member"] == 4 and hs[0]["status"] == "waiting"
    assert [h["member"] for h in holds(app, user="dara")] == [4]


def test_return_makes_earliest_hold_ready():
    app = fresh_app()
    place(app, 1, "chen", now=NOW)        # placed later in time, lower id
    place(app, 1, "dara", now=T_EARLY)    # placed earlier in time, higher id
    before = len(outbox(app))
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    hs = {h["member"]: h for h in holds(app, "?book=1")}
    assert hs[4]["status"] == "ready" and hs[4]["ready_at"] == T_RET
    assert hs[3]["status"] == "waiting" and hs[3]["ready_at"] is None
    assert app.get("/api/books/1", user="eli", now=T_RET).json["status"] == "reserved"
    msgs = new_msgs(app, before, "hold_ready")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == {"hold": hs[4]["id"], "book": 1, "member": 4}


def test_reserved_book_only_borrowable_by_ready_member():
    app = fresh_app()
    place(app, 1, "dara")
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    assert_error(app.post("/api/books/1/borrow", {}, user="chen", now=T_RET), 409, "conflict")
    assert_error(app.post("/api/books/1/borrow", {"member": 3}, user="ada", now=T_RET), 409, "conflict")
    r = app.post("/api/books/1/borrow", {}, user="dara", now=T_LATER)
    assert r.status == 200, r
    assert r.json["status"] == "on_loan"
    h = holds(app, "?book=1")[0]
    assert h["status"] == "fulfilled"
    open_loans = [l for l in app.get("/api/loans?book=1", user="ada", now=T_LATER).json["items"]
                  if l["returned_at"] is None]
    assert len(open_loans) == 1 and open_loans[0]["member"] == 4
    assert open_loans[0]["borrowed_at"] == T_LATER and open_loans[0]["due_at"] == "2026-03-17"


def test_ready_member_at_loan_limit_keeps_hold():
    app = fresh_app()
    place(app, 1, "hana")
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    assert_error(app.post("/api/books/1/borrow", {}, user="hana", now=T_RET), 409, "conflict")
    h = holds(app, "?book=1")[0]
    assert h["status"] == "ready" and h["member"] == 8
    assert app.get("/api/books/1", user="ada", now=T_RET).json["status"] == "reserved"
    assert app.post("/api/loans/51/return", {}, user="hana", now=T_RET).status == 200
    assert app.post("/api/books/1/borrow", {}, user="hana", now=T_RET).status == 200
    assert holds(app, "?book=1")[0]["status"] == "fulfilled"


def test_cancel_ready_hold_passes_to_next_then_frees_book():
    app = fresh_app()
    place(app, 1, "dara", now=T_EARLY)
    place(app, 1, "chen", now=NOW)
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    by_member = {h["member"]: h for h in holds(app, "?book=1")}
    n = len(outbox(app))
    r = app.post(f"/api/holds/{by_member[4]['id']}/cancel", {}, user="dara", now=T_LATER)
    assert r.status == 200, r
    assert r.json["status"] == "cancelled"
    by_member = {h["member"]: h for h in holds(app, "?book=1")}
    assert by_member[3]["status"] == "ready" and by_member[3]["ready_at"] == T_LATER
    msgs = new_msgs(app, n, "hold_ready")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == {"hold": by_member[3]["id"], "book": 1, "member": 3}
    assert app.get("/api/books/1", user="ada", now=T_LATER).json["status"] == "reserved"
    assert app.post(f"/api/holds/{by_member[3]['id']}/cancel", {}, user="chen", now=T_LATER).status == 200
    assert app.get("/api/books/1", user="ada", now=T_LATER).json["status"] == "available"
    assert len(new_msgs(app, n, "hold_ready")) == 1  # no further hold became ready
    assert app.post("/api/books/1/borrow", {}, user="eli", now=T_LATER).status == 200


def test_cancel_permissions_and_state():
    app = fresh_app()
    place(app, 1, "dara")
    hid = holds(app)[0]["id"]
    assert_error(app.post(f"/api/holds/{hid}/cancel", {}, user="chen", now=NOW), 403, "forbidden")
    assert app.post(f"/api/holds/{hid}/cancel", {}, user="ben", now=NOW).status == 200
    assert_error(app.post(f"/api/holds/{hid}/cancel", {}, user="dara", now=NOW), 409, "conflict")
    assert_error(app.post(f"/api/holds/{hid}/cancel", {}, user="chen", now=NOW), 403, "forbidden")  # 403 before 409
    # a cancelled waiting hold does not get served on return
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    assert app.get("/api/books/1", user="ada", now=T_RET).json["status"] == "available"
    # fulfilled hold cannot be cancelled
    place(app, 22, "dara", now=T_RET)
    assert app.post("/api/loans/52/return", {}, user="chen", now=T_RET).status == 200
    assert app.post("/api/books/22/borrow", {}, user="dara", now=T_RET).status == 200
    h = holds(app, "?book=22")[0]
    assert h["status"] == "fulfilled"
    assert_error(app.post(f"/api/holds/{h['id']}/cancel", {}, user="dara", now=T_RET), 409, "conflict")


def test_hold_read_permissions():
    app = fresh_app()
    place(app, 1, "dara")
    place(app, 1, "chen")
    place(app, 22, "eli")
    dara_hold = holds(app, "?member=4")[0]["id"]
    assert [h["member"] for h in holds(app, user="chen")] == [3]
    assert holds(app, "?book=22", user="chen") == []
    assert_error(app.get(f"/api/holds/{dara_hold}", user="chen", now=NOW), 403, "forbidden")
    assert app.get(f"/api/holds/{dara_hold}", user="dara", now=NOW).status == 200
    assert len(holds(app, user="ada")) == 3
    assert [h["member"] for h in holds(app, "?book=1", user="ben")] == [4, 3]


def test_holds_cannot_be_written_directly():
    app = fresh_app()
    place(app, 1, "chen")
    hid = holds(app)[0]["id"]
    body = {"book": 22, "member": 3, "placed_at": NOW, "status": "waiting"}
    for user in ("ada", "chen"):
        assert_error(app.post("/api/holds", body, user=user, now=NOW), 403, "forbidden")
        assert_error(app.patch(f"/api/holds/{hid}", {"status": "ready"}, user=user, now=NOW), 403, "forbidden")
        assert_error(app.delete(f"/api/holds/{hid}", user=user, now=NOW), 403, "forbidden")
    assert holds(app)[0]["status"] == "waiting"
    assert app.get("/ui/holds/new", user="ada", now=NOW).status == 403


def test_return_without_holds_unchanged():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/loans/52/return", {}, user="chen", now=T_RET)
    assert r.status == 200 and r.json["returned_at"] == T_RET
    assert app.get("/api/books/22", user="chen", now=T_RET).json["status"] == "available"
    assert new_msgs(app, before, "hold_ready") == []
    assert app.post("/api/books/22/borrow", {}, user="dara", now=T_RET).status == 200


def test_ui_hold_and_borrow_forms():
    app = fresh_app()
    ui = parse_ui(app.get("/ui/books/1", user="chen", now=NOW).text)
    assert "hold" in ui.actions and "borrow" not in ui.actions
    ui = parse_ui(app.get("/ui/books/3", user="chen", now=NOW).text)
    assert "borrow" in ui.actions and "hold" not in ui.actions
    place(app, 1, "dara")
    assert app.post("/api/loans/55/return", {}, user="ivan", now=T_RET).status == 200
    ui = parse_ui(app.get("/ui/books/1", user="dara", now=T_RET).text)
    assert ui.fields["status"] == "reserved" and "borrow" in ui.actions
    ui = parse_ui(app.get("/ui/books/1", user="chen", now=T_RET).text)
    assert "borrow" not in ui.actions
    hid = holds(app)[0]["id"]
    ui = parse_ui(app.get(f"/ui/holds/{hid}", user="dara", now=T_RET).text)
    assert "cancel" in ui.actions and ui.fields["status"] == "ready"
    assert app.get(f"/ui/holds/{hid}", user="chen", now=T_RET).status == 403
