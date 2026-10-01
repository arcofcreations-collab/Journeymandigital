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
        out[("display", e["id"])] = json.dumps(e.get("display"))
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
    for name, fn in (model.get("functions") or {}).items():
        out[("function", name)] = json.dumps(fn, sort_keys=True)
    return out


def _loc_labels(mdl, loc):
    """Footprint labels for the behaviour an expression location controls."""
    ent = mdl["entities"][loc[1]]
    n = ent["name"]
    kind = loc[0]
    if kind == "field":
        f = ent["fields"][loc[2]]
        if loc[3] in ("computed", "read_if"):
            return {f"{n}.field:{f['name']}"}
        return {f"{n}.create", f"{n}.update"}
    if kind == "rule":
        return {f"{n}.{loc[2]}"}
    if kind == "constraint":
        return {f"{n}.create", f"{n}.update"}
    if kind == "action":
        return {_action_part(n, ent["actions"][loc[2]]["name"], loc[3])}
    if kind == "trigger":
        return {f"{n}.{ent['triggers'][loc[2]]['on']}"}
    return set()


def _action_part(n, aname, key):
    part = {"allow": "allow", "guard": "guard", "guard_message": "guard", "effects": "effects", "params": "params"}.get(key)
    return f"{n}.action:{aname}" + (f".{part}" if part else "")


def _touched_ids(old_world, new_world):
    out = {}
    for eid in set(old_world["records"]) | set(new_world["records"]):
        o, n = old_world["records"].get(eid, {}), new_world["records"].get(eid, {})
        ids = {rid for rid in set(o) | set(n) if o.get(rid) != n.get(rid)}
        if ids:
            out[eid] = ids
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
    """What a change may alter in observable behaviour, as labels:

      "E.read"            which records of E are visible
      "E.create" | "E.update" | "E.delete" | "E.action:N" | "E.any"   outcome of an operation
      "E.field:F"         the value or presence of field F in E's records

    ``direct`` labels come from elements the operators modify themselves; ``consequences`` are
    labels reached only through dependencies (other features that read what changed). Direct
    differences are accepted; consequences must be acknowledged by the change.
    """

    def __init__(self):
        self.direct = set()
        self.consequences = set()
        self.renamed_fields = {}   # (entity new name, old field name) -> new field name
        self.renamed_entities = {}  # old name -> new name
        self.reasons = []
        self.declared = []

    def all(self):
        return self.direct | self.consequences

    def to_json(self):
        return {"direct": sorted(self.direct), "consequences": sorted(self.consequences - self.direct),
                "renamed_fields": {f"{e}.{o}": n for (e, o), n in self.renamed_fields.items()},
                "renamed_entities": self.renamed_entities, "declared": self.declared,
                "why": self.reasons[:200]}


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

    for eid, e in new_model["entities"].items():
        oe = old_model["entities"].get(eid)
        if oe and oe["name"] != e["name"]:
            fp.renamed_entities[oe["name"]] = e["name"]
        if oe:
            for fid, f in e["fields"].items():
                of = oe["fields"].get(fid)
                if of and of["name"] != f["name"]:
                    fp.renamed_fields[(e["name"], of["name"])] = f["name"]

    D = fp.direct
    seeds_fields, seeds_colls = set(), set()  # what dependents may read: (ename, fname), enames
    for k in changed:
        kind = k[0]
        if kind == "entity":
            eid = k[1]
            n = ename(eid)
            if eid not in old_model["entities"] or eid not in new_model["entities"]:
                D.update({f"{n}.any", f"{n}.read"})
                seeds_colls.add(n)
                fp.reasons.append(f"entity {n} added or removed")
        elif kind == "field":
            eid, fid = k[1], k[2]
            n, f = ename(eid), fname(eid, fid)
            D.update({f"{n}.field:{f}", f"{n}.create", f"{n}.update"})
            seeds_fields.add((n, f))
            for mdl in (old_model, new_model):  # a reference's on_delete policy governs deletes of its target
                fd = mdl["entities"].get(eid, {}).get("fields", {}).get(fid)
                if fd and M.refers_to(fd) in mdl["entities"]:
                    D.add(f"{mdl['entities'][M.refers_to(fd)]['name']}.delete")
            for old_name, new_name in fp.renamed_fields.items():
                if old_name[0] == n and new_name == f:
                    D.add(f"{n}.field:{old_name[1]}")
            fp.reasons.append(f"field {n}.{f} changed")
        elif kind == "rule":
            eid, rule = k[1], k[2]
            n = ename(eid)
            D.add(f"{n}.{rule}")
            fp.reasons.append(f"rule {n}.{rule} changed")
        elif kind == "constraint":
            n = ename(k[1])
            D.update({f"{n}.create", f"{n}.update"})
            fp.reasons.append(f"a constraint on {n} changed")
            for e in new_model["entities"].values():
                for a in e["actions"].values():
                    if _writes(a["effects"], n, e["name"]):
                        fp.consequences.add(f"{e['name']}.action:{a['name']}")
                        fp.reasons.append(f"action {e['name']}.{a['name']} writes {n}, so the constraint can affect it")
        elif kind == "action":
            eid, aid = k[1], k[2]
            n = ename(eid)
            a0 = old_model["entities"].get(eid, {}).get("actions", {}).get(aid)
            a1 = new_model["entities"].get(eid, {}).get("actions", {}).get(aid)
            if not a0 or not a1 or a0["name"] != a1["name"]:
                for a in (a0, a1):
                    if a:
                        D.add(f"{n}.action:{a['name']}")
            else:
                for key in ("allow", "guard", "guard_message", "effects", "params"):
                    if json.dumps(a0.get(key), sort_keys=True) != json.dumps(a1.get(key), sort_keys=True):
                        D.add(_action_part(n, a1["name"], key))
            fp.reasons.append(f"action {n}.{aid} changed")
        elif kind == "trigger":
            eid, tid = k[1], k[2]
            n = ename(eid)
            for mdl in (new_model, old_model):
                t = mdl["entities"].get(eid, {}).get("triggers", {}).get(tid)
                if t:
                    D.add(f"{n}.{t['on']}")
                    # everything else that causes this event now behaves differently too
                    for e in mdl["entities"].values():
                        for a in e["actions"].values():
                            if _causes(a["effects"], n, t["on"], e["name"]):
                                fp.consequences.add(f"{e['name']}.action:{a['name']}")
                                fp.reasons.append(f"action {e['name']}.{a['name']} can fire the changed trigger on {n}")
                        for ot in e["triggers"].values():
                            if ot["id"] != tid and _causes(ot["effects"], n, t["on"], e["name"]):
                                fp.consequences.add(f"{e['name']}.{ot['on']}")
            fp.reasons.append(f"trigger on {n} changed")
        elif kind == "display":
            fp.reasons.append(f"how {ename(k[1])} records are shown in the UI changed (no API effect)")
        elif kind == "function":
            # every expression that calls the function changes with it: those behaviours are direct
            for mdl in (new_model, old_model):
                for loc, ent, src, kw in M.expressions(mdl):
                    try:
                        an = E.analyse(src, M.tenv_for_location(mdl, ent, kw))
                    except E.ExprError:
                        continue
                    if k[1] in an.calls:
                        D.update(_loc_labels(mdl, loc))
            fp.reasons.append(f"function {k[1]} changed")
        elif kind == "users":
            D.add("*.any")
            fp.reasons.append("the user directory changed")

    dfields, membership = _data_changes(old_world, new_world, new_model)
    for eid, fid in dfields:
        n, f = ename(eid), fname(eid, fid)
        D.add(f"{n}.field:{f}")
        seeds_fields.add((n, f))
        fp.reasons.append(f"stored values of {n}.{f} changed")
    for eid in membership:
        n = ename(eid)
        D.add(f"{n}.read")
        seeds_colls.add(n)
        fp.reasons.append(f"records of {n} added or removed")
    ue = M.user_entity(new_model)
    if ue and (any(eid == ue["id"] for eid, _ in dfields) or ue["id"] in membership):
        D.add("*.any")
        fp.reasons.append("user records changed: any request may now authenticate differently")

    for mdl in (new_model, old_model):
        _close(mdl, fp, seeds_fields, seeds_colls)
    for d in declared:
        fp.consequences.add(d)
        fp.declared.append(d)
    return fp


def _causes(effects, target, event, own):
    """Can these effects cause `event` (create/update/delete/action:x) on entity `target`?"""
    for eff in effects or []:
        if event == "create" and eff.get("create") == target:
            return True
        if event == "update" and (("update" in eff) or ("set" in eff and own == target)):
            return True
        if event == "delete" and "delete" in eff:
            return True
        for key in ("then", "else", "do"):
            if _causes(eff.get(key), target, event, own):
                return True
    return False


def scope_warnings(fp, change):
    """Elements this change modifies that neither its request nor its interpretation mentions.
    Not a rejection: a prompt to confirm that an edit outside the stated scope is intended."""
    import re
    text = (str(change.get("request") or "") + " " + str(change.get("interpretation") or "")).lower()
    words = set(re.findall(r"[a-z0-9_]+", text))

    def mentioned(name):
        name = name.lower()
        variants = {name, name.rstrip("s"), name + "s", name.replace("_", " ")}
        return any(v in words or (" " in v and v in text) for v in variants)
    out = []
    for lab in sorted(fp.direct):
        ent, _, rest = lab.partition(".")
        if ent == "*" or not mentioned(ent) and not mentioned(rest.split(":")[-1].split(".")[0]):
            out.append(lab)
        elif rest.startswith("field:") and not mentioned(rest[6:]) and not mentioned(ent):
            out.append(lab)
    return out


def _writes(effects, target, own):
    for eff in effects or []:
        if eff.get("create") == target or ("set" in eff and "update" not in eff and own == target):
            return True
        if "update" in eff or "delete" in eff:
            return True  # target type unknown statically: be conservative
        if any(_writes(eff.get(k), target, own) for k in ("then", "else", "do")):
            return True
    return False


def _close(mdl, fp, seeds_fields, seeds_colls):
    """Every behaviour that reads (transitively) what changed becomes a consequence."""
    deps = M.dependencies(mdl)
    changed_pairs, changed_colls = set(seeds_fields), set(seeds_colls)
    C = fp.consequences
    grew, seen = True, set()
    while grew:
        grew = False
        for loc, (reads, colls, owner) in deps.items():
            if loc in seen or not (reads & changed_pairs or colls & changed_colls):
                continue
            seen.add(loc)
            grew = True
            kind = loc[0]
            ent = mdl["entities"][loc[1]]
            n = ent["name"]
            if kind == "field":
                f = ent["fields"][loc[2]]
                if loc[3] == "computed":
                    C.add(f"{n}.field:{f['name']}")
                    changed_pairs.add((n, f["name"]))
                elif loc[3] == "read_if":
                    C.add(f"{n}.field:{f['name']}")
                else:
                    C.update({f"{n}.create", f"{n}.update"})
            elif kind == "rule":
                C.add(f"{n}.{loc[2]}")
            elif kind == "constraint":
                C.update({f"{n}.create", f"{n}.update"})
            elif kind == "action":
                C.add(_action_part(n, ent["actions"][loc[2]]["name"], loc[3]))
            elif kind == "trigger":
                C.add(f"{n}.{ent['triggers'][loc[2]]['on']}")
            fp.reasons.append(f"{M.describe(mdl, loc)} reads what changed")


# ------------------------------------------------------------------ probes & replay
def generate_probes(model, world, now, per_entity=3, focus=None, thorough=False):
    """The probe set = every v1 probe, unchanged, followed by the v2 additions.

    Keeping the v1 set verbatim makes coverage monotonic: a behaviour difference that v1 probes
    exposed is still exposed (the same requests are still sent and compared). See REVISIONS P3."""
    seen, out = set(), []
    for p in _probes_v1(model, world, now, per_entity=per_entity, focus=focus) + _probes_extra(
            model, world, now, per_entity=per_entity, focus=focus, thorough=thorough):
        key = json.dumps(p, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _probes_v1(model, world, now, per_entity=3, focus=None):
    """v1 probe set, kept verbatim (see generate_probes). Requests that exercise every collection, record operation and action as several users.

    ``focus`` maps entity id -> record ids whose stored data the change touched; those records
    are always probed, because their dependent behaviour is where consequences show up."""
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
        sample = ids[:per_entity] + ids[-per_entity:] if len(ids) > 2 * per_entity else list(ids)
        for rid in sorted((focus or {}).get(e["id"], ()))[:40]:
            if rid not in sample and rid in R.records(world, e["id"]):
                sample.append(rid)
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


def _probes_extra(model, world, now, per_entity=3, focus=None, thorough=False):
    """Requests that exercise every collection, record operation and action as several users.

    ``focus`` maps entity id -> record ids whose stored data the change touched; those records
    are always probed, because their dependent behaviour is where consequences show up.
    Besides normal requests, the set includes edge cases: filters (including an unknown field),
    an empty create, a create with fractional numbers, and a no-op PATCH of every writable field
    (field permissions). ``thorough`` (engine-upgrade snapshots) uses every user and up to 40
    records per collection."""
    probes = []
    ue = M.user_entity(model)
    users = [None]
    if ue:
        key = model["users"]["key"]
        recs = R.records(world, ue["id"])
        if thorough:
            users += [recs[rid].get(key) for rid in sorted(recs)]
        else:
            groups = {}
            enum_fields = [f["id"] for f in ue["fields"].values() if f["type"] in ("enum", "bool") and not f.get("computed")]
            for rid in sorted(recs):
                sig = tuple(recs[rid].get(f) for f in enum_fields)
                groups.setdefault(sig, []).append(recs[rid].get(key))
            for names in groups.values():
                users += names[:2]
    t = now.isoformat()
    if thorough:
        per_entity = 20
    for e in model["entities"].values():
        coll = e["name"]
        ids = sorted(R.records(world, e["id"]))
        sample = ids[:per_entity] + ids[-per_entity:] if len(ids) > 2 * per_entity else list(ids)
        for rid in sorted((focus or {}).get(e["id"], ()))[:40]:
            if rid not in sample and rid in R.records(world, e["id"]):
                sample.append(rid)
        stored = [f for f in M.ordered_fields(e) if not f.get("computed")]
        writable = [f for f in stored if not f.get("system")]
        first_rec = R.records(world, e["id"]).get(ids[0]) if ids else None
        filters = []
        if first_rec is not None:
            for f in stored[:3]:
                v = first_rec.get(f["id"])
                if v is not None and not isinstance(v, (list, dict)):
                    filters.append({f["name"]: json.dumps(v) if isinstance(v, bool) else str(v)})
        filters.append({"no_such_field": "1"})
        for u in users:
            probes.append({"method": "GET", "path": f"/api/{coll}", "query": {}, "body": None, "user": u, "now": t})
            for q in filters:
                probes.append({"method": "GET", "path": f"/api/{coll}", "query": q, "body": None, "user": u, "now": t})
            for rid in sample:
                probes.append({"method": "GET", "path": f"/api/{coll}/{rid}", "query": {}, "body": None, "user": u, "now": t})
                for a in e["actions"].values():
                    probes.append({"method": "POST", "path": f"/api/{coll}/{rid}/{a['name']}", "query": {},
                                   "body": {}, "user": u, "now": t})
            if ids:
                src = R.records(world, e["id"])[ids[-1]]
                body = {}
                for f in writable:
                    v = src.get(f["id"])
                    if f.get("unique") and isinstance(v, str):
                        v = v + "-probe"
                    if v is not None:
                        body[f["name"]] = v
                probes.append({"method": "POST", "path": f"/api/{coll}", "query": {}, "body": body, "user": u, "now": t})
                numeric = {f["name"] for f in writable if f["type"] == "number"}
                frac = {k: (float(v) + 0.125 if k in numeric and isinstance(v, (int, float)) and not isinstance(v, bool) else v)
                        for k, v in body.items()}
                if frac != body:
                    probes.append({"method": "POST", "path": f"/api/{coll}", "query": {}, "body": frac, "user": u, "now": t})
                dup = {f["name"]: src.get(f["id"]) for f in writable if src.get(f["id"]) is not None}
                if any(f.get("unique") for f in writable) and dup != body:
                    probes.append({"method": "POST", "path": f"/api/{coll}", "query": {}, "body": dup, "user": u, "now": t})
                probes.append({"method": "POST", "path": f"/api/{coll}", "query": {}, "body": {}, "user": u, "now": t})
                for f in writable:
                    probes.append({"method": "PATCH", "path": f"/api/{coll}/{ids[0]}", "query": {},
                                   "body": {f["name"]: first_rec.get(f["id"])}, "user": u, "now": t})
                probes.append({"method": "DELETE", "path": f"/api/{coll}/{ids[-1]}", "query": {}, "body": None, "user": u, "now": t})
            if ue and e["id"] == ue["id"] and u is not None:
                own = next((rid for rid, d in R.records(world, e["id"]).items() if d.get(model["users"]["key"]) == u), None)
                if own is not None:
                    for f in writable:
                        probes.append({"method": "PATCH", "path": f"/api/{coll}/{own}", "query": {},
                                       "body": {f["name"]: R.records(world, e["id"])[own].get(f["id"])}, "user": u, "now": t})
    probes.append({"method": "GET", "path": "/api/_outbox", "query": {}, "body": None, "user": users[-1], "now": t})
    return probes


def _run_probe(model, world, p):
    """(status, body, emitted messages, records written) -- the last so that side-effects a
    response does not show (e.g. the loan an action creates) are compared too."""
    now = dt.datetime.fromisoformat(p["now"]) if p.get("now") else dt.datetime(2026, 1, 1)
    mark = len(world["outbox"])
    status, out, ctx = R.handle_full(model, world, p["method"], p["path"], p.get("query") or {}, p.get("body"), p.get("user"), now)
    emitted = copy.deepcopy(world["outbox"][mark:])
    writes = {}
    if status < 400:
        for eid, rid, _prev in ctx.journal:
            ent = model["entities"].get(eid)
            if not ent:
                continue
            data = R.records(world, eid).get(rid)
            writes.setdefault(ent["name"], {})[str(rid)] = (
                None if data is None else {f["name"]: data.get(fid) for fid, f in ent["fields"].items() if not f.get("computed")})
    ctx.rollback()  # every probe sees the same starting state
    del world["outbox"][mark:]
    return status, out, emitted, writes


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


def _op_labels(n, op, os_, ns):
    """Which part of an operation explains a change between two status codes.
    403 comes from a permission (rule/allow), 409 from a guard, 400 from input validation;
    `fail` effects can produce any of them."""
    statuses = {os_, ns}
    if op.startswith("action:"):
        a = f"{n}.{op}"
        if 404 in statuses:
            return [{a}]
        if 403 in statuses:
            return [{f"{a}.allow"}, {f"{a}.effects"}, {f"{n}.read"}]
        if 409 in statuses:
            return [{f"{a}.guard"}, {f"{a}.effects"}]
        if 400 in statuses:
            return [{f"{a}.params"}, {f"{a}.effects"}]
        return [{f"{a}.effects"}]
    if op in ("create", "update", "delete"):
        if 403 in statuses:
            return [{f"{n}.{op}"}, {f"{n}.read"}]
        if 409 in statuses:
            return [{f"{n}.{op}_guard"}, {f"{n}.{op}"}] if op != "create" else [{f"{n}.create_guard"}]
        return [{f"{n}.{op}"}]
    return [{f"{n}.read"}]


def _labels_needed(fp, method, path, old, new, query=None):
    """The footprint labels that would explain the difference between two outcomes.
    Returns a list of alternatives; each alternative is a set of labels that together explain it."""
    coll, parts = _target(path)
    if coll is None:
        return [{"*.any"}]
    n = fp.renamed_entities.get(coll, coll)
    op = _op_of(method, parts)
    (os_, ob, oe, ow), (ns, nb, ne, nw) = old, new
    base = [{f"{n}.any"}, {"*.any"}]
    wl = _write_labels(fp, ow, nw)
    if op == "outbox":
        return base + [{"*.outbox"}]
    if (os_, ob, oe) == (ns, nb, ne):
        # only the stored side-effects differ: the operation's effects changed, or exactly those fields did
        return base + _op_labels(n, op, os_, ns) + [wl]
    if os_ != ns or (isinstance(ob, dict) and isinstance(nb, dict) and ob.get("error") != nb.get("error")):
        if op in ("list", "read"):
            return base + [{f"{n}.read"}]
        return base + _op_labels(n, op, os_, ns)
    if oe != ne:
        return base + _op_labels(n, op, os_, ns)
    if os_ >= 400:
        return [set()]
    if op not in ("list", "read"):
        alts = base + _op_labels(n, op, os_, ns)
        keys = _diff_keys(fp, n, _translate(fp, n, ob) if isinstance(ob, dict) else ob, nb)
        if keys is not None:
            alts.append({f"{n}.field:{k}" for k in keys} | wl)
        return alts
    if op == "list":
        oi = {i["id"]: _translate(fp, n, i) for i in (ob or {}).get("items", [])}
        ni = {i["id"]: i for i in (nb or {}).get("items", [])}
        need = set()
        fields = set()
        for rid in set(oi) & set(ni):
            fields |= {f"{n}.field:{k}" for k in _diff_keys(fp, n, oi[rid], ni[rid]) or []}
        alts = base
        if set(oi) != set(ni):
            need.add(f"{n}.read")
            if query:  # a filtered list changes membership when the filtered field changes
                alts = alts + [fields | {f"{n}.field:{fp.renamed_fields.get((n, k), k)}" for k in query}]
        return alts + [need | fields]
    keys = _diff_keys(fp, n, _translate(fp, n, ob) if isinstance(ob, dict) else ob, nb)
    return base + [{f"{n}.field:{k}" for k in keys}] if keys is not None else base


def covers(have, label):
    """Does a set of labels explain `label`? Parents cover their parts: E.action:N covers
    E.action:N.allow etc., E.any covers everything of E, *.any and 'all' cover everything."""
    if label in have or "*.any" in have or "all" in have:
        return True
    ent = label.split(".", 1)[0]
    if f"{ent}.any" in have:
        return True
    parts = label.split(".")
    for k in range(len(parts) - 1, 0, -1):
        if ".".join(parts[:k]) in have and parts[k - 1].startswith("action:"):
            return True
    if label.endswith("_guard") and label[: -len("_guard")] in have:
        return True  # older labels: E.update covered E.update_guard
    return False


def _covered(need, have):
    return all(covers(have, x) for x in need)


def _translate_writes(fp, w):
    out = {}
    for ename, recs in (w or {}).items():
        en = fp.renamed_entities.get(ename, ename)
        out[en] = {rid: (None if d is None else {fp.renamed_fields.get((en, k), k): v for k, v in d.items()})
                   for rid, d in recs.items()}
    return out


def _write_labels(fp, ow, nw):
    """Labels explaining a difference in written records: the fields whose written values differ
    (fields present on only one side are new or removed fields: explained by their own label)."""
    o = _translate_writes(fp, ow)
    need = set()
    for en in set(o) | set(nw or {}):
        a, b = o.get(en, {}), (nw or {}).get(en, {})
        for rid in set(a) | set(b):
            x, y = a.get(rid), b.get(rid)
            if (x is None) != (y is None):
                need.add(f"{en}.create" if y is not None else f"{en}.delete")
                continue
            if x is None:
                continue
            for k in set(x) & set(y):
                if x[k] != y[k]:
                    need.add(f"{en}.field:{k}")
    return need


def _diff_keys(fp, n, o, nw):
    if not isinstance(o, dict) or not isinstance(nw, dict):
        return None
    return {k for k in set(o) | set(nw) if o.get(k) != nw.get(k) or (k in o) != (k in nw)}


def classify(fp, acknowledged, method, path, old, new, query=None):
    """'direct', 'acknowledged', 'consequence' or 'unexplained' (with the labels involved)."""
    alts = _labels_needed(fp, method, path, old, new, query)
    ack = set(acknowledged)
    possible = fp.all() | ack
    best = None
    for need in alts:
        if _covered(need, fp.direct):
            return "direct", need
        if _covered(need, possible):
            missing = {x for x in need if not covers(fp.direct, x) and not covers(ack, x)}
            if not missing:
                best = best or ("acknowledged", need)
            elif _covered(need, fp.all()):
                best = best if best and best[0] == "acknowledged" else ("consequence", missing)
    if best:
        return best
    smallest = min(alts, key=len)
    return "unexplained", smallest


def replay(old_model, old_world, new_model, new_world, probes, fp, acknowledged=(), limit_examples=8):
    stats = {"probes": len(probes), "identical": 0, "direct": 0, "acknowledged": 0, "consequence": 0,
             "unexplained": 0, "consequence_labels": {}, "examples": [], "direct_examples": []}
    stats["_golden"] = []
    for p in probes:
        old = _run_probe(old_model, old_world, p)
        np_ = _rename_probe(fp, p)
        new = _run_probe(new_model, new_world, np_)
        stats["_golden"].append([np_, list(new)])
        if _same(old, new, fp, p):
            stats["identical"] += 1
            continue
        verdict, labels = classify(fp, acknowledged, p["method"], p["path"], old, new, p.get("query"))
        if new[0] == 500 and old[0] != 500:
            verdict, labels = "unexplained", {"crash"}
        stats[verdict] += 1
        brief = {"request": f"{p['method']} {p['path']} as {p.get('user')}" + (f" {json.dumps(p.get('body'))}" if p.get("body") else ""),
                 "before": [old[0], _short(old[1])], "after": [new[0], _short(new[1])], "labels": sorted(labels)}
        if verdict == "consequence":
            for lab in labels:
                stats["consequence_labels"][lab] = stats["consequence_labels"].get(lab, 0) + 1
        if verdict in ("consequence", "unexplained") and len(stats["examples"]) < limit_examples:
            stats["examples"].append(dict(brief, kind=verdict))
        elif verdict in ("direct", "acknowledged") and len(stats["direct_examples"]) < limit_examples:
            stats["direct_examples"].append(brief)
    return stats


def _rename_probe(fp, p):
    coll, parts = _target(p["path"])
    if coll and coll in fp.renamed_entities:
        p = dict(p, path="/api/" + "/".join([fp.renamed_entities[coll]] + parts[1:]))
    if coll:
        newc = fp.renamed_entities.get(coll, coll)
        if isinstance(p.get("body"), dict):
            p = dict(p, body={fp.renamed_fields.get((newc, k), k): v for k, v in p["body"].items()})
        if p.get("query"):
            p = dict(p, query={fp.renamed_fields.get((newc, k), k): v for k, v in p["query"].items()})
    return p


def _same(old, new, fp, p):
    coll, parts = _target(p["path"])
    newc = fp.renamed_entities.get(coll, coll) if coll else coll
    ob = old[1]
    if isinstance(ob, dict) and "items" in ob and coll:
        ob = {"items": [_translate(fp, newc, i) for i in ob["items"]]}
    elif isinstance(ob, dict) and coll:
        ob = _translate(fp, newc, ob)
    if not (old[0] == new[0] and ob == new[1] and old[2] == new[2]):
        return False
    return not _write_labels(fp, old[3] if len(old) > 3 else {}, new[3] if len(new) > 3 else {})


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
            if path.startswith("/ui/"):
                from . import ui as U
                from . import uicheck
                status, html = U.handle(model, w, path, st.get("as") or ex.get("as"), now)
                if "status" in st and status != st["status"]:
                    ok, detail = False, f"{st['do']}: expected status {st['status']}, got {status}"
                    break
                if st.get("ui"):
                    problem = uicheck.check(uicheck.parse(html), st["ui"])
                    if problem:
                        ok, detail = False, f"{st['do']}: {problem}"
                        break
                continue
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
def _yaml_keys(v):
    """YAML 1.1 reads the keys `on:` / `off:` as booleans; in a change file they are always names."""
    if isinstance(v, dict):
        return {({True: "on", False: "off"}.get(k, k) if isinstance(k, bool) else k): _yaml_keys(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_yaml_keys(x) for x in v]
    return v


def load_change(path_or_doc):
    if isinstance(path_or_doc, dict):
        return _yaml_keys(path_or_doc), None
    import yaml
    with open(path_or_doc) as fh:
        return _yaml_keys(yaml.safe_load(fh)), os.path.dirname(os.path.abspath(path_or_doc))


def apply_change(directory, change, dry_run=False, extra_footprint=(), kind="change", base_dir=None, now=None):
    """Run the full pipeline. Returns the report dict (also stored in the ledger)."""
    t0 = time.perf_counter()
    change = _yaml_keys(change)
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
        fp = compute_footprint(model0, model1, world0, world1, list(extra_footprint))
        report["footprint"] = fp.to_json()
        report["scope_warnings"] = scope_warnings(fp, change)
        timings["footprint_ms"] = _ms(t)

        t = time.perf_counter()
        if fresh:
            report["replay"] = {"skipped": "first change: there is no previous version"}
        else:
            probe_now = dt.datetime.fromisoformat(change["probe_now"]) if change.get("probe_now") else now
            probes = store.requests() + generate_probes(model0, world0, probe_now, focus=_touched_ids(world0, world1))
            ack = list(change.get("consequences") or [])
            if isinstance(change.get("consequences"), str):
                ack = [change["consequences"]]
            report["replay"] = replay(model0, copy.deepcopy(world0), model1, copy.deepcopy(world1), probes, fp, ack)
            rp = report["replay"]
            if rp["unexplained"]:
                raise ChangeRejected("replaying recorded and generated requests shows behaviour changes that nothing in "
                                     "this change accounts for (see replay.examples): regressions or engine faults")
            if rp["consequence"]:
                labs = ", ".join(sorted(rp["consequence_labels"]))
                raise ChangeRejected(f"this change also alters other behaviour through dependencies: {labs} "
                                     f"(see replay.examples). If that is intended, list them under `consequences:`; "
                                     f"otherwise adjust the change")
        timings["replay_ms"] = _ms(t)

        t = time.perf_counter()
        exp = run_expectations(model1, world1, change.get("expect"), now.isoformat())
        report["expectations"] = exp
        timings["expect_ms"] = _ms(t)
        if any(not e["passed"] for e in exp):
            raise ChangeRejected("stated expectations fail on the changed application (see expectations)")

        report["inverse"] = inverse
        report["verdict"] = "dry-run passed" if dry_run else "committed"
        (report.get("replay") or {}).pop("_golden", None)
        timings["total_ms"] = _ms(t0)
        report["timings"] = timings
        if not dry_run:
            store.save_all(model1, world1)
            report["seq"] = store.append_ledger(report)
            golden = [[p, list(_run_probe(model1, world1, p))] for p in
                      store.requests() + generate_probes(model1, world1, now, thorough=True)]
            golden += [[p, list(_run_any(model1, world1, p))] for p in ui_probes(model1, world1, now)]
            store.save_golden({"engine": engine_version(), "seq": report["seq"], "world": world1,
                               "probes": golden})
        return report
    except ChangeRejected as exc:
        (report.get("replay") or {}).pop("_golden", None)
        report["verdict"] = "rejected"
        report["reason"] = str(exc)
        timings["total_ms"] = _ms(t0)
        report["timings"] = timings
        if not dry_run:
            report["seq"] = store.append_ledger(report)
        return report
    finally:
        store.close()


def engine_version():
    """Hash of the engine's source files (what an upgrade check compares against)."""
    import hashlib
    h = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for f in sorted(os.listdir(here)):
        if f.endswith(".py"):
            with open(os.path.join(here, f), "rb") as fh:
                h.update(f.encode() + fh.read())
    return h.hexdigest()[:16]


def ui_probes(model, world, now, per_entity=3):
    """UI pages for the golden snapshot: list, a few detail pages and the create form, as each
    sampled user. (Replay of application changes compares the API; engine upgrades also the UI.)"""
    sample_users = sorted({p.get("user") for p in generate_probes(model, world, now, per_entity=1)}, key=str)
    out = []
    t = now.isoformat()
    for e in model["entities"].values():
        ids = sorted(R.records(world, e["id"]))
        sample = ids[:per_entity] + ids[-per_entity:] if len(ids) > 2 * per_entity else ids
        for u in sample_users:
            out.append({"method": "GET", "path": f"/ui/{e['name']}", "user": u, "now": t, "ui": True})
            out.append({"method": "GET", "path": f"/ui/{e['name']}/new", "user": u, "now": t, "ui": True})
            for rid in sample:
                out.append({"method": "GET", "path": f"/ui/{e['name']}/{rid}", "user": u, "now": t, "ui": True})
    return out


def _run_any(model, world, p):
    if p.get("ui"):
        from . import ui as U
        now = dt.datetime.fromisoformat(p["now"])
        return U.handle(model, world, p["path"], p.get("user"), now)
    return _run_probe(model, world, p)


def snapshot(directory):
    """Record golden responses for the current state (also done automatically on every commit)."""
    store = Store(directory)
    model, world = store.load()
    now = dt.datetime.utcnow().replace(microsecond=0)
    probes = store.requests() + generate_probes(model, world, now, thorough=True) + ui_probes(model, world, now)
    golden = [[p, list(_run_any(model, copy.deepcopy(world), p))] for p in probes]
    store.save_golden({"engine": engine_version(), "seq": None, "world": world, "probes": golden})
    store.close()
    return len(golden)


def upgrade_check(directory, limit_examples=10):
    """Replay the golden probes against the installed engine, on the data as it was when they were
    recorded. Any difference is a behaviour change caused by the engine, not by the application."""
    store = Store(directory)
    model, _ = store.load()
    g = store.golden()
    store.close()
    if not g:
        return {"verdict": "no snapshot", "reason": "no golden snapshot yet: run `accrete snapshot APP` with the old engine"}
    world = g["world"]
    world["records"] = {eid: {int(k): v for k, v in recs.items()} for eid, recs in world["records"].items()}
    diffs = []
    for p, want in g["probes"]:
        got = _run_any(model, copy.deepcopy(world), p)
        if json.loads(json.dumps(list(got), default=str)) != json.loads(json.dumps(want, default=str)):
            diffs.append({"request": f"{p['method']} {p['path']} as {p.get('user')}" + (f" {json.dumps(p.get('body'))}" if p.get("body") else ""),
                          "before": [want[0], _short(want[1])], "after": [got[0], _short(got[1])]})
    return {"verdict": "same" if not diffs else "DIFFERENT", "probes": len(g["probes"]), "differences": len(diffs),
            "recorded_with_engine": g["engine"], "current_engine": engine_version(), "examples": diffs[:limit_examples]}


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
    # undoing a change may alter exactly what the change altered (and what it acknowledged)
    ack = list(fp.get("direct", [])) + list(fp.get("consequences", [])) + list(fp.get("declared", []))
    for k, v in fp.get("renamed_fields", {}).items():
        ent = k.split(".", 1)[0]
        ack.append(f"{ent}.field:{v}")
        ack.append(f"{ent}.field:{k.split('.', 1)[1]}")
    change = {"request": f"revert change #{seq}: {entry.get('request', '')}", "ops": entry["inverse"],
              "consequences": ack}
    rep = apply_change(directory, change, dry_run=dry_run, kind="revert")
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
