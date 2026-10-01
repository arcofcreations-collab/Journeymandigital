"""Planted-bug study: how reliable are accrete's change checks?

  python harness/planted.py run [--limit N] [--seed S]     -> results/v2/planted/raw.jsonl
  python harness/planted.py summary                        -> results/v2/planted/summary.json (+ printed table)

Starting points are the real change files that v1 accrete implementers wrote and that passed the
independent hidden tests (results/*/*/accrete-artifacts/changes). For each, starting from the
exact state the implementer started from:

* VALID: the original change, and the original plus an unrelated valid edit (should be accepted).
* Mutants, each a single planted bug:
  - slip:<kind>   one expression inside the change's own operators is mutated (comparison flipped,
                  constant changed, and/or swapped, `not` dropped); <kind> says where: permission rule,
                  guard, constraint, computed value, stored data (backfill/update/convert), effect.
  - stray-computed  an unrelated existing computed field is changed (its dependents change through
                    dependencies)
  - stray-rule      an unrelated existing permission rule is changed
  - stray-guard     an unrelated existing action guard is changed
  - stray-data      one unrelated stored value is changed
  - stray-user      one user's role/flag is changed (permissions change through stored data)

Every mutant is also force-applied without checks and compared with the original change by an
independent EXHAUSTIVE oracle (every user x every GET of every record and list x every action on
every record, plus the raw stored data). A mutant with no observable difference is "equivalent"
and excluded from detection rates. For effective mutants we record whether accrete rejected it
(with the implementer's expectations, and with automatic checks only) and whether the challenge's
hidden acceptance tests would have caught it.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "harness"))

from accrete import change as C  # noqa: E402
from accrete import model as M  # noqa: E402
from accrete import ops as O  # noqa: E402
from accrete import runtime as R  # noqa: E402
from accrete.store import Store  # noqa: E402
import archive as A  # noqa: E402

OUT = os.path.join(ROOT, "results", "v2", "planted")
NOW = dt.datetime(2026, 3, 1, 12, 0)
EXPR_KEYS = {"computed", "default", "read_if", "write_if", "expr", "guard", "allow", "when", "if", "update",
             "delete", "fail", "backfill", "convert", "where", "in"}


# ------------------------------------------------------------------ corpus
def corpus():
    out = []
    for cset in ("dev", "eval"):
        for res in sorted(glob.glob(os.path.join(ROOT, "results", cset, "*", "accrete.json"))):
            d = json.load(open(res))
            cid = d["id"]
            files = sorted(glob.glob(os.path.join(os.path.dirname(res), "accrete-artifacts", "changes", "*.yaml")))
            if not d.get("success") or not files:
                continue
            when = dt.datetime.utcfromtimestamp(d["t_start"]).replace(microsecond=0) if d.get("t_start") else NOW
            out.append({"set": cset, "id": cid, "app": d["app"], "start": A.start_dir(cset, cid, "accrete"), "files": files,
                        "now": when})
    return out


def load(path):
    doc, base = C.load_change(path)
    return doc, base


# ------------------------------------------------------------------ expression mutation
def _mutants_of_expr(src, rng, k=2):
    try:
        tree = ast.parse(str(src).strip(), mode="eval")
    except SyntaxError:
        return []
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sites.append(("cmp", node))
        elif isinstance(node, ast.BoolOp):
            sites.append(("bool", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)) and not isinstance(node.value, bool):
            sites.append(("const", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            sites.append(("boolconst", node))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append(("not", node))
    rng.shuffle(sites)
    flip = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
            ast.Is: ast.IsNot, ast.IsNot: ast.Is, ast.In: ast.NotIn, ast.NotIn: ast.In}
    out = []
    for kind, node in sites[:k]:
        t = copy.deepcopy(tree)
        target = [n for n in ast.walk(t) if type(n) is type(node) and ast.dump(n) == ast.dump(node)][0]
        if kind == "cmp":
            target.ops = [flip.get(type(target.ops[0]), ast.Eq)()] + target.ops[1:]
        elif kind == "bool":
            target.op = ast.Or() if isinstance(target.op, ast.And) else ast.And()
        elif kind == "const":
            v = target.value
            target.value = v + 1 if isinstance(v, (int, float)) else (v + "_x" if v else "x")
        elif kind == "boolconst":
            target.value = not target.value
        elif kind == "not":
            t = _replace(t, target, target.operand)
        try:
            new = ast.unparse(t)
        except Exception:  # noqa: BLE001
            continue
        if new != ast.unparse(tree):
            out.append((kind, new))
    return out


def _replace(tree, old, new):
    class T(ast.NodeTransformer):
        def generic_visit(self, node):
            if node is old:
                return new
            return super().generic_visit(node)
    return T().visit(tree)


def _expr_sites(obj, path=()):
    """(path, key, src) for every expression string inside an operator's arguments."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("set", "values", "payload") and isinstance(v, dict):
                for kk, vv in v.items():
                    if isinstance(vv, str):
                        yield path + (k, kk), k, vv
            elif k in EXPR_KEYS and isinstance(v, str):
                yield path + (k,), k, v
            elif isinstance(v, (dict, list)):
                yield from _expr_sites(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _expr_sites(v, path + (i,))


def _slip_kind(op_name, path, key):
    if op_name == "set_rule" or key in ("allow", "write_if", "read_if"):
        return "permission"
    if key == "guard" or op_name in ("add_constraint", "change_constraint") or key == "fail":
        return "guard/constraint"
    if key in ("computed",):
        return "computed"
    if op_name == "update_records" or key in ("backfill", "convert", "default"):
        return "stored-data"
    return "effect"


def _set_path(obj, path, value):
    for p in path[:-1]:
        obj = obj[p]
    obj[path[-1]] = value


def slip_mutants(doc, rng, per_change=6):
    out = []
    for i, op in enumerate(doc.get("ops") or []):
        (name, args), = op.items()
        for path, key, src in _expr_sites(args):
            for kind, new in _mutants_of_expr(src, rng, k=1):
                m = copy.deepcopy(doc)
                _set_path(m["ops"][i][name], path, new)
                out.append((f"slip:{_slip_kind(name, path, key)}", f"{name}.{'.'.join(map(str, path))}: {src!r} -> {new!r}", m))
    rng.shuffle(out)
    return out[:per_change]


def stray_mutants(doc, model, world, rng):
    out = []
    ents = list(model["entities"].values())
    ue = M.user_entity(model)
    # computed fields that something else reads
    deps = M.dependencies(model)
    read_by_others = set()
    for loc, (reads, colls, owner) in deps.items():
        for e, f in reads:
            read_by_others.add((e, f))
    comp = [(e, f) for e in ents for f in e["fields"].values() if f.get("computed") and (e["name"], f["name"]) in read_by_others]
    if comp:
        e, f = rng.choice(comp)
        for kind, new in _mutants_of_expr(f["computed"], rng, k=1):
            m = copy.deepcopy(doc)
            m["ops"] = list(m["ops"]) + [{"change_field": {"entity": e["name"], "name": f["name"], "computed": new}}]
            out.append(("stray-computed", f"{e['name']}.{f['name']}: {f['computed']!r} -> {new!r}", m))
    rules = [(e, r) for e in ents for r in ("read", "create", "update", "delete") if e["rules"].get(r) not in (None, "", "True", "False")]
    if rules:
        e, r = rng.choice(rules)
        for kind, new in _mutants_of_expr(e["rules"][r], rng, k=1):
            m = copy.deepcopy(doc)
            m["ops"] = list(m["ops"]) + [{"set_rule": {"entity": e["name"], "rule": r, "expr": new}}]
            out.append(("stray-rule", f"{e['name']} rule {r}: {e['rules'][r]!r} -> {new!r}", m))
    guards = [(e, a) for e in ents for a in e["actions"].values() if a.get("guard")]
    if guards:
        e, a = rng.choice(guards)
        for kind, new in _mutants_of_expr(a["guard"], rng, k=1):
            m = copy.deepcopy(doc)
            m["ops"] = list(m["ops"]) + [{"change_action": {"entity": e["name"], "name": a["name"], "guard": new}}]
            out.append(("stray-guard", f"{e['name']}.{a['name']} guard: {a['guard']!r} -> {new!r}", m))
    # one stored value somewhere else
    cands = []
    for e in ents:
        if ue and e["id"] == ue["id"]:
            continue
        for f in e["fields"].values():
            if f.get("computed") or f["type"] not in ("text", "int", "number", "bool", "enum"):
                continue
            for rid, d in R.records(world, e["id"]).items():
                if d.get(f["id"]) is not None:
                    cands.append((e, f, rid, d[f["id"]]))
    if cands:
        e, f, rid, v = rng.choice(cands)
        nv = (not v) if f["type"] == "bool" else (v + 1 if f["type"] in ("int", "number") else
              (next((x for x in f.get("values") or [] if x != v), v) if f["type"] == "enum" else str(v) + "x"))
        m = copy.deepcopy(doc)
        m["ops"] = list(m["ops"]) + [{"update_records": {"entity": e["name"], "where": f"record.id == {rid}",
                                                         "set": {f["name"]: json.dumps(nv) if not isinstance(nv, bool) else str(nv)}}}]
        out.append(("stray-data", f"{e['name']} {rid}.{f['name']}: {v!r} -> {nv!r}", m))
    if ue:
        flags = [f for f in ue["fields"].values() if f["type"] in ("enum", "bool") and not f.get("computed")]
        recs = list(R.records(world, ue["id"]).items())
        if flags and recs:
            f = rng.choice(flags)
            rid, d = rng.choice(recs)
            v = d.get(f["id"])
            nv = (not v) if f["type"] == "bool" else next((x for x in f.get("values") or [] if x != v), v)
            if nv != v:
                m = copy.deepcopy(doc)
                m["ops"] = list(m["ops"]) + [{"update_records": {"entity": ue["name"], "where": f"record.id == {rid}",
                                                                 "set": {f["name"]: json.dumps(nv) if not isinstance(nv, bool) else str(nv)}}}]
                out.append(("stray-user", f"{ue['name']} {rid}.{f['name']}: {v!r} -> {nv!r}", m))
    return out


def valid_variants(doc, model, rng):
    out = [("valid:original", "the implementer's change as written", copy.deepcopy(doc))]
    ents = [e for e in model["entities"].values()]
    e = rng.choice(ents)
    m = copy.deepcopy(doc)
    m["ops"] = list(m["ops"]) + [{"add_field": {"entity": e["name"], "name": "planted_note", "type": "text"}}]
    out.append(("valid:extra-field", f"plus an unrelated optional field {e['name']}.planted_note", m))
    return out


# ------------------------------------------------------------------ applying
def _prepare_state(item, tmp):
    app = os.path.join(tmp, "start")
    shutil.copytree(item["start"], app, ignore=shutil.ignore_patterns("report-*.json", "__pycache__", "CHANGE_NOTES.md",
                                                                      "CLARIFICATION.md"))
    for f in item["files"][:-1]:  # earlier change files of the same run are part of the starting point
        doc, base = load(f)
        rep = C.apply_change(app, doc, base_dir=base, now=item["now"])
        if rep["verdict"] != "committed":
            raise RuntimeError(f"prefix change failed: {rep.get('reason')}")
    return app


def force_apply(app, doc, base):
    """Apply operators without any checks (the oracle's view of what the mutant would do)."""
    st = Store(app)
    model, world = st.load()
    st.close()
    m, w = M.clone(model), copy.deepcopy(world)
    cx = O.ChangeCtx(m, w, NOW, base or app)
    for op in O.expand(doc.get("ops") or []):
        O.apply(cx, op)
    return m, w


def exhaustive(model, world):
    """Every user x (every list, every record GET, every action on every record), on copies."""
    ue = M.user_entity(model)
    key = model["users"]["key"] if ue else None
    users = [None] + ([d.get(key) for _, d in sorted(R.records(world, ue["id"]).items())] if ue else [])
    out = {}
    for e in model["entities"].values():
        ids = sorted(R.records(world, e["id"]))
        last = R.records(world, e["id"]).get(ids[-1]) if ids else None
        body = None
        if last is not None:
            body = {}
            for f in e["fields"].values():
                v = last.get(f["id"])
                if f.get("computed") or f.get("system") or v is None:
                    continue
                body[f["name"]] = v + "-o" if (f.get("unique") and isinstance(v, str)) else v
        for u in users:
            out[(e["name"], "list", u)] = _call(model, world, "GET", f"/api/{e['name']}", u)
            if body is not None:
                out[(e["name"], "create", u)] = _call(model, world, "POST", f"/api/{e['name']}", u, body)
            for rid in ids:
                out[(e["name"], rid, u)] = _call(model, world, "GET", f"/api/{e['name']}/{rid}", u)
                for a in e["actions"].values():
                    out[(e["name"], rid, a["name"], u)] = _call(model, world, "POST", f"/api/{e['name']}/{rid}/{a['name']}", u, {})
    return out


def _call(model, world, method, path, user, body=None):
    status, body_out, ctx = R.handle_full(model, world, method, path, {}, body, user, NOW)
    emitted = copy.deepcopy(world["outbox"][ctx.outbox_mark:])
    ctx.rollback()
    del world["outbox"][ctx.outbox_mark:]
    return json.dumps([status, body_out, emitted], sort_keys=True, default=str)


def oracle_diff(ref, mut):
    """Observable differences between reference and mutant states: API responses + stored data."""
    (m1, w1), (m2, w2) = ref, mut
    a, b = exhaustive(m1, copy.deepcopy(w1)), exhaustive(m2, copy.deepcopy(w2))
    api = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
    data = json.dumps(w1["records"], sort_keys=True, default=str) != json.dumps(w2["records"], sort_keys=True, default=str)
    return {"api_differences": len(api), "data_differs": data, "examples": [str(k) for k in api[:3]]}


def hidden_tests_catch(item, model, world):
    """Would the challenge's own hidden tests (+ base suite) fail on this state?"""
    tmp = tempfile.mkdtemp(prefix="planted-ht-")
    app = os.path.join(tmp, "app")
    shutil.copytree(item["start"], app, ignore=shutil.ignore_patterns("report-*.json", "__pycache__"))
    st = Store(app)
    st.save_all(model, world)
    st.close()
    test = os.path.join(ROOT, "challenges", item["set"], item["id"], f"test_{item['id']}.py")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "harness", "run_acceptance.py"), app, test],
                       env=dict(os.environ, PYTHONPATH=os.path.join(ROOT, "harness") + os.pathsep + ROOT),
                       capture_output=True, text=True, cwd=tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    last = (r.stdout.strip().splitlines() or ["?"])[-1]
    try:
        p, t = last.split()[0].split("/")
        return int(p) < int(t)
    except Exception:  # noqa: BLE001
        return None


def stage(rep):
    if rep["verdict"] != "rejected":
        return None
    r = rep.get("reason", "")
    if r.startswith("operator"):
        return "operator"
    if (rep.get("static_check") or {}).get("problems"):
        return "static"
    if (rep.get("data_check") or {}).get("violations"):
        return "data"
    if "consequences" in r or "dependencies" in r:
        return "replay:consequence"
    if "accounts for" in r or "regressions" in r:
        return "replay:unexplained"
    if "expectations" in r:
        return "expectations"
    return "other"


def run(limit=None, seed=7):
    os.makedirs(OUT, exist_ok=True)
    rng = random.Random(seed)
    raw = open(os.path.join(OUT, "raw.jsonl"), "w")
    items = corpus()[:limit] if limit else corpus()
    global NOW
    for item in items:
        NOW = item["now"]  # every application, probe and oracle request of this item uses the original run time
        tmp = tempfile.mkdtemp(prefix="planted-")
        try:
            start = _prepare_state(item, tmp)
            doc, base = load(item["files"][-1])
            st = Store(start)
            model0, world0 = st.load()
            st.close()
            ref = force_apply(start, doc, base)
            cases = valid_variants(doc, model0, rng) + slip_mutants(doc, rng) + stray_mutants(doc, model0, world0, rng)
            for cat, desc, mdoc in cases:
                row = {"set": item["set"], "id": item["id"], "app": item["app"], "category": cat, "mutation": desc}
                try:
                    forced = force_apply(start, mdoc, base)
                    od = oracle_diff(ref, forced) if not cat.startswith("valid") else {"api_differences": None}
                    row["oracle"] = od
                except Exception as exc:  # noqa: BLE001
                    forced = None
                    row["oracle"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
                for mode in ("with_expect", "auto_only"):
                    d = copy.deepcopy(mdoc)
                    if mode == "auto_only":
                        d.pop("expect", None)
                    app = os.path.join(tmp, f"m{abs(hash((cat, desc, mode))) % 10**8}")
                    shutil.copytree(start, app)
                    rep = C.apply_change(app, d, base_dir=base, now=item["now"])
                    row[mode] = {"verdict": rep["verdict"], "stage": stage(rep), "reason": (rep.get("reason") or "")[:200],
                                 "ms": (rep.get("timings") or {}).get("total_ms"), "scope_warnings": rep.get("scope_warnings") or []}
                    shutil.rmtree(app, ignore_errors=True)
                if forced and not cat.startswith("valid"):
                    row["hidden_tests_catch"] = hidden_tests_catch(item, *forced)
                od = row["oracle"]
                row["effective"] = bool(cat.startswith("valid") or "error" in od or od.get("api_differences") or od.get("data_differs")
                                        or row.get("hidden_tests_catch") or row["with_expect"]["stage"] == "expectations")
                raw.write(json.dumps(row, default=str) + "\n")
                raw.flush()
                print(item["id"], cat, row["effective"], row["with_expect"]["verdict"], row["auto_only"]["verdict"], flush=True)
        except Exception as exc:  # noqa: BLE001
            print("SKIP", item["id"], type(exc).__name__, exc, flush=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    raw.close()


def summary(name="raw.jsonl"):
    rows = [json.loads(x) for x in open(os.path.join(OUT, name))]
    cats = sorted({r["category"] for r in rows})
    table = []
    for c in cats:
        rs = [r for r in rows if r["category"] == c]
        eff = [r for r in rs if r["effective"]]
        row = {"category": c, "cases": len(rs), "equivalent": len(rs) - len(eff), "effective": len(eff)}
        if c.startswith("valid"):
            row["accepted_with_expect"] = sum(1 for r in rs if r["with_expect"]["verdict"] == "committed")
            row["false_rejections"] = [f"{r['id']}: {r['with_expect']['reason']}" for r in rs if r["with_expect"]["verdict"] != "committed"]
            row["scope_false_alarms"] = sum(1 for r in rs if r["with_expect"].get("scope_warnings"))
        else:
            row["rejected_with_expect"] = sum(1 for r in eff if r["with_expect"]["verdict"] == "rejected")
            row["rejected_auto_only"] = sum(1 for r in eff if r["auto_only"]["verdict"] == "rejected")
            row["hidden_tests_catch"] = sum(1 for r in eff if r.get("hidden_tests_catch"))
            row["stages_auto_only"] = {}
            for r in eff:
                s = r["auto_only"]["stage"] or "missed"
                row["stages_auto_only"][s] = row["stages_auto_only"].get(s, 0) + 1
            row["equivalent_but_rejected"] = sum(1 for r in rs if not r["effective"] and r["with_expect"]["verdict"] == "rejected")
            row["missed_auto_but_scope_warned"] = sum(1 for r in eff if r["auto_only"]["verdict"] != "rejected"
                                                      and r["auto_only"].get("scope_warnings"))
        table.append(row)
    json.dump(table, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print(f"{'category':20} {'cases':>5} {'equiv':>5} {'eff':>4} {'rej(exp)':>8} {'rej(auto)':>9} {'hidden':>6}  stages(auto)")
    for t in table:
        if t["category"].startswith("valid"):
            print(f"{t['category']:20} {t['cases']:5} {'':>5} {'':>4} accepted {t['accepted_with_expect']}/{t['cases']}  false rejections: {len(t['false_rejections'])}  scope warnings (false alarms): {t['scope_false_alarms']}")
        else:
            print(f"{t['category']:20} {t['cases']:5} {t['equivalent']:5} {t['effective']:4} {t['rejected_with_expect']:8} "
                  f"{t['rejected_auto_only']:9} {t['hidden_tests_catch']:6}  {t['stages_auto_only']}  missed-but-scope-warned {t['missed_auto_but_scope_warned']}")
    return table


if __name__ == "__main__":
    if sys.argv[1] == "run":
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 7
        run(lim, seed)
    else:
        summary(sys.argv[2] if len(sys.argv) > 2 else "raw.jsonl")
