"""Print the results tables (markdown) used in docs/RESULTS.md, straight from results/*.

  python harness/report.py > results/tables.md
"""
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import analyze  # noqa: E402


def cell(d):
    if not d:
        return "–", "–", "–", "–", "–"
    ok = "✔" if d.get("success") else "✘"
    return (f"{ok} {d.get('hidden_passed')}/{d.get('hidden_total')}" + (f" r{len(d['regressions'])}" if d.get("regressions") else ""),
            f"{d['duration_ms'] / 60000:.2f}", str(d.get("tool_uses")), f"{d.get('tokens', 0) / 1000:.0f}",
            str(d.get("change_lines", "–")))


def table(cset):
    base = os.path.join(ROOT, "results", cset)
    print(f"\n#### {cset} set: every run (first attempts; ✔/✘ = success, rN = N regressions)\n")
    print("| ID | app | categories | accrete | min | tools | ktok | Δlines | baseline | min | tools | ktok | Δlines | time ratio |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for cid in sorted(os.listdir(base)):
        if not os.path.isdir(os.path.join(base, cid)):
            continue
        meta = json.load(open(os.path.join(ROOT, "challenges", cset, cid, "meta.json")))
        rows = {}
        for s in ("accrete", "baseline"):
            p1 = os.path.join(base, cid, f"{s}.attempt1.json")
            p = os.path.join(base, cid, f"{s}.json")
            rows[s] = json.load(open(p1)) if os.path.exists(p1) else (json.load(open(p)) if os.path.exists(p) else None)
        a, b = cell(rows["accrete"]), cell(rows["baseline"])
        ratio = (f"{rows['baseline']['duration_ms'] / rows['accrete']['duration_ms']:.1f}x"
                 if rows["accrete"] and rows["baseline"] else "–")
        cats = ", ".join(meta["categories"])
        print(f"| {cid} | {meta['app']} | {cats} | " + " | ".join(a) + " | " + " | ".join(b) + f" | {ratio} |")
    later = [cid for cid in sorted(os.listdir(base)) if os.path.exists(os.path.join(base, cid, "accrete.attempt1.json"))]
    for cid in later:
        d = json.load(open(os.path.join(base, cid, "accrete.json")))
        print(f"\n{cid} accrete second attempt (after engine revision, not counted above): "
              f"{'✔' if d.get('success') else '✘'} {d['hidden_passed']}/{d['hidden_total']}, {d['duration_ms'] / 60000:.2f} min, "
              f"{d['tool_uses']} tools, {d['tokens'] / 1000:.0f} ktok")


def summary(cset):
    rows = analyze.load(cset)
    s = analyze.summarize(rows, "first")
    print(f"\n#### {cset} set: summary (first attempts)\n")
    print("| | accrete | baseline | baseline ÷ accrete |")
    print("|---|---|---|---|")
    a, b = s["accrete"], s["baseline"]

    def r(x, y):
        return f"{y / x:.2f}x" if x and y else "–"
    print(f"| correct (all hidden tests pass, no regressions) | {a['success']}/{a['n']} | {b['success']}/{b['n']} | |")
    print(f"| regressions | {a['regressions']} | {b['regressions']} | |")
    print(f"| median change time (min) | {a['median_min']} | {b['median_min']} | **{r(a['median_min'], b['median_min'])}** |")
    print(f"| mean change time (min) | {a['mean_min']} | {b['mean_min']} | {r(a['mean_min'], b['mean_min'])} |")
    print(f"| total agent time (min) | {a['total_min']} | {b['total_min']} | {r(a['total_min'], b['total_min'])} |")
    print(f"| median tool calls | {a['median_tool_calls']} | {b['median_tool_calls']} | {r(a['median_tool_calls'], b['median_tool_calls'])} |")
    print(f"| median tokens (k) | {a['median_ktokens']} | {b['median_ktokens']} | {r(a['median_ktokens'], b['median_ktokens'])} |")
    print(f"| total tokens (k) | {a['total_ktokens']} | {b['total_ktokens']} | {r(a['total_ktokens'], b['total_ktokens'])} |")
    lines = {}
    for sys_ in ("accrete", "baseline"):
        xs = [v["change_lines"] for (cid, s_, w), v in rows.items() if s_ == sys_ and w == "first" and v and v.get("change_lines")]
        lines[sys_] = statistics.median(xs) if xs else None
    print(f"| median changed lines (non-zero) | {lines['accrete']} | {lines['baseline']} | {r(lines['accrete'], lines['baseline'])} |")
    ratios = [p["ratio"] for p in s["pairs"]]
    print(f"| paired time ratio: median / min / max | | | {statistics.median(ratios):.2f}x / {min(ratios):.2f}x / {max(ratios):.2f}x |")
    print(f"| challenges where accrete was ≥5x faster | | | {sum(1 for x in ratios if x >= 5)}/{len(ratios)} |")


if __name__ == "__main__":
    for cset in ("dev", "eval"):
        summary(cset)
        table(cset)
