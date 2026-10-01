"""Live demonstration: real changes, real checks, on a fresh copy of the library application.

  accrete demo [--keep DIR] [--pause]

Nothing here is replayed from a recording. Each step writes a change file, runs it through the
full pipeline, and prints the pipeline's own report. At the end, every change is reverted and
the result is compared with the untouched original: model, every stored record and the
independent base acceptance suite.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

from . import change as C
from . import runtime as R
from .cli import print_report
from .store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("1. A rename, written once",
     "A rename is one operator. Every expression and effect that mentions the field is rewritten; "
     "stored data is keyed by field id, so no record is touched. The UI and API follow automatically.",
     {"request": "Call the books field 'author' 'writer' everywhere",
      "interpretation": "Rename books.author to books.writer",
      "ops": [{"rename_field": {"entity": "books", "from": "author", "to": "writer"}}],
      "expect": [{"as": "ada", "do": "GET /api/books/3", "status": 200}]},
     [("GET", "/api/books/3", "hana")]),
    ("2. A new required field with no plan for existing data -> rejected",
     "The data check re-validates all 40 existing books against the changed model. "
     "Nothing is committed.",
     {"request": "Every book must have a shelf location",
      "ops": [{"add_field": {"entity": "books", "name": "shelf", "type": "text", "required": True}}]},
     []),
    ("3. The same change with a data policy -> committed",
     "Existing books get a derived shelf code; new books must supply one (400 otherwise).",
     {"request": "Every book must have a shelf location",
      "interpretation": "Required text field; existing books are shelved by the first letter of their title",
      "ops": [{"add_field": {"entity": "books", "name": "shelf", "type": "text", "required": True,
                             "backfill": "'S-' + record.title[0].upper()"}}],
      "expect": [{"as": "ada", "do": "POST /api/books", "body": {"title": "New", "writer": "X", "isbn": "999-0-demo"}, "status": 400},
                 {"as": "ada", "do": "POST /api/books", "body": {"title": "New", "writer": "X", "isbn": "999-0-demo", "shelf": "S-N"}, "status": 201}]},
     [("GET", "/api/books/3", "hana")]),
    ("4. A change with a hidden consequence -> rejected until acknowledged",
     "Marking books as damaged changes the computed status. The borrow guard reads status, so "
     "borrowing a damaged book now fails. The change never mentioned borrowing; replay finds it "
     "and shows before/after examples.",
     {"request": "Librarians can mark a book as damaged; damaged books show status 'damaged'",
      "ops": [{"add_field": {"entity": "books", "name": "damaged", "type": "bool", "default": "False",
                             "write_if": "user.role == 'librarian'"}},
              {"change_field": {"entity": "books", "name": "status",
                                "computed": "'damaged' if record.damaged else ('on_loan' if any(l.book == record and "
                                            "l.returned_at is None for l in loans) else 'available')"}},
              {"update_records": {"entity": "books", "where": "record.id == 2", "set": {"damaged": "True"}}}]},
     []),
    ("5. The same change with the consequence acknowledged -> committed",
     "Listing the consequence turns an accident into a decision. It is recorded in the ledger.",
     {"request": "Librarians can mark a book as damaged; damaged books show status 'damaged'",
      "interpretation": "Bool field writable by librarians; status computed from it; book 2 is known damaged; "
                        "damaged books cannot be borrowed (intended)",
      "ops": [{"add_field": {"entity": "books", "name": "damaged", "type": "bool", "default": "False",
                             "write_if": "user.role == 'librarian'"}},
              {"change_field": {"entity": "books", "name": "status",
                                "computed": "'damaged' if record.damaged else ('on_loan' if any(l.book == record and "
                                            "l.returned_at is None for l in loans) else 'available')"}},
              {"update_records": {"entity": "books", "where": "record.id == 2", "set": {"damaged": "True"}}}],
      "consequences": ["books.action:borrow"],
      "expect": [{"as": "hana", "do": "POST /api/books/2/borrow", "status": 409},
                 {"as": "hana", "do": "PATCH /api/books/3", "body": {"damaged": True}, "status": 403}]},
     [("POST", "/api/books/2/borrow", "hana"), ("PATCH", "/api/books/3", "hana", {"damaged": True})]),
    ("6. A behaviour change that lies about itself -> rejected",
     "The interpretation says 'tighten the borrow limit', but the operator also opens every loan to every "
     "member. Replay alone cannot catch this: the operator says it changes the read rule, so the 19 "
     "differences count as intended. What catches it is the expectation written from the request: "
     "a member must still not see other members' loans.",
     {"request": "Members may have at most 2 open loans",
      "ops": [{"change_action": {"entity": "books", "name": "borrow",
                                 "guard": "record.status == 'available' and (params.member or user).active and "
                                          "count(loans, member=(params.member or user), returned_at=None) < 2"}},
              {"set_rule": {"entity": "loans", "rule": "read", "expr": "True"}}],
      "expect": [{"as": "hana", "do": "GET /api/loans/1", "status": 403}]},
     []),
]


def _say(text, pause):
    print(text)
    if pause:
        input("  [enter] ")


def _snapshot(directory):
    st = Store(directory)
    model, world = st.load()
    st.close()
    recs = {e["name"]: R.records(world, eid) for eid, e in model["entities"].items()}
    model = dict(model)
    model.pop("seq", None)  # the id allocator only moves forward: ids of removed elements are never reused
    return json.dumps(model, sort_keys=True, default=str), json.dumps(recs, sort_keys=True, default=str)


def run(keep=None, pause=False):
    src = os.path.join(ROOT, "apps", "library")
    work = keep or os.path.join(tempfile.mkdtemp(prefix="accrete-demo-"), "library")
    if os.path.exists(work):
        shutil.rmtree(work)
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("__pycache__", "report-*.json"))
    print(f"accrete live demo on a fresh copy of the library app: {work}\n")
    original = _snapshot(work)
    committed = []
    for title, why, doc, calls in STEPS:
        print("=" * 100)
        _say(f"{title}\n{why}\n", False)
        print("change file:")
        print("  " + yaml.safe_dump(doc, sort_keys=False, width=110).replace("\n", "\n  ").rstrip())
        t = time.perf_counter()
        rep = C.apply_change(work, doc)
        print(f"\npipeline ({(time.perf_counter() - t) * 1000:.0f} ms wall):")
        print_report(rep)
        if rep["verdict"] == "committed":
            committed.append(rep["seq"])
        for c in calls:
            method, path, user = c[:3]
            body = c[3] if len(c) > 3 else ({} if method in ("POST", "PATCH") else None)
            st = Store(work)
            model, world = st.load()
            st.close()
            status, out, _ = R.handle_full(model, world, method, path, {}, body, user, R.parse_now(None))
            print(f"  live call as {user}: {method} {path} -> {status} {json.dumps(out)[:150]}")
        _say("", pause)
    print("=" * 100)
    print("7. Undo: revert every committed change, newest first (each revert is itself a checked change)\n")
    for seq in reversed(committed):
        rep = C.revert(work, seq)
        print(f"  revert #{seq}: {rep['verdict']}" + (f" ({rep.get('reason')})" if rep.get("reason") else ""))
    after = _snapshot(work)
    print(f"\n  model identical to original: {after[0] == original[0]}")
    print(f"  every stored record identical to original: {after[1] == original[1]}")
    print("\n8. Independent check: the base acceptance suite (written separately from accrete) on the reverted app\n")
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), work,
                        os.path.join(ROOT, "challenges", "base", "test_library_base.py")], env=env,
                       capture_output=True, text=True)
    print("  " + (r.stdout.strip().splitlines() or ["(no output)"])[-1])
    print("\nledger:")
    st = Store(work)
    for e in st.ledger():
        print(f"  #{e['seq']} {e['verdict']:9} {e.get('kind', 'change'):6} {e.get('request', '')[:80]}")
    st.close()
    print(f"\nThe instance is left at {work}. Try: accrete serve {work}   or   accrete log {work} 3")
    return 0
