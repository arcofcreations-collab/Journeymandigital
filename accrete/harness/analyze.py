"""Aggregate results of a challenge set: success, regressions, time, tool calls, tokens.

  python harness/analyze.py SET [--json OUT]

First attempts are what counts. For challenges re-run after an engine revision, the archived
first attempt is `<system>.attempt1.json`; the latest attempt is reported separately.
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(cset):
    base = os.path.join(ROOT, "results", cset)
    rows = {}
    for cid in sorted(os.listdir(base)):
        for system in ("accrete", "baseline"):
            first = os.path.join(base, cid, f"{system}.attempt1.json")
            last = os.path.join(base, cid, f"{system}.json")
            if os.path.exists(first):
                rows[(cid, system, "first")] = json.load(open(first))
                rows[(cid, system, "latest")] = json.load(open(last)) if os.path.exists(last) else None
            elif os.path.exists(last):
                rows[(cid, system, "first")] = rows[(cid, system, "latest")] = json.load(open(last))
    return rows


def med(xs):
    return statistics.median(xs) if xs else None


def summarize(rows, which):
    out = {}
    ids = sorted({cid for cid, _, _ in rows})
    for system in ("accrete", "baseline"):
        rs = [rows.get((cid, system, which)) for cid in ids]
        rs = [r for r in rs if r and r.get("duration_ms")]
        out[system] = {
            "n": len(rs),
            "success": sum(1 for r in rs if r.get("success")),
            "regressions": sum(len(r.get("regressions", [])) for r in rs),
            "median_min": round(med([r["duration_ms"] / 60000 for r in rs]), 2) if rs else None,
            "mean_min": round(statistics.mean([r["duration_ms"] / 60000 for r in rs]), 2) if rs else None,
            "total_min": round(sum(r["duration_ms"] for r in rs) / 60000, 1),
            "median_tool_calls": med([r["tool_uses"] for r in rs]),
            "median_ktokens": round(med([r["tokens"] / 1000 for r in rs]), 1) if rs else None,
            "total_ktokens": round(sum(r["tokens"] for r in rs) / 1000, 1),
        }
    pairs = []
    for cid in ids:
        a, b = rows.get((cid, "accrete", which)), rows.get((cid, "baseline", which))
        if a and b and a.get("duration_ms") and b.get("duration_ms"):
            pairs.append({"id": cid, "accrete_min": round(a["duration_ms"] / 60000, 2),
                          "baseline_min": round(b["duration_ms"] / 60000, 2),
                          "ratio": round(b["duration_ms"] / a["duration_ms"], 2),
                          "accrete_ok": bool(a.get("success")), "baseline_ok": bool(b.get("success"))})
    out["pairs"] = pairs
    if out["accrete"]["median_min"] and out["baseline"]["median_min"]:
        out["median_time_reduction"] = round(out["baseline"]["median_min"] / out["accrete"]["median_min"], 2)
        out["median_paired_ratio"] = round(med([p["ratio"] for p in pairs]), 2)
        out["token_reduction_total"] = round(out["baseline"]["total_ktokens"] / out["accrete"]["total_ktokens"], 2)
    return out


if __name__ == "__main__":
    cset = sys.argv[1]
    rows = load(cset)
    res = {"first_attempt": summarize(rows, "first"), "latest_attempt": summarize(rows, "latest")}
    for which in ("first_attempt", "latest_attempt"):
        r = res[which]
        print(f"\n== {cset}: {which.replace('_', ' ')}")
        for s in ("accrete", "baseline"):
            x = r[s]
            print(f"  {s:9} correct {x['success']}/{x['n']}  regressions {x['regressions']}  median {x['median_min']} min "
                  f"(mean {x['mean_min']}, total {x['total_min']})  median tools {x['median_tool_calls']}  "
                  f"median ktok {x['median_ktokens']} (total {x['total_ktokens']})")
        if "median_time_reduction" in r:
            print(f"  median time reduction (baseline median / accrete median): {r['median_time_reduction']}x;"
                  f" median of paired ratios: {r['median_paired_ratio']}x; total-token reduction {r['token_reduction_total']}x")
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w") as fh:
            json.dump(res, fh, indent=1)
