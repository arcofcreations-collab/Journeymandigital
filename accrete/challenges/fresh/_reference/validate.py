"""Validate challenge set F01-F14 against the private reference implementation.

For every challenge:
  * hidden tests all pass on the reference state with the change applied;
  * they do not all pass on the state before the change (for expect_rejection challenges exactly
    test_clarification_written fails before);
  * the base tests failing on the changed state are exactly meta.superseded_base_tests, and every
    listed name exists in the base suite.
Also checks that every base suite passes on the unchanged reference.
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build  # noqa: E402
from run import run  # noqa: E402

BEFORE = {"F01": "expenses_base", "F02": "expenses_F01", "F03": "expenses_F02", "F04": "expenses_F03",
          "F05": "expenses_F04", "F06": "expenses_F05", "F07": "maintenance_base", "F08": "maintenance_base",
          "F09": "maintenance_base", "F10": "library_base", "F11": "library_base", "F12": "library_base",
          "F13": "expenses_base", "F14": "expenses_base"}


def base_names(app):
    tree = ast.parse(open(os.path.join(WS, "tests", "base", f"test_{app}_base.py")).read())
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def failing(res):
    return {r["test"].split("::")[-1] for r in res["results"] if not r["passed"]}


def main():
    build.main()
    ok = True
    report = []
    for app in ("library", "expenses", "maintenance"):
        res = run(f"{app}_base", os.path.join(WS, "tests", "base", f"test_{app}_base.py"))
        good = res["total"] > 0 and not failing(res)
        ok &= good
        report.append(f"base {app}: {res['passed']}/{res['total']} {'OK' if good else 'FAIL'}")
    for cid in sorted(BEFORE):
        d = os.path.join(WS, "challenges", "fresh", cid)
        meta = json.load(open(os.path.join(d, "meta.json")))
        app = meta["app"]
        after = f"{app}_{cid}"
        test = os.path.join(d, f"test_{cid}.py")
        ra = run(after, test)
        rb = run(BEFORE[cid], test)
        fb = failing(rb)
        rbase = run(after, os.path.join(WS, "tests", "base", f"test_{app}_base.py"))
        sup = set(meta["superseded_base_tests"])
        problems = []
        if failing(ra) or ra["total"] == 0:
            problems.append(f"after fails {sorted(failing(ra))}")
        if meta["expect_rejection"]:
            if fb != {"test_clarification_written"}:
                problems.append(f"before failing set {sorted(fb)} != clarification only")
        elif not fb:
            problems.append("all hidden tests already pass before the change")
        missing = sup - base_names(app)
        if missing:
            problems.append(f"unknown superseded names {sorted(missing)}")
        if failing(rbase) != sup:
            problems.append(f"superseded mismatch: extra={sorted(failing(rbase) - sup)} missing={sorted(sup - failing(rbase))}")
        if meta["depends_on"] and BEFORE[cid] != f"{app}_{meta['depends_on']}":
            problems.append("depends_on does not match the before state")
        ok &= not problems
        report.append(f"{cid} {app:<11} after {ra['passed']}/{ra['total']}  before {rb['passed']}/{rb['total']}  "
                      f"base-after {rbase['passed']}/{rbase['total']} (superseded {len(sup)})  "
                      + ("OK" if not problems else "PROBLEMS: " + "; ".join(problems)))
    print("\n".join(report))
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
