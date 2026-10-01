"""Independent check for X5 (written before any run; never shown to implementers or reviewers)."""
import datetime as dt, os, sys
sys.path.insert(0, os.environ["ORG"])
from msgorg import absences as A

def ms(*a): return int(dt.datetime(*a).timestamp() * 1000)

def one(body, when, direction="sent"):
    return A.analyse_conversation([{"id": 1, "key": "k", "date_ms": ms(*when), "direction": direction, "body": body}])

def test_evening_undated_is_next_day():
    f, = one("Sorry I can't come in", (2026, 3, 4, 19, 30)); assert f["work_start"] == "2026-03-05"

def test_six_pm_boundary():
    f, = one("Sorry I can't come in", (2026, 3, 4, 18, 0)); assert f["work_start"] == "2026-03-05"
    f, = one("Sorry I can't come in", (2026, 3, 4, 17, 59)); assert f["work_start"] == "2026-03-04"

def test_daytime_undated_same_day():
    f, = one("I'm sick, can't make it", (2026, 3, 4, 9, 0)); assert f["work_start"] == "2026-03-04"

def test_dated_today_unchanged_in_evening():
    f, = one("I can't come in today", (2026, 3, 4, 19, 0)); assert f["work_start"] == "2026-03-04"

def test_dated_tomorrow_unchanged():
    f, = one("I can't come in tomorrow", (2026, 3, 4, 20, 0)); assert f["work_start"] == "2026-03-05"

def test_note_present():
    f, = one("Sorry I can't come in", (2026, 3, 4, 19, 30))
    assert any("19:30" in n and "next day" in n for n in f["notes"])

def test_preceding_message_date_still_used():
    msgs = [{"id": 1, "key": "a", "date_ms": ms(2026,3,4,19,0), "direction": "received", "body": "Can you do Friday?"},
            {"id": 2, "key": "b", "date_ms": ms(2026,3,4,19,5), "direction": "sent", "body": "Sorry I can't make it"}]
    f, = [x for x in A.analyse_conversation(msgs) if x["first_msg"] == 2]
    assert f["work_start"] == "2026-03-06"
