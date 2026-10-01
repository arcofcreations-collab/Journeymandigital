"""Regression tests for the v2.1 revisions (docs/REVISIONS.md, section v2.1).

Run: python -m pytest tests -q   (from the repository root)
"""
import datetime as dt
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from accrete import change as C  # noqa: E402
from accrete import expr as E  # noqa: E402
from accrete import runtime as R  # noqa: E402
from accrete.store import Store  # noqa: E402

NOW = dt.datetime(2026, 3, 1, 12, 0)


def _copy(tmp_path, name):
    d = tmp_path / name
    shutil.copytree(os.path.join(ROOT, "apps", name), d, ignore=shutil.ignore_patterns("report-*.json"))
    return str(d)


@pytest.fixture
def lib(tmp_path):
    return _copy(tmp_path, "library")


@pytest.fixture
def exp(tmp_path):
    return _copy(tmp_path, "expenses")


@pytest.fixture
def mnt(tmp_path):
    return _copy(tmp_path, "maintenance")


def apply(d, doc, **kw):
    return C.apply_change(d, doc, now=NOW, **kw)


def load(d):
    st = Store(d)
    m, w = st.load()
    st.close()
    return m, w


LIMIT_4 = {"change_action": {"entity": "books", "name": "borrow", "guard":
                             "record.status == 'available' and (params.member or user).active "
                             "and count(loans, member=(params.member or user), returned_at=None) < 4"}}


# ------------------------------------------------------------------ weakness 1: probe inputs
def test_create_probes_send_explicit_values_that_differ_from_defaults(lib):
    model, world = load(lib)
    bodies = [p["body"] for p in C.generate_probes(model, world, NOW) if p["method"] == "POST" and p["path"] == "/api/members"]
    assert any(b.get("active") is False for b in bodies)  # default is True


def test_engine_bug_defaults_overwrite_provided_values_is_detected(mnt, monkeypatch):
    C.snapshot(mnt)
    orig = R.apply_defaults

    def buggy(ctx, ent, data, provided, errors=None):
        return orig(ctx, ent, data, set(), errors)
    monkeypatch.setattr(R, "apply_defaults", buggy)
    assert C.upgrade_check(mnt)["verdict"] == "DIFFERENT"


def test_action_probes_carry_parameter_bodies_including_a_missing_id(lib):
    model, world = load(lib)
    bodies = [p["body"] for p in C.generate_probes(model, world, NOW) if p["path"].endswith("/borrow")]
    assert any(isinstance(b, dict) and isinstance(b.get("member"), int) and b["member"] != C.MISSING_ID for b in bodies)
    assert any(isinstance(b, dict) and b.get("member") == C.MISSING_ID for b in bodies)


def test_chains_reach_a_count_limit(lib):
    # 3 -> 4 open loans: only a member who borrows several books in a row reaches the limit
    rep = apply(lib, {"request": "Members may borrow at most 4 books", "ops": [LIMIT_4]}, dry_run=True)
    assert rep["verdict"] == "dry-run passed", rep.get("reason")
    assert rep["replay"]["direct"] > 0


def test_numbers_at_full_precision_reach_values_stored_by_effects(mnt, monkeypatch):
    rep = apply(mnt, {"request": "r", "ops": [
        {"add_field": {"entity": "work_orders", "name": "cost", "type": "number", "system": True}},
        {"add_action": {"entity": "work_orders", "name": "log_cost", "params": {"amount": "number required"},
                        "allow": "user.role == 'supervisor'", "effects": [{"set": {"cost": "params.amount * 1.07"}}]}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    assert C.upgrade_check(mnt)["verdict"] == "same"
    orig = R.to_storage
    monkeypatch.setattr(R, "to_storage", lambda f, v: round(v, 1) if f.get("type") == "number" and isinstance(v, float) else orig(f, v))
    assert C.upgrade_check(mnt)["verdict"] == "DIFFERENT"


def test_empty_collection_gets_typed_create_bodies(exp):
    rep = apply(exp, {"request": "r", "ops": [
        {"add_entity": {"name": "batches", "fields": {"items": "list ref claims required distinct",
                                                       "total": {"type": "number", "system": True,
                                                                 "default": "sum(c.amount for c in record.items)"}},
                        "rules": {"create": "user.role == 'finance'",
                                  "create_guard": "all(c.status == 'approved' for c in record.items)"}}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    model, world = load(exp)
    probes = [p for p in C.generate_probes(model, world, NOW) if p["path"] == "/api/batches" and p["method"] == "POST"]
    assert any(C._run_probe(model, world, p)[0] == 201 for p in probes)  # some body refers to approved claims only


def test_time_window_boundary_is_probed_in_the_snapshot(lib, monkeypatch):
    rep = apply(lib, {"request": "r", "ops": [
        {"add_field": {"entity": "loans", "name": "extended", "type": "bool", "system": True, "default": "False"}},
        {"add_action": {"entity": "loans", "name": "extend", "allow": "record.member == user or user.role == 'librarian'",
                        "guard": "record.returned_at is None and not record.extended and now <= record.borrowed_at + hours(72)",
                        "effects": [{"set": {"extended": "True"}}]}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    assert C.upgrade_check(lib)["verdict"] == "same"
    monkeypatch.setitem(E.BUILTINS, "hours", lambda n: dt.timedelta(hours=n + 24))  # planted: windows one day longer
    assert C.upgrade_check(lib)["verdict"] == "DIFFERENT"


# ------------------------------------------------------------------ weakness 2: failed requests
REMIND = {"add_action": {"entity": "loans", "name": "remind", "allow": "user.role == 'librarian'",
                         "effects": [{"emit": "reminder", "payload": {"loan": "record"}},
                                     {"fail": "'loan already returned'", "when": "record.returned_at is not None"}]}}


def test_failed_request_keeping_its_messages_is_detected(lib, monkeypatch):
    assert apply(lib, {"request": "r", "ops": [REMIND]})["verdict"] == "committed"
    assert C.upgrade_check(lib)["verdict"] == "same"

    def rollback_keeps_outbox(self):
        for eid, rid, prev in reversed(self.journal):
            recs = R.records(self.world, eid)
            if prev is None:
                recs.pop(rid, None)
            else:
                recs[rid] = prev
        self.journal.clear()
        self.invalidate()
    monkeypatch.setattr(R.Ctx, "rollback", rollback_keeps_outbox)
    assert C.upgrade_check(lib)["verdict"] == "DIFFERENT"


def test_failed_request_leaving_records_behind_is_detected(lib, monkeypatch):
    ops = [{"add_field": {"entity": "loans", "name": "reminded", "type": "bool", "system": True, "default": "False"}},
           {"add_action": {"entity": "loans", "name": "remind", "allow": "user.role == 'librarian'",
                           "effects": [{"set": {"reminded": "True"}},
                                       {"fail": "'loan already returned'", "when": "record.returned_at is not None"}]}}]
    assert apply(lib, {"request": "r", "ops": ops})["verdict"] == "committed"
    model, world = load(lib)
    probe = {"method": "POST", "path": "/api/loans/1/remind", "query": {}, "body": {}, "user": "ada", "now": NOW.isoformat()}
    good = C._run_probe(model, world, probe)
    assert good[0] == 409 and good[3] == {}

    def rollback_keeps_records(self):
        del self.world["outbox"][self.outbox_mark:]
        self.journal.clear()
    monkeypatch.setattr(R.Ctx, "rollback", rollback_keeps_records)
    bad = C._run_probe(model, world, probe)
    assert bad[0] == 409 and bad[3].get("loans", {}).get("1", {}).get("reminded") is True
    # and the probe still left the state as it found it
    assert C._run_probe(model, world, dict(probe, method="GET", path="/api/loans/1"))[1]["reminded"] is False


# ------------------------------------------------------------------ weakness 3: several times
DUE_10 = {"change_field": {"entity": "work_orders", "name": "due_date", "computed":
                           "record.created_at.date() + days(1 if record.priority == 'urgent' else 10 "
                           "if record.priority == 'normal' else 30)"}}


def test_time_dependent_consequence_is_found_at_another_time(mnt):
    # at this `now` every affected order is overdue in both versions: only another time shows the difference
    later = dt.datetime(2026, 6, 1, 12)
    doc = {"request": "Normal-priority work orders are due 10 days after creation", "ops": [DUE_10]}
    rep = C.apply_change(mnt, doc, dry_run=True, now=later)
    assert rep["verdict"] == "rejected" and "work_orders.field:overdue" in rep["reason"]
    assert rep["replay"]["other_times"]
    assert any(" at " in ex["request"] for ex in rep["replay"]["examples"])
    rep = C.apply_change(mnt, dict(doc, consequences=["work_orders.field:overdue"]), dry_run=True, now=later)
    assert rep["verdict"] == "dry-run passed", rep.get("reason")


def test_no_extra_times_when_the_change_cannot_touch_clock_dependent_behaviour(exp):
    rep = apply(exp, {"request": "Claims get a note", "ops": [{"add_field": {"entity": "claims", "name": "note", "type": "text"}}]},
                dry_run=True)
    assert rep["verdict"] == "dry-run passed" and "other_times" not in rep["replay"]


# ------------------------------------------------------------------ weakness 4: guard_message as text
def _renew(msg, fail="'already returned'"):
    return {"request": "Loans can be renewed once", "ops": [
        {"add_field": {"entity": "loans", "name": "renewed", "type": "bool", "system": True, "default": "False"}},
        {"add_action": {"entity": "loans", "name": "renew", "allow": "user.role == 'librarian'",
                        "guard": "record.returned_at is None and not record.renewed", "guard_message": msg,
                        "effects": [{"set": {"renewed": "True"}},
                                    {"fail": fail, "when": "record.returned_at is not None"}]}}],
        "consequences": ["all"]}


def test_plain_text_guard_message_is_accepted_as_text(lib):
    rep = apply(lib, _renew("this loan cannot be renewed, sorry", fail="loan already returned"))
    assert rep["verdict"] == "committed", rep.get("reason")
    assert any("plain text" in n for n in rep["what_happened"])
    model, world = load(lib)
    loans = R.handle(model, world, "GET", "/api/loans", {}, None, "ada", NOW)[1]["items"]
    returned = next(x["id"] for x in loans if x["returned_at"] is not None)
    status, out = R.handle(model, world, "POST", f"/api/loans/{returned}/renew", {}, {}, "ada", NOW)
    assert status == 409 and out["message"] == "this loan cannot be renewed, sorry"


def test_quoted_guard_message_keeps_its_meaning(lib):
    rep = apply(lib, _renew("'no renewal for loan ' + str(record.id)"))
    assert rep["verdict"] == "committed", rep.get("reason")
    model, _ = load(lib)
    act = next(a for e in model["entities"].values() for a in e["actions"].values() if a["name"] == "renew")
    assert act["guard_message"] == "'no renewal for loan ' + str(record.id)"


def test_message_that_parses_as_a_name_gets_an_exact_fix(lib):
    from accrete import cli
    rep = apply(lib, _renew("overdue"))
    assert rep["verdict"] == "rejected"
    assert any('guard_message: "\'overdue\'"' in p for p in rep["static_check"]["problems"])
    assert any(h == 'replace that line with: guard_message: "\'overdue\'"' for h in cli.next_steps(rep))


# ------------------------------------------------------------------ weakness 5: scope warnings
BASE = {"request": "Members may borrow at most 4 books", "interpretation": "Raise the open-loan limit in the borrow guard from 3 to 4",
        "consequences": ["all"]}


def _scope(lib, extra):
    rep = apply(lib, dict(BASE, ops=[LIMIT_4] + extra), dry_run=True)
    assert rep["verdict"] == "dry-run passed", rep.get("reason")
    return rep["scope_warnings"]


def test_scope_no_false_alarm_for_inert_field_or_user_field(lib):
    assert _scope(lib, []) == []
    assert _scope(lib, [{"add_field": {"entity": "members", "name": "planted_note", "type": "text"}}]) == []
    assert _scope(lib, [{"add_field": {"entity": "members", "name": "max_loans", "type": "int", "default": "4"}}]) == []


def test_scope_flags_stray_edits_inside_a_mentioned_entity(lib):
    assert _scope(lib, [{"update_records": {"entity": "books", "where": "record.id == 16", "set": {"title": "'X'"}}}])
    assert _scope(lib, [{"update_records": {"entity": "members", "where": "record.id == 5", "set": {"role": "'librarian'"}}}])
    assert _scope(lib, [{"change_action": {"entity": "loans", "name": "return", "guard": "True"}}]) == ["loans.action:return"]
    assert _scope(lib, [{"set_rule": {"entity": "loans", "rule": "read", "expr": "True"}}]) == ["loans.read"]


def test_scope_accepts_named_data_edits_and_renames(lib):
    rep = apply(lib, {"request": "Fix the title of book 16", "ops": [
        {"update_records": {"entity": "books", "where": "record.id == 16", "set": {"title": "'X'"}}}]}, dry_run=True)
    assert rep["scope_warnings"] == []
    rep = apply(lib, {"request": "rename returned_at to closed_at", "ops": [
        {"rename_field": {"entity": "loans", "from": "returned_at", "to": "closed_at"}}]}, dry_run=True)
    assert rep["verdict"] == "dry-run passed" and rep["scope_warnings"] == []
