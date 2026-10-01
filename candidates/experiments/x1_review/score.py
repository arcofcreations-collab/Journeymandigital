"""Score X1 verdicts against the key (harmful = independently confirmed; see build.py)."""
import json, os, sys, glob
S = sys.argv[1]
arm = sys.argv[2] if len(sys.argv) > 2 else "with-model"
key = {c["case"]: c for c in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.json")))}
verd, times = {}, {}
for p in sorted(glob.glob(os.path.join(S, "p*"))):
    try:
        t0 = float(open(os.path.join(p, "start_ts")).read().split()[0])
    except Exception:
        t0 = None
    rows = [json.loads(l) for l in open(os.path.join(p, "verdicts.jsonl")) if l.strip()]
    prev = t0
    for r in rows:
        verd[r["case"]] = r
        if prev is not None:
            times[r["case"]] = float(r["ts"]) - prev
        prev = float(r["ts"])
out = {"arm": arm, "cases": len(verd), "valid": {}, "harmful": {}, "by_category": {}, "per_case": []}
vt = [c for c in key.values() if c["category"].startswith("valid")]
ht = [c for c in key.values() if not c["category"].startswith("valid")]
def rej(c): return verd.get(c["case"], {}).get("verdict") == "REJECT"
out["valid"] = {"n": len(vt), "false_rejections": sum(rej(c) for c in vt), "answered": sum(c["case"] in verd for c in vt)}
out["harmful"] = {"n": len(ht), "detected": sum(rej(c) for c in ht), "answered": sum(c["case"] in verd for c in ht),
                  "authored_expectations_detected": sum((c["round4"]["with_expect"] or {}).get("verdict") == "rejected" for c in ht),
                  "auto_only_detected": sum((c["round4"]["auto_only"] or {}).get("verdict") == "rejected" for c in ht),
                  "hidden_tests_detect": sum(bool(c["round4"].get("hidden_tests_catch")) for c in ht)}
for c in ht:
    b = out["by_category"].setdefault(c["category"], {"n": 0, "review": 0, "expectations": 0, "auto": 0})
    b["n"] += 1; b["review"] += rej(c)
    b["expectations"] += (c["round4"]["with_expect"] or {}).get("verdict") == "rejected"
    b["auto"] += (c["round4"]["auto_only"] or {}).get("verdict") == "rejected"
for cid, c in sorted(key.items()):
    out["per_case"].append({"case": cid, "category": c["category"], "id": c["id"], "verdict": verd.get(cid, {}).get("verdict"),
                            "seconds": round(times.get(cid, -1), 1), "delta_chars": c["delta_chars"],
                            "reason": verd.get(cid, {}).get("reason", "")[:200], "mutation": c["mutation"][:150]})
ts = sorted(v for v in times.values() if v > 0)
out["seconds_per_case_median"] = ts[len(ts) // 2] if ts else None
out["seconds_per_case_mean"] = round(sum(ts) / len(ts), 1) if ts else None
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"result_{arm}.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("cases", "valid", "harmful", "seconds_per_case_median", "seconds_per_case_mean")}, indent=0))
for k, v in out["by_category"].items(): print(k, v)
for r in out["per_case"]:
    if (r["category"].startswith("valid") and r["verdict"] == "REJECT") or (not r["category"].startswith("valid") and r["verdict"] != "REJECT"):
        print("WRONG:", r["case"], r["category"], r["verdict"], "|", r["mutation"][:90], "|", r["reason"][:160])
