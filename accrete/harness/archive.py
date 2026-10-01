"""Archive what each implementer actually produced, and measure the size of each change.

  python harness/archive.py SET

For every run in the set:
- accrete: the change files the agent wrote (`changes/*.yaml` newer than the starting app's)
  and CHANGE_NOTES.md / CLARIFICATION.md.
- baseline: a unified diff of all text files (code, SQL, templates, tests, docs) between the
  starting app and the result, plus the notes. Binary data.db is excluded.

These go to results/<set>/<ID>/<system>-artifacts/. Change size is the number of added or
removed lines across those artifacts (for accrete: lines of the new change files), written to
results/<set>/<ID>/<system>.json as `change_lines` / `files_touched`.
"""
import difflib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
import experiment as X  # noqa: E402

TEXT = (".py", ".sql", ".html", ".md", ".txt", ".yaml", ".yml", ".json", ".cfg", ".toml", ".ini")


def start_dir(cset, cid, system):
    meta = X.load_meta(cset, cid)
    if meta.get("depends_on"):
        return os.path.join(X.ws_path(cset, meta["depends_on"], system), "app")
    return os.path.join(X.BASE_APPS[system], meta["app"])


def files(d):
    out = {}
    for root, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ("__pycache__", ".pytest_cache")]
        for f in fs:
            if f.endswith(TEXT) and not f.startswith("report-"):
                p = os.path.join(root, f)
                out[os.path.relpath(p, d)] = p
    return out


def read(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read().splitlines(keepends=True)
    except (UnicodeDecodeError, FileNotFoundError):
        return []


def archive(cset, cid, system):
    ws = X.ws_path(cset, cid, system)
    app = os.path.join(ws, "app")
    if not os.path.isdir(app):
        return None
    start = start_dir(cset, cid, system)
    dest = os.path.join(ROOT, "results", cset, cid, f"{system}-artifacts")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    a, b = files(start), files(app)
    if cid and os.path.isdir(start) and start.startswith(X.SCRATCH):
        pass
    changed, lines = [], 0
    diff_out = []
    for rel in sorted(set(a) | set(b)):
        if rel in ("CHANGE_NOTES.md", "CLARIFICATION.md", "seed_data.json") or rel.endswith("_seed.json"):
            continue
        old, new = read(a[rel]) if rel in a else [], read(b[rel]) if rel in b else []
        if old == new:
            continue
        d = list(difflib.unified_diff(old, new, f"a/{rel}", f"b/{rel}"))
        n = sum(1 for x in d if (x.startswith("+") or x.startswith("-")) and not x.startswith(("+++", "---")))
        changed.append(rel)
        lines += n
        diff_out += d
        if system == "accrete" and rel.startswith("changes/") and rel not in a:
            os.makedirs(os.path.join(dest, "changes"), exist_ok=True)
            shutil.copy(b[rel], os.path.join(dest, rel))
    if system == "baseline" or diff_out:
        with open(os.path.join(dest, "change.diff"), "w") as fh:
            fh.writelines(diff_out)
    for n in ("CHANGE_NOTES.md", "CLARIFICATION.md"):
        if os.path.exists(os.path.join(app, n)):
            shutil.copy(os.path.join(app, n), os.path.join(dest, n))
    res = os.path.join(ROOT, "results", cset, cid, f"{system}.json")
    if os.path.exists(res):
        d = json.load(open(res))
        d["change_lines"], d["files_touched"] = lines, len(changed)
        with open(res, "w") as fh:
            json.dump(d, fh, indent=1)
    return cid, system, len(changed), lines


if __name__ == "__main__":
    cset = sys.argv[1]
    for cid in sorted(os.listdir(os.path.join(ROOT, "challenges", cset))):
        if not os.path.isdir(os.path.join(ROOT, "challenges", cset, cid)):
            continue
        for system in ("accrete", "baseline"):
            r = archive(cset, cid, system)
            if r:
                print(f"{r[0]} {r[1]:9} files {r[2]:3}  lines +- {r[3]}")
