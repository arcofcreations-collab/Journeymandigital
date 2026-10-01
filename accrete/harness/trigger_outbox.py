"""Find and independently verify requests that trigger the `rollback-keeps-outbox` engine bug.

  python harness/trigger_outbox.py      -> results/v2/planted/rollback_outbox_triggers.json

The planted engine bug "failed requests keep the messages they emitted" matters only for a
request that emits a message and then fails, for example:
- a `fail` effect after an `emit`;
- a constraint violated by the effects (checked after them);
- an error in a later effect or trigger.

Step 1 (search, correct engine): for every application in the engine study corpus, enumerate
requests:
- every user x every action on every record, with parameter bodies built from the declared
  parameter types and values found in stored data;
- creates and PATCHes built from existing records.

Instrument `Ctx.rollback` to record when a failed request had appended messages before rolling
back.

Step 2 (independent verification): for each triggering request found (at most 3 per app), copy the
application twice. Run the request through the `accrete call` command line, once with the correct
engine and once with the mutated engine (a patched copy on PYTHONPATH, exactly as in
planted_engine.py). Then read the stored outbox and records straight from each copy's app.db with
sqlite3. This bypasses accrete's runtime and checker.

Step 3: if no application in the corpus can trigger it, a minimal application is built: the base
library app plus one action whose effects emit a message and then fail. The same independent
verification is run on it, to show what the bug does once triggered.
"""
from __future__ import annotations

import copy
import itertools
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "harness"))
from accrete import model as M  # noqa: E402
from accrete import runtime as R  # noqa: E402
from accrete.store import Store  # noqa: E402
import planted_engine as PE  # noqa: E402

OUT = os.path.join(ROOT, "results", "v2", "planted", "rollback_outbox_triggers.json")
NOW = R.parse_now("2026-03-01T12:00:00") if hasattr(R, "parse_now") else None
MUTANT = [m for m in PE.MUTANTS if m[0] == "rollback-keeps-outbox"][0]


def apps():
    out = PE.apps()
    runs2 = os.environ.get("ACCRETE_RUNS2", os.path.join(os.path.dirname(PE.RUNS), "runs2"))
    for cset in ("dev", "eval"):
        for d in sorted(__import__("glob").glob(os.path.join(runs2, cset, "*", "accrete2", "t1", "app"))):
            out.append((f"v2{cset}", d.split(os.sep)[-4], d))
    return out


def values_for(model, world, p, rng):
    t = p.get("type")
    if p.get("values"):
        return list(p["values"]) + ["zzz"]
    if t == "ref" and p.get("ref"):
        ids = sorted(R.records(world, p["ref"]))
        return ids[:3] + ids[-2:] + [999999]
    base = {"text": ["x", ""], "number": [0, 1.25, 1000000.5, -1], "integer": [0, 1, 7, 1000000, -1],
            "bool": [True, False], "date": ["2026-03-01", "2027-01-01", "2020-01-01"],
            "datetime": ["2026-03-01T12:00:00", "2030-01-01T00:00:00"]}.get(t)
    if base is not None:
        return base
    # structured parameters (lists of items etc.): items built from field names of other entities
    samples = [[], None]
    for e in model["entities"].values():
        ids = sorted(R.records(world, e["id"]))
        if ids:
            samples.append([{"part": ids[0], "quantity": 1}])
            samples.append([{e["name"].rstrip("s"): ids[0], "quantity": 10 ** 6}])
            samples.append(ids[:2])
    rng.shuffle(samples)
    return samples[:8]


def bodies(model, world, action, rng, limit=24):
    params = action.get("params") or {}
    if not params:
        return [{}]
    names = sorted(params)
    pools = [values_for(model, world, params[n], rng) for n in names]
    combos = list(itertools.product(*pools))
    rng.shuffle(combos)
    out = [{}] + [dict(zip(names, c)) for c in combos[:limit]]
    return out


def search(model, world, rng):
    hits = []
    orig = R.Ctx.rollback

    def spy(self):
        if len(self.world["outbox"]) > self.outbox_mark:
            spy.flag = [m["channel"] for m in self.world["outbox"][self.outbox_mark:]]
        return orig(self)

    R.Ctx.rollback = spy
    try:
        ue = M.user_entity(model)
        key = model["users"]["key"] if ue else None
        users = [d.get(key) for _, d in sorted(R.records(world, ue["id"]).items())] if ue else [None]
        now = R.parse_now("2026-03-01T12:00:00")
        for e in model["entities"].values():
            for rid in sorted(R.records(world, e["id"])):
                for a in e["actions"].values():
                    for body in bodies(model, world, a, rng):
                        for u in users:
                            spy.flag = None
                            w = copy.deepcopy(world)
                            status, out = R.handle(model, w, "POST", f"/api/{e['name']}/{rid}/{a['name']}", {}, body, u, now)
                            if spy.flag and status >= 400:
                                hits.append({"user": u, "method": "POST", "path": f"/api/{e['name']}/{rid}/{a['name']}",
                                             "body": body, "status": status, "emitted_then_rolled_back": spy.flag,
                                             "response": out})
                                if len(hits) >= 3:
                                    return hits
    finally:
        R.Ctx.rollback = orig
    return hits


def mutant_engine(work):
    eng = os.path.join(work, "engine-mutant")
    if os.path.exists(os.path.join(eng, "accrete")):
        return eng
    shutil.copytree(os.path.join(ROOT, "accrete"), os.path.join(eng, "accrete"), ignore=shutil.ignore_patterns("__pycache__"))
    p = os.path.join(eng, "accrete", MUTANT[2])
    text = open(p).read()
    assert MUTANT[3] in text
    open(p, "w").write(text.replace(MUTANT[3], MUTANT[4], 1))
    return eng


def stored(app):
    db = sqlite3.connect(os.path.join(app, "app.db"))
    out = {"outbox": [json.loads(r[0]) for r in db.execute("select json from outbox order by id")],
           "records": sorted(db.execute("select eid, rid, data from records").fetchall())}
    db.close()
    return out


def verify(src, hit, work):
    res = {}
    for name, pp in (("correct", ROOT), ("mutant", mutant_engine(work))):
        app = os.path.join(work, f"app-{name}")
        shutil.rmtree(app, ignore_errors=True)
        shutil.copytree(src, app, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
        before = stored(app)
        cmd = [sys.executable, "-m", "accrete.cli", "call", app, hit["method"], hit["path"], "--now", "2026-03-01T12:00:00", "--commit"]
        if hit["user"] is not None:
            cmd += ["--as", hit["user"]]
        if hit["body"] is not None:
            cmd += ["--body", json.dumps(hit["body"])]
        r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH=pp), capture_output=True, text=True, cwd=work)
        after = stored(app)
        res[name] = {"cli_output": (r.stdout + r.stderr)[-400:], "outbox_added": after["outbox"][len(before["outbox"]):],
                     "records_changed": before["records"] != after["records"]}
    res["harmful"] = res["mutant"]["outbox_added"] != res["correct"]["outbox_added"]
    return res


def minimal_app(work):
    """Base library + one action that emits and then fails (a realistic 'notify, then refuse' slip)."""
    app = os.path.join(work, "minimal-library")
    shutil.copytree(os.path.join(ROOT, "apps", "library"), app, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
    change = os.path.join(work, "notify.yaml")
    with open(change, "w") as fh:
        fh.write("""request: "Librarians can send a reminder for a loan; reminders for returned loans are refused"
interpretation: "emit first, then refuse returned loans (the order matters only on failure)"
ops:
  - add_action:
      entity: loans
      name: remind
      allow: "user.role == 'librarian'"
      effects:
        - emit: reminder
          payload: {loan: record}
        - fail: "'loan already returned'"
          when: "record.returned_at is not None"
""")
    r = subprocess.run([sys.executable, "-m", "accrete.cli", "apply", app, change], env=dict(os.environ, PYTHONPATH=ROOT),
                       capture_output=True, text=True)
    return app, r.stdout[-600:] + r.stderr[-300:]


def main():
    rng = random.Random(5)
    work = tempfile.mkdtemp(prefix="trig-outbox-")
    report = {"apps": [], "minimal": None}
    try:
        logged = {}
        if os.environ.get("TRIGGER_FROM_LOG"):  # reuse a completed search (its log lines) after a later crash
            for line in open(os.environ["TRIGGER_FROM_LOG"]):
                p = line.split()
                if len(p) >= 2 and ":" in p[0] and p[1].isdigit():
                    logged[p[0]] = int(p[1])
        for cset, name, d in apps():
            if f"{cset}:{name}" in logged and logged[f"{cset}:{name}"] == 0:
                report["apps"].append({"app": f"{cset}:{name}", "triggering_requests_found": 0, "verified": [],
                                       "from_log": True})
                continue
            tmp_app = os.path.join(work, "load-copy")
            shutil.rmtree(tmp_app, ignore_errors=True)
            shutil.copytree(d, tmp_app, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
            model, world = Store(tmp_app).load()  # a copy: opening a store adds tables
            hits = search(model, world, rng)
            entry = {"app": f"{cset}:{name}", "triggering_requests_found": len(hits), "verified": []}
            for h in hits[:3]:
                v = verify(d, h, os.path.join(work, f"{cset}-{name}"))
                entry["verified"].append({"request": {k: h[k] for k in ("user", "method", "path", "body", "status")},
                                          "emitted_then_rolled_back": h["emitted_then_rolled_back"], **v})
            report["apps"].append(entry)
            print(entry["app"], len(hits), [v["harmful"] for v in entry["verified"]], flush=True)
        if not any(e["triggering_requests_found"] for e in report["apps"]):
            mw = os.path.join(work, "minimal")
            os.makedirs(mw)
            app, log = minimal_app(mw)
            model, world = Store(app).load()
            hits = search(model, world, rng)
            report["minimal"] = {"apply_log": log, "triggering_requests_found": len(hits),
                                 "verified": [dict(request={k: h[k] for k in ("user", "method", "path", "body", "status")},
                                                   **verify(app, h, mw)) for h in hits[:2]]}
            # does the upgrade check (golden snapshot of the minimal app) catch the bug?
            script = ("import json,sys\nfrom accrete import change as C\nr=C.upgrade_check(sys.argv[1]);"
                      "print(json.dumps([r['verdict'], r.get('differences')]))")
            subprocess.run([sys.executable, "-c", "import sys;from accrete import change as C;C.snapshot(sys.argv[1])", app],
                           env=dict(os.environ, PYTHONPATH=ROOT), capture_output=True, text=True)
            r = subprocess.run([sys.executable, "-c", script, app], env=dict(os.environ, PYTHONPATH=mutant_engine(mw + "x")),
                               capture_output=True, text=True)
            report["minimal"]["upgrade_check_with_mutant"] = (r.stdout.strip().splitlines() or [r.stderr[-300:]])[-1]
            print("minimal", report["minimal"]["triggering_requests_found"], report["minimal"]["upgrade_check_with_mutant"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    json.dump(report, open(OUT, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
