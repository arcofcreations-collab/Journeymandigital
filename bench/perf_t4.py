"""T4: runtime for one 100,000-row column on this machine (single process).

Cases: (a) worst case, forced through the surrogate randomisation test;
(b) sorted panel resolved by structure; (c) unambiguous column. Best of 3.
"""
import json
import os
import random
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dmguard.core import resolve_column  # noqa: E402

rng = random.Random(5)
worst = [date(2000 + rng.randrange(20), rng.randrange(1, 13), rng.randrange(1, 13)).strftime("%d/%m/%Y")
         for _ in range(100_000)]
panel_days = [date(2000, 1, 1) + timedelta(days=i // 10) for i in range(300_000)]
panel = [d.strftime("%m/%d/%Y") for d in panel_days if d.day <= 12][:100_000]
unamb = [(date(2000, 1, 1) + timedelta(days=i // 10)).strftime("%m/%d/%Y") for i in range(100_000)]
cases = {
    "worst_case_forced_surrogate_test": (worst, dict(threshold_bits=0.0, min_z=float("inf"))),
    "default_on_unsorted_random": (worst, {}),
    "sorted_panel_structure": (panel, {}),
    "unambiguous_validity": (unamb, {}),
}
out = {}
for name, (vals, kw) in cases.items():
    best = min(_time for _time in (
        (lambda: (lambda t: (resolve_column(vals, **kw), time.perf_counter() - t)[1])(time.perf_counter()))()
        for _ in range(3)))
    r = resolve_column(vals, **kw)
    out[name] = {"rows": len(vals), "seconds_best_of_3": round(best, 3), "verdict": r.verdict, "method": r.method}
    print(name, out[name])
os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
with open(os.path.join(os.path.dirname(__file__), "results", "perf_t4.json"), "w") as fh:
    json.dump(out, fh, indent=1)
