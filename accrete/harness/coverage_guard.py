"""Coverage regression guard for the reliability studies.

  python harness/coverage_guard.py engine    # engine-upgrade check: per (planted bug, app)
  python harness/coverage_guard.py changes   # change pipeline: per planted change mutant (automatic checks only)

Compares the latest results with every earlier round kept in results/v2/planted/ and lists
everything that an earlier round detected but the latest misses. Exit code 1 if anything
regressed. Rounds are development evidence; the final reliability numbers come from held-out
bugs measured once after the freeze (docs/RELIABILITY.md).
"""
import glob
import json
import os
import sys

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "v2", "planted")


def engine_detected(path):
    out = set()
    for m in json.load(open(path)):
        for a in m.get("per_app", []):
            if a["check"] == "DIFFERENT":
                out.add((m["mutant"], a["app"]))
    return out


def change_detected(path):
    out = set()
    for line in open(path):
        r = json.loads(line)
        if r["category"].startswith("valid"):
            continue
        if r["auto_only"]["verdict"] == "rejected":
            out.add((r["id"], r["category"], r["mutation"]))
    return out


def main(kind):
    if kind == "engine":
        rounds = sorted(glob.glob(os.path.join(D, "engine_round*.json")))
        latest, fn = os.path.join(D, "engine.json"), engine_detected
    else:
        rounds = sorted(glob.glob(os.path.join(D, "raw_round*.jsonl")))
        latest, fn = os.path.join(D, "raw.jsonl"), change_detected
    now = fn(latest)
    lost = set()
    for r in rounds:
        if os.path.abspath(r) == os.path.abspath(latest):
            continue
        before = fn(r)
        missing = before - now
        print(f"{os.path.basename(r)}: detected {len(before)}, latest detects {len(now)}, lost {len(missing)}")
        lost |= missing
    for x in sorted(lost):
        print("  LOST:", x)
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
