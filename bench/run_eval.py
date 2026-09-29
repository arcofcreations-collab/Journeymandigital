"""Run all methods on a split and write raw + summary results.

usage: python bench/run_eval.py DEV|TEST
"""

import json
import math
import os
import platform
import random
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from cases import generate  # noqa: E402
from methods import METHODS, outcome  # noqa: E402

import dmguard  # noqa: E402

OUTCOMES = ("correct", "silent_wrong", "abstain", "error")


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def cluster_bootstrap(records, method, what, reps=2000, seed=1):
    by_src = defaultdict(list)
    for r in records:
        by_src[r["source"]].append(r["outcomes"][method] == what)
    srcs = sorted(by_src)
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        k = n = 0
        for _ in srcs:
            xs = by_src[srcs[rng.randrange(len(srcs))]]
            k += sum(xs)
            n += len(xs)
        stats.append(k / n if n else 0.0)
    stats.sort()
    return (stats[int(0.025 * reps)], stats[int(0.975 * reps) - 1])


def summarise(records, methods, klass):
    rs = [r for r in records if r["klass"] == klass]
    out = {"n": len(rs), "n_sources": len({r["source"] for r in rs})}
    for m in methods:
        cnt = Counter(r["outcomes"][m] for r in rs)
        row = {}
        for o in OUTCOMES:
            lo, hi = wilson(cnt[o], len(rs))
            row[o] = {"k": cnt[o], "rate": cnt[o] / len(rs) if rs else float("nan"),
                      "wilson95": [lo, hi]}
        out[m] = row
    return out


def main():
    split = sys.argv[1] if len(sys.argv) > 1 else "DEV"
    cases = generate(split)
    methods = list(METHODS)
    records = []
    timing = defaultdict(float)
    t0 = time.time()
    for i, c in enumerate(cases):
        rec = {"case_id": c.case_id, "source": c.source, "kind": c.kind, "size": c.size,
               "shuffled": c.shuffled, "render": c.render, "klass": c.klass,
               "n_values": sum(1 for s in c.strings if s), "outcomes": {}}
        for m in methods:
            ts = time.perf_counter()
            status, parsed = METHODS[m](c)
            timing[m] += time.perf_counter() - ts
            rec["outcomes"][m] = outcome(c, status, parsed)
        records.append(rec)
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(cases)} cases, {time.time() - t0:.0f}s", flush=True)

    res_dir = os.path.join(HERE, "results")
    os.makedirs(res_dir, exist_ok=True)
    with open(os.path.join(res_dir, f"raw_{split}.jsonl"), "w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    import duckdb
    import pandas

    summary = {
        "split": split,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"python": platform.python_version(), "pandas": pandas.__version__,
                        "duckdb": duckdb.__version__, "dmguard": dmguard.__version__,
                        "dmguard_threshold_bits": dmguard.DEFAULT_THRESHOLD_BITS,
                        "machine": platform.machine()},
        "n_cases": len(records),
        "classes": dict(Counter(r["klass"] for r in records)),
        "seconds_per_method": {m: round(t, 2) for m, t in timing.items()},
        "by_class": {k: summarise(records, methods, k)
                     for k in ("ambiguous", "unambiguous", "degenerate")},
    }
    amb = [r for r in records if r["klass"] == "ambiguous"]
    summary["cluster_bootstrap95_ambiguous"] = {
        m: {o: cluster_bootstrap(amb, m, o) for o in ("correct", "silent_wrong")}
        for m in methods
    } if amb else {}
    brk = {}
    for key in ("size", "shuffled", "source"):
        groups = defaultdict(list)
        for r in amb:
            groups[str(r[key])].append(r)
        brk[key] = {g: {"n": len(rs), **{m: {o: sum(r["outcomes"][m] == o for r in rs)
                                              for o in OUTCOMES} for m in methods}}
                    for g, rs in sorted(groups.items())}
    summary["ambiguous_breakdown"] = brk
    with open(os.path.join(res_dir, f"summary_{split}.json"), "w") as fh:
        json.dump(summary, fh, indent=1)

    print(f"\n{split}: {len(records)} cases, classes {summary['classes']}")
    for k in ("ambiguous", "unambiguous", "degenerate"):
        s = summary["by_class"][k]
        print(f"\n[{k}] n={s['n']} from {s['n_sources']} source columns")
        print(f"  {'method':16s} " + " ".join(f"{o:>14s}" for o in OUTCOMES))
        for m in methods:
            print(f"  {m:16s} " + " ".join(
                f"{s[m][o]['rate'] * 100:6.1f}% ({s[m][o]['k']:4d})" for o in OUTCOMES))
    print("\nseconds per method:", summary["seconds_per_method"])


if __name__ == "__main__":
    main()
