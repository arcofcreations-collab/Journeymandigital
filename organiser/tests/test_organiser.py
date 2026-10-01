import json, os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import fixture as F
from msgorg import store as S, app as A

def setup(tmp_path):
    x = tmp_path / "b.xml"; F.build(str(x)); db = S.open_db(str(tmp_path / "a.db"))
    r = S.import_file(db, str(x)); A.recompute_absences(db); return db, r, x

def by_date(db, d, contact=None):
    return [f for f in A.absences(db, contact=contact) if f["work_start"] == d]

def test_import_counts_dedupe_and_errors(tmp_path):
    db, r, x = setup(tmp_path)
    assert r["errors"] == 1 and r["parsed"] == len(F.CONV) + 1 and r["declared"] == len(F.CONV) + 2
    r2 = S.import_file(db, str(x))
    assert r2["added"] == 0 and r2["duplicates"] == r2["parsed"]
    assert db.execute("select count(*) from messages").fetchone()[0] == len(F.CONV) + 1
    cov = S.coverage(db)
    assert any("declares" in g for g in cov["known_gaps"]) and any("RCS" in g for g in cov["known_gaps"])

def test_contacts_merge_number_formats(tmp_path):
    db, *_ = setup(tmp_path)
    ok = [c for c in A.contacts(db) if c["display"] == "Mr Okafor"]
    assert len(ok) == 1 and ok[0]["n"] == 4

def test_tentative_is_not_confirmed(tmp_path):
    db, *_ = setup(tmp_path)
    f, = by_date(db, "2026-03-06")
    assert f["status"] == "proposed" and "tentative" in " ".join(f["notes"])

def test_request_acknowledged_is_confirmed_but_not_taken(tmp_path):
    db, *_ = setup(tmp_path)
    f, = by_date(db, "2026-03-12")
    assert f["status"] == "confirmed" and len(f["evidence"]) == 2 and "not established" in f["actually_taken"]

def test_sick_today_and_declined(tmp_path):
    db, *_ = setup(tmp_path)
    assert by_date(db, "2026-03-16")[0]["status"] == "confirmed"
    sat = {f["kind"]: f["status"] for f in by_date(db, "2026-03-21")}
    assert sat["statement"] == "declined" and sat["their_cancellation"] == "cancelled"

def test_retraction_cancels(tmp_path):
    db, *_ = setup(tmp_path)
    f, = by_date(db, "2026-03-11")
    assert f["status"] == "cancelled" and f["revisions"]

def test_reschedule_records_new_date(tmp_path):
    db, *_ = setup(tmp_path)
    f, = by_date(db, "2026-03-25")
    assert f["status"] == "rescheduled" and f["rescheduled_to"][0] == "2026-03-27"

def test_corrections_do_not_touch_sources(tmp_path):
    db, *_ = setup(tmp_path)
    before = db.execute("select group_concat(body, '|') from messages").fetchone()[0]
    f, = by_date(db, "2026-03-06")
    A.correct(db, f["id"], "status", "confirmed", "she agreed by phone")
    A.recompute_absences(db)  # corrections survive recomputation
    g, = by_date(db, "2026-03-06")
    assert g["status"] == "confirmed" and g["corrected"]
    assert db.execute("select group_concat(body, '|') from messages").fetchone()[0] == before

def test_search_filters_jobs_and_export(tmp_path):
    db, *_ = setup(tmp_path)
    A.set_job(db, "Dana (Cafe)", "cafe")
    assert {m["display"] for m in A.search(db, job="cafe")} == {"Dana (Cafe)"}
    assert all(m["direction"] == "sent" for m in A.search(db, "Friday", direction="sent"))
    assert len(A.search(db, start="2026-03-16", end="2026-03-16")) == 2
    md = A.export(A.absences(db, job="cafe"), "md")
    assert "not established" in md and "Doctor's appointment" in md
    assert "2026-03-12" in A.export(A.absences(db), "csv")

def test_context_and_delete(tmp_path):
    db, *_ = setup(tmp_path)
    mid = A.search(db, "Doctor")[0]["id"]
    ctx = A.context(db, mid, 1, 1)
    assert [m["id"] for m in ctx][1] == mid and len(ctx) == 3
    p = str(tmp_path / "a.db"); db.close(); S.delete_all(p); assert not os.path.exists(p)
