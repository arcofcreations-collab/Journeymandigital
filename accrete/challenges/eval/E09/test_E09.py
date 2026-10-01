"""Hidden acceptance tests for E09 (library): household guardians.

Guardians after migration (from the brief): eli(5) and jo(10) -> dara(4); gus(7) -> fatima(6); lena(12) -> kemal(11).
Loans from spec/apps/library_seed.json:
  dara 1 23 26 29 41 59 | eli 8 16 20 33 39 40 60 (open 60) | jo 2 9 10 17 27 32 34 46 50 57 (open 46 50 57)
  fatima 3 45 54 (open 54) | gus 7 14 25 47 (open 47) | kemal 12 18 35 37 42 44 49 56 | lena none (inactive)
"""
from accept_client import fresh_app, parse_ui

NOW = "2026-03-01T12:00:00"

GUARDIAN = {1: None, 2: None, 3: None, 4: None, 5: 4, 6: None, 7: 6, 8: None, 9: None, 10: 4, 11: None, 12: 11}
DARA_LOANS = [1, 2, 8, 9, 10, 16, 17, 20, 23, 26, 27, 29, 32, 33, 34, 39, 40, 41, 46, 50, 57, 59, 60]
FATIMA_LOANS = [3, 7, 14, 25, 45, 47, 54]
KEMAL_LOANS = [12, 18, 35, 37, 42, 44, 49, 56]


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


def test_guardians_migrated():
    app = fresh_app()
    members = app.get("/api/members", user="ada", now=NOW).json["items"]
    assert [m["id"] for m in members] == list(range(1, 13))
    for m in members:
        assert m["guardian"] == GUARDIAN[m["id"]], m
    assert ids(app.get("/api/members?guardian=4", user="ada", now=NOW)) == [5, 10]
    assert ids(app.get("/api/members?guardian=null", user="ben", now=NOW)) == [1, 2, 3, 4, 6, 8, 9, 11]
    m = app.get("/api/members/10", user="ada", now=NOW).json
    assert (m["username"], m["name"], m["role"], m["active"]) == ("jo", "Jo Novak", "member", True)


def test_guardian_reads_dependants():
    app = fresh_app()
    assert ids(app.get("/api/members", user="dara", now=NOW)) == [4, 5, 10]
    assert ids(app.get("/api/members", user="fatima", now=NOW)) == [6, 7]
    assert ids(app.get("/api/members", user="kemal", now=NOW)) == [11, 12]
    assert ids(app.get("/api/members", user="eli", now=NOW)) == [5]
    assert ids(app.get("/api/members", user="chen", now=NOW)) == [3]
    assert app.get("/api/members/12", user="kemal", now=NOW).json["active"] is False
    assert_error(app.get("/api/members/4", user="eli", now=NOW), 403, "forbidden")   # not the other way round
    assert_error(app.get("/api/members/7", user="dara", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/loans", user="dara", now=NOW)) == DARA_LOANS
    assert ids(app.get("/api/loans", user="fatima", now=NOW)) == FATIMA_LOANS
    assert ids(app.get("/api/loans", user="kemal", now=NOW)) == KEMAL_LOANS
    assert ids(app.get("/api/loans", user="eli", now=NOW)) == [8, 16, 20, 33, 39, 40, 60]
    assert ids(app.get("/api/loans?member=5", user="dara", now=NOW)) == [8, 16, 20, 33, 39, 40, 60]
    assert app.get("/api/loans/60", user="dara", now=NOW).json["member"] == 5
    assert_error(app.get("/api/loans/54", user="dara", now=NOW), 403, "forbidden")
    assert_error(app.get("/api/loans/59", user="eli", now=NOW), 403, "forbidden")


def test_guardian_borrows_for_dependant():
    app = fresh_app()
    before = len(outbox(app))
    r = app.post("/api/books/3/borrow", {"member": 5}, user="dara", now=NOW)
    assert r.status == 200 and r.json["status"] == "on_loan"
    loan = app.get("/api/loans?book=3", user="ada", now=NOW).json["items"][0]
    assert loan["member"] == 5 and loan["due_at"] == "2026-03-15"
    msgs = outbox(app)[before:]
    assert [m["payload"] for m in msgs] == [{"loan": loan["id"], "book": 3, "member": 5}]
    assert loan["id"] in ids(app.get("/api/loans", user="eli", now=NOW))
    n = len(outbox(app))
    assert_error(app.post("/api/books/13/borrow", {"member": 10}, user="dara", now=NOW), 409, "conflict")   # jo: 3 loans
    assert_error(app.post("/api/books/13/borrow", {"member": 12}, user="kemal", now=NOW), 409, "conflict")  # lena inactive
    assert_error(app.post("/api/books/13/borrow", {"member": 3}, user="dara", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/13/borrow", {"member": 4}, user="eli", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/13/borrow", {"member": 5}, user="fatima", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/books/1/borrow", {"member": 3}, user="dara", now=NOW), 403, "forbidden")    # 403 before 409
    assert len(outbox(app)) == n
    assert app.get("/api/books/13", user="ada", now=NOW).json["status"] == "available"
    r = app.post("/api/books/14/borrow", {"member": 7}, user="fatima", now=NOW)
    assert r.status == 200


def test_guardian_returns_dependants_loans():
    app = fresh_app()
    r = app.post("/api/loans/60/return", {}, user="dara", now=NOW)
    assert r.status == 200 and r.json["returned_at"] == NOW and r.json["member"] == 5
    assert app.post("/api/loans/47/return", {}, user="fatima", now=NOW).status == 200
    assert_error(app.post("/api/loans/54/return", {}, user="dara", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/59/return", {}, user="eli", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/39/return", {}, user="dara", now=NOW), 409, "conflict")   # already returned
    assert_error(app.post("/api/loans/54/return", {}, user="chen", now=NOW), 403, "forbidden")
    assert app.get("/api/loans/59", user="ada", now=NOW).json["returned_at"] is None


def test_guardian_cannot_edit_dependants():
    app = fresh_app()
    assert_error(app.patch("/api/members/5", {"name": "Eli N."}, user="dara", now=NOW), 403, "forbidden")
    assert_error(app.delete("/api/members/5", user="dara", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/members/3", {"guardian": 9}, user="chen", now=NOW), 403, "forbidden")
    assert_error(app.patch("/api/members/5", {"guardian": None}, user="eli", now=NOW), 403, "forbidden")
    r = app.patch("/api/members/5", {"name": "Eli Novak-Ruiz"}, user="eli", now=NOW)
    assert r.status == 200 and r.json["guardian"] == 4
    assert app.get("/api/members/5", user="ada", now=NOW).json["name"] == "Eli Novak-Ruiz"


def test_librarian_manages_guardians():
    app = fresh_app()
    for body, mid in (({"guardian": 3}, 3), ({"guardian": 999}, 3), ({"guardian": 5}, 3), ({"guardian": 6}, 4),
                      ({"guardian": "dara"}, 3)):
        assert_error(app.patch(f"/api/members/{mid}", body, user="ada", now=NOW), 400, "validation")
    assert app.get("/api/members/3", user="ada", now=NOW).json["guardian"] is None
    r = app.patch("/api/members/3", {"guardian": 9}, user="ada", now=NOW)
    assert r.status == 200 and r.json["guardian"] == 9
    assert ids(app.get("/api/loans", user="ivan", now=NOW)) == [5, 13, 15, 21, 31, 43, 48, 52, 55]
    r = app.patch("/api/members/5", {"guardian": None}, user="ben", now=NOW)
    assert r.status == 200 and r.json["guardian"] is None
    assert_error(app.get("/api/members/5", user="dara", now=NOW), 403, "forbidden")
    assert_error(app.post("/api/loans/60/return", {}, user="dara", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/members", user="dara", now=NOW)) == [4, 10]
    r = app.post("/api/members", {"username": "mia", "name": "Mia Novak", "role": "member", "guardian": 4},
                 user="ada", now=NOW)
    assert r.status == 201 and r.json["guardian"] == 4 and r.json["active"] is True
    assert ids(app.get("/api/members", user="dara", now=NOW)) == [4, 10, r.json["id"]]
    r = app.post("/api/members", {"username": "noa", "name": "Noa", "role": "member"}, user="ada", now=NOW)
    assert r.status == 201 and r.json["guardian"] is None
    assert_error(app.post("/api/members", {"username": "kai", "name": "Kai", "role": "member", "guardian": 10},
                          user="ada", now=NOW), 400, "validation")


def test_deleting_members_with_dependants():
    app = fresh_app()
    assert_error(app.delete("/api/members/4", user="ada", now=NOW), 409, "conflict")
    assert app.delete("/api/members/12", user="ada", now=NOW).status == 204   # a dependant without loans
    assert ids(app.get("/api/members", user="kemal", now=NOW)) == [11]


def test_ui_for_guardians():
    app = fresh_app()
    assert parse_ui(app.get("/ui/members", user="dara", now=NOW).text).rows == [4, 5, 10]
    assert parse_ui(app.get("/ui/loans", user="fatima", now=NOW).text).rows == FATIMA_LOANS
    ui = parse_ui(app.get("/ui/members/5", user="dara", now=NOW).text)
    assert ui.fields["username"] == "eli" and "guardian" in ui.fields
    assert "return" in parse_ui(app.get("/ui/loans/60", user="dara", now=NOW).text).actions
    assert app.get("/ui/loans/54", user="dara", now=NOW).status == 403
    assert app.get("/ui/members/new", user="dara", now=NOW).status == 403
    r = app.get("/ui/members/new", user="ada", now=NOW)
    assert r.status == 200 and {"username", "name", "role", "guardian"} <= set(parse_ui(r.text).inputs)


def test_other_members_unchanged():
    app = fresh_app()
    assert ids(app.get("/api/loans", user="chen", now=NOW)) == [13, 15, 43, 52]
    assert ids(app.get("/api/loans", user="hana", now=NOW)) == [4, 6, 11, 19, 22, 24, 28, 30, 36, 38, 51, 53, 58]
    assert_error(app.post("/api/books/3/borrow", {"member": 4}, user="chen", now=NOW), 403, "forbidden")
    assert ids(app.get("/api/members", user="ada", now=NOW)) == list(range(1, 13))
    assert app.post("/api/books/3/borrow", {}, user="eli", now=NOW).status == 200
