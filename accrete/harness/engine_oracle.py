"""Independent oracle for the engine-upgrade study: classify every (planted engine bug, app) pair.

  python harness/engine_oracle.py [--mutants FILE.json] [--out NAME] [--seqlen N]
      -> results/v2/planted/engine_oracle[_NAME].json (+ printed table)

accrete's `upgrade-check` replays probes that accrete generates itself, so it cannot also be the
judge of which engine bugs are harmful. This oracle is written separately. It shares nothing
with change.generate_probes; it only uses the public request interface (runtime.handle and
ui.handle) and reads the model's names and types from app.db.

* **Differential random sequences.** For each app, a seeded sequence of N stateful requests:
  - users: every user, plus anonymous;
  - request kinds: list GETs with random filters (including unknown filter names), record GETs,
    UI list/detail/new pages, creates and PATCHes, DELETEs, and actions with parameter bodies;
  - create and PATCH bodies are copied from existing records and then perturbed: dropped fields,
    nulls, duplicated values, numbers with 2-3 decimals, shifted dates and counts.

  The same sequence runs, state carried from request to request, under the correct engine and
  under the bug. A pair is independently CONFIRMED HARMFUL when any response, emitted message, or
  the final stored records/outbox differ, or when the app's own acceptance tests fail under the
  bug (taken from the engine study file).
* **UNAFFECTED:** the app's model does not contain the construct the bug touches. Examples: no
  `unique` field for unique-skipped; no `write_if` for write-if-ignored; no action that both emits
  a message and can fail afterwards for rollback-keeps-outbox. Such pairs cannot be harmful,
  whatever the requests.
* **UNEXERCISED:** the construct exists but neither the sequences nor the acceptance tests showed a
  difference. The bug may be harmless in that app, or the oracle may not have hit it.

Detection rates of `upgrade-check` are reported among CONFIRMED HARMFUL pairs only. Detections in
the other two classes are reported separately: these are differences the check observed that the
oracle did not.
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
OUT_DIR = os.path.join(ROOT, "results", "v2", "planted")

RUNNER = r'''
import copy, datetime as dt, json, sqlite3, sys
from accrete import runtime as R
from accrete import ui as U
db = sqlite3.connect(sys.argv[1])
meta = dict(db.execute("select key, value from meta"))
model = json.loads(meta["model"])
world = {"records": {}, "next_id": json.loads(meta.get("next_id", "{}")), "outbox": [],
         "outbox_next": int(meta.get("outbox_next", "1"))}
for eid, rid, data in db.execute("select eid, rid, data from records"):
    world["records"].setdefault(eid, {})[rid] = json.loads(data)
for (row,) in db.execute("select json from outbox order by id"):
    world["outbox"].append(json.loads(row))
seq = json.load(open(sys.argv[2]))
now = dt.datetime(2026, 3, 1, 12, 0)
out = []
for q in seq:
    n0 = len(world["outbox"])
    try:
        if q["kind"] == "ui":
            r = U.handle(model, world, q["path"], q["user"], now)
            r = [r[0], r[1] if isinstance(r[1], str) else json.dumps(r[1], sort_keys=True, default=str)]
        else:
            st, body = R.handle(model, world, q["method"], q["path"], q.get("query") or {}, q.get("body"), q["user"], now)
            r = [st, json.dumps(body, sort_keys=True, default=str)]
    except Exception as exc:
        r = ["EXC", type(exc).__name__ + ": " + str(exc)[:200]]
    out.append(r + [json.dumps(world["outbox"][n0:], sort_keys=True, default=str)])
final = json.dumps({"records": world["records"], "outbox": world["outbox"]}, sort_keys=True, default=str)
print(json.dumps({"responses": out, "final": final}))
'''


def load_model(app):
    db = sqlite3.connect(os.path.join(app, "app.db"))
    meta = dict(db.execute("select key, value from meta"))
    recs = {}
    for eid, rid, data in db.execute("select eid, rid, data from records"):
        recs.setdefault(eid, {})[rid] = json.loads(data)
    db.close()
    return json.loads(meta["model"]), recs


# ------------------------------------------------------------------ static "uses the construct" predicates
def _exprs(model):
    return json.dumps(model)


def _effects_emit_then_can_fail(effects, seen_emit=False):
    """True if some path emits and later has a fail/write/create/delete that can fail."""
    for eff in effects or []:
        if not isinstance(eff, dict):
            continue
        for k in ("then", "else", "do"):
            if k in eff and _effects_emit_then_can_fail(eff[k], seen_emit):
                return True
        if "emit" in eff:
            if any(x in eff for x in ("set", "create", "update", "delete")):
                return True  # writes in the same step are checked afterwards
            seen_emit = True
            if "for" in eff or "in" in eff:
                return True
            continue
        if seen_emit and any(x in eff for x in ("fail", "set", "create", "update", "delete")):
            return True
    return False


def uses(mutant, model):
    ents = list(model["entities"].values())
    fields = [f for e in ents for f in e["fields"].values()]
    actions = [a for e in ents for a in e["actions"].values()]
    text = _exprs(model)
    has = {
        "count+1": "count(" in text,
        "days+1": "days(" in text,
        "guard-before-allow": any(a.get("allow") not in (None, "", "True") and a.get("guard") not in (None, "", "True") for a in actions),
        "list-desc": True,
        "list-ignores-read": any((e.get("rules") or {}).get("read") not in (None, "", "True") for e in ents),
        "date-format": any(f["type"] == "datetime" for f in fields),
        "required-skipped": any(f.get("required") and not f.get("computed") and not f.get("system") for f in fields),
        "unique-skipped": any(f.get("unique") for f in fields),
        "write-if-ignored": any(f.get("write_if") for f in fields),
        "number-rounding": any(f["type"] == "number" and not f.get("computed") for f in fields),
        "ui-forms-ignore-guard": any(a.get("guard") not in (None, "", "True") for a in actions),
        "rollback-keeps-outbox": any(_effects_emit_then_can_fail(a.get("effects")) for a in actions)
        or any(_effects_emit_then_can_fail(t.get("effects") or t.get("do")) for e in ents
               for t in (e.get("triggers") or {}).values() if isinstance(t, dict)),
        "unknown-filter-ignored": True,
        "defaults-on-provided-null": any(f.get("default") not in (None, "") and not f.get("computed") for f in fields),
    }
    return has.get(mutant, True)


# ------------------------------------------------------------------ request sequences
def perturb(v, f, rng, recs_by_name):
    t = f["type"]
    r = rng.random()
    if r < 0.12:
        return None
    if t == "number":
        return round(rng.choice([v if isinstance(v, (int, float)) else 1, 10, 0.01]) * rng.choice([1, 1.5, 3.17]) + rng.choice([0, 0.005, 0.125, 2.375]), 3)
    if t == "integer":
        return (v if isinstance(v, int) and not isinstance(v, bool) else 1) + rng.choice([-1, 0, 1, 5])
    if t == "bool":
        return rng.choice([True, False])
    if t == "date":
        return rng.choice(["2026-02-27", "2026-03-01", "2026-03-02", "2026-04-15", "2025-12-31"])
    if t == "datetime":
        return rng.choice(["2026-02-27T09:30:00", "2026-03-01T12:00:00", "2026-03-08T12:00:01"])
    if t == "ref":
        ids = sorted(recs_by_name.get(f.get("ref"), {}))
        return rng.choice(ids + [999]) if ids else v
    if f.get("values"):
        return rng.choice(list(f["values"]) + ["bogus"])
    if t == "text":
        return rng.choice([v, (v or "") + "-x", "", "  ", v])
    return v


def sequence(model, recs, rng, n):
    ue_id = [e for e in model["entities"].values() if e["id"] == model.get("users", {}).get("entity")]
    ents = list(model["entities"].values())
    key = model.get("users", {}).get("key")
    users = [None]
    for e in ents:
        if model.get("users") and e["id"] == model["users"].get("entity"):
            users += [d.get(key) for _, d in sorted(recs.get(e["id"], {}).items())]
    if len(users) == 1:
        users = [None] + sorted({str(v) for d in recs.values() for r in d.values() for v in [r.get(key)] if v})[:10]
    seq = []
    for _ in range(n):
        e = rng.choice(ents)
        rows = recs.get(e["id"], {})
        ids = sorted(int(i) for i in rows) or [1]
        rid = rng.choice(ids + [ids[-1] + 50])
        u = rng.choice(users)
        flds = [f for f in e["fields"].values() if not f.get("computed")]
        sample = rows.get(str(rng.choice(ids))) or rows.get(rng.choice(ids)) or {}
        k = rng.random()
        if k < 0.18:
            q = {}
            if rng.random() < 0.6 and e["fields"]:
                f = rng.choice(list(e["fields"].values()))
                v = sample.get(f["id"])
                q[f["name"] if rng.random() < 0.9 else "no_such_field"] = "null" if v is None else str(v).lower() if isinstance(v, bool) else str(v)
            seq.append({"kind": "api", "method": "GET", "path": f"/api/{e['name']}", "query": q, "user": u})
        elif k < 0.32:
            seq.append({"kind": "api", "method": "GET", "path": f"/api/{e['name']}/{rid}", "user": u})
        elif k < 0.42:
            p = rng.choice([f"/ui/{e['name']}", f"/ui/{e['name']}/{rid}", f"/ui/{e['name']}/new"])
            seq.append({"kind": "ui", "path": p, "user": u})
        elif k < 0.60:
            body = {}
            for f in flds:
                if f.get("system") or rng.random() < 0.15:
                    continue
                v = sample.get(f["id"])
                body[f["name"]] = v if rng.random() < 0.7 else perturb(v, f, rng, {x["id"]: recs.get(x["id"], {}) for x in ents})
            for u2 in [u] + rng.sample(users, min(3, len(users))):
                seq.append({"kind": "api", "method": "POST", "path": f"/api/{e['name']}", "body": body, "user": u2})
        elif k < 0.76:
            body = {}
            for f in rng.sample(flds, min(len(flds), rng.choice([1, 1, 2, 3]))):
                v = sample.get(f["id"])
                body[f["name"]] = v if rng.random() < 0.3 else perturb(v, f, rng, {x["id"]: recs.get(x["id"], {}) for x in ents})
            for u2 in [u] + rng.sample(users, min(3, len(users))):
                seq.append({"kind": "api", "method": "PATCH", "path": f"/api/{e['name']}/{rid}", "body": body, "user": u2})
        elif k < 0.80:
            seq.append({"kind": "api", "method": "DELETE", "path": f"/api/{e['name']}/{rid}", "user": u})
        else:
            if not e["actions"]:
                continue
            a = rng.choice(list(e["actions"].values()))
            body = {}
            for pn, p in (a.get("params") or {}).items():
                if rng.random() < 0.1:
                    continue
                if p.get("type") == "ref" and p.get("ref"):
                    pids = sorted(int(i) for i in recs.get(p["ref"], {})) or [1]
                    body[pn] = rng.choice(pids + [999])
                elif p.get("values"):
                    body[pn] = rng.choice(list(p["values"]))
                else:
                    body[pn] = perturb(None if p.get("type") != "text" else "note", {"type": p.get("type", "text")}, rng, {})
                    if body[pn] is None and p.get("type") == "text":
                        body[pn] = "reason"
            for u2 in [u] + rng.sample(users, min(3, len(users))):
                seq.append({"kind": "api", "method": "POST", "path": f"/api/{e['name']}/{rid}/{a['name']}", "body": body, "user": u2})
    return seq


def run_seq(app, seq_file, engine_path, work):
    r = subprocess.run([sys.executable, "-c", RUNNER, os.path.join(os.path.abspath(app), "app.db"), seq_file],
                       env=dict(os.environ, PYTHONPATH=engine_path), capture_output=True, text=True, cwd=work, timeout=1800)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {"error": r.stderr[-500:]}


def main(mutants_file=None, name="", seqlen=3000, seeds=(1, 2)):
    import planted_engine as PE
    mutants = PE.MUTANTS if not mutants_file else [tuple(m) for m in json.load(open(mutants_file))]
    study = os.path.join(OUT_DIR, f"engine{name and '_' + name}.json") if name else os.path.join(OUT_DIR, "engine.json")
    det = {}
    if os.path.exists(study):
        for m in json.load(open(study)):
            for a in m.get("per_app", []):
                det[(m["mutant"], a["app"])] = (a["check"], a["acceptance_tests_fail"])
    work = tempfile.mkdtemp(prefix="eng-oracle-")
    rows = []
    try:
        targets = PE.apps()
        engines = {}
        for mid, desc, fname, old, new in mutants:
            eng = os.path.join(work, f"engine-{mid}")
            shutil.copytree(os.path.join(ROOT, "accrete"), os.path.join(eng, "accrete"), ignore=shutil.ignore_patterns("__pycache__"))
            p = os.path.join(eng, "accrete", fname)
            text = open(p).read()
            if old not in text:
                print(mid, "PATCH FAILED")
                continue
            open(p, "w").write(text.replace(old, new, 1))
            engines[mid] = eng
        for cset, app_name, src in targets:
            model, recs = load_model(src)
            label = f"{cset}:{app_name}"
            seqs = []
            for s in seeds:
                rng = random.Random(f"{s}-{label}")
                f = os.path.join(work, f"seq-{cset}-{app_name}-{s}.json")
                json.dump(sequence(model, recs, rng, seqlen), open(f, "w"))
                seqs.append(f)
            ref = [run_seq(src, f, ROOT, work) for f in seqs]
            for mid, eng in engines.items():
                diffs, first = 0, None
                for f, r0 in zip(seqs, ref):
                    r1 = run_seq(src, f, eng, work)
                    if "error" in r0 or "error" in r1:
                        diffs += 1
                        first = first or (r0.get("error") or r1.get("error"))[-160:]
                        continue
                    for i, (a, b) in enumerate(zip(r0["responses"], r1["responses"])):
                        if a != b:
                            diffs += 1
                            if first is None:
                                q = json.load(open(f))[i]
                                first = {"request": q, "correct": [str(x)[:160] for x in a], "bug": [str(x)[:160] for x in b]}
                    if r0["final"] != r1["final"]:
                        diffs += 1
                        first = first or "final stored state differs"
                check, tests_fail = det.get((mid, label), (None, None))
                used = uses(mid, model)
                harmful = bool(diffs) or bool(tests_fail)
                cls = "harmful" if harmful else ("unaffected" if not used else "unexercised")
                rows.append({"mutant": mid, "app": label, "class": cls, "oracle_differences": diffs,
                             "acceptance_tests_fail": tests_fail, "construct_used": used,
                             "check_detected": check == "DIFFERENT", "example": first})
            print(label, "done", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    summary = {}
    for mid in engines:
        rs = [r for r in rows if r["mutant"] == mid]
        h = [r for r in rs if r["class"] == "harmful"]
        summary[mid] = {"apps": len(rs), "harmful": len(h), "detected_among_harmful": sum(r["check_detected"] for r in h),
                        "unaffected": sum(r["class"] == "unaffected" for r in rs),
                        "unexercised": sum(r["class"] == "unexercised" for r in rs),
                        "check_detected_outside_harmful": sum(r["check_detected"] for r in rs if r["class"] != "harmful"),
                        "harmful_by_sequences_only": sum(1 for r in h if r["oracle_differences"] and not r["acceptance_tests_fail"]),
                        "harmful_by_tests_only": sum(1 for r in h if r["acceptance_tests_fail"] and not r["oracle_differences"])}
    out = os.path.join(OUT_DIR, f"engine_oracle{name and '_' + name}.json")
    json.dump({"summary": summary, "rows": rows, "seqlen": seqlen, "seeds": list(seeds)}, open(out, "w"), indent=1, default=str)
    print(f"{'mutant':26} {'harm':>4} {'det':>4} {'unaff':>5} {'unex':>4} {'det-outside':>11}")
    for mid, s in summary.items():
        print(f"{mid:26} {s['harmful']:4} {s['detected_among_harmful']:4} {s['unaffected']:5} {s['unexercised']:4} {s['check_detected_outside_harmful']:11}")
    return summary


if __name__ == "__main__":
    a = sys.argv[1:]
    mf = a[a.index("--mutants") + 1] if "--mutants" in a else None
    nm = a[a.index("--out") + 1] if "--out" in a else ""
    sl = int(a[a.index("--seqlen") + 1]) if "--seqlen" in a else 3000
    main(mf, nm, sl)
