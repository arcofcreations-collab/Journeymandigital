"""Run acceptance test files against an application instance.

usage: python run_acceptance.py <instance_dir> <test_file_or_dir> [--json out.json]
Prints pass/fail per test; exit code 0 only if all pass.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    inst, tests = sys.argv[1], sys.argv[2]
    out = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    env = dict(os.environ, ACCEPT_TARGET=os.path.abspath(inst),
               PYTHONPATH=HERE + os.pathsep + os.environ.get("PYTHONPATH", ""))
    report = os.path.join("/tmp", f"accept-{os.getpid()}.xml")
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", tests,
                        f"--junitxml={report}"], env=env, capture_output=True, text=True)
    dt = time.time() - t0
    import xml.etree.ElementTree as ET
    results = []
    if os.path.exists(report):
        for tc in ET.parse(report).getroot().iter("testcase"):
            failed = tc.find("failure") is not None or tc.find("error") is not None
            msg = ""
            for tag in ("failure", "error"):
                el = tc.find(tag)
                if el is not None:
                    msg = (el.get("message") or "")[:300]
            results.append({"test": f"{tc.get('classname')}::{tc.get('name')}", "passed": not failed, "message": msg})
        os.remove(report)
    summary = {"instance": inst, "tests": tests, "passed": sum(r["passed"] for r in results),
               "total": len(results), "seconds": round(dt, 2), "results": results,
               "pytest_tail": p.stdout[-2000:] if not results else ""}
    if out:
        with open(out, "w") as fh:
            json.dump(summary, fh, indent=1)
    for r in results:
        print(("PASS " if r["passed"] else "FAIL ") + r["test"] + ("" if r["passed"] else "  -> " + r["message"]))
    print(f"{summary['passed']}/{summary['total']} passed in {dt:.1f}s")
    if not results:
        print(p.stdout[-3000:], p.stderr[-2000:])
    sys.exit(0 if results and summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
