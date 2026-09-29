"""Choose the evidence threshold (and weekday weight) on the DEV split only.

Selection rule (v2, see docs/ACTIVITY_LOG.md for why v1 was replaced):
maximise DEV utility = auto_correct - 5 * silent_wrong on ambiguous cases
(a silent error is treated as five times worse than an abstention), subject
to silent_wrong <= 2%. Among tied settings prefer weekday weight 1 (plain
sum, no weighting), then the grid threshold nearest the geometric midpoint
of the tied threshold interval (so the choice is not pinned to either edge
of what DEV can distinguish). Writes bench/results/dev_tuning.json.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cases import generate  # noqa: E402

from dmguard.core import resolve_column  # noqa: E402

THRESHOLDS = [0, 2, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40]
WEIGHTS = [1.0]  # weekday weight fixed to a plain sum since method v1.3 (see activity log)


def main():
    cases = [c for c in generate("DEV") if c.klass == "ambiguous"]
    grid = []
    for w in WEIGHTS:
        for tau in THRESHOLDS:
            correct = wrong = abstain = 0
            for c in cases:
                res = resolve_column(c.strings, threshold_bits=tau)
                if not res.resolved:
                    abstain += 1
                elif res.verdict == c.render:
                    correct += 1
                else:
                    wrong += 1
            n = len(cases)
            grid.append({"weekday_weight": w, "threshold_bits": tau, "n": n,
                         "auto_correct": correct / n, "silent_wrong": wrong / n,
                         "abstain": abstain / n})
            print(grid[-1], flush=True)
    for g in grid:
        g["utility"] = round(g["auto_correct"] - 5 * g["silent_wrong"], 9)
    ok = [g for g in grid if g["silent_wrong"] <= 0.02]
    top = max(g["utility"] for g in ok)
    tied = [g for g in ok if g["utility"] == top]
    w = 1.0 if any(g["weekday_weight"] == 1.0 for g in tied) else tied[0]["weekday_weight"]
    taus = [g["threshold_bits"] for g in tied if g["weekday_weight"] == w]
    lo, hi = max(min(taus), 1), max(taus)
    mid = (lo * hi) ** 0.5
    best = min((g for g in tied if g["weekday_weight"] == w),
               key=lambda g: (abs(g["threshold_bits"] - mid), -g["threshold_bits"]))
    os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
    with open(os.path.join(os.path.dirname(__file__), "results", "dev_tuning.json"), "w") as fh:
        json.dump({"chosen": best, "grid": grid}, fh, indent=1)
    for g in grid:
        print(g)
    print("CHOSEN", best)


if __name__ == "__main__":
    main()
