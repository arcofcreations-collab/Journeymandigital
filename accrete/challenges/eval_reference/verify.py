import json, os, subprocess, sys, ast
WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INST = {"E01": "m1", "E02": "m2", "E03": "m3", "E04": "m4", "E05": "m5", "E06": "m6", "E07": "m7",
        "E08": "lib_E08", "E09": "lib_E09", "E10": "lib_E10", "E11": "exp_E11", "E12": "exp_E12",
        "E13": "exp_E13", "E14": "lib_E14"}
PREV = {"E01": "maintenance", "E02": "m1", "E03": "m2", "E04": "m3", "E05": "m4", "E06": "m5", "E07": "m6",
        "E08": "lib", "E09": "lib", "E10": "lib", "E11": "exp", "E12": "exp", "E13": "exp", "E14": "lib_E08"}
BASE = {"maintenance": "test_maintenance_base.py", "library": "test_library_base.py", "expenses": "test_expenses_base.py"}

def run(inst, tests):
    out = os.path.join(WS, "_ref", "inst", "_r.json")
    subprocess.run([sys.executable, os.path.join(WS, "harness", "run_acceptance.py"), os.path.join(WS, "_ref", "inst", inst),
                    tests, "--json", out], capture_output=True, text=True)
    d = json.load(open(out))
    return d

ok = True
for cid, inst in INST.items():
    meta = json.load(open(os.path.join(WS, "challenges", "eval", cid, "meta.json")))
    base = os.path.join(WS, "tests", "base", BASE[meta["app"]])
    names = {n.name for n in ast.parse(open(base).read()).body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}
    missing = [t for t in meta["superseded_base_tests"] if t not in names]
    d = run(inst, base)
    failing = sorted(r["test"].split("::")[1] for r in d["results"] if not r["passed"])
    sup = sorted(meta["superseded_base_tests"])
    h = run(inst, os.path.join(WS, "challenges", "eval", cid, f"test_{cid}.py"))
    p = run(PREV[cid], os.path.join(WS, "challenges", "eval", cid, f"test_{cid}.py"))
    match = failing == sup
    ok &= match and not missing and h["passed"] == h["total"]
    print(f"{cid} sup={len(sup):2d} base_fail={len(failing):2d} match={match} missing={missing} hidden={h['passed']}/{h['total']} on_prev_state={p['passed']}/{p['total']}")
    if not match:
        print("   extra failing:", set(failing) - set(sup), " not failing:", set(sup) - set(failing))
print("ALL OK" if ok else "PROBLEMS")
