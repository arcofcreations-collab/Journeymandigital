"""Run a test file against a reference state with temp copies kept inside the workspace.

usage: python _ref/run.py <state_name> <test_file> [-q]
Prints failing tests (or all with -v). Exit 0 iff all pass.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
TMP = os.path.join(WS, "_tmp")


def run(state, test_file):
    os.makedirs(TMP, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=TMP)
    out = os.path.join(tmp, "result.json")
    env = dict(os.environ, TMPDIR=tmp)
    subprocess.run([sys.executable, os.path.join(WS, "harness", "run_acceptance.py"),
                    os.path.join(HERE, "states", state), test_file, "--json", out],
                   env=env, capture_output=True, text=True)
    try:
        with open(out) as fh:
            res = json.load(fh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


if __name__ == "__main__":
    res = run(sys.argv[1], sys.argv[2])
    verbose = "-v" in sys.argv
    for r in res["results"]:
        if verbose or not r["passed"]:
            print(("PASS " if r["passed"] else "FAIL ") + r["test"].split("::")[-1] + ("" if r["passed"] else "  -> " + r["message"][:400]))
    print(f"{res['passed']}/{res['total']}", res.get("pytest_tail", "")[-1500:])
    sys.exit(0 if res["total"] and res["passed"] == res["total"] else 1)
