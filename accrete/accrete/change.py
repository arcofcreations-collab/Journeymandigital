"""The change pipeline: one authoritative change -> verified, committed (or rejected) software.

    request + operators
      -> interpret (expand macros, show what each operator means)
      -> apply in a sandbox (model + data together; inverse captured)
      -> static check        (every expression still resolves and type-checks: obligations)
      -> data check          (every existing record satisfies the new model)
      -> footprint           (what the change is *allowed* to alter, computed from the model diff
                              closed over the dependency graph)
      -> differential replay (recorded + generated requests run on old and new versions; any
                              difference outside the footprint is a regression)
      -> expectations        (examples the change author states, run on the new version)
      -> commit atomically + ledger entry with the full report and the inverse, or reject
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import time

from . import expr as E
from . import model as M
from . import ops as O
from . import runtime as R
from .store import Store


class ChangeRejected(Exception):
    pass


# ------------------------------------------------------------------ footprint
def _elements(model):
    """Flatten the model into comparable elements keyed by stable ids."""
    out = {}
    for e in model["entities"].values():
        out[("entity", e["id"])] = e["name"]
        for f in e["fields"].values():
            out[("field", e["id"], f["id"])] = json.dumps(f, sort_keys=True)
        for r in M.RULES:
            out[("rule", e["id"], r)] = json.dumps([e["rules"].get(r), e.get("guard_messages", {}).get(r)])
        for c in e["constraints"].values():
            out[("constraint", e["id"], c["id"])] = json.dumps(c, sort_keys=True)
        for a in e["actions"].values():
            out[("action", e["id"], a["id"])] = json.dumps(a, sort_keys=True)
        for t in e["triggers"].values():
            out[("trigger", e["id"], t["id"])] = json.dumps(t, sort_keys=True)
    out[("users",)] = json.dumps(model.get("users"))
    return out


def _data_changes(old_world, new_world, new_model):
    """Which (entity id, field id) values changed, and which entities gained/lost records."""
    fields, membership = set(), set()
    eids = set(old_world["records"]) | set(new_world["records"])
    for eid in eids:
        o = old_world["records"].get(eid, {})
        n = new_world["records"].get(eid, {})
        if set(o) != set(n):
            membership.add(eid)
        for rid in set(o) & set(n):
            od, nd = o[rid], n[rid]
            for fid in set(od) | set(nd):
                if od.get(fid) != nd.get(fid):
                    fields.add((eid, fid))
    return fields, membership


class Footprint:
    """What a change may legitimately alter in observable behaviour."""

    def __init__(self):
        self.fields = set()        # (entity name, field name) whose values in responses may differ
        self.visibility = set()    # entity names whose read rule / membership may differ
        self.ops = set()           # (entity name, op) op in create/update/delete/action:<name>/any
        self.renamed_fields = {}   # (entity new name, old field name) -> new field name
        self.renamed_entities = {}  # old name -> new name
        self.reasons = []          # human-readable account: element -> consequence
        self.declared = []         # extra footprint declared by the change author

    def to_json(self):
        return {"fields": sorted(f"{e}.{f}" for e, f in self.fields), "visibility": sorted(self.visibility),
                "operations": sorted(f"{e}.{o}" for e, o in self.ops),
                "renamed_fields": {f"{e}.{o}": n for (e, o), n in self.renamed_fields.items()},
                "renamed_entities": self.renamed_entities, "declared": self.declared,
                "consequences": self.reasons[:200]}

    def allows_op(self, ent, op):
        return (ent, op) in self.ops or (ent, "any") in self.ops or ent in self.visibility


def compute_footprint(old_model, new_model, old_world, new_world, declared=()):
    fp = Footprint()
    old_el, new_el = _elements(old_model), _elements(new_model)
    changed = {k for k in set(old_el) | set(new_el) if old_el.get(k) != new_el.get(k)}

    def ename(eid):
        e = new_model["entities"].get(eid) or old_model["entities"].get(eid)
        return e["name"] if e else eid

    def fname(eid, fid):
        for mdl in (new_model, old_model):
            e = mdl["entities"].get(eid)
            if e and fid in e["fields"]:
                return e["fields"][fid]["name"]
        return fid

    # renames (for translating old responses before comparing)
    for eid, e in new_model["entities"].items():
        oe = old_model["entities"].get(eid)
        if oe and oe["name"] != e["name"]:
            fp.renamed_entities[oe["name"]] = e["name"]
        if oe:
            for fid, f in e["fields"].items():
                of = oe["fields"].get(fid)
                if of and of["name"] != f["name"]:
                    fp.renamed_fields[(e["name"], of["name"])] = f["name"]

    affected_fields = set()   # (eid, fid)
    affected_entities = set()  # eids whose membership/visibility changes
    for k in changed:
        kind = k[0]
        if kind == "entity":
            eid = k[1]
            if eid not in old_model["entities"] or eid not in new_model["entities"]:
                fp.ops.add((ename(eid), "any"))
                fp.visibility.add(ename(eid))
                affected_entities.add(eid)
                fp.reasons.append(f"entity {ename(eid)} added or removed: all of its operations")
        elif kind == "field":
            eid, fid = k[1], k[2]
            affected_fields.add((eid, fid))
            fp.ops.update({(ename(eid), "create"), (ename(eid), "update")})
            fp.reasons.append(f"field {ename(eid)}.{fname(eid, fid)} changed: its values, create and update")
        elif kind == "rule":
            eid, rule = k[1], k[2]
            if rule == "read":
                fp.visibility.add(ename(eid))
                affected_entities.add(eid)
            else:
                fp.ops.add((ename(eid), {"update_guard": "update", "delete_guard": "delete"}.get(rule, rule)))
            fp.reasons.append(f"rule {ename(eid)}.{rule} changed")
        elif kind == "constraint":
            eid = k[1]
            fp.ops.update({(ename(eid), "create"), (ename(eid), "update")})
            affected_entities.add(("writes", eid))
            fp.reasons.append(f"a constraint on {ename(eid)} changed: create/update and actions writing {ename(eid)}")
        elif kind == "action":
            eid, aid = k[1], k[2]
            a = (new_model["entities"].get(eid, {}).get("actions", {}).get(aid)
                 or old_model["entities"].get(eid, {}).get("actions", {}).get(aid))
            fp.ops.add((ename(eid), f"action:{a['name']}"))
            oa = old_model["entities"].get(eid, {}).get("actions", {}).get(aid)
            if oa and a and oa["name"] != a["name"]:
                fp.ops.add((ename(eid), f"action:{oa['name']}"))
            fp.reasons.append(f"action {ename(eid)}.{a['name']} changed")
        elif kind == "trigger":
            eid, tid = k[1], k[2]
            t = (new_model["entities"].get(eid, {}).get("triggers", {}).get(tid)
                 or old_model["entities"].get(eid, {}).get("triggers", {}).get(tid))
            ev = t["on"]
            fp.ops.add((ename(eid), ev if ev.startswith("action:") else ev))
            fp.reasons.append(f"trigger {ename(eid)}.{t['name']} changed: {ev}")
        elif kind == "users":
            fp.ops.add(("*", "any"))
            fp.reasons.append("the user directory changed: every request")

    dfields, membership = _data_changes(old_world, new_world, new_model)
    for eid, fid in dfields:
        affected_fields.add((eid, fid))
        fp.reasons.append(f"stored values of {ename(eid)}.{fname(eid, fid)} changed")
    for eid in membership:
        affected_entities.add(eid)
        fp.visibility.add(ename(eid))
        fp.reasons.append(f"records of {ename(eid)} added or removed")

    # close over the dependency graph of the *new* model (and the old one, for removed reads)
    for mdl in (new_model, old_model):
        _close(mdl, fp, affected_fields, affected_entities, ename, fname)
    # writers of constrained entities
    for item in list(affected_entities):
        if isinstance(item, tuple) and item[0] == "writes":
            target = ename(item[1])
            for e in new_model["entities"].values():
                for a in e["actions"].values():
                    if _writes(a["effects"], target, e["name"]):
                        fp.ops.add((e["name"], f"action:{a['name']}"))
                        fp.reasons.append(f"action {e['name']}.{a['name']} writes {target}")
    for d in declared:
        ent, _, op = d.partition(".")
        if op in ("read", "visibility"):
            fp.visibility.add(ent)
        elif op.startswith("field:"):
            fp.fields.add((ent, op[6:]))
        else:
            fp.ops.add((ent, op or "any"))
        fp.declared.append(d)
    return fp


def _writes(effects, target, own):
    for eff in effects or []:
        if eff.get("create") == target or ("set" in eff and "update" not in eff and own == target):
            return True
        if "update" in eff or "delete" in eff:
            return True  # unknown target type: be conservative
        if _writes(eff.get("then"), target, own) or _writes(eff.get("else"), target, own):
            return True
    return False


def _close(mdl, fp, affected_fields, affected_entities, ename, fname):
    deps = M.dependencies(mdl)
    name_of = {}
    for e in mdl["entities"].values():
        for f in e["fields"].values():
            name_of[(e["name"], f["name"])] = (e["id"], f["id"])
    changed_pairs = {(ename(eid), fname(eid, fid)) for eid, fid in affected_fields}
    changed_colls = {ename(x) for x in affected_entities if not isinstance(x, tuple)}
    for eid, fid in affected_fields:
        fp.fields.add((ename(eid), fname(eid, fid)))
    grew = True
    seen = set()
    while grew:
        grew = False
        for loc, (reads, colls, owner) in deps.items():
            if loc in seen:
                continue
            if reads & changed_pairs or colls & changed_colls:
                seen.add(loc)
                grew = True
                kind = loc[0]
                ent = mdl["entities"][loc[1]]
                desc = M.describe(mdl, loc)
                if kind == "field":
                    f = ent["fields"][loc[2]]
                    fp.fields.add((ent["name"], f["name"]))
                    changed_pairs.add((ent["name"], f["name"]))
                    if loc[3] in ("read_if",):
                        fp.ops.add((ent["name"], "any"))
                    if loc[3] in ("write_if", "default"):
                        fp.ops.update({(ent["name"], "create"), (ent["name"], "update")})
                elif kind == "rule":
                    if loc[2] == "read":
                        fp.visibility.add(ent["name"])
                        changed_colls.add(ent["name"])
                    else:
                        fp.ops.add((ent["name"], {"update_guard": "update", "delete_guard": "delete"}.get(loc[2], loc[2])))
                elif kind == "constraint":
                    fp.ops.update({(ent["name"], "create"), (ent["name"], "update")})
                elif kind == "action":
                    a = ent["actions"][loc[2]]
                    fp.ops.add((ent["name"], f"action:{a['name']}"))
                elif kind == "trigger":
                    t = ent["triggers"][loc[2]]
                    fp.ops.add((ent["name"], t["on"]))
                fp.reasons.append(f"{desc} depends on what changed")


# ------------------------------------------------------------------ probes & replay
def generate_probes(model, world, now, per_entity=3):
    """Requests that exercise every collection, record operation and action as several users."""
    probes = []
    ue = M.user_entity(model)
    users = [None]
    if ue:
        key = model["users"]["key"]
        recs = R.records(world, ue["id"])
        groups = {}
        enum_fields = [f["id"] for f in ue["fields"].values() if f["type"] in ("enum", "bool") and not f.get("computed")]
        for rid in sorted(recs):
            sig = tuple(recs[rid].get(f) for f in enum_fields)
            groups.setdefault(sig, []).append(recs[rid].get(key))
        for names in groups.values():
            users += names[:2]
    t = now.isoformat()
    for e in model["entities"].values():
        coll = e["name"]
        ids = sorted(R.records(world, e["id"]))
        sample = ids[:per_entity] + ids[-per_entity:] if len(ids) > 2 * per_entity else ids
        for u in users:
            probes.append({"method": "GET", "path": f"/api/{coll}", "query": {}, "body": None, "user": u, "now": t})
            for rid in sample:
                probes.append({"method": "GET", "path": f"/api/{coll}/{rid}", "query": {}, "body": None, "user": u, "now": t})
                for a in e["actions"].values():
                    probes.append({"method": "POST", "path": f"/api/{coll}/{rid}/{a['name']}", "query": {},
                                   "body": {}, "user": u, "now": t})
            if ids:
                src = R.records(world, e["id"])[ids[-1]]
                body = {}
                for f in e["fields"].values():
                    if f.get("computed") or f.get("system"):
                        continue
                    v = src.get(f["id"])
                    if f.get("unique") and isinstance(v, str):
                        v = v + "-probe"
                    if v is not None:
                        body[f["name"]] = v
                probes.append({"method": "POST", "path": f"/api/{coll}", "query": {}, "body": body, "user": u, "now": t})
                first = next((f for f in M.ordered_fields(e) if not f.get("computed") and not f.get("system")), None)
                if first is not None:
                    probes.append({"method": "PATCH", "path": f"/api/{coll}/{ids[0]}", "query": {},
                                   "body": {first["name"]: src.get(first["id"]) if first["type"] != "ref" else src.get(first["id"])},
                                   "user": u, "now": t})
                probes.append({"method": "DELETE", "path": f"/api/{coll}/{ids[-1]}", "query": {}, "body": None, "user": u, "now": t})
    probes.append({"method": "GET", "path": "/api/_outbox", "query": {}, "body": None, "user": users[-1], "now": t})
    return probes


def _run_probe(model, world, p):
    now = dt.datetime.fromisoformat(p["now"]) if p.get("now") else dt.datetime(2026, 1, 1)
    mark = len(world["outbox"])
    status, out, ctx = R.handle_full(model, world, p["method"], p["path"], p.get("query") or {}, p.get("body"), p.get("user"), now)
    emitted = copy.deepcopy(world["outbox"][mark:])
    ctx.rollback()  # every probe sees the same starting state
    del world["outbox"][mark:]
    world_next = world.get("next_id")
    return status, out, emitted


def _target(path):
    parts = [x for x in path.split("/") if x][1:]
    if not parts:
        return None, None
    coll = parts[0]
    return coll, parts


def _op_of(method, parts):
    if parts[0] == "_outbox":
        return "outbox"
    if len(parts) == 1:
        return "list" if method == "GET" else "create"
    if len(parts) == 2:
        return {"GET": "read", "PATCH": "update", "DELETE": "delete"}.get(method, "other")
    return f"action:{parts[2]}"


def _translate(fp, coll, value):
    """Express an old response in the new model's names (renamed fields)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[fp.renamed_fields.get((coll, k), k)] = v
        return out
    return value


def _explain_diff(fp, method, path, old, new):
    """Return None if the difference is inside the footprint, else a reason string."""
    coll, parts = _target(path)
    if coll is None:
        return "unrouted request differs"
    new_coll = fp.renamed_entities.get(coll, coll)
    op = _op_of(method, parts)
    (os_, ob, oe), (ns, nb, ne) = old, new
    if op == "outbox":
        return None if (fp.ops or fp.fields) and _outbox_ok(fp) else "outbox differs"
    if (new_coll, "any") in fp.ops or ("*", "any") in fp.ops:
        return None
    entity_ops = {"list": "read", "read": "read"}
    if os_ != ns or (isinstance(ob, dict) and isinstance(nb, dict) and ob.get("error") != nb.get("error")):
        if new_coll in fp.visibility:
            return None
        if op in ("create", "update", "delete") and (new_coll, op) in fp.ops:
            return None
        if op.startswith("action:") and (new_coll, op) in fp.ops:
            return None
        if ns == 500:
            return f"new version crashes: {nb.get('message') if isinstance(nb, dict) else nb}"
        return f"status {os_} -> {ns} for {op} on {new_coll}, which this change should not affect"
    if oe != ne and not (op.startswith("action:") and (new_coll, op) in fp.ops) and not (op in ("create", "update", "delete") and (new_coll, op) in fp.ops):
        return f"integration messages differ for {op} on {new_coll}"
    if os_ >= 400:
        return None
    if op.startswith("action:") and (new_coll, op) in fp.ops:
        return None
    if op in ("create", "update", "delete") and (new_coll, op) in fp.ops:
        return None
    if op == "list":
        oi = {i["id"]: _translate(fp, new_coll, i) for i in (ob or {}).get("items", [])}
        ni = {i["id"]: i for i in (nb or {}).get("items", [])}
        if set(oi) != set(ni) and new_coll not in fp.visibility:
            return f"list of {new_coll} contains different records"
        for rid in set(oi) & set(ni):
            r = _record_diff(fp, new_coll, oi[rid], ni[rid])
            if r:
                return r
        return None
    if isinstance(ob, dict) and isinstance(nb, dict):
        return _record_diff(fp, new_coll, _translate(fp, new_coll, ob), nb)
    return None if ob == nb else f"response differs for {op} on {new_coll}"


def _outbox_ok(fp):
    return True


def _record_diff(fp, coll, o, n):
    for k in set(o) | set(n):
        if k == "id" and False:
            continue
        if o.get(k) != n.get(k) or (k in o) != (k in n):
            if (coll, k) in fp.fields:
                continue
            if coll in fp.visibility and (k in o) != (k in n):
                continue
            return f"{coll}.{k} changed from {json.dumps(o.get(k))} to {json.dumps(n.get(k))}"
    return None


def replay(old_model, old_world, new_model, new_world, probes, fp, limit_examples=8):
    stats = {"probes": len(probes), "identical": 0, "explained": 0, "unexplained": 0, "examples": [], "explained_examples": []}
    for p in probes:
        old = _run_probe(old_model, old_world, p)
        new = _run_probe(new_model, new_world, _rename_probe(fp, p))
        if _same(old, new, fp, p):
            stats["identical"] += 1
            continue
        why = _explain_diff(fp, p["method"], p["path"], old, new)
        brief = {"request": f"{p['method']} {p['path']} as {p.get('user')}", "old": [old[0], _short(old[1])], "new": [new[0], _short(new[1])]}
        if why is None:
            stats["explained"] += 1
            if len(stats["explained_examples"]) < limit_examples:
                stats["explained_examples"].append(brief)
        else:
            stats["unexplained"] += 1
            if len(stats["examples"]) < limit_examples:
                stats["examples"].append(dict(brief, why=why))
    return stats


def _rename_probe(fp, p):
    coll, parts = _target(p["path"])
    if coll and coll in fp.renamed_entities:
        p = dict(p, path="/api/" + "/".join([fp.renamed_entities[coll]] + parts[1:]))
    if isinstance(p.get("body"), dict) and coll:
        newc = fp.renamed_entities.get(coll, coll)
        p = dict(p, body={fp.renamed_fields.get((newc, k), k): v for k, v in p["body"].items()})
    return p


def _same(old, new, fp, p):
    coll, parts = _target(p["path"])
    newc = fp.renamed_entities.get(coll, coll) if coll else coll
    ob = old[1]
    if isinstance(ob, dict) and "items" in ob and coll:
        ob = {"items": [_translate(fp, newc, i) for i in ob["items"]]}
    elif isinstance(ob, dict) and coll:
        ob = _translate(fp, newc, ob)
    return old[0] == new[0] and ob == new[1] and old[2] == new[2]


def _short(v):
    s = json.dumps(v)
    return s if len(s) < 300 else s[:300] + "..."


# ------------------------------------------------------------------ expectations
def run_expectations(model, world, expects, default_now):
    results = []
    for ex in expects or []:
        w = copy.deepcopy(world)
        steps = ex.get("steps") or [ex]
        ok, detail = True, ""
        for st in steps:
            method, _, path = st["do"].partition(" ")
            path, _, qs = path.partition("?")
            from urllib.parse import parse_qsl
            now = dt.datetime.fromisoformat(st.get("now") or ex.get("now") or default_now)
            status, out = R.handle(model, w, method.upper(), path, dict(parse_qsl(qs)), st.get("body", {} if method.upper() in ("POST", "PATCH") else None),
                                   st.get("as") or ex.get("as"), now)
            if "status" in st and status != st["status"]:
                ok, detail = False, f"{st['do']}: expected status {st['status']}, got {status} {_short(out)}"
                break
            if "json" in st and not _subset(st["json"], out):
                ok, detail = False, f"{st['do']}: expected {json.dumps(st['json'])} within {_short(out)}"
                break
            if "count" in st and (not isinstance(out, dict) or len(out.get("items", [])) != st["count"]):
                ok, detail = False, f"{st['do']}: expected {st['count']} items, got {_short(out)}"
                break
        results.append({"name": ex.get("name") or steps[0]["do"], "passed": ok, "detail": detail})
    return results


def _subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(_subset(e, a) for e, a in zip(expected, actual))
    return expected == actual


# ------------------------------------------------------------------ data check
def data_violations(model, world, now, limit=8):
    problems = []
    ctx = R.Ctx(model, world, None, now)
    for e in model["entities"].values():
        bad = {}
        for rid in sorted(R.records(world, e["id"])):
            errs = R.validate_record(ctx, e, rid, R.records(world, e["id"])[rid], is_new=False)
            for k, msg in errs.items():
                bad.setdefault((k, msg), []).append(rid)
        for (k, msg), rids in bad.items():
            problems.append({"entity": e["name"], "field_or_rule": k, "message": msg, "count": len(rids),
                             "examples": rids[:limit]})
    return problems


# ------------------------------------------------------------------ the pipeline
def load_change(path_or_doc):
    if isinstance(path_or_doc, dict):
        return path_or_doc, None
    import yaml
    with open(path_or_doc) as fh:
        return yaml.safe_load(fh), os.path.dirname(os.path.abspath(path_or_doc))


def apply_change(directory, change, dry_run=False, extra_footprint=(), kind="change", base_dir=None, now=None):
    """Run the full pipeline. Returns the report dict (also stored in the ledger)."""
    t0 = time.perf_counter()
    timings = {}
    store = Store(directory)
    model0, world0 = store.load()
    fresh = model0 is None
    if fresh:
        model0, world0 = M.empty_model(os.path.basename(os.path.abspath(directory))), R.empty_world()
    now = now or dt.datetime.utcnow().replace(microsecond=0)
    report = {"kind": kind, "request": change.get("request", ""), "interpretation": change.get("interpretation", ""),
              "operators": change.get("ops", []), "started": dt.datetime.utcnow().replace(microsecond=0).isoformat(),
              "dry_run": dry_run}
    try:
        ops = O.expand(change.get("ops") or [])
        report["expanded_operators"] = len(ops)
        model1, world1 = M.clone(model0), copy.deepcopy(world0)
        cx = O.ChangeCtx(model1, world1, now, base_dir or directory)
        inverse = []
        for i, op in enumerate(ops):
            try:
                inverse = O.apply(cx, op) + inverse
            except (O.OpError, M.ModelError, E.ExprError, KeyError, TypeError, ValueError) as exc:
                raise ChangeRejected(f"operator {i + 1} ({next(iter(op))}) failed: {exc}") from None
        report["what_happened"] = cx.notes
        report["warnings"] = cx.warnings
        timings["apply_ms"] = _ms(t0)

        t = time.perf_counter()
        static = M.check(model1)
        report["static_check"] = {"problems": static}
        timings["static_ms"] = _ms(t)
        if static:
            raise ChangeRejected("the change leaves parts of the application inconsistent (see static_check); "
                                 "update or remove the dependents in the same change")

        t = time.perf_counter()
        viol = data_violations(model1, world1, now)
        report["data_check"] = {"records": sum(len(r) for r in world1["records"].values()), "violations": viol}
        timings["data_ms"] = _ms(t)
        if viol:
            raise ChangeRejected("existing data does not satisfy the changed application (see data_check); "
                                 "add an update_records operator, a backfill, or `existing: exempt`")

        t = time.perf_counter()
        fp = compute_footprint(model0, model1, world0, world1, list(extra_footprint) + list(change.get("intent") or []))
        report["footprint"] = fp.to_json()
        timings["footprint_ms"] = _ms(t)

        t = time.perf_counter()
        if fresh:
            report["replay"] = {"skipped": "first change: there is no previous version"}
        else:
            probe_now = dt.datetime.fromisoformat(change["probe_now"]) if change.get("probe_now") else now
            probes = store.requests() + generate_probes(model0, world0, probe_now)
            report["replay"] = replay(model0, copy.deepcopy(world0), model1, copy.deepcopy(world1), probes, fp)
            if report["replay"]["unexplained"]:
                raise ChangeRejected("replaying recorded and generated requests shows behaviour changes outside "
                                     "what this change touches (see replay.examples): likely regressions. If they are "
                                     "intended, declare them under `intent:`")
        timings["replay_ms"] = _ms(t)

        t = time.perf_counter()
        exp = run_expectations(model1, world1, change.get("expect"), now.isoformat())
        report["expectations"] = exp
        timings["expect_ms"] = _ms(t)
        if any(not e["passed"] for e in exp):
            raise ChangeRejected("stated expectations fail on the changed application (see expectations)")

        report["inverse"] = inverse
        report["verdict"] = "dry-run passed" if dry_run else "committed"
        timings["total_ms"] = _ms(t0)
        report["timings"] = timings
        if not dry_run:
            store.save_all(model1, world1)
            report["seq"] = store.append_ledger(report)
        return report
    except ChangeRejected as exc:
        report["verdict"] = "rejected"
        report["reason"] = str(exc)
        timings["total_ms"] = _ms(t0)
        report["timings"] = timings
        if not dry_run:
            report["seq"] = store.append_ledger(report)
        return report
    finally:
        store.close()


def revert(directory, seq, dry_run=False, force=False):
    store = Store(directory)
    ledger = store.ledger()
    store.close()
    entry = next((e for e in ledger if e["seq"] == seq), None)
    if entry is None or entry.get("verdict") != "committed":
        return {"verdict": "rejected", "reason": f"change #{seq} is not a committed change"}
    if entry.get("reverted_by"):
        return {"verdict": "rejected", "reason": f"change #{seq} was already reverted"}
    later = [e for e in ledger if e["seq"] > seq and e.get("verdict") == "committed"]
    conflicts = _overlaps(entry, later)
    if conflicts and not force:
        return {"verdict": "rejected", "reason": "later changes build on this one: " + "; ".join(conflicts)
                + ". Revert those first, or rerun with --force to attempt it anyway (it is still fully checked)."}
    fp = entry.get("footprint", {})
    declared = [f"{x}" for x in fp.get("operations", [])] + [f"{v}.read" for v in fp.get("visibility", [])] + \
               [f"{x.split('.')[0]}.field:{x.split('.', 1)[1]}" for x in fp.get("fields", [])]
    change = {"request": f"revert change #{seq}: {entry.get('request', '')}", "ops": entry["inverse"]}
    rep = apply_change(directory, change, dry_run=dry_run, extra_footprint=declared, kind="revert")
    if rep.get("verdict") == "committed":
        st = Store(directory)
        with st.db:
            row = st.db.execute("select json from ledger where seq=?", (seq,)).fetchone()
            d = json.loads(row[0])
            d["reverted_by"] = rep["seq"]
            st.db.execute("update ledger set json=? where seq=?", (json.dumps(d), seq))
        st.close()
    return rep


def _names_touched(entry):
    out = set()
    for d in entry.get("footprint", {}).get("fields", []):
        out.add(d)
    for d in entry.get("footprint", {}).get("operations", []):
        out.add(d)
    return out


def _overlaps(entry, later):
    mine = set()
    for op in entry.get("operators", []):
        if isinstance(op, dict):
            (name, args), = op.items()
            if isinstance(args, dict):
                if "entity" in args and "name" in args:
                    mine.add(f"{args['entity']}.{args['name']}")
                if name == "add_entity":
                    mine.add(args.get("name"))
    out = []
    for e in later:
        for op in e.get("operators", []):
            if isinstance(op, dict):
                (name, args), = op.items()
                if not isinstance(args, dict):
                    continue
                refs = {f"{args.get('entity')}.{args.get('name')}", f"{args.get('entity')}.{args.get('from')}",
                        str(args.get("entity")), str(args.get("name"))}
                text = json.dumps(args)
                hit = [m for m in mine if m and (m in refs or (m.split('.')[-1] in text and m.split('.')[0] in text))]
                if hit:
                    out.append(f"change #{e['seq']} ({e.get('request', '')[:60]}) uses {', '.join(sorted(hit))}")
                    break
    return out


def _ms(t):
    return round((time.perf_counter() - t) * 1000, 1)
