"""Summarise v2 runs: correctness, full cost to a correct result, ratios, variation across trials.

  python harness/analyze_v2.py SET [SET ...]   -> results/v2/analysis_<SET>.json (+ printed tables)

Per run (challenge x system x trial):
- `correct`: the final attempt passes the hidden tests, with no regressions on the base tests.
  For expect_rejection challenges, a clarification must be written and the app left unchanged.
- `cost_s` (time to a correct result): implementing agent durations of every attempt, plus the
  verification time of every attempt, plus recorded extra work.
- `tokens`, `tool_uses`: summed over all attempts.

Runs that never became correct keep their full cost and count as failures. The target compares
medians of per-challenge ratios: baseline cost / accrete cost, using the per-challenge median over
trials.
"""
from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results", "v2")
SYSTEMS = ("accrete2", "baseline2")


def runs(cset):
    out = []
    for f in sorted(glob.glob(os.path.join(RES, cset, "*", "*", "t*", "trial.json"))):
        d = json.load(open(f))
        if d.get("system") not in SYSTEMS:
            continue
        out.append(d)
    return out


def summarise(cset):
    rs = runs(cset)
    ids = sorted({r["id"] for r in rs})
    table, ratios, ratios_by_trial = [], [], {}
    per_sys = {s: {"runs": 0, "finished": 0, "correct": 0, "correct_first_attempt": 0, "repairs": 0,
                   "cost_s": [], "tokens": [], "tool_uses": [], "extra_s": 0.0, "unfinished": 0} for s in SYSTEMS}
    for cid in ids:
        row = {"id": cid}
        med = {}
        for s in SYSTEMS:
            mine = [r for r in rs if r["id"] == cid and r["system"] == s]
            for r in mine:
                p = per_sys[s]
                p["runs"] += 1
                if not r.get("finished"):
                    p["unfinished"] += 1
                    continue
                p["finished"] += 1
                p["correct"] += bool(r.get("correct"))
                p["correct_first_attempt"] += r.get("correct_at_attempt") == 1
                p["repairs"] += max(0, len(r["attempts"]) - 1)
                p["cost_s"].append(r["cost_s"])
                p["tokens"].append(sum(a.get("tokens") or 0 for a in r["attempts"]))
                p["tool_uses"].append(sum(a.get("tool_uses") or 0 for a in r["attempts"]))
                p["extra_s"] += sum(x.get("seconds", 0) for x in r.get("extra", []))
            fin = [r for r in mine if r.get("finished")]
            row[s] = [{"trial": r["trial"], "correct": r.get("correct"), "attempts": len(r["attempts"]),
                       "cost_s": r["cost_s"]} for r in sorted(fin, key=lambda r: r["trial"])]
            if fin:
                med[s] = st.median(r["cost_s"] for r in fin)
                row[s + "_median_cost_s"] = med[s]
                row[s + "_all_correct"] = all(r.get("correct") for r in fin)
        if len(med) == 2 and med["accrete2"] > 0:
            row["ratio"] = round(med["baseline2"] / med["accrete2"], 2)
            ratios.append(row["ratio"])
        for s_trial in {r["trial"] for r in rs if r["id"] == cid}:
            c = {s: [r for r in rs if r["id"] == cid and r["system"] == s and r["trial"] == s_trial and r.get("finished")] for s in SYSTEMS}
            if all(c.values()):
                ratios_by_trial.setdefault(s_trial, []).append(c["baseline2"][0]["cost_s"] / c["accrete2"][0]["cost_s"])
        table.append(row)
    summary = {"set": cset, "challenges": len(ids), "median_ratio": round(st.median(ratios), 2) if ratios else None,
               "ratios": ratios, "per_trial_median_ratio": {t: round(st.median(v), 2) for t, v in sorted(ratios_by_trial.items())},
               "systems": {}}
    for s, p in per_sys.items():
        summary["systems"][s] = {k: v for k, v in p.items() if not isinstance(v, list)}
        for k in ("cost_s", "tokens", "tool_uses"):
            v = p[k]
            summary["systems"][s][k + "_median"] = round(st.median(v), 1) if v else None
            summary["systems"][s][k + "_total"] = round(sum(v), 1) if v else 0
    summary["table"] = table
    json.dump(summary, open(os.path.join(RES, f"analysis_{cset}.json"), "w"), indent=1)
    print(f"== {cset}: {len(ids)} challenges; median ratio (baseline/accrete cost) = {summary['median_ratio']}; "
          f"per trial: {summary['per_trial_median_ratio']}")
    for s, p in summary["systems"].items():
        print(f"  {s:10} runs {p['runs']} finished {p['finished']} correct {p['correct']} (first attempt {p['correct_first_attempt']}), "
              f"repairs {p['repairs']}, median cost {p['cost_s_median']}s, total {p['cost_s_total']}s, "
              f"median tokens {p['tokens_median']}, median tool uses {p['tool_uses_median']}")
    for row in table:
        print(f"  {row['id']}: " + "  ".join(f"{s}=" + ",".join(f"{'ok' if x['correct'] else 'FAIL'}/{x['attempts']}a/{x['cost_s']}s" for x in row.get(s, []))
                                           for s in SYSTEMS) + f"  ratio={row.get('ratio')}")
    return summary


if __name__ == "__main__":
    for c in sys.argv[1:] or ["dev", "eval"]:
        summarise(c)
