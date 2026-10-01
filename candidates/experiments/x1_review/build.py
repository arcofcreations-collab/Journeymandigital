"""X1: can a reviewer catch faults by reading a behavioural delta instead of writing expectations?

  python build.py [--per-cat N] [--valid N]  -> cases/*.json, packets/packet_<k>.md, key.json

Cases are regenerated deterministically with accrete's planted-bug study generator (seed 7, same
order as harness/planted.py run). A case is either:
- a valid original change (as committed by a v1 implementer); or
- a mutant (one planted slip or stray change) that the independent oracle CONFIRMED harmful in
  round 4 (results/v2/planted/raw_round4.jsonl):
  - exhaustive API differences vs the original, or
  - stored-data differences, or
  - the challenge's hidden tests fail.
  The authored-expectation rejection is NOT used as evidence of harm here.

For each case the reviewer sees ONLY the change request (the challenge brief) and the delta of the
(possibly mutated) change, rendered by candidates/dr/delta.py. Not the change file, not the
expectations. Cases are shuffled; the key is kept apart.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ACC = os.path.join(REPO, "accrete")
sys.path.insert(0, os.path.join(HERE, "..", "..", "dr"))
sys.path.insert(0, os.path.join(ACC, "harness"))
sys.path.insert(0, ACC)
import delta as D  # noqa: E402
import planted as P  # noqa: E402

RAW = os.environ.get("X1_RAW", os.path.join(ACC, "results", "v2", "planted", "raw_round4.jsonl"))


def confirmed(row):
    od = row.get("oracle") or {}
    return bool(od.get("api_differences") or od.get("data_differs") or row.get("hidden_tests_catch"))


def main(per_cat=3, n_valid=10, seed=7, pick_seed=11):
    raw = {}
    for l in open(RAW):
        r = json.loads(l)
        raw[(r["id"], r["category"], r["mutation"])] = r
    rng = random.Random(seed)
    pool = {}
    for item in P.corpus():
        P.NOW = item["now"]
        tmp = tempfile.mkdtemp(prefix="x1-")
        try:
            start = P._prepare_state(item, tmp)
            doc, base = P.load(item["files"][-1])
            st = P.Store(start)
            model0, world0 = st.load()
            st.close()
            cases = P.valid_variants(doc, model0, rng) + P.slip_mutants(doc, rng) + P.stray_mutants(doc, model0, world0, rng)
            for cat, desc, mdoc in cases:
                r = raw.get((item["id"], cat, desc))
                if r is None:
                    continue
                if cat == "valid:original" or (not cat.startswith("valid") and confirmed(r)):
                    keep = os.path.join(HERE, "states", f"{item['set']}-{item['id']}")
                    if not os.path.exists(keep):
                        shutil.copytree(start, keep, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
                    pool.setdefault(cat, []).append({"set": item["set"], "id": item["id"], "category": cat, "mutation": desc,
                                                     "doc": mdoc, "base": base, "start": keep, "now": item["now"].isoformat(),
                                                     "round4": {k: r.get(k) for k in ("with_expect", "auto_only", "hidden_tests_catch", "oracle")}})
        except Exception as exc:  # noqa: BLE001
            print("skip", item["id"], exc)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    pick = random.Random(pick_seed)
    chosen = []
    for cat, items in sorted(pool.items()):
        pick.shuffle(items)
        chosen += items[: (n_valid if cat == "valid:original" else per_cat)]
    pick.shuffle(chosen)
    os.makedirs(os.path.join(HERE, "cases"), exist_ok=True)
    key = []
    for k, c in enumerate(chosen, 1):
        brief = json.load(open(os.path.join(ACC, "challenges", c["set"], c["id"], "meta.json")))["brief"]
        import datetime as dt
        d = D.compute(c["start"], c["doc"], c["base"], dt.datetime.fromisoformat(c["now"]))
        text = D.render(d, limit_chars=20000)
        c["case"] = f"C{k:02d}"
        c["delta_chars"] = len(text)
        c["brief"] = brief
        with open(os.path.join(HERE, "cases", f"{c['case']}.md"), "w") as fh:
            fh.write(f"# Case {c['case']}\n\n## Change request\n\n{brief}\n\n## Behaviour delta\n\n```\n{text}\n```\n")
        key.append({k2: v for k2, v in c.items() if k2 not in ("doc", "brief")})
    json.dump(key, open(os.path.join(HERE, "key.json"), "w"), indent=1, default=str)
    print(len(chosen), "cases;", {cat: sum(1 for c in chosen if c["category"] == cat) for cat in sorted({c["category"] for c in chosen})})


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[a.index("--per-cat") + 1]) if "--per-cat" in a else 3, int(a[a.index("--valid") + 1]) if "--valid" in a else 10)
