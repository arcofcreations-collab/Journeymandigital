"""Experiment runner: prepare isolated workspaces, verify results, record measurements.

  python harness/experiment.py prepare SET ID SYSTEM      -> prints the workspace and the agent prompt
  python harness/experiment.py verify  SET ID SYSTEM      -> hidden tests + base regression suite
  python harness/experiment.py record  SET ID SYSTEM duration_ms tool_uses tokens
  python harness/experiment.py summary SET

SYSTEM is `accrete` or `baseline`. Workspaces live outside the repository (in the session
scratchpad) so implementers cannot see hidden tests or each other's work. Both systems get the
same prompt apart from one paragraph that points at their own documentation.
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.environ.get("ACCRETE_RUNS", "/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/runs")
CHALLENGES = os.path.join(ROOT, "challenges")
RESULTS = os.path.join(ROOT, "results")
BASE_APPS = {"accrete": os.path.join(ROOT, "apps"), "baseline": os.path.join(ROOT, "baseline")}
SYSTEM_TEXT = {
    "accrete": ("This application is built with accrete. {ws}/GUIDE.md is its complete documentation: read it "
                "first, then use the `accrete` command (installed). Change the application only through "
                "`accrete apply` (never edit app.db or other files in the app directory by hand)."),
    "baseline": ("This application is a conventional Flask + SQLite application. {ws}/app/README.md explains its "
                 "structure, tests and migrations. Change it as a skilled engineer would: keep the code clean, add "
                 "a migration for schema or data changes, update and run its tests."),
}
PROMPT = """You are a software engineer applying one change request to an existing application.

Rules:
- Work ONLY inside {ws}. Do not read, list or search anything outside it.
- Your very first action: run `date -u +%s.%N > {ws}/t_start`. Your very last action: run `date -u +%s.%N > {ws}/t_end`.

{system}

The application instance is {ws}/app. It implements the external contract in {ws}/CONTRACT.md and the
requirements in {ws}/REQUIREMENTS.md{history}. Everything in those documents must keep working
except where this change request intentionally alters it. Existing data must be preserved or
migrated as the request requires.

CHANGE REQUEST
--------------
{brief}
--------------

Carry the change out completely: implement it, migrate existing data where needed, and verify the
result yourself (the application in {ws}/app must work when loaded through {ws}/app/app_entry.py).
If the request must not be executed as stated (contradictory, unsafe, or too ambiguous to implement
correctly), leave the application's behaviour unchanged and write {ws}/app/CLARIFICATION.md explaining
why and what decision is needed. Otherwise write {ws}/app/CHANGE_NOTES.md (a few lines: your
interpretation, what you changed, how you verified it).

When finished, reply with one line: DONE or CLARIFICATION.
"""


def load_meta(cset, cid):
    with open(os.path.join(CHALLENGES, cset, cid, "meta.json")) as fh:
        return json.load(fh)


def ws_path(cset, cid, system):
    return os.path.join(SCRATCH, cset, cid, system)


def chain(cset, cid):
    out = []
    meta = load_meta(cset, cid)
    while meta.get("depends_on"):
        meta = load_meta(cset, meta["depends_on"])
        out.insert(0, meta)
    return out


def prepare(cset, cid, system):
    meta = load_meta(cset, cid)
    ws = ws_path(cset, cid, system)
    if os.path.exists(ws):
        shutil.rmtree(ws)
    os.makedirs(ws)
    if meta.get("depends_on"):
        src = os.path.join(ws_path(cset, meta["depends_on"], system), "app")
        if not os.path.exists(src):
            raise SystemExit(f"run {meta['depends_on']} for {system} first")
    else:
        src = os.path.join(BASE_APPS[system], meta["app"])
    shutil.copytree(src, os.path.join(ws, "app"), ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache",
                                                                                "CHANGE_NOTES.md", "CLARIFICATION.md"))
    shutil.copy(os.path.join(ROOT, "spec", "CONTRACT.md"), os.path.join(ws, "CONTRACT.md"))
    shutil.copy(os.path.join(ROOT, "spec", "apps", f"{meta['app']}.md"), os.path.join(ws, "REQUIREMENTS.md"))
    history = ""
    prev = chain(cset, cid)
    if prev:
        with open(os.path.join(ws, "HISTORY.md"), "w") as fh:
            fh.write("# Changes already applied to this application (in order)\n\n")
            for m in prev:
                fh.write(f"## {m['id']}\n\n{m['brief']}\n\n")
        history = f", as changed by the earlier requests in {ws}/HISTORY.md"
    if system == "accrete":
        shutil.copy(os.path.join(ROOT, "docs", "GUIDE.md"), os.path.join(ws, "GUIDE.md"))
    rev = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "accrete"], capture_output=True, text=True).stdout.strip()
    with open(os.path.join(ws, "VERSION"), "w") as fh:
        fh.write(rev + ("+dirty" if dirty else "") + "\n")
    prompt = PROMPT.format(ws=ws, system=SYSTEM_TEXT[system].format(ws=ws), brief=meta["brief"], history=history)
    with open(os.path.join(ws, "PROMPT.txt"), "w") as fh:
        fh.write(prompt)
    print(prompt)


def _superseded(cset, cid):
    # each challenge lists every base test that is false in the state after it (cumulative over its chain)
    return set(load_meta(cset, cid).get("superseded_base_tests", []))


def verify(cset, cid, system):
    meta = load_meta(cset, cid)
    ws = ws_path(cset, cid, system)
    app = os.path.join(ws, "app")
    res_dir = os.path.join(RESULTS, cset, cid)
    os.makedirs(res_dir, exist_ok=True)
    out = {"id": cid, "system": system, "app": meta["app"], "categories": meta["categories"],
           "expect_rejection": meta.get("expect_rejection", False)}
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness"))
    # hidden tests for this challenge (and the chain it builds on)
    tests = [os.path.join(CHALLENGES, cset, m["id"], f"test_{m['id']}.py") for m in [meta]]
    runs = {}
    for name, target in [("hidden", tests[0]), ("base", os.path.join(CHALLENGES, "base", f"test_{meta['app']}_base.py"))]:
        jf = os.path.join(res_dir, f"{system}-{name}.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), app, target, "--json", jf],
                       env=env, capture_output=True, text=True)
        with open(jf) as fh:
            runs[name] = json.load(fh)
    sup = _superseded(cset, cid)
    base_results = [r for r in runs["base"]["results"] if r["test"].split("::")[-1] not in sup]
    regressions = [r["test"].split("::")[-1] for r in base_results if not r["passed"]]
    out["hidden_passed"], out["hidden_total"] = runs["hidden"]["passed"], runs["hidden"]["total"]
    out["hidden_failures"] = [r["test"].split("::")[-1] + ": " + r["message"][:200] for r in runs["hidden"]["results"] if not r["passed"]]
    out["base_checked"] = len(base_results)
    out["regressions"] = regressions
    out["clarification_written"] = os.path.exists(os.path.join(app, "CLARIFICATION.md"))
    out["success"] = (out["hidden_total"] > 0 and out["hidden_passed"] == out["hidden_total"] and not regressions)
    vp = os.path.join(ws, "VERSION")
    out["accrete_version"] = open(vp).read().strip() if os.path.exists(vp) else None
    for name in ("t_start", "t_end"):
        p = os.path.join(ws, name)
        out[name] = float(open(p).read().strip()) if os.path.exists(p) else None
    if out["t_start"] and out["t_end"]:
        out["self_timed_s"] = round(out["t_end"] - out["t_start"], 1)
    path = os.path.join(res_dir, f"{system}.json")
    if os.path.exists(path):
        with open(path) as fh:
            prev = json.load(fh)
        for k in ("duration_ms", "tool_uses", "tokens"):
            if k in prev:
                out[k] = prev[k]
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: out[k] for k in ("id", "system", "success", "hidden_passed", "hidden_total", "regressions", "clarification_written")}))


def record(cset, cid, system, duration_ms, tool_uses, tokens):
    path = os.path.join(RESULTS, cset, cid, f"{system}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d = json.load(open(path)) if os.path.exists(path) else {"id": cid, "system": system}
    d.update(duration_ms=int(duration_ms), tool_uses=int(tool_uses), tokens=int(tokens))
    with open(path, "w") as fh:
        json.dump(d, fh, indent=1)
    print("recorded", cid, system, duration_ms, tool_uses, tokens)


def summary(cset):
    rows = []
    base = os.path.join(RESULTS, cset)
    for cid in sorted(os.listdir(base)):
        for system in ("accrete", "baseline"):
            p = os.path.join(base, cid, f"{system}.json")
            if os.path.exists(p):
                rows.append(json.load(open(p)))
    print(f"{'id':5} {'system':9} {'ok':3} {'hidden':8} {'regr':5} {'min':>6} {'tools':>5} {'ktok':>6}")
    for r in rows:
        print(f"{r['id']:5} {r['system']:9} {'Y' if r.get('success') else 'n':3} "
              f"{str(r.get('hidden_passed')) + '/' + str(r.get('hidden_total')):8} {len(r.get('regressions', [])):5} "
              f"{(r.get('duration_ms') or 0) / 60000:6.1f} {r.get('tool_uses', 0):5} {(r.get('tokens') or 0) / 1000:6.0f}")
    return rows


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "prepare":
        prepare(*sys.argv[2:5])
    elif cmd == "verify":
        verify(*sys.argv[2:5])
    elif cmd == "record":
        record(*sys.argv[2:8])
    elif cmd == "summary":
        summary(sys.argv[2])
