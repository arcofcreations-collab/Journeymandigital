"""Fresh adversarial evaluation (SYNTHETIC, truth known by construction).

Seed 777 was not used during development; the families are those of
tests/test_misleading_patterns.py (see docs/SPEC_v3_REVIEW_FIXES.md).
Writes bench/results/adversarial_777.json.
"""
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))

from cases import Case, classify, render  # noqa: E402
from methods import METHODS, outcome  # noqa: E402
from test_misleading_patterns import FAMILIES  # noqa: E402

SEED, PER_FAMILY = 777, 60


def main():
    records = []
    for fam in sorted(FAMILIES):
        rng = random.Random(f"{SEED}-{fam}")
        for i in range(PER_FAMILY):
            ds = [d for d in FAMILIES[fam](rng) if d.day <= 12]
            if not ds:
                continue
            shuffled = rng.random() < 0.4
            if shuffled:
                rng.shuffle(ds)
            truth = [datetime(d.year, d.month, d.day) for d in ds]
            for order in ("DMY", "MDY"):
                c = Case(case_id=f"{fam}#{i}:{order}", split="ADV", source=fam, kind="synthetic",
                         size=len(ds), shuffled=shuffled, render=order, truth=truth,
                         strings=render(truth, order, False), has_time=False, klass=classify(truth))
                rec = {"family": fam, "klass": c.klass, "outcomes": {}}
                for m, fn in METHODS.items():
                    rec["outcomes"][m] = outcome(c, *fn(c))
                records.append(rec)
    amb = [r for r in records if r["klass"] == "ambiguous"]
    summary = {"seed": SEED, "per_family": PER_FAMILY, "n_cases": len(records),
               "n_ambiguous": len(amb), "overall": {}, "by_family": {}}
    for m in METHODS:
        summary["overall"][m] = dict(Counter(r["outcomes"][m] for r in amb))
    by = defaultdict(list)
    for r in amb:
        by[r["family"]].append(r)
    for fam, rs in sorted(by.items()):
        summary["by_family"][fam] = {"n": len(rs), **{m: dict(Counter(r["outcomes"][m] for r in rs))
                                                      for m in METHODS}}
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", f"adversarial_{SEED}.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    n = len(amb)
    print(f"fresh adversarial set (seed {SEED}): {n} ambiguous cases")
    for m in METHODS:
        c = summary["overall"][m]
        print(f"  {m:22s} correct {c.get('correct', 0) / n:6.1%}  silent_wrong "
              f"{c.get('silent_wrong', 0) / n:6.1%}  abstain {c.get('abstain', 0) / n:6.1%}  "
              f"error {c.get('error', 0) / n:6.1%}")
    print("\n  silent-wrong by family (dmguard_v1_0_0 / dmguard / dmguard_accept_likely):")
    for fam, v in summary["by_family"].items():
        print(f"    {fam:22s} n={v['n']:4d}  " + " / ".join(
            str(v[m].get("silent_wrong", 0)) for m in ("dmguard_v1_0_0", "dmguard", "dmguard_accept_likely")))


if __name__ == "__main__":
    main()
