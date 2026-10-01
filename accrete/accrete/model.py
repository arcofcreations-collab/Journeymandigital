"""The application model: one structure from which every behaviour is derived.

Elements have stable ids; names are labels. Stored records are keyed by field *id*, so a
rename never touches data. Every behavioural element is an expression (see expr.py).

model = {
  "app": str, "users": {"entity": eid, "key": fid},
  "entities": {eid: Entity},
  "seq": int                                 # id counter
}
Entity = {
  "id", "name",
  "fields": {fid: {"id","name","type","required","unique","values","ref","default",
                   "computed","system","read_if","write_if","label"}},
  "order": [fid, ...],
  "rules": {"read","create","update","delete","update_guard","delete_guard"},   # expressions
  "guard_messages": {...},
  "constraints": {cid: {"id","name","expr","message","since"}},
  "actions": {aid: {"id","name","params":{pname:{type,required,ref,values}},
                    "allow","guard","guard_message","effects":[...]}},
  "triggers": {tid: {"id","name","on","when","effects":[...]}},
}
Effects (lists, executed in order):
  {"set": {field: expr}}                       target record
  {"create": entity, "values": {field: expr}, "as": var}
  {"update": expr_records, "set": {field: expr}}
  {"delete": expr_records}
  {"emit": channel, "payload": {key: expr}}
  {"fail": message_expr, "status": 400|403|409, "when": expr}
  {"if": expr, "then": [...], "else": [...]}
"""
from __future__ import annotations

import copy

from . import expr as E

FIELD_TYPES = {"text", "int", "number", "bool", "date", "datetime", "enum", "ref"}
RULES = ("read", "create", "update", "delete", "update_guard", "delete_guard")
EVENTS = ("create", "update", "delete")


class ModelError(Exception):
    pass


def empty_model(app: str) -> dict:
    return {"app": app, "users": None, "entities": {}, "seq": 0}


def new_id(model: dict, prefix: str) -> str:
    model["seq"] += 1
    return f"{prefix}{model['seq']}"


# ------------------------------------------------------------------ lookups
def entity(model, name_or_id):
    ents = model["entities"]
    if name_or_id in ents:
        return ents[name_or_id]
    for e in ents.values():
        if e["name"] == name_or_id:
            return e
    raise ModelError(f"unknown entity {name_or_id!r}")


def has_entity(model, name):
    return any(e["name"] == name for e in model["entities"].values())


def field(ent, name_or_id):
    if name_or_id in ent["fields"]:
        return ent["fields"][name_or_id]
    for f in ent["fields"].values():
        if f["name"] == name_or_id:
            return f
    raise ModelError(f"{ent['name']} has no field {name_or_id!r}")


def has_field(ent, name):
    return any(f["name"] == name for f in ent["fields"].values())


def ordered_fields(ent):
    return [ent["fields"][fid] for fid in ent["order"] if fid in ent["fields"]]


def user_entity(model):
    if not model.get("users"):
        return None
    return model["entities"].get(model["users"]["entity"])


# ------------------------------------------------------------------ type env for expressions
def type_schema(model):
    out = {}
    for e in model["entities"].values():
        fields = {}
        for f in e["fields"].values():
            fields[f["name"]] = {"type": f["type"], "ref": model["entities"][f["ref"]]["name"] if f.get("ref") in model["entities"] else f.get("ref")}
        out[e["name"]] = {"fields": fields}
    return out


def tenv_for(model, ent=None, params=None, extra=None):
    schema = type_schema(model)
    variables = {"now": None, "today": None, "input": None, "old": None}
    ue = user_entity(model)
    variables["user"] = ("entity", ue["name"]) if ue else None
    if ent is not None:
        variables["record"] = ("entity", ent["name"])
        variables["old"] = ("entity", ent["name"])
    if params is not None:
        variables["params"] = ("params", None)
    for k, v in (extra or {}).items():
        variables[k] = v
    return E.TypeEnv(schema, variables, params or {})


# ------------------------------------------------------------------ walking all expressions
def walk_expressions(model, fn):
    """Call fn(loc, entity, src, kw) for every expression; if fn returns a string, replace it.

    ``kw`` carries what the type checker needs: action params and effect-local variables.
    """
    for e in model["entities"].values():
        for f in e["fields"].values():
            for key in ("default", "computed", "read_if", "write_if"):
                if f.get(key) not in (None, ""):
                    r = fn(("field", e["id"], f["id"], key), e, f[key], {})
                    if isinstance(r, str):
                        f[key] = r
        for rname in RULES:
            if e["rules"].get(rname) not in (None, ""):
                r = fn(("rule", e["id"], rname), e, e["rules"][rname], {})
                if isinstance(r, str):
                    e["rules"][rname] = r
        for c in e["constraints"].values():
            r = fn(("constraint", e["id"], c["id"]), e, c["expr"], {})
            if isinstance(r, str):
                c["expr"] = r
        for a in e["actions"].values():
            kw = {"params": a["params"]}
            for key in ("allow", "guard", "guard_message"):
                if a.get(key) not in (None, ""):
                    r = fn(("action", e["id"], a["id"], key), e, a[key], kw)
                    if isinstance(r, str):
                        a[key] = r
            _walk_effects(("action", e["id"], a["id"], "effects"), e, a["effects"], kw, {}, fn)
        for t in e["triggers"].values():
            if t.get("when") not in (None, ""):
                r = fn(("trigger", e["id"], t["id"], "when"), e, t["when"], {})
                if isinstance(r, str):
                    t["when"] = r
            _walk_effects(("trigger", e["id"], t["id"], "effects"), e, t["effects"], {}, {}, fn)


def _walk_effects(loc, ent, effects, kw, extra, fn):
    extra = dict(extra)

    def visit(where, holder, key, local_extra):
        r = fn(where, ent, holder[key], dict(kw, extra=dict(local_extra)))
        if isinstance(r, str):
            holder[key] = r

    for i, eff in enumerate(effects or []):
        here = loc + (i,)
        if "update" in eff:
            visit(here + ("update",), eff, "update", extra)
            target = None
            for fname in list(eff.get("set", {})):
                visit(here + ("set", fname), eff["set"], fname, dict(extra, it=target))
        elif "set" in eff:
            for fname in list(eff["set"]):
                visit(here + ("set", fname), eff["set"], fname, extra)
        if "create" in eff:
            for fname in list(eff.get("values", {})):
                visit(here + ("values", fname), eff["values"], fname, extra)
            if eff.get("as"):
                extra[eff["as"]] = ("entity", eff["create"])
        if "delete" in eff:
            visit(here + ("delete",), eff, "delete", extra)
        if "emit" in eff:
            for key in list(eff.get("payload", {})):
                visit(here + ("payload", key), eff["payload"], key, extra)
        if "fail" in eff:
            visit(here + ("fail",), eff, "fail", extra)
            if eff.get("when"):
                visit(here + ("when",), eff, "when", extra)
        if "if" in eff:
            visit(here + ("if",), eff, "if", extra)
            _walk_effects(here + ("then",), ent, eff.get("then"), kw, extra, fn)
            _walk_effects(here + ("else",), ent, eff.get("else"), kw, extra, fn)


def expressions(model):
    out = []
    walk_expressions(model, lambda loc, e, src, kw: out.append((loc, e, src, kw)))
    return out


def tenv_for_location(model, ent, kw):
    return tenv_for(model, ent, params=kw.get("params"), extra=kw.get("extra") or {})


# ------------------------------------------------------------------ validation
def check(model) -> list[str]:
    """Static problems in the model: unresolved names, bad references, bad types."""
    errors = []
    names = {}
    for e in model["entities"].values():
        if e["name"] in names:
            errors.append(f"two entities are named {e['name']!r}")
        names[e["name"]] = e
        fnames = set()
        for f in e["fields"].values():
            if f["name"] in fnames or f["name"] == "id":
                errors.append(f"{e['name']}: duplicate or reserved field name {f['name']!r}")
            fnames.add(f["name"])
            if f["type"] not in FIELD_TYPES:
                errors.append(f"{e['name']}.{f['name']}: unknown type {f['type']!r}")
            if f["type"] == "ref" and f.get("ref") not in model["entities"]:
                errors.append(f"{e['name']}.{f['name']}: refers to a missing entity")
            if f["type"] == "enum" and not f.get("values"):
                errors.append(f"{e['name']}.{f['name']}: enum without values")
        for a in e["actions"].values():
            for p, spec in a["params"].items():
                if spec.get("type") == "ref" and spec.get("ref") not in names and spec.get("ref") not in model["entities"]:
                    pass
    for loc, ent, src, kw in expressions(model):
        try:
            an = E.analyse(src, tenv_for_location(model, ent, kw))
        except E.ExprError as exc:
            errors.append(f"{describe(model, loc)}: {exc}")
            continue
        for err in an.errors:
            errors.append(f"{describe(model, loc)}: {err} in `{src}`")
    if model.get("users"):
        ue = model["entities"].get(model["users"]["entity"])
        if not ue or model["users"]["key"] not in ue["fields"]:
            errors.append("the users entity or its key field is missing")
    return errors


def describe(model, loc) -> str:
    ent = model["entities"].get(loc[1])
    en = ent["name"] if ent else loc[1]
    kind = loc[0]
    if kind == "field":
        f = ent["fields"].get(loc[2]) if ent else None
        return f"{en}.{f['name'] if f else loc[2]} ({loc[3]})"
    if kind == "rule":
        return f"{en} rule {loc[2]}"
    if kind == "constraint":
        c = ent["constraints"].get(loc[2]) if ent else None
        return f"{en} constraint {c['name'] if c else loc[2]}"
    holder = ent["actions" if kind == "action" else "triggers"].get(loc[2]) if ent else None
    return f"{en} {kind} {holder['name'] if holder else loc[2]} ({'.'.join(str(x) for x in loc[3:])})"


# ------------------------------------------------------------------ dependency graph
def dependencies(model):
    """Map each expression location to the (entity name, field name) pairs and collections it reads."""
    deps = {}
    for loc, ent, src, kw in expressions(model):
        try:
            an = E.analyse(src, tenv_for_location(model, ent, kw))
            deps[loc] = (an.reads, an.collections, ent["name"])
        except E.ExprError:
            deps[loc] = (set(), set(), ent["name"])
    return deps


def clone(model):
    return copy.deepcopy(model)
