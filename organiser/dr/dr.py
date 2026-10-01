"""Delta Review for the organiser.

    python dr/dr.py diff       # observe the current code over the behaviour space; print the grouped delta vs approved
    python dr/dr.py approve    # record the current observations as the approved baseline (dr/approved.json)

Approving a delta records a *judgement*, not proof of correctness. Behaviour outside dr/space.py is not covered.
"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import space  # noqa: E402

APPROVED = os.path.join(HERE, "approved.json")


def diff(old, new, examples=3):
    lines = []
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    lines.append(f"BEHAVIOUR DELTA over the declared space ({len(new)} observations: synthetic corpus of "
                 f"{len(space.corpus())} conversations x the app's questions). Not listed = unchanged *within this space only*.")
    groups = collections.defaultdict(list)
    for k in changed:
        o, n = old[k], new[k]
        if isinstance(o, dict) and isinstance(n, dict):
            sig = tuple(sorted(f"{f}: {json.dumps(o.get(f))[:40]} -> {json.dumps(n.get(f))[:40]}" if f in ("status", "kind", "context")
                               else f"{f} changed" for f in set(o) | set(n) if o.get(f) != n.get(f)))
        else:
            sig = (k.split("|")[0] + " changed",)
        groups[sig].append(k)
    for sig, ks in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"* CHANGED [{len(ks)}] " + "; ".join(sig))
        for k in ks[:examples]:
            o, n = old[k], new[k]
            if isinstance(o, dict) and isinstance(n, dict):
                fs = sorted(f for f in set(o) | set(n) if o.get(f) != n.get(f))
                lines.append(f"    e.g. {k} (status {o.get('status')}, work {o.get('work')})")
                for f in fs:
                    lines.append(f"       {f}: {json.dumps(o.get(f))[:200]} -> {json.dumps(n.get(f))[:200]}")
            else:
                lines.append(f"    e.g. {k}\n       before {json.dumps(o)[:300]}\n       after  {json.dumps(n)[:300]}")
    for title, ks, src in (("NEW", added, new), ("GONE", removed, old)):
        by = collections.defaultdict(list)
        for k in ks:
            v = src[k]
            by[(k.split("|")[0], v.get("status") if isinstance(v, dict) else None, v.get("kind") if isinstance(v, dict) else None)].append(k)
        for (typ, st, kd), kk in sorted(by.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"* {title} [{len(kk)}] {typ}" + (f" status={st} kind={kd}" if st else ""))
            for k in kk[:examples]:
                lines.append(f"    e.g. {k} -> {json.dumps(src[k])[:300]}")
    if not (added or removed or changed):
        lines.append("(no differences)")
    return "\n".join(lines), {"changed": len(changed), "new": len(added), "gone": len(removed)}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "diff"
    obs = space.observe()
    if cmd == "approve":
        json.dump(obs, open(APPROVED, "w"), indent=0, sort_keys=True)
        print(f"approved {len(obs)} observations")
        return
    old = json.load(open(APPROVED)) if os.path.exists(APPROVED) else {}
    text, counts = diff(old, obs)
    print(text)
    print("SUMMARY", json.dumps(counts))


if __name__ == "__main__":
    main()
