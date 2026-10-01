"""Behavioural delta of a change: what observably differs between before and after, summarised for review.

The question this module serves: can an implementer establish that a change is correct by READING
a system-computed delta, instead of WRITING expectations or tests?

The delta is computed by differential execution over a bounded request space:
- every probe accrete would generate for the old and for the new model (thorough mode, including
  UI pages);
- run on the same starting data, each probe isolated from the next;
plus the full stored-data difference made by the change itself (migrations, backfills).

The summary groups differing probes by:
- request shape (method + path template + query keys);
- the user's role;
- the kind of difference (status, fields added/removed/changed, records shown, messages emitted).

For each group it shows counts and up to three concrete examples. Anything that does not differ is
not shown: the reader can rely on "not listed = unchanged" ONLY within the bounded probe space. That
limitation is stated in the summary header.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile

ACCRETE = os.environ.get("ACCRETE_ROOT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "accrete"))
sys.path.insert(0, os.path.abspath(ACCRETE))
from accrete import change as C  # noqa: E402
from accrete import model as M  # noqa: E402
from accrete import ops as O  # noqa: E402
from accrete import runtime as R  # noqa: E402
from accrete.store import Store  # noqa: E402


def load_state(app):
    tmp = tempfile.mkdtemp(prefix="dr-load-")
    shutil.copytree(app, os.path.join(tmp, "a"), ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
    st = Store(os.path.join(tmp, "a"))
    m, w = st.load()
    st.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return m, w


def apply_ops(model, world, doc, base, now):
    m, w = M.clone(model), copy.deepcopy(world)
    cx = O.ChangeCtx(m, w, now, base)
    for op in O.expand(doc.get("ops") or []):
        O.apply(cx, op)
    return m, w


def _user_role(model, world, name):
    ue = M.user_entity(model)
    if not ue or name is None:
        return "anonymous"
    key = model["users"]["key"]
    for _, d in R.records(world, ue["id"]).items():
        if d.get(key) == name:
            for f in ue["fields"].values():
                if f["name"] == "role":
                    return str(d.get(f["id"]))
            return "user"
    return "unknown-user"


def _template(path):
    return re.sub(r"/\d+", "/{id}", path)


def _norm(result):
    """(status, body, emitted, writes[, setup]) -> comparable pieces."""
    status, body = result[0], result[1]
    emitted = result[2] if len(result) > 2 else []
    return status, body, [{"channel": m.get("channel"), "payload": m.get("payload")} for m in (emitted or [])]


def _body_diff(a, b):
    """Field-level differences between two JSON bodies (records or lists of records)."""
    out = []
    if isinstance(a, str) or isinstance(b, str):  # UI pages: compare the parsed contract view
        try:
            sys.path.insert(0, os.path.join(os.path.abspath(ACCRETE), "accrete"))
            from accrete import uicheck as U
            pa, pb = U.parse(a or ""), U.parse(b or "")
            for k in ("rows", "actions", "inputs", "creates"):
                if sorted(map(str, pa[k])) != sorted(map(str, pb[k])):
                    out.append(f"{k}: {pa[k][:12]} -> {pb[k][:12]}")
            for k in sorted(set(pa["fields"]) | set(pb["fields"])):
                if pa["fields"].get(k) != pb["fields"].get(k):
                    out.append(f"field {k}: {pa['fields'].get(k)!r} -> {pb['fields'].get(k)!r}")
        except Exception:  # noqa: BLE001
            out.append("page differs")
        return out
    if isinstance(a, dict) and isinstance(b, dict) and "items" in a and "items" in b:
        ia = {x.get("id"): x for x in a["items"] if isinstance(x, dict)}
        ib = {x.get("id"): x for x in b["items"] if isinstance(x, dict)}
        if set(ia) != set(ib):
            gone, new = sorted(set(ia) - set(ib)), sorted(set(ib) - set(ia))
            if gone:
                out.append(f"no longer listed: ids {gone[:10]}")
            if new:
                out.append(f"now listed: ids {new[:10]}")
        for k in sorted(set(ia) & set(ib), key=str):
            for d in _body_diff(ia[k], ib[k]):
                out.append(f"#{k} {d}")
        if not out and [x.get("id") for x in a["items"]] != [x.get("id") for x in b["items"]]:
            out.append("order changed")
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"+{k}={json.dumps(b[k])[:60]}")
            elif k not in b:
                out.append(f"-{k}")
            elif a[k] != b[k]:
                if isinstance(a[k], dict) and isinstance(b[k], dict):
                    out.extend(f"{k}.{d}" for d in _body_diff(a[k], b[k]))
                else:
                    out.append(f"{k}: {json.dumps(a[k])[:50]} -> {json.dumps(b[k])[:50]}")
        return out
    return [f"{json.dumps(a)[:80]} -> {json.dumps(b)[:80]}"] if a != b else []


def _shape(diffs):
    """Abstract a list of field diffs into a groupable signature (drop ids and values)."""
    keys = set()
    for d in diffs:
        d = re.sub(r"^#\S+ ", "", d)
        m = re.match(r"^([+-]?[\w.]+)", d)
        keys.add(m.group(1) if m else d[:30])
    return tuple(sorted(keys))


def compute(start_app, doc, base_dir, now):
    model0, world0 = load_state(start_app)
    model1, world1 = apply_ops(model0, world0, doc, base_dir or start_app, now)
    probes = []
    seen = set()
    for m, w in ((model0, world0), (model1, world1)):
        for p in C.generate_probes(m, w, now, thorough=True) + C.ui_probes(m, w, now):
            k = json.dumps(p, sort_keys=True, default=str)
            if k not in seen:
                seen.add(k)
                probes.append(p)
    rows = []
    for p in probes:
        try:
            a = C._run_any(model0, copy.deepcopy(world0), p)
        except Exception as exc:  # noqa: BLE001
            a = (599, f"error {type(exc).__name__}", [], [])
        try:
            b = C._run_any(model1, copy.deepcopy(world1), p)
        except Exception as exc:  # noqa: BLE001
            b = (599, f"error {type(exc).__name__}", [], [])
        sa, ba, ea = _norm(a)
        sb, bb, eb = _norm(b)
        if (sa, ba, ea) == (sb, bb, eb):
            continue
        rows.append({"method": "UI" if p.get("ui") else p.get("method"), "path": p.get("path"),
                     "query": p.get("query") or {}, "body": p.get("body"), "user": p.get("user"),
                     "role": _user_role(model1, world1, p.get("user")),
                     "status": [sa, sb], "diff": _body_diff(ba, bb) if sa == sb else [],
                     "emitted": [ea, eb] if ea != eb else None})
    data = _data_delta(model0, world0, model1, world1)
    return {"probes": len(probes), "differing": len(rows), "rows": rows, "data": data,
            "model_changes": _model_changes(model0, model1)}


def _data_delta(m0, w0, m1, w1):
    out = []
    names = {e["id"]: e for e in list(m0["entities"].values()) + list(m1["entities"].values())}
    for eid in sorted(set(w0["records"]) | set(w1["records"])):
        e = names.get(eid)
        o, n = w0["records"].get(eid, {}), w1["records"].get(eid, {})
        added, removed = sorted(set(n) - set(o)), sorted(set(o) - set(n))
        fname = {fid: f["name"] for fid, f in (e or {"fields": {}})["fields"].items()}
        if e is None:
            continue
        changed = {}
        for rid in sorted(set(o) & set(n)):
            for fid in sorted(set(o[rid]) | set(n[rid])):
                if o[rid].get(fid) != n[rid].get(fid):
                    changed.setdefault(fname.get(fid, fid), []).append((rid, o[rid].get(fid), n[rid].get(fid)))
        if added or removed or changed:
            out.append({"entity": e["name"], "added": added, "removed": removed,
                        "changed": {k: v for k, v in changed.items()},
                        "added_examples": [{fname.get(k, k): v for k, v in n[r].items()} for r in added[:3]]})
    return out


def _model_changes(m0, m1):
    out = []
    e0 = {e["name"]: e for e in m0["entities"].values()}
    e1 = {e["name"]: e for e in m1["entities"].values()}
    for n in sorted(set(e1) - set(e0)):
        out.append(f"new collection {n}: fields {[f['name'] for f in e1[n]['fields'].values()]}, "
                   f"actions {[a['name'] for a in e1[n]['actions'].values()]}")
    for n in sorted(set(e0) - set(e1)):
        out.append(f"removed collection {n}")
    for n in sorted(set(e0) & set(e1)):
        a, b = e0[n], e1[n]
        fa = {f["name"]: f for f in a["fields"].values()}
        fb = {f["name"]: f for f in b["fields"].values()}
        for f in sorted(set(fb) - set(fa)):
            x = fb[f]
            out.append(f"{n}: new field {f} ({x['type']}{', computed: ' + x['computed'] if x.get('computed') else ''}"
                       f"{', write_if: ' + x['write_if'] if x.get('write_if') else ''})")
        for f in sorted(set(fa) - set(fb)):
            out.append(f"{n}: removed field {f}")
        for f in sorted(set(fa) & set(fb)):
            for k in ("type", "computed", "default", "write_if", "read_if", "required", "unique", "values"):
                if fa[f].get(k) != fb[f].get(k):
                    out.append(f"{n}.{f}.{k}: {fa[f].get(k)!r} -> {fb[f].get(k)!r}")
        for k in sorted(set(a.get("rules") or {}) | set(b.get("rules") or {})):
            if (a.get("rules") or {}).get(k) != (b.get("rules") or {}).get(k):
                out.append(f"{n} rule {k}: {(a.get('rules') or {}).get(k)!r} -> {(b.get('rules') or {}).get(k)!r}")
        aa = {x["name"]: x for x in a["actions"].values()}
        ab = {x["name"]: x for x in b["actions"].values()}
        for x in sorted(set(ab) - set(aa)):
            out.append(f"{n}: new action {x} allow={ab[x].get('allow')!r} guard={ab[x].get('guard')!r}")
        for x in sorted(set(aa) & set(ab)):
            for k in ("allow", "guard", "params", "effects", "guard_message"):
                if aa[x].get(k) != ab[x].get(k):
                    out.append(f"{n}.{x}.{k}: {json.dumps(aa[x].get(k))[:160]} -> {json.dumps(ab[x].get(k))[:160]}")
        for k in sorted(set(a.get("constraints") or {}) | set(b.get("constraints") or {})):
            if (a.get("constraints") or {}).get(k) != (b.get("constraints") or {}).get(k):
                out.append(f"{n} constraint changed: {json.dumps((b.get('constraints') or {}).get(k))[:160]}")
        if json.dumps(a.get("triggers"), sort_keys=True) != json.dumps(b.get("triggers"), sort_keys=True):
            out.append(f"{n}: triggers changed")
    return out


def render(delta, limit_chars=12000):
    """A compact, reviewable text."""
    lines = [f"BEHAVIOUR DELTA over {delta['probes']} generated requests (each run on the same starting data, "
             f"before vs after). {delta['differing']} differ. Requests outside this generated set are NOT covered.", ""]
    lines.append("MODEL CHANGES:")
    lines += [f"  - {x}" for x in delta["model_changes"]] or ["  (none)"]
    lines.append("")
    lines.append("STORED DATA CHANGED BY THE CHANGE ITSELF:")
    if not delta["data"]:
        lines.append("  (none)")
    for d in delta["data"]:
        if d["added"]:
            lines.append(f"  {d['entity']}: {len(d['added'])} records added (ids {d['added'][:8]}{'...' if len(d['added']) > 8 else ''}); "
                         f"e.g. {json.dumps(d['added_examples'][:2], default=str)[:300]}")
        if d["removed"]:
            lines.append(f"  {d['entity']}: {len(d['removed'])} records removed (ids {d['removed'][:10]})")
        for f, ch in d["changed"].items():
            vals = {}
            for rid, a, b in ch:
                vals.setdefault((json.dumps(a, default=str)[:40], json.dumps(b, default=str)[:40]), []).append(rid)
            parts = [f"{a}->{b} for {len(ids)} (ids {ids[:8]}{'...' if len(ids) > 8 else ''})" for (a, b), ids in
                     sorted(vals.items(), key=lambda kv: -len(kv[1]))[:6]]
            lines.append(f"  {d['entity']}.{f}: " + "; ".join(parts) + (f"; +{len(vals) - 6} more value pairs" if len(vals) > 6 else ""))
    lines.append("")
    lines.append("REQUEST BEHAVIOUR THAT CHANGED (grouped; count = differing requests in the group):")
    groups = {}
    for r in delta["rows"]:
        q = ",".join(sorted(r["query"])) if r["query"] else ""
        kind = (f"status {r['status'][0]}->{r['status'][1]}" if r["status"][0] != r["status"][1] else
                "body " + ",".join(_shape(r["diff"]))[:120] if r["diff"] else "")
        if r["emitted"]:
            kind += f" messages {[m['channel'] for m in r['emitted'][0]]}->{[m['channel'] for m in r['emitted'][1]]}"
        key = (r["method"], _template(r["path"]) + (f"?{q}" if q else ""), kind)
        groups.setdefault(key, []).append(r)
    for (meth, tpl, kind), rs in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        roles = sorted({r["role"] for r in rs})
        lines.append(f"* {meth} {tpl} as {'/'.join(roles)}: {kind}  [{len(rs)}]")
        for r in rs[:2]:
            ex = f"    e.g. {r['method']} {r['path']}"
            if r["query"]:
                ex += "?" + "&".join(f"{k}={v}" for k, v in r["query"].items())
            if r["body"]:
                ex += f" body={json.dumps(r['body'], default=str)[:120]}"
            ex += f" as {r['user']}: {r['status'][0]}->{r['status'][1]}"
            if r["diff"]:
                ex += "; " + "; ".join(r["diff"][:4])[:300]
            if r["emitted"]:
                ex += f"; messages {json.dumps(r['emitted'][0])[:150]} -> {json.dumps(r['emitted'][1])[:200]}"
            lines.append(ex)
    text = "\n".join(lines)
    if len(text) > limit_chars:
        text = text[:limit_chars] + f"\n... (truncated; {len(groups)} groups in total)"
    return text


if __name__ == "__main__":
    app, change = sys.argv[1], sys.argv[2]
    now = dt.datetime.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else dt.datetime(2026, 3, 1, 12, 0)
    doc, base = C.load_change(change)
    print(render(compute(app, doc, base, now)))
