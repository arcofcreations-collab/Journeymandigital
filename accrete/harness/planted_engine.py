"""Engine-upgrade study: does `accrete upgrade-check` catch behaviour changes caused by the engine?

  python harness/planted_engine.py      -> results/v2/planted/engine.json (+ printed table)

For every application available (the 3 base apps and the final app of every v1 accrete run), a
golden snapshot is recorded with the current engine. Then each planted engine bug (a realistic
"upgrade" regression, as a source patch on a temporary copy of the engine) is installed in a
subprocess and `upgrade_check` is run on every app. A bug counts as detected for an app when
the check reports DIFFERENT. The independent oracle is the app's own hidden/base acceptance
tests run with the buggy engine: they tell whether the bug is observable in that app at all.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from accrete import change as C  # noqa: E402

RUNS = os.environ.get("ACCRETE_RUNS", "/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/runs")
OUT = os.path.join(ROOT, "results", "v2", "planted")

# (id, description, file, old text, new text)
MUTANTS = [
    ("count+1", "count() reports one too many when anything matches", "expr.py",
     "    return len(_where(items, where))", "    n = len(_where(items, where))\n    return n + 1 if n else 0"),
    ("days+1", "days(n) adds an extra day", "expr.py", "    return _dt.timedelta(days=n)", "    return _dt.timedelta(days=n + 1)"),
    ("guard-before-allow", "action error precedence: 409 guard checked before 403 allow", "runtime.py",
     "    if not can_read(ctx, ent, rid) or not action_allowed(ctx, ent, rec, action, params):\n        halt(403",
     "    if not action_possible(ctx, ent, rec, action, params):\n        halt(409, 'not possible')\n    if not can_read(ctx, ent, rid) or not action_allowed(ctx, ent, rec, action, params):\n        halt(403"),
    ("list-desc", "lists returned in descending id order", "runtime.py",
     "    for rid in sorted(records(ctx.world, ent[\"id\"])):\n        if not can_read(ctx, ent, rid):",
     "    for rid in sorted(records(ctx.world, ent[\"id\"]), reverse=True):\n        if not can_read(ctx, ent, rid):"),
    ("list-ignores-read", "lists ignore the read rule", "runtime.py",
     "    for rid in sorted(records(ctx.world, ent[\"id\"])):\n        if not can_read(ctx, ent, rid):\n            continue",
     "    for rid in sorted(records(ctx.world, ent[\"id\"])):\n        if False:\n            continue"),
    ("date-format", "datetimes serialised with a space instead of T", "runtime.py",
     "        return v.replace(microsecond=0).isoformat()\n    if isinstance(v, dt.date):",
     "        return v.replace(microsecond=0).isoformat(sep=' ')\n    if isinstance(v, dt.date):"),
    ("required-skipped", "required fields not enforced", "runtime.py",
     "            if f.get(\"required\"):\n                errors[f[\"name\"]] = \"is required\"",
     "            if False:\n                errors[f[\"name\"]] = \"is required\""),
    ("unique-skipped", "uniqueness not enforced", "runtime.py",
     "                    errors[f[\"name\"]] = \"must be unique\"", "                    pass"),
    ("write-if-ignored", "field-level write permissions ignored", "runtime.py",
     "        if f.get(\"write_if\") and not _safe_test(", "        if False and not _safe_test("),
    ("number-rounding", "numbers stored with 1 decimal", "runtime.py",
     "        return round(float(v), 6) if not isinstance(v, bool) else float(v)",
     "        return round(float(v), 1) if not isinstance(v, bool) else float(v)"),
    ("ui-forms-ignore-guard", "UI shows action forms even when the guard fails", "ui.py",
     "        if R.action_allowed(ctx, ent, rec, a, {}) and R.action_possible(ctx, ent, rec, a, {}):",
     "        if R.action_allowed(ctx, ent, rec, a, {}):"),
    ("rollback-keeps-outbox", "failed requests keep the messages they emitted", "runtime.py",
     "        del self.world[\"outbox\"][self.outbox_mark:]\n        self.world[\"next_id\"]",
     "        self.world[\"next_id\"]"),
    ("unknown-filter-ignored", "unknown filters silently return []", "runtime.py",
     "        halt(400, \"unknown filter\", {k: \"no such field\" for k in unknown})", "        return 200, {\"items\": []}"),
    ("defaults-on-provided-null", "defaults overwrite explicit values", "runtime.py",
     "        if f.get(\"computed\") or f[\"id\"] in provided:", "        if f.get(\"computed\"):"),
]


def apps():
    out = [("base", a, os.path.join(ROOT, "apps", a)) for a in ("library", "expenses", "maintenance")]
    for cset in ("dev", "eval"):
        for d in sorted(glob.glob(os.path.join(RUNS, cset, "*", "accrete", "app"))):
            cid = d.split(os.sep)[-3]
            out.append((cset, cid, d))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    work = tempfile.mkdtemp(prefix="planted-engine-")
    targets = []
    for cset, name, src in apps():
        dst = os.path.join(work, f"{cset}-{name}")
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
        C.snapshot(dst)
        targets.append((cset, name, dst))
    engine_src = os.path.join(ROOT, "accrete")
    results = []
    for mid, desc, fname, old, new in MUTANTS:
        eng = os.path.join(work, f"engine-{mid}")
        shutil.copytree(engine_src, os.path.join(eng, "accrete"), ignore=shutil.ignore_patterns("__pycache__"))
        p = os.path.join(eng, "accrete", fname)
        text = open(p).read()
        if old not in text:
            results.append({"mutant": mid, "description": desc, "error": "patch did not apply"})
            print(mid, "PATCH FAILED")
            continue
        open(p, "w").write(text.replace(old, new, 1))
        script = ("import json,sys\nfrom accrete import change as C\nout={}\nfor d in sys.argv[1:]:\n"
                  "    r=C.upgrade_check(d); out[d]=[r['verdict'], r.get('differences'), r.get('probes')]\nprint(json.dumps(out))")
        r = subprocess.run([sys.executable, "-c", script] + [t[2] for t in targets], env=dict(os.environ, PYTHONPATH=eng),
                           capture_output=True, text=True, cwd=work)
        try:
            checks = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            results.append({"mutant": mid, "description": desc, "error": r.stderr[-300:]})
            print(mid, "ERROR", r.stderr[-300:])
            continue
        per_app = []
        for cset, name, d in targets:
            verdict, ndiff, nprobes = checks[d]
            # independent oracle: does the app's own acceptance test fail under the buggy engine?
            test = (os.path.join(ROOT, "challenges", "base", f"test_{name}_base.py") if cset == "base"
                    else os.path.join(ROOT, "challenges", cset, name, f"test_{name}.py"))
            t = subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), d, test],
                               env=dict(os.environ, PYTHONPATH=eng + os.pathsep + os.path.join(ROOT, "harness")),
                               capture_output=True, text=True, cwd=work)
            last = (t.stdout.strip().splitlines() or ["?"])[-1]
            try:
                passed, total = map(int, last.split()[0].split("/"))
                tests_fail = passed < total
            except Exception:  # noqa: BLE001
                tests_fail = None
            per_app.append({"app": f"{cset}:{name}", "check": verdict, "differences": ndiff, "probes": nprobes,
                            "acceptance_tests_fail": tests_fail})
        det = sum(1 for a in per_app if a["check"] == "DIFFERENT")
        obs = sum(1 for a in per_app if a["acceptance_tests_fail"])
        both_missed = sum(1 for a in per_app if a["acceptance_tests_fail"] and a["check"] != "DIFFERENT")
        results.append({"mutant": mid, "description": desc, "apps": len(per_app), "detected_in_apps": det,
                        "tests_fail_in_apps": obs, "observable_by_tests_but_missed": both_missed, "per_app": per_app})
        print(f"{mid:26} detected in {det:2}/{len(per_app)} apps; acceptance tests fail in {obs:2}; "
              f"tests fail but check missed: {both_missed}")
    json.dump(results, open(os.path.join(OUT, "engine.json"), "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
