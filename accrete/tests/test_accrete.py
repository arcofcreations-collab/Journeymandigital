"""Regression tests for accrete itself: the change pipeline and the model features.

Run: python -m pytest accrete/tests -q   (from the repository root)
"""
import datetime as dt
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from accrete import change as C  # noqa: E402
from accrete import runtime as R  # noqa: E402
from accrete.store import Store  # noqa: E402

NOW = dt.datetime(2026, 3, 1, 12, 0)


@pytest.fixture
def lib(tmp_path):
    d = tmp_path / "library"
    shutil.copytree(os.path.join(ROOT, "apps", "library"), d, ignore=shutil.ignore_patterns("report-*.json"))
    return str(d)


@pytest.fixture
def exp(tmp_path):
    d = tmp_path / "expenses"
    shutil.copytree(os.path.join(ROOT, "apps", "expenses"), d, ignore=shutil.ignore_patterns("report-*.json"))
    return str(d)


def call(d, method, path, user, body=None, query=None):
    st = Store(d)
    model, world = st.load()
    st.close()
    return R.handle(model, world, method, path, query or {}, body if body is not None else ({} if method in ("POST", "PATCH") else None), user, NOW)


def snapshot(d):
    st = Store(d)
    model, world = st.load()
    st.close()
    model = dict(model)
    model.pop("seq")
    return json.dumps(model, sort_keys=True), json.dumps(world["records"], sort_keys=True, default=str)


def apply(d, doc):
    return C.apply_change(d, doc, now=NOW)


# ------------------------------------------------------------------ pipeline
def test_rename_rewrites_dependents_and_reverts_exactly(lib):
    before = snapshot(lib)
    rep = apply(lib, {"request": "r", "ops": [{"rename_field": {"entity": "loans", "from": "returned_at", "to": "closed_at"}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    assert rep["replay"]["unexplained"] == 0
    assert "closed_at" in call(lib, "GET", "/api/loans/1", "ada")[1]
    assert call(lib, "GET", "/api/books/2", "ada")[1]["status"] in ("available", "on_loan")  # dependents rewritten
    assert C.revert(lib, rep["seq"])["verdict"] == "committed"
    assert snapshot(lib) == before


def test_required_field_without_data_plan_is_rejected_and_changes_nothing(lib):
    before = snapshot(lib)
    rep = apply(lib, {"request": "r", "ops": [{"add_field": {"entity": "books", "name": "shelf", "type": "text", "required": True}}]})
    assert rep["verdict"] == "rejected"
    assert rep["data_check"]["violations"][0]["count"] == 40
    assert snapshot(lib) == before


def test_unacknowledged_consequence_is_rejected_then_accepted(lib):
    ops = [{"add_field": {"entity": "books", "name": "damaged", "type": "bool", "default": "False"}},
           {"change_field": {"entity": "books", "name": "status", "computed":
                             "'damaged' if record.damaged else ('on_loan' if any(l.book == record and l.returned_at is None for l in loans) else 'available')"}},
           {"update_records": {"entity": "books", "where": "record.id == 2", "set": {"damaged": "True"}}}]
    rep = apply(lib, {"request": "r", "ops": ops})
    assert rep["verdict"] == "rejected" and "books.action:borrow" in rep["reason"]
    rep = apply(lib, {"request": "r", "ops": ops, "consequences": ["books.action:borrow"]})
    assert rep["verdict"] == "committed"


def test_static_check_catches_dangling_reference(lib):
    rep = apply(lib, {"request": "r", "ops": [{"remove_field": {"entity": "loans", "name": "returned_at"}}]})
    assert rep["verdict"] == "rejected" and rep["static_check"]["problems"]


def test_failed_expectation_rejects(lib):
    rep = apply(lib, {"request": "r", "ops": [{"set_rule": {"entity": "loans", "rule": "read", "expr": "True"}}],
                      "expect": [{"as": "hana", "do": "GET /api/loans/1", "status": 403}]})
    assert rep["verdict"] == "rejected"


def test_yaml_on_key_is_accepted(lib, tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("request: r\nops:\n  - add_trigger: {entity: loans, name: t, on: create, effects: [{emit: x, payload: {a: '1'}}]}\n")
    doc, base = C.load_change(str(p))
    rep = apply(lib, doc)
    # borrow creates loans, so it now emits too: a consequence the change must acknowledge
    assert rep["verdict"] == "rejected" and "books.action:borrow" in rep["reason"]
    rep = apply(lib, dict(doc, consequences=["books.action:borrow"]))
    assert rep["verdict"] == "committed", rep.get("reason")


# ------------------------------------------------------------------ model features
def test_promote_field_keeps_required_and_ui_text(lib):
    rep = apply(lib, {"request": "r", "ops": [{"promote_field": {"entity": "books", "field": "author", "to": "authors", "key": "name"}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    st, out = call(lib, "POST", "/api/books", "ada", {"title": "T", "isbn": "x-1"})
    assert st == 400 and "author" in out["fields"]
    names = [a["name"] for a in call(lib, "GET", "/api/authors", "ada")[1]["items"]]
    assert names[0] == "M. Reyes"  # first appearance order
    from accrete import ui
    st2 = Store(lib)
    model, world = st2.load()
    st2.close()
    ctx = R.Ctx(model, world, "ada", NOW)
    assert ui.shown(ctx, model["entities"][next(e for e, x in model["entities"].items() if x["name"] == "books")], "author", 1) == "M. Reyes"


def test_list_field_create_guard_and_for_effect(exp):
    rep = apply(exp, {"request": "r", "ops": [
        {"add_entity": {"name": "batches", "fields": {"items": "list ref claims required distinct",
                                                       "total": {"type": "number", "system": True, "default": "sum(c.amount for c in record.items)"}},
                        "rules": {"create": "user.role == 'finance'", "create_guard": "all(c.status == 'approved' for c in record.items)"},
                        "triggers": {"pay": {"on": "create", "effects": [
                            {"for": "c", "in": "record.items", "do": [{"update": "c", "set": {"status": "'paid'"}},
                                                                    {"emit": "paid", "payload": {"claim": "c"}}]}]}}}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    approved = [c["id"] for c in call(exp, "GET", "/api/claims", "fiona")[1]["items"] if c["status"] == "approved"]
    other = next(c["id"] for c in call(exp, "GET", "/api/claims", "fiona")[1]["items"] if c["status"] == "draft")
    assert call(exp, "POST", "/api/batches", "marco", {"items": "x"})[0] == 403
    assert call(exp, "POST", "/api/batches", "fiona", {"items": [other, 99999]})[0] == 409  # 409 wins over 400
    assert call(exp, "POST", "/api/batches", "fiona", {"items": [approved[0], approved[0]]})[0] == 400
    assert call(exp, "POST", "/api/batches", "fiona", {"items": []})[0] == 400
    st = Store(exp)
    model, world = st.load()
    st.close()
    status, out = R.handle(model, world, "POST", "/api/batches", {}, {"items": approved[:2]}, "fiona", NOW)
    assert status == 201 and out["items"] == approved[:2]
    assert [m["payload"]["claim"] for m in world["outbox"] if m["channel"] == "paid"] == approved[:2]
    status, out = R.handle(model, world, "GET", "/api/_outbox", {"channel": "paid"}, None, "fiona", NOW)
    assert [m["channel"] for m in out["items"]] == ["paid", "paid"]


def test_on_delete_policies(lib):
    rep = apply(lib, {"request": "r", "ops": [
        {"add_entity": {"name": "notes", "fields": {"book": {"type": "ref", "ref": "books", "on_delete": "cascade"}, "text": "text"}}},
        {"add_records": {"entity": "notes", "records": [{"book": 40, "text": "a"}, {"book": 40, "text": "b"}]}}]})
    assert rep["verdict"] == "committed", rep.get("reason")
    free = [b["id"] for b in call(lib, "GET", "/api/books", "ada")[1]["items"]
            if not any(l["book"] == b["id"] for l in call(lib, "GET", "/api/loans", "ada")[1]["items"])]
    st = Store(lib)
    model, world = st.load()
    st.close()
    target = 40 if 40 in free else None
    if target is None:
        pytest.skip("book 40 has loans in this seed")
    status, _ = R.handle(model, world, "DELETE", f"/api/books/{target}", {}, None, "ada", NOW)
    assert status == 204
    assert R.handle(model, world, "GET", "/api/notes", {}, None, "ada", NOW)[1]["items"] == []


def test_restrict_is_default(lib):
    assert call(lib, "DELETE", "/api/members/3", "ada")[0] == 409  # chen has loans


def test_unknown_filter_and_blank_required_text(lib):
    assert call(lib, "GET", "/api/books", "ada", query={"bogus": "1"})[0] == 400
    assert call(lib, "GET", "/api/books", "ada", query={"year": "2005"})[0] == 200
    st, out = call(lib, "POST", "/api/books", "ada", {"title": "  ", "author": "A", "isbn": "x-9"})
    assert st == 400 and "title" in out["fields"]
