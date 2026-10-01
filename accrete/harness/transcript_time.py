"""Where does an implementing agent's time go? (cause analysis for the v2 result)

  python harness/transcript_time.py MAPFILE TASKDIR [--sets dev,eval]  -> results/v2/time_breakdown.json

Reads the agents' transcripts (JSONL, one event per line, with timestamps). Every assistant step
(one model turn ending in a tool call) is attributed to one category, from the tool and its
arguments:
- orient: reading the guide or README, the contract and requirements, the app's code or model,
  `accrete show/context`, `dev.py overview`, ls/grep/cat.
- author-impl: writing or editing the implementation (accrete ops; baseline code, migrations and
  templates).
- author-verif: writing verification (accrete `expect:` entries; baseline tests and test scripts).
- check: running checks (`accrete apply`, `dev.py check`, pytest, scripts using the test client).
- bookkeeping: timestamps, notes, README and docs.

A step's time = model time (from the previous event to the assistant message, i.e. thinking and
writing the call) + tool time (from the call to its result). Characters written into Write/Edit
inputs are counted per category. Accrete change files are split at `expect:` into impl and verif.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def classify(tool, inp):
    s = json.dumps(inp)
    path = inp.get("file_path", "") if isinstance(inp, dict) else ""
    cmd = inp.get("command", "") if isinstance(inp, dict) else ""
    if "t_start_" in s or "t_end_" in s:
        return "bookkeeping"
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        if "CHANGE_NOTES" in path or "CLARIFICATION" in path or path.endswith("README.md"):
            return "bookkeeping"
        if "/tests/" in path or os.path.basename(path).startswith("test_") or "check" in os.path.basename(path) or "smoke" in path or "verify" in path:
            return "author-verif"
        if path.endswith((".yaml", ".yml")):
            return "author-yaml"
        return "author-impl"
    if tool == "Read":
        if "/tests/" in path:
            return "orient"
        return "orient"
    if tool in ("Grep", "Glob"):
        return "orient"
    if tool == "Bash":
        if re.search(r"cat\s*>|<<\s*'?EOF", cmd) and ("expect" in cmd or "test_" in cmd or "assert" in cmd):
            return "author-verif"
        if re.search(r"accrete(\.cli)?\s+apply|dev\.py\s+check|pytest|run_acceptance|accept_client|app_entry|dev\.py\s+call|accrete(\.cli)?\s+call", cmd):
            return "check"
        if re.search(r"cat\s*>|<<\s*'?EOF|sed -i|python3? - <<", cmd):
            if "CHANGE_NOTES" in cmd or "README" in cmd:
                return "bookkeeping"
            return "author-impl"
        if re.search(r"dev\.py\s+notes|CHANGE_NOTES|README", cmd):
            return "bookkeeping"
        return "orient"
    return "other"


def written_chars(tool, inp, cat):
    if tool == "Write":
        return {cat: len(inp.get("content", ""))} if cat != "author-yaml" else _split_yaml(inp.get("content", ""))
    if tool == "Edit":
        return {cat if cat != "author-yaml" else "author-impl": len(inp.get("new_string", ""))}
    if tool == "Bash" and cat.startswith("author"):
        return {cat: len(inp.get("command", ""))}
    return {}


def _split_yaml(text):
    k = re.search(r"^expect:\s*$", text, re.M)
    if not k:
        return {"author-impl": len(text)}
    return {"author-impl": k.start(), "author-verif": len(text) - k.start()}


def analyse(path):
    events = [json.loads(l) for l in open(path) if l.strip()]
    steps, prev_t, pending = [], None, {}
    for e in events:
        t = e.get("timestamp")
        if not t:
            continue
        t = ts(t)
        msg = e.get("message") or {}
        if e.get("type") == "assistant" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if b.get("type") == "tool_use":
                    cat = classify(b["name"], b.get("input") or {})
                    st = {"cat": cat, "model_s": max(0.0, t - (prev_t or t)), "tool_s": 0.0,
                          "chars": written_chars(b["name"], b.get("input") or {}, cat)}
                    pending[b["id"]] = (st, t)
                    steps.append(st)
                    prev_t = t
            if not any(b.get("type") == "tool_use" for b in msg["content"]):
                last_text_t = t  # thinking/text blocks belong to the next tool call (or the final report)
        elif e.get("type") == "user" and isinstance(msg.get("content"), list):
            for b in msg["content"]:
                if b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    st, t0 = pending.pop(b["tool_use_id"])
                    st["tool_s"] = max(0.0, t - t0)
                    prev_t = t
        elif prev_t is None:
            prev_t = t
    tail = [ts(e["timestamp"]) for e in events if e.get("timestamp") and e.get("type") == "assistant"]
    if tail and prev_t is not None and tail[-1] > prev_t:
        steps.append({"cat": "final", "model_s": tail[-1] - prev_t, "tool_s": 0.0, "chars": {}})
    out = {}
    for s in steps:
        c = s["cat"] if s["cat"] != "author-yaml" else "author-impl"
        o = out.setdefault(c, {"steps": 0, "model_s": 0.0, "tool_s": 0.0, "chars": 0})
        o["steps"] += 1
        o["model_s"] += s["model_s"]
        o["tool_s"] += s["tool_s"]
        for k, v in s["chars"].items():
            out.setdefault(k, {"steps": 0, "model_s": 0.0, "tool_s": 0.0, "chars": 0})["chars"] += v
    return out


def main(mapfile, taskdir, sets=("dev", "eval")):
    agg = {}
    per_run = []
    for line in open(mapfile):
        p = line.split()
        if len(p) < 4 or p[1] not in sets or p[3] not in ("accrete2", "baseline2"):
            continue
        f = os.path.join(taskdir, p[0] + ".output")
        if not os.path.exists(f):
            continue
        a = analyse(f)
        per_run.append({"set": p[1], "id": p[2], "system": p[3], "breakdown": a})
        A = agg.setdefault(p[3], {})
        for c, v in a.items():
            x = A.setdefault(c, {"steps": 0, "model_s": 0.0, "tool_s": 0.0, "chars": 0})
            for k in x:
                x[k] += v[k]
    out = {"per_run": per_run, "aggregate": agg}
    json.dump(out, open(os.path.join(ROOT, "results", "v2", "time_breakdown.json"), "w"), indent=1)
    for sysname, A in agg.items():
        n = sum(1 for r in per_run if r["system"] == sysname)
        tot = sum(v["model_s"] + v["tool_s"] for v in A.values())
        print(f"== {sysname}: {n} runs, mean {tot / max(n, 1):.0f}s of attributed time per run")
        for c, v in sorted(A.items(), key=lambda kv: -(kv[1]["model_s"] + kv[1]["tool_s"])):
            t = v["model_s"] + v["tool_s"]
            print(f"  {c:13} {100 * t / tot:5.1f}%  per run: {t / n:6.1f}s (model {v['model_s'] / n:5.1f}s, tool {v['tool_s'] / n:5.1f}s), "
                  f"steps {v['steps'] / n:4.1f}, chars written {v['chars'] / n:7.0f}")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1])
