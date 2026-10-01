"""Make an isolated working copy for an improver agent (see docs/EXPOSURE.md).

  python harness/isolated_copy.py DEST [--evidence PATH ...]
  python harness/isolated_copy.py --diff DEST       -> lists files that differ from the repository

The copy contains the engine, apps, baseline_v2, docs, specs, dev and base challenges, the
harness and tests. It does NOT contain:
- .git (no history, so no way to read later commits);
- challenges/fresh and challenges/heldout (the unseen evaluation material);
- results/ (except the dev evidence files passed with --evidence, copied to EVIDENCE/);
- docs/EXPOSURE.md.
After copying, the copy is scanned to confirm that none of the excluded material is present.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCLUDE_TOP = {".git", "results", "__pycache__", ".pytest_cache"}
EXCLUDE_PATHS = {os.path.join("challenges", "fresh"), os.path.join("challenges", "heldout"),
                 os.path.join("docs", "EXPOSURE.md")}


def _ignore(src, names):
    rel = os.path.relpath(src, ROOT)
    out = set()
    for n in names:
        p = os.path.normpath(os.path.join(rel, n))
        if n in EXCLUDE_TOP or p in EXCLUDE_PATHS or n.endswith(".egg-info"):
            out.add(n)
    return out


def make(dest, evidence=()):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(ROOT, dest, ignore=_ignore)
    if evidence:
        ev = os.path.join(dest, "EVIDENCE")
        os.makedirs(ev, exist_ok=True)
        for p in evidence:
            shutil.copy(p, ev)
    bad = []
    for d, dirs, files in os.walk(dest):
        rel = os.path.relpath(d, dest)
        if rel.startswith(os.path.join("challenges", "fresh")) or rel.startswith(os.path.join("challenges", "heldout")) or ".git" in rel.split(os.sep):
            bad.append(rel)
        for f in files:
            if "heldout" in f or f in ("SHA256SUMS",) or f.startswith("test_F"):
                bad.append(os.path.join(rel, f))
    if bad:
        raise SystemExit(f"isolation check failed: {bad[:5]}")
    print(f"isolated copy at {dest} (no .git, no fresh/heldout challenges, no results)")


def diff(dest):
    out = []
    for d, dirs, files in os.walk(dest):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".pytest_cache", "EVIDENCE") and not x.endswith(".egg-info")]
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, dest)
            q = os.path.join(ROOT, rel)
            if not os.path.exists(q):
                out.append(("added", rel))
            elif not filecmp.cmp(p, q, shallow=False):
                out.append(("changed", rel))
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in EXCLUDE_TOP and not x.endswith(".egg-info")
                   and os.path.normpath(os.path.join(os.path.relpath(d, ROOT), x)) not in EXCLUDE_PATHS]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), ROOT)
            if rel in EXCLUDE_PATHS:
                continue
            if not os.path.exists(os.path.join(dest, rel)):
                out.append(("removed", rel))
    for k, rel in sorted(out, key=lambda x: x[1]):
        print(k, rel)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--diff":
        diff(a[1])
    elif a:
        ev = a[a.index("--evidence") + 1:] if "--evidence" in a else []
        make(a[0], ev)
    else:
        print(__doc__)
