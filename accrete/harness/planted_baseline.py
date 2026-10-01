"""Baseline counterpart of the planted-bug study: how reliable is `python dev.py check`?

  python harness/planted_baseline.py run [--seed S] [--per-run N] [--jobs J]  -> results/v2/planted/baseline_raw.jsonl
  python harness/planted_baseline.py summary                                  -> results/v2/planted/baseline_summary.json

The conventional baseline (baseline_v2) tells its implementers to trust `python dev.py check`
(their tests + the app's existing tests, data.db = seed rebuild, contract/UI scan). This study
plants single bugs into the final applications that baseline2 implementers produced in the v2
development comparison (runs that passed the hidden tests) and asks whether that check rejects
them, in the same categories as the accrete study (harness/planted.py):

* slip:code        one expression on a line the implementer added or changed in the package is
                   mutated (comparison flipped, and/or swapped, `not` dropped, True/False swapped,
                   integer constant +1, error class swapped between 400/403/404/409)
* slip:stored-data one literal or comparison in the implementer's new migration is mutated, and
                   data.db is rebuilt consistently (as a developer who edits a migration would)
* stray-code       the same mutations on an unchanged line of existing permission/service/validation code
* stray-data       the newest migration also changes one unrelated stored value (data.db rebuilt)
* stray-user       the newest migration also changes one user's role or flag (data.db rebuilt)

A mutant is "effective" when an independent oracle sees a difference from the unmutated final
application: every user x every API list and record GET x every action POST on every record
(database restored after each), the raw stored data, and the challenge's hidden + base acceptance
tests (a test that passes on the reference and fails on the mutant). Equivalent mutants are
excluded from detection rates. "Rejected" means `dev.py check` exits non-zero; scan warnings that
the reference did not have are recorded separately (the analogue of accrete's scope warnings).
The unmutated final application is also checked (valid control: should pass).
"""
from __future__ import annotations

import concurrent.futures as cf
import difflib
import glob
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
RUNS2 = os.environ.get("ACCRETE_RUNS2", "/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/runs2")
OUT = os.path.join(ROOT, "results", "v2", "planted")
PACKAGES = {"library": ("library_app", "members"), "expenses": ("expenses_app", "employees"),
            "maintenance": ("maintenance_app", "users")}
ERRORS = ["Forbidden", "Conflict", "ValidationError", "NotFound"]

SWEEP = r'''
import hashlib, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("devmod", sys.argv[1])
dev = importlib.util.module_from_spec(spec); spec.loader.exec_module(dev)
users = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] != "-" else None
c = dev.Copy()
try:
    app = c.app; app.logger.disabled = True
    users = users or c.users()
    colls = dev.api_collections(app); acts = dev.api_actions(app)
    pristine = c.save_db()
    out = {}
    def h(r):
        try:
            body = json.dumps(r.get_json(), sort_keys=True)
        except Exception:
            body = r.get_data(as_text=True)
        return [r.status_code, hashlib.sha1(body.encode()).hexdigest()[:16]]
    ids = {}
    for u in users:
        for coll in colls:
            r = c.request("GET", f"/api/{coll}", u); out[f"GET /api/{coll} {u}"] = h(r)
            if r.status_code == 200:
                ids.setdefault(coll, set()).update(i["id"] for i in r.get_json()["items"])
    for u in users:
        for coll in colls:
            for i in sorted(ids.get(coll, ())):
                out[f"GET /api/{coll}/{i} {u}"] = h(c.request("GET", f"/api/{coll}/{i}", u))
    for u in users:
        for coll, a in acts:
            for i in sorted(ids.get(coll, ())):
                r = c.request("POST", f"/api/{coll}/{i}/{a}", u, body={})
                out[f"POST /api/{coll}/{i}/{a} {u}"] = h(r)
                if r.status_code < 300:
                    out[f"AFTER /api/{coll}/{i}/{a} {u}"] = h(c.request("GET", f"/api/{coll}/{i}", u))
                    c.restore_db(pristine)
    dump = dev.dump_db(dev.DATA_DB, skip_applied_at=True)
    print(json.dumps({"users": users, "responses": out, "data": hashlib.sha1(json.dumps(dump, sort_keys=True, default=str).encode()).hexdigest()}))
finally:
    c.close()
'''


def corpus():
    out = []
    for res in sorted(glob.glob(os.path.join(ROOT, "results", "v2", "*", "*", "baseline2", "t*", "trial.json"))):
        st = json.load(open(res))
        if not st.get("finished") or not st.get("correct"):
            continue
        cset, cid, trial = st["set"], st["id"], st["trial"]
        ws = os.path.join(RUNS2, cset, cid, "baseline2", f"t{trial}")
        if not os.path.exists(os.path.join(ws, "app", "dev.py")):
            continue
        meta = json.load(open(os.path.join(ROOT, "challenges", cset, cid, "meta.json")))
        if meta.get("expect_rejection"):
            continue
        start = (os.path.join(RUNS2, cset, meta["depends_on"], "baseline2", f"t{trial}", "app") if meta.get("depends_on")
                 else os.path.join(ROOT, "baseline_v2", meta["app"]))
        out.append({"set": cset, "id": cid, "trial": trial, "app": meta["app"], "final": os.path.join(ws, "app"),
                    "start": start, "superseded": meta.get("superseded_base_tests", [])})
    return out


# ------------------------------------------------------------------ mutation operators
def line_mutants(line):
    """All single-site textual mutations of one source line (may not compile; filtered later)."""
    out = []
    code = line.split("#", 1)[0]
    if not code.strip() or code.strip().startswith(("def ", "class ", "import ", "from ", "@", '"""', "'''")):
        return out
    for a, b in [("==", "!="), ("!=", "=="), ("<=", "<"), (">=", ">"), (" < ", " <= "), (" > ", " >= "),
                 (" and ", " or "), (" or ", " and "), ("True", "False"), ("False", "True"), (" is None", " is not None"),
                 (" is not None", " is None"), (" in ", " not in "), (" not in ", " in ")]:
        start = 0
        while True:
            k = code.find(a, start)
            if k < 0:
                break
            if not (a == " in " and code[max(0, k - 4):k + 1].endswith(" not ")) and not (a == "==" and code[k - 1:k] in "<>!="):
                out.append(line[:k] + b + line[k + len(a):])
            start = k + len(a)
    m = re.search(r"\bnot\s+", code)
    if m:
        out.append(line[:m.start()] + line[m.end():])
    for m in re.finditer(r"(?<![\w.\"'])(\d+)(?![\w.\"'])", code):
        out.append(line[:m.start()] + str(int(m.group(1)) + 1) + line[m.end():])
    for e in ERRORS:
        for m in re.finditer(r"\b" + e + r"\b", code):
            for f in ERRORS:
                if f != e:
                    out.append(line[:m.start()] + f + line[m.end():])
    return out


def sql_mutants(line):
    out = []
    code = line.split("--", 1)[0]
    if not code.strip():
        return out
    for a, b in [(" = ", " <> "), (" <> ", " = "), (" < ", " <= "), (" > ", " >= "), ("<=", "<"), (">=", ">"),
                 (" AND ", " OR "), (" OR ", " AND "), (" IS NULL", " IS NOT NULL"), (" IS NOT NULL", " IS NULL")]:
        k = code.find(a)
        if k >= 0:
            out.append(line[:k] + b + line[k + len(a):])
    for m in re.finditer(r"(?<![\w.'])(\d+)(?![\w.'])", code):
        out.append(line[:m.start()] + str(int(m.group(1)) + 1) + line[m.end():])
    for m in re.finditer(r"'([a-z_]+)'", code):
        out.append(line[:m.start()] + f"'{m.group(1)}x'" + line[m.end():])
    return out


def changed_lines(start_file, final_file):
    new = open(final_file).read().splitlines()
    old = open(start_file).read().splitlines() if os.path.exists(start_file) else []
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    added, same = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        (same if tag == "equal" else added).extend(range(j1, j2))
    return added, same


def _compiles(path):
    return subprocess.run([sys.executable, "-m", "py_compile", path], capture_output=True).returncode == 0


def make_mutants(item, rng, per_run):
    pkg, user_table = PACKAGES[item["app"]]
    final, start = item["final"], item["start"]
    slips, strays, sql_slips = [], [], []
    for path in sorted(glob.glob(os.path.join(final, pkg, "*.py"))):
        rel = os.path.relpath(path, final)
        added, same = changed_lines(os.path.join(start, rel), path)
        lines = open(path).read().splitlines()
        for n in added:
            for m in line_mutants(lines[n]):
                slips.append(("slip:code", rel, n, m))
        if os.path.basename(path) in ("permissions.py", "services.py", "validation.py"):
            for n in same:
                for m in line_mutants(lines[n]):
                    strays.append(("stray-code", rel, n, m))
    mig_dir = os.path.join(final, pkg, "migrations")
    new_migs = [p for p in sorted(glob.glob(os.path.join(mig_dir, "*.sql")))
                if not os.path.exists(os.path.join(start, pkg, "migrations", os.path.basename(p)))]
    for p in new_migs:
        lines = open(p).read().splitlines()
        for n, line in enumerate(lines):
            if re.search(r"\b(UPDATE|INSERT|SET|WHERE|CASE|WHEN)\b", line, re.I):
                for m in sql_mutants(line):
                    sql_slips.append(("slip:stored-data", os.path.relpath(p, final), n, m))
    rng.shuffle(slips)
    rng.shuffle(strays)
    rng.shuffle(sql_slips)
    chosen = slips[: per_run["slip"]] + sql_slips[: per_run["sql"]] + strays[: per_run["stray"]]
    # stray-data / stray-user: one UPDATE appended to the newest migration (or a new migration)
    conn = sqlite3.connect(os.path.join(final, "data.db"))
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
              if r[0] not in ("schema_version", "sqlite_sequence", user_table) and not r[0].startswith("sqlite")]
    extra = []
    for _ in range(20):
        if not tables:
            break
        t = rng.choice(tables)
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})") if r[1] != "id" and r[5] == 0]
        rows = conn.execute(f"SELECT * FROM {t}").fetchall()
        names = [d[1] for d in conn.execute(f"PRAGMA table_info({t})")]
        if not rows or not cols:
            continue
        row = dict(zip(names, rng.choice(rows)))
        c = rng.choice(cols)
        v = row[c]
        if v is None or (isinstance(v, str) and c.endswith("_id")):
            continue
        new = (v + 1 if isinstance(v, int) else round(v + 1.5, 2) if isinstance(v, float) else v + "x")
        lit = f"'{new}'" if isinstance(new, str) else str(new)
        extra.append(("stray-data", f"UPDATE {t} SET {c} = {lit} WHERE id = {row['id']};"))
        break
    ucols = [r[1] for r in conn.execute(f"PRAGMA table_info({user_table})")]
    users = conn.execute(f"SELECT * FROM {user_table}").fetchall()
    if "role" in ucols and users:
        roles = sorted({u[ucols.index("role")] for u in users})
        u = rng.choice(users)
        other = [r for r in roles if r != u[ucols.index("role")]]
        if other:
            extra.append(("stray-user", f"UPDATE {user_table} SET role = '{rng.choice(other)}' WHERE id = {u[0]};"))
    conn.close()
    return chosen, extra, new_migs


def build_mutant(item, work, mut, new_migs):
    """Copy the final app (+ harness client) and apply one mutant; returns the app dir or None."""
    ws = os.path.join(work, "ws")
    app = os.path.join(ws, "app")
    shutil.copytree(item["final"], app, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".dev"))
    os.makedirs(os.path.join(work, "harness"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "harness", "accept_client.py"), os.path.join(work, "harness"))
    if mut is None:
        return app
    kind = mut[0]
    pkg, _ = PACKAGES[item["app"]]
    if kind in ("slip:code", "stray-code", "slip:stored-data"):
        _, rel, n, newline = mut
        p = os.path.join(app, rel)
        lines = open(p).read().split("\n")
        lines[n] = newline
        open(p, "w").write("\n".join(lines))
        if p.endswith(".py") and not _compiles(p):
            return None
    else:
        _, stmt = mut
        mig_dir = os.path.join(app, pkg, "migrations")
        if new_migs:
            p = os.path.join(mig_dir, os.path.basename(new_migs[-1]))
            open(p, "a").write("\n" + stmt + "\n")
        else:
            nums = [int(os.path.basename(f)[:4]) for f in glob.glob(os.path.join(mig_dir, "*.sql"))]
            open(os.path.join(mig_dir, f"{max(nums) + 1:04d}_adjust.sql"), "w").write("-- data adjustment\n" + stmt + "\n")
    if kind != "slip:code" and kind != "stray-code":
        r = subprocess.run([sys.executable, "seed.py"], cwd=app, capture_output=True, text=True)
        if r.returncode != 0:
            return None
    shutil.rmtree(os.path.join(app, "__pycache__"), ignore_errors=True)
    return app


def sweep(app, users=None):
    r = subprocess.run([sys.executable, "-c", SWEEP, os.path.join(app, "dev.py"), json.dumps(users) if users else "-"],
                       capture_output=True, text=True, cwd=app, timeout=900)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001 - a mutant that breaks the app entirely
        return {"error": (r.stderr or r.stdout)[-400:]}


def acceptance(app, item):
    res = {}
    tests = [os.path.join(ROOT, "challenges", "base", f"test_{item['app']}_base.py"),
             os.path.join(ROOT, "challenges", item["set"], item["id"], f"test_{item['id']}.py")]
    for t in tests:
        out = os.path.join(tempfile.mkdtemp(prefix="pb-acc-"), "r.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), app, t, "--json", out],
                       env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness")), capture_output=True, text=True, timeout=900)
        try:
            for r in json.load(open(out))["results"]:
                res[r["test"]] = r["passed"]
        except Exception:  # noqa: BLE001
            res[t] = False
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    return res


def dev_check(app):
    r = subprocess.run([sys.executable, "dev.py", "check"], cwd=app, capture_output=True, text=True, timeout=1800)
    text = r.stdout + r.stderr
    m = re.search(r"WARN contract/UI scan: (\d+) finding", text)
    return {"rejected": r.returncode != 0, "warnings": int(m.group(1)) if m else 0,
            "tail": "\n".join(text.strip().splitlines()[-6:])[-800:]}


def run_item(item, seed, per_run):
    rng = random.Random(f"{seed}-{item['set']}-{item['id']}-{item['trial']}")
    muts, extra, new_migs = make_mutants(item, rng, per_run)
    rows = []
    base = tempfile.mkdtemp(prefix="pb-")
    try:
        ref_app = build_mutant(item, os.path.join(base, "ref"), None, new_migs)
        ref_check = dev_check(ref_app)
        ref_sweep = sweep(ref_app)
        ref_acc = acceptance(ref_app, item)
        rows.append({"set": item["set"], "id": item["id"], "trial": item["trial"], "kind": "VALID:final",
                     "rejected": ref_check["rejected"], "warnings": ref_check["warnings"], "tail": ref_check["tail"]})
        for k, mut in enumerate(muts + extra):
            work = os.path.join(base, f"m{k}")
            app = build_mutant(item, work, mut, new_migs)
            desc = mut[3] if len(mut) == 4 else mut[1]
            loc = f"{mut[1]}:{mut[2] + 1}" if len(mut) == 4 else "migration"
            row = {"set": item["set"], "id": item["id"], "trial": item["trial"], "kind": mut[0], "where": loc,
                   "mutation": desc.strip()[:200]}
            if app is None:
                row["skipped"] = "does not compile / rebuild failed"
                rows.append(row)
                shutil.rmtree(work, ignore_errors=True)
                continue
            chk = dev_check(app)
            sw = sweep(app, ref_sweep.get("users"))
            acc = acceptance(app, item)
            if "error" in sw:
                diffs, data_diff = ["app does not start: " + sw["error"][-120:]], False
            else:
                diffs = [k2 for k2, v in ref_sweep.get("responses", {}).items() if sw["responses"].get(k2) != v]
                diffs += [k2 for k2 in sw["responses"] if k2 not in ref_sweep.get("responses", {})]
                data_diff = sw.get("data") != ref_sweep.get("data")
            test_fail = sorted(t for t, ok in acc.items() if ref_acc.get(t) and not ok)
            row.update({"effective": bool(diffs or data_diff or test_fail), "oracle_differences": len(diffs),
                        "oracle_examples": diffs[:3], "data_differs": data_diff, "acceptance_failures": test_fail[:5],
                        "rejected": chk["rejected"], "new_warnings": max(0, chk["warnings"] - ref_check["warnings"]),
                        "tail": chk["tail"]})
            rows.append(row)
            shutil.rmtree(work, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return rows


def run(seed=11, per_run=None, jobs=3, name="baseline_raw.jsonl"):
    per_run = per_run or {"slip": 6, "sql": 2, "stray": 3}
    os.makedirs(OUT, exist_ok=True)
    items = corpus()
    print(f"{len(items)} baseline2 runs in the corpus", flush=True)
    path = os.path.join(OUT, name)
    with open(path, "w") as fh, cf.ProcessPoolExecutor(jobs) as ex:
        futs = {ex.submit(run_item, it, seed, per_run): it for it in items}
        for f in cf.as_completed(futs):
            it = futs[f]
            try:
                rows = f.result()
            except Exception as exc:  # noqa: BLE001
                print("SKIP", it["id"], type(exc).__name__, exc, flush=True)
                continue
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            eff = [r for r in rows if r.get("effective")]
            print(f"{it['set']} {it['id']}: {len(rows)} rows, {len(eff)} effective, "
                  f"{sum(r['rejected'] for r in eff)} rejected", flush=True)


def summary(name="baseline_raw.jsonl"):
    rows = [json.loads(l) for l in open(os.path.join(OUT, name))]
    out = {"valid": {}, "mutants": {}}
    valid = [r for r in rows if r["kind"].startswith("VALID")]
    out["valid"] = {"n": len(valid), "rejected": sum(r["rejected"] for r in valid),
                    "rejected_ids": [r["id"] for r in valid if r["rejected"]]}
    kinds = sorted({r["kind"] for r in rows if not r["kind"].startswith("VALID")})
    for k in kinds:
        rs = [r for r in rows if r["kind"] == k and "skipped" not in r]
        eff = [r for r in rs if r["effective"]]
        out["mutants"][k] = {"planted": len(rs), "equivalent": len(rs) - len(eff), "effective": len(eff),
                             "rejected_by_check": sum(r["rejected"] for r in eff),
                             "warned_only": sum(1 for r in eff if not r["rejected"] and r["new_warnings"]),
                             "missed": sum(1 for r in eff if not r["rejected"] and not r["new_warnings"]),
                             "missed_but_hidden_or_base_tests_fail": sum(1 for r in eff if not r["rejected"] and r["acceptance_failures"]),
                             "rejected_equivalent": sum(r["rejected"] for r in rs if not r["effective"])}
    json.dump(out, open(os.path.join(OUT, name.replace("raw", "summary").replace(".jsonl", ".json")), "w"), indent=1)
    print(f"valid controls: {out['valid']['n']}, rejected {out['valid']['rejected']}")
    print(f"{'kind':18} {'eff':>4} {'rejected':>9} {'warned':>7} {'missed':>7}")
    for k, v in out["mutants"].items():
        print(f"{k:18} {v['effective']:4} {v['rejected_by_check']:9} {v['warned_only']:7} {v['missed']:7}")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run":
        seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 11
        jobs = int(a[a.index("--jobs") + 1]) if "--jobs" in a else 3
        run(seed=seed, jobs=jobs)
    elif a and a[0] == "summary":
        summary(a[1] if len(a) > 1 else "baseline_raw.jsonl")
    else:
        print(__doc__)
