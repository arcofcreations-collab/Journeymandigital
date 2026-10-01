"""v2 experiment runner: repeated trials, clean starts, repairs, full cost to a correct result.

  python harness/experiment2.py prepare SET ID SYSTEM TRIAL       -> workspace + PROMPT.txt (attempt 1)
  python harness/experiment2.py verify  SET ID SYSTEM TRIAL       -> scores the latest attempt
  python harness/experiment2.py record  SET ID SYSTEM TRIAL duration_ms tool_uses tokens
  python harness/experiment2.py repair  SET ID SYSTEM TRIAL       -> REPAIR_PROMPT.txt for the next attempt
  python harness/experiment2.py extra   SET ID SYSTEM TRIAL seconds "note"   (engine changes etc., counted in the cost)
  python harness/experiment2.py status  SET

SYSTEM is `accrete2` (accrete v2: engine at the v2 freeze, docs/GUIDE.md) or `baseline2` (the
baseline apps with the v2 tooling and documentation in baseline_v2/). Each trial has its own
workspace; a chained challenge starts from the same system's and trial's final result of the
previous step (after its repairs), never from another trial. Workspaces never contain other
trials' or other systems' work.

Cost to a correct result = the sum over attempts of the implementing agent's duration, plus the
harness verification time of every attempt, plus recorded extra work (e.g. engine changes and
their regression checks). A trial that is still failing after the last allowed repair is
recorded as not correct (its cost is reported, and it counts as a failure).
"""
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
SCRATCH = os.environ.get("ACCRETE_RUNS2", "/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/runs2")
CHALLENGES = os.path.join(ROOT, "challenges")
RESULTS = os.path.join(ROOT, "results", "v2")
BASE_APPS = {"accrete2": os.path.join(ROOT, "apps"), "baseline2": os.path.join(ROOT, "baseline_v2")}
MAX_REPAIRS = 2
SYSTEM_TEXT = {
    "accrete2": ("This application is built with accrete. {ws}/GUIDE.md is its complete documentation: read it "
                 "first, then use the `accrete` command (installed). Change the application only through "
                 "`accrete apply` (never edit app.db or other files in the app directory by hand)."),
    "baseline2": ("This application is a conventional Flask + SQLite application. {ws}/app/README.md is its "
                  "complete documentation (structure, tooling, tests, migrations): read it first. Change it as a "
                  "skilled engineer would: keep the code clean, add a migration for schema or data changes, update "
                  "and run its tests."),
}
PROMPT = """You are a software engineer applying one change request to an existing application.

Rules:
- Work ONLY inside {ws}. Do not read, list or search anything outside it, with one exception:
  {client} is the public test client the evaluators use (the same for every team). You may read and
  import it (tests that look for `../../harness` from the app directory find it there); do not modify it.
- Your very first action: run `date -u +%s.%N > {ws}/t_start_{n}`. Your very last action: run `date -u +%s.%N > {ws}/t_end_{n}`.

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
REPAIR = """You are a software engineer. A change request was implemented in this application, but acceptance
testing found problems. Fix them.

Rules:
- Work ONLY inside {ws}. Do not read, list or search anything outside it, with one exception:
  {client} is the public test client the evaluators use. You may read and import it; do not modify it.
- Your very first action: run `date -u +%s.%N > {ws}/t_start_{n}`. Your very last action: run `date -u +%s.%N > {ws}/t_end_{n}`.

{system}

The application instance is {ws}/app (contract: {ws}/CONTRACT.md, requirements: {ws}/REQUIREMENTS.md{history}).
The change request that was implemented:
--------------
{brief}
--------------

Problems reported by acceptance testing (observed behaviour; the tests themselves are not available):
{problems}

Fix the application so the change request is met and everything else keeps working. Existing data
must be preserved. Update {ws}/app/CHANGE_NOTES.md (or, if the request must not be executed as
stated, leave behaviour unchanged and write {ws}/app/CLARIFICATION.md).

When finished, reply with one line: DONE or CLARIFICATION.
"""


def meta(cset, cid):
    with open(os.path.join(CHALLENGES, cset, cid, "meta.json")) as fh:
        return json.load(fh)


def chain(cset, cid):
    out, m = [], meta(cset, cid)
    while m.get("depends_on"):
        m = meta(cset, m["depends_on"])
        out.insert(0, m)
    return out


def ws_path(cset, cid, system, trial):
    return os.path.join(SCRATCH, cset, cid, system, f"t{trial}")


def res_dir(cset, cid, system, trial):
    d = os.path.join(RESULTS, cset, cid, system, f"t{trial}")
    os.makedirs(d, exist_ok=True)
    return d


def state(cset, cid, system, trial):
    p = os.path.join(res_dir(cset, cid, system, trial), "trial.json")
    return json.load(open(p)) if os.path.exists(p) else {"id": cid, "system": system, "trial": trial, "attempts": []}


def save_state(cset, cid, system, trial, st):
    with open(os.path.join(res_dir(cset, cid, system, trial), "trial.json"), "w") as fh:
        json.dump(st, fh, indent=1)


def _engine_rev():
    rev = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "accrete", "baseline_v2", "docs/GUIDE.md"],
                           capture_output=True, text=True).stdout.strip()
    return rev + ("+dirty" if dirty else "")


def _common(cset, cid, system, trial):
    m = meta(cset, cid)
    ws = ws_path(cset, cid, system, trial)
    client = os.path.join(os.path.dirname(ws), "harness", "accept_client.py")
    history = ""
    if chain(cset, cid):
        history = f", as changed by the earlier requests in {ws}/HISTORY.md"
    return m, ws, client, history


def prepare(cset, cid, system, trial):
    m, ws, client, history = _common(cset, cid, system, trial)
    if os.path.exists(ws):
        shutil.rmtree(ws)
    os.makedirs(ws)
    if m.get("depends_on"):
        prev = ws_path(cset, m["depends_on"], system, trial)
        prev_state = state(cset, m["depends_on"], system, trial)
        if not os.path.exists(os.path.join(prev, "app")) or not prev_state.get("finished"):
            raise SystemExit(f"run {m['depends_on']} trial {trial} for {system} to completion first")
        src = os.path.join(prev, "app")
    else:
        src = os.path.join(BASE_APPS[system], m["app"])
    shutil.copytree(src, os.path.join(ws, "app"), ignore=shutil.ignore_patterns(
        "__pycache__", ".pytest_cache", "CHANGE_NOTES.md", "CLARIFICATION.md", ".dev_snapshot*"))
    os.makedirs(os.path.dirname(client), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "harness", "accept_client.py"), client)
    shutil.copy(os.path.join(ROOT, "spec", "CONTRACT.md"), os.path.join(ws, "CONTRACT.md"))
    shutil.copy(os.path.join(ROOT, "spec", "apps", f"{m['app']}.md"), os.path.join(ws, "REQUIREMENTS.md"))
    prev = chain(cset, cid)
    if prev:
        with open(os.path.join(ws, "HISTORY.md"), "w") as fh:
            fh.write("# Changes already applied to this application (in order)\n\n")
            for p in prev:
                fh.write(f"## {p['id']}\n\n{p['brief']}\n\n")
    if system == "accrete2":
        shutil.copy(os.path.join(ROOT, "docs", "GUIDE.md"), os.path.join(ws, "GUIDE.md"))
    # base-suite results of the starting state (regressions are relative to it)
    before = os.path.join(res_dir(cset, cid, system, trial), "base_before.json")
    subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), os.path.join(ws, "app"),
                    os.path.join(CHALLENGES, "base", f"test_{m['app']}_base.py"), "--json", before],
                   env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness")), capture_output=True, text=True)
    st = {"id": cid, "set": cset, "system": system, "trial": trial, "app": m["app"], "categories": m["categories"],
          "expect_rejection": m.get("expect_rejection", False), "version": _engine_rev(), "attempts": [], "extra": []}
    save_state(cset, cid, system, trial, st)
    text = PROMPT.format(ws=ws, client=client, n=1, system=SYSTEM_TEXT[system].format(ws=ws), brief=m["brief"], history=history)
    with open(os.path.join(ws, "PROMPT.txt"), "w") as fh:
        fh.write(text)
    print(os.path.join(ws, "PROMPT.txt"))


def _superseded(cset, cid):
    return set(meta(cset, cid).get("superseded_base_tests", []))


def verify(cset, cid, system, trial):
    t0 = time.time()
    m, ws, client, history = _common(cset, cid, system, trial)
    st = state(cset, cid, system, trial)
    n = len(st["attempts"])
    if n == 0:
        raise SystemExit("record the attempt first")
    app = os.path.join(ws, "app")
    rd = res_dir(cset, cid, system, trial)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness"))
    runs = {}
    for name, target in [("hidden", os.path.join(CHALLENGES, cset, cid, f"test_{cid}.py")),
                         ("base", os.path.join(CHALLENGES, "base", f"test_{m['app']}_base.py"))]:
        jf = os.path.join(rd, f"attempt{n}-{name}.json")
        subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), app, target, "--json", jf],
                       env=env, capture_output=True, text=True)
        runs[name] = json.load(open(jf))
    sup = _superseded(cset, cid)
    before = json.load(open(os.path.join(rd, "base_before.json")))
    passed_before = {r["test"].split("::")[-1] for r in before["results"] if r["passed"]}
    regressions = [r for r in runs["base"]["results"] if not r["passed"] and r["test"].split("::")[-1] not in sup
                   and r["test"].split("::")[-1] in passed_before]
    a = st["attempts"][-1]
    a["hidden_passed"], a["hidden_total"] = runs["hidden"]["passed"], runs["hidden"]["total"]
    a["hidden_failures"] = [r["test"].split("::")[-1] + ": " + r["message"][:300] for r in runs["hidden"]["results"] if not r["passed"]]
    a["regressions"] = [r["test"].split("::")[-1] + ": " + r["message"][:300] for r in regressions]
    a["clarification_written"] = os.path.exists(os.path.join(app, "CLARIFICATION.md"))
    a["success"] = a["hidden_total"] > 0 and a["hidden_passed"] == a["hidden_total"] and not regressions
    for k in ("t_start", "t_end"):
        p = os.path.join(ws, f"{k}_{n}")
        a[k] = float(open(p).read().strip()) if os.path.exists(p) else None
    a["verify_s"] = round(time.time() - t0, 1)
    if a["success"] or n > MAX_REPAIRS:
        st["finished"] = True
        st["correct"] = a["success"]
        st["correct_at_attempt"] = n if a["success"] else None
    st["cost_s"] = round(sum((x.get("duration_ms") or 0) / 1000 + (x.get("verify_s") or 0) for x in st["attempts"])
                         + sum(e["seconds"] for e in st.get("extra", [])), 1)
    st["tokens"] = sum(x.get("tokens") or 0 for x in st["attempts"])
    st["tool_uses"] = sum(x.get("tool_uses") or 0 for x in st["attempts"])
    save_state(cset, cid, system, trial, st)
    print(json.dumps({"id": cid, "system": system, "trial": trial, "attempt": n, "success": a["success"],
                      "hidden": f"{a['hidden_passed']}/{a['hidden_total']}", "regressions": len(regressions),
                      "finished": st.get("finished", False), "cost_s": st["cost_s"]}))


def record(cset, cid, system, trial, duration_ms, tool_uses, tokens):
    st = state(cset, cid, system, trial)
    st["attempts"].append({"attempt": len(st["attempts"]) + 1, "duration_ms": int(duration_ms), "tool_uses": int(tool_uses),
                           "tokens": int(tokens)})
    save_state(cset, cid, system, trial, st)
    print("recorded attempt", len(st["attempts"]))


def repair(cset, cid, system, trial):
    m, ws, client, history = _common(cset, cid, system, trial)
    st = state(cset, cid, system, trial)
    if st.get("finished"):
        raise SystemExit("trial finished; nothing to repair")
    a = st["attempts"][-1]
    problems = [f"- {x}" for x in a.get("hidden_failures", [])] + [f"- (previously working behaviour) {x}" for x in a.get("regressions", [])]
    n = len(st["attempts"]) + 1
    text = REPAIR.format(ws=ws, client=client, n=n, system=SYSTEM_TEXT[system].format(ws=ws), brief=m["brief"],
                         history=history, problems="\n".join(problems))
    p = os.path.join(ws, f"REPAIR_PROMPT_{n}.txt")
    with open(p, "w") as fh:
        fh.write(text)
    print(p)


def extra(cset, cid, system, trial, seconds, note):
    st = state(cset, cid, system, trial)
    st.setdefault("extra", []).append({"seconds": float(seconds), "note": note})
    save_state(cset, cid, system, trial, st)


def status(cset):
    base = os.path.join(RESULTS, cset)
    for cid in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        for system in ("accrete2", "baseline2"):
            d = os.path.join(base, cid, system)
            if not os.path.isdir(d):
                continue
            for t in sorted(os.listdir(d)):
                p = os.path.join(d, t, "trial.json")
                if os.path.exists(p):
                    s = json.load(open(p))
                    att = s.get("attempts", [])
                    print(f"{cid} {system:9} {t} attempts={len(att)} finished={s.get('finished', False)} correct={s.get('correct')} "
                          f"cost={s.get('cost_s')}s")


if __name__ == "__main__":
    c = sys.argv[1]
    args = sys.argv[2:]
    if c == "prepare":
        prepare(args[0], args[1], args[2], int(args[3]))
    elif c == "verify":
        verify(args[0], args[1], args[2], int(args[3]))
    elif c == "record":
        record(args[0], args[1], args[2], int(args[3]), *args[4:7])
    elif c == "repair":
        repair(args[0], args[1], args[2], int(args[3]))
    elif c == "extra":
        extra(args[0], args[1], args[2], int(args[3]), args[4], args[5])
    elif c == "status":
        status(args[0])
