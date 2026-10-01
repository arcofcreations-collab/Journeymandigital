"""Typed change operators.

Each operator transforms the model *and* the stored data in one step and returns the list of
operators that exactly undo it (capturing whatever data it destroys). Operators work on
sandbox copies; the change pipeline (change.py) decides whether the result is committed.

Consequences that follow from the model's structure are handled here once, generically:
renames rewrite every dependent expression (type-guided), data is keyed by stable ids, and
derived interfaces (API/UI/validation/permissions) need no edits because they are computed.
Consequences that need a decision (existing data, broken dependents) surface as obligations
in the pipeline's static and data checks.
"""
from __future__ import annotations

import copy
import json
import os

from . import expr as E
from . import model as M
from . import runtime as R


class OpError(Exception):
    pass


class ChangeCtx:
    def __init__(self, model, world, now, base_dir):
        self.model, self.world, self.now, self.base_dir = model, world, now, base_dir
        self.notes = []          # human-readable account of what each operator did
        self.warnings = []

    def rctx(self, user=None):
        c = R.Ctx(self.model, self.world, user, self.now)
        return c


# ------------------------------------------------------------------ field specs
def parse_field_spec(model, name, spec):
    """Accept {"type": ...} dicts or shorthand strings like 'text required unique', 'ref members',
    'enum draft|submitted'."""
    if isinstance(spec, str):
        toks = spec.split()
        d = {"type": toks[0]}
        rest = toks[1:]
        if d["type"] == "ref":
            d["ref"] = rest.pop(0)
        elif d["type"] == "enum":
            d["values"] = rest.pop(0).split("|")
        for t in rest:
            d[t] = True
        spec = d
    spec = dict(spec)
    f = {"id": None, "name": name, "type": spec.pop("type", "text"), "required": bool(spec.pop("required", False)),
         "unique": bool(spec.pop("unique", False)), "values": spec.pop("values", None), "ref": None,
         "default": _expr_or_none(spec.pop("default", None)), "computed": _expr_or_none(spec.pop("computed", None)),
         "system": bool(spec.pop("system", False)), "read_if": _expr_or_none(spec.pop("read_if", None)),
         "write_if": _expr_or_none(spec.pop("write_if", None)), "label": spec.pop("label", None)}
    ref = spec.pop("ref", None)
    if f["type"] == "ref":
        if ref is None:
            raise OpError(f"field {name}: ref fields need `ref: <entity>`")
        f["ref"] = ref  # entity *name* until resolved
    if f["computed"]:
        f["required"] = False
    spec.pop("backfill", None)
    if spec:
        raise OpError(f"field {name}: unknown keys {sorted(spec)}")
    return f


def _expr_or_none(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "True" if v else "False"
    return str(v)


def _resolve_ref(model, f, pending_names=()):
    if f["type"] == "ref" and f["ref"] not in model["entities"]:
        try:
            f["ref"] = M.entity(model, f["ref"])["id"]
        except M.ModelError:
            raise OpError(f"field {f['name']}: no entity named {f['ref']!r}") from None


def _new_entity(model, name):
    if M.has_entity(model, name):
        raise OpError(f"an entity named {name!r} already exists")
    eid = M.new_id(model, "e")
    return {"id": eid, "name": name, "fields": {}, "order": [],
            "rules": {"read": "True", "create": "True", "update": "True", "delete": "True"},
            "guard_messages": {}, "constraints": {}, "actions": {}, "triggers": {}}


def _effects(v):
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)


def _norm_effects(effects):
    out = []
    for eff in _effects(effects):
        eff = dict(eff)
        for key in ("set", "values", "payload"):
            if key in eff:
                eff[key] = {k: _expr_or_none(v) for k, v in eff[key].items()}
        for key in ("if", "when", "fail", "update", "delete"):
            if key in eff and not isinstance(eff[key], (list, dict)):
                eff[key] = _expr_or_none(eff[key])
        if "then" in eff:
            eff["then"] = _norm_effects(eff["then"])
        if "else" in eff:
            eff["else"] = _norm_effects(eff["else"])
        out.append(eff)
    return out


def _params(model, params):
    out = {}
    for pname, spec in (params or {}).items():
        f = parse_field_spec(model, pname, spec)
        out[pname] = {"type": f["type"], "required": f["required"], "values": f["values"], "ref": f["ref"]}
    return out


# ------------------------------------------------------------------ entity operators
def op_add_entity(cx, a):
    m = cx.model
    ent = _new_entity(m, a["name"])
    m["entities"][ent["id"]] = ent
    for fname, spec in (a.get("fields") or {}).items():
        f = parse_field_spec(m, fname, spec)
        f["id"] = M.new_id(m, "f")
        ent["fields"][f["id"]] = f
        ent["order"].append(f["id"])
    for f in ent["fields"].values():
        _resolve_ref(m, f)
    for rname, src in (a.get("rules") or {}).items():
        _set_rule(ent, rname, src)
    for cname, c in (a.get("constraints") or {}).items():
        _add_constraint(cx, ent, cname, c, existing="enforce")
    for aname, act in (a.get("actions") or {}).items():
        _add_action(m, ent, aname, act)
    for tname, trig in (a.get("triggers") or {}).items():
        _add_trigger(m, ent, tname, trig)
    cx.notes.append(f"added entity {a['name']} with {len(ent['fields'])} fields")
    return [{"remove_entity": {"name": a["name"]}}]


def op_remove_entity(cx, a):
    m = cx.model
    ent = M.entity(m, a["name"])
    snapshot = copy.deepcopy(ent)
    data = copy.deepcopy(R.records(cx.world, ent["id"]))
    del m["entities"][ent["id"]]
    cx.world["records"].pop(ent["id"], None)
    cx.notes.append(f"removed entity {ent['name']} ({len(data)} records kept in the ledger for undo)")
    return [{"restore_entity": {"definition": snapshot, "records": {str(k): v for k, v in data.items()},
                                "next_id": cx.world["next_id"].get(ent["id"])}}]


def op_restore_entity(cx, a):
    m = cx.model
    ent = copy.deepcopy(a["definition"])
    if ent["id"] in m["entities"] or M.has_entity(m, ent["name"]):
        raise OpError(f"cannot restore {ent['name']}: an entity with that id or name exists")
    m["entities"][ent["id"]] = ent
    cx.world["records"][ent["id"]] = {int(k): v for k, v in a["records"].items()}
    if a.get("next_id"):
        cx.world["next_id"][ent["id"]] = a["next_id"]
    cx.notes.append(f"restored entity {ent['name']} with {len(a['records'])} records")
    return [{"remove_entity": {"name": ent["name"]}}]


def op_rename_entity(cx, a):
    m = cx.model
    ent = M.entity(m, a["from"])
    if M.has_entity(m, a["to"]):
        raise OpError(f"an entity named {a['to']!r} already exists")
    rewritten = _rewrite_all(cx, kind="entity", entity=None, old=a["from"], new=a["to"])
    ent["name"] = a["to"]
    # effect targets name entities by name
    for e in m["entities"].values():
        for holder in list(e["actions"].values()) + list(e["triggers"].values()):
            _rename_effect_entity(holder["effects"], a["from"], a["to"])
        for act in e["actions"].values():
            for p in act["params"].values():
                if p.get("ref") == a["from"]:
                    p["ref"] = a["to"]
    cx.notes.append(f"renamed entity {a['from']} -> {a['to']}; {rewritten} expression(s) rewritten")
    return [{"rename_entity": {"from": a["to"], "to": a["from"]}}]


def _rename_effect_entity(effects, old, new):
    for eff in effects or []:
        if eff.get("create") == old:
            eff["create"] = new
        _rename_effect_entity(eff.get("then"), old, new)
        _rename_effect_entity(eff.get("else"), old, new)


# ------------------------------------------------------------------ field operators
def op_add_field(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    if M.has_field(ent, a["name"]):
        raise OpError(f"{ent['name']} already has a field {a['name']!r}")
    spec = a.get("spec") or {k: v for k, v in a.items() if k not in ("entity", "name", "backfill", "position")}
    f = parse_field_spec(m, a["name"], spec)
    f["id"] = M.new_id(m, "f")
    _resolve_ref(m, f)
    ent["fields"][f["id"]] = f
    ent["order"].append(f["id"])
    filled = 0
    if not f.get("computed"):
        rc = cx.rctx()
        src = _expr_or_none(a.get("backfill")) or f.get("default")
        for rid, data in R.records(cx.world, ent["id"]).items():
            if src:
                data[f["id"]] = R.to_storage(f, rc.eval(src, record=R.Rec(rc, ent, rid)))
                filled += 1
            else:
                data.setdefault(f["id"], None)
            rc.invalidate()
    cx.notes.append(f"added field {ent['name']}.{f['name']} ({f['type']})"
                    + (f"; computed as `{f['computed']}`" if f.get("computed") else f"; filled {filled} existing records"))
    return [{"remove_field": {"entity": ent["name"], "name": f["name"]}}]


def op_remove_field(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    f = M.field(ent, a["name"])
    values = {str(rid): d.pop(f["id"], None) for rid, d in R.records(cx.world, ent["id"]).items()}
    del ent["fields"][f["id"]]
    ent["order"] = [x for x in ent["order"] if x != f["id"]]
    cx.notes.append(f"removed field {ent['name']}.{f['name']} ({len(values)} values kept in the ledger for undo)")
    return [{"restore_field": {"entity": ent["name"], "definition": copy.deepcopy(f), "values": values}}]


def op_restore_field(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    f = copy.deepcopy(a["definition"])
    if f["id"] in ent["fields"] or M.has_field(ent, f["name"]):
        raise OpError(f"cannot restore {ent['name']}.{f['name']}: it exists")
    ent["fields"][f["id"]] = f
    ent["order"].append(f["id"])
    restored = 0
    for rid, d in R.records(cx.world, ent["id"]).items():
        if str(rid) in a["values"]:
            d[f["id"]] = a["values"][str(rid)]
            restored += 1
        else:
            d[f["id"]] = None
    cx.notes.append(f"restored field {ent['name']}.{f['name']} ({restored} values)")
    return [{"remove_field": {"entity": ent["name"], "name": f["name"]}}]


def op_rename_field(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    f = M.field(ent, a["from"])
    if M.has_field(ent, a["to"]):
        raise OpError(f"{ent['name']} already has a field {a['to']!r}")
    rewritten = _rewrite_all(cx, kind="field", entity=ent["name"], old=a["from"], new=a["to"])
    keys = _rename_effect_keys(m, ent["name"], a["from"], a["to"])
    f["name"] = a["to"]
    cx.notes.append(f"renamed field {ent['name']}.{a['from']} -> {a['to']}; {rewritten} expression(s) and "
                    f"{keys} effect assignment(s) rewritten; stored data untouched (keyed by field id)")
    return [{"rename_field": {"entity": ent["name"], "from": a["to"], "to": a["from"]}}]


def _rename_effect_keys(m, ename, old, new):
    count = 0

    def walk(effects, own):
        nonlocal count
        for eff in effects or []:
            target = None
            if "create" in eff:
                target = eff["create"]
                d = eff.get("values", {})
            elif "update" in eff:
                target = "?"
                d = eff.get("set", {})
            elif "set" in eff:
                target = own
                d = eff["set"]
            else:
                d = {}
            if old in d and target in (ename, "?"):
                d[new] = d.pop(old)
                count += 1
            walk(eff.get("then"), own)
            walk(eff.get("else"), own)

    for e in m["entities"].values():
        for holder in list(e["actions"].values()) + list(e["triggers"].values()):
            walk(holder["effects"], e["name"])
    return count


def op_change_field(cx, a):
    """Change a field's definition; existing values are converted with `convert` (an expression
    over `value` and `record`) or `map` (old value -> new value)."""
    m = cx.model
    ent = M.entity(m, a["entity"])
    f = M.field(ent, a["name"])
    old_def = copy.deepcopy(f)
    changes = {k: v for k, v in a.items() if k not in ("entity", "name", "convert", "map")}
    if "spec" in changes:
        changes.update(changes.pop("spec"))
    if "rename" in changes:
        raise OpError("use rename_field to rename")
    for k, v in changes.items():
        if k in ("default", "computed", "read_if", "write_if"):
            f[k] = _expr_or_none(v)
        elif k == "ref":
            f["ref"] = v
            _resolve_ref(m, f)
        elif k in ("type", "values", "label"):
            f[k] = v
        elif k in ("required", "unique", "system"):
            f[k] = bool(v)
        else:
            raise OpError(f"change_field: unknown key {k!r}")
    if f["type"] == "ref" and f.get("ref") not in m["entities"]:
        _resolve_ref(m, f)
    before, absent = _stored_values(cx.world, ent, f["id"])
    converted = 0
    if a.get("convert") or a.get("map"):
        rc = cx.rctx()
        for rid, d in R.records(cx.world, ent["id"]).items():
            old = d.get(f["id"])
            if a.get("map") is not None:
                new = a["map"].get(old, old) if old is not None else None
            else:
                new = rc.eval(str(a["convert"]), value=R.from_storage(old_def, old, rc) if old is not None else None,
                              record=R.Rec(rc, ent, rid))
                new = R.to_storage(f, new)
            if new != old:
                converted += 1
            d[f["id"]] = new
            rc.invalidate()
    if old_def.get("computed") and not f.get("computed"):
        # materialise a formerly derived value
        rc_old = R.Ctx(_model_with_field(m, ent, old_def), cx.world, None, cx.now)
        for rid, d in R.records(cx.world, ent["id"]).items():
            d[f["id"]] = R.to_storage(f, rc_old.eval(old_def["computed"], record=R.Rec(rc_old, rc_old.model["entities"][ent["id"]], rid)))
    cx.notes.append(f"changed {ent['name']}.{f['name']}: {', '.join(sorted(changes)) or 'values'}; {converted} stored value(s) converted")
    return [{"restore_field_def": {"entity": ent["name"], "field_id": f["id"], "definition": old_def, "values": before,
                                   "absent": absent}}]


def _stored_values(world, ent, fid):
    """Stored values of one field, distinguishing 'stored as null' from 'not stored at all'
    (computed fields are never stored), so an inverse can restore storage exactly."""
    values, absent = {}, []
    for rid, d in R.records(world, ent["id"]).items():
        if fid in d:
            values[str(rid)] = d[fid]
        else:
            absent.append(str(rid))
    return values, absent


def _model_with_field(m, ent, fdef):
    mm = copy.deepcopy(m)
    mm["entities"][ent["id"]]["fields"][fdef["id"]] = copy.deepcopy(fdef)
    return mm


def op_restore_field_def(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    cur = ent["fields"].get(a["field_id"])
    if cur is None:
        raise OpError(f"cannot restore field definition: field no longer exists in {ent['name']}")
    before, absent = _stored_values(cx.world, ent, cur["id"])
    now_def = copy.deepcopy(cur)
    ent["fields"][a["field_id"]] = copy.deepcopy(a["definition"])
    ent["fields"][a["field_id"]]["name"] = now_def["name"]  # the name is owned by rename_field
    gone = set(a.get("absent", ()))
    for rid, d in R.records(cx.world, ent["id"]).items():
        if str(rid) in a["values"]:
            d[cur["id"]] = a["values"][str(rid)]
        elif str(rid) in gone or a["definition"].get("computed"):
            d.pop(cur["id"], None)
    cx.notes.append(f"restored the definition and values of {ent['name']}.{now_def['name']}")
    return [{"restore_field_def": {"entity": ent["name"], "field_id": a["field_id"], "definition": now_def, "values": before,
                                   "absent": absent}}]


# ------------------------------------------------------------------ data operators
def op_update_records(cx, a):
    """Data lens: set fields on existing records matching `where` (expression over `record`)."""
    m = cx.model
    ent = M.entity(m, a["entity"])
    rc = cx.rctx()
    before = {}
    n = 0
    for rid in sorted(R.records(cx.world, ent["id"])):
        rec = R.Rec(rc, ent, rid)
        if a.get("where") and not rc.test(str(a["where"]), False, record=rec):
            continue
        d = R.records(cx.world, ent["id"])[rid]
        new_vals = {}
        for fname, ex in a["set"].items():
            f = M.field(ent, fname)
            new_vals[f["id"]] = R.to_storage(f, rc.eval(_expr_or_none(ex), record=rec))
        before[str(rid)] = {fid: d.get(fid) for fid in new_vals}
        d.update(new_vals)
        rc.invalidate()
        n += 1
    cx.notes.append(f"updated {n} existing {ent['name']} record(s): {', '.join(a['set'])}")
    return [{"restore_values": {"entity": ent["name"], "values": before}}]


def op_restore_values(cx, a):
    ent = M.entity(cx.model, a["entity"])
    recs = R.records(cx.world, ent["id"])
    before = {}
    for rid, vals in a["values"].items():
        d = recs.get(int(rid))
        if d is None:
            continue
        before[rid] = {fid: d.get(fid) for fid in vals}
        d.update(vals)
    cx.notes.append(f"restored values on {len(before)} {ent['name']} record(s)")
    return [{"restore_values": {"entity": ent["name"], "values": before}}]


def op_add_records(cx, a):
    m = cx.model
    ent = M.entity(m, a["entity"])
    rows = list(a.get("records") or [])
    if a.get("from_json"):
        path = a["from_json"]
        if not os.path.isabs(path):
            path = os.path.join(cx.base_dir, path)
        with open(path) as fh:
            doc = json.load(fh)
        rows += doc[a.get("key", ent["name"])] if isinstance(doc, dict) else doc
    recs = R.records(cx.world, ent["id"])
    added = []
    for row in rows:
        row = dict(row)
        rid = row.pop("id", None)
        if rid is None:
            rid = max([cx.world["next_id"].get(ent["id"], 1)] + [r + 1 for r in recs])
        if rid in recs:
            raise OpError(f"{ent['name']} {rid} already exists")
        data = {}
        for fname, v in row.items():
            f = M.field(ent, fname)
            if f.get("computed"):
                continue
            data[f["id"]] = v
        for f in ent["fields"].values():
            data.setdefault(f["id"], None) if not f.get("computed") else None
        recs[rid] = data
        cx.world["next_id"][ent["id"]] = max(cx.world["next_id"].get(ent["id"], 1), rid + 1)
        added.append(rid)
    cx.notes.append(f"added {len(added)} {ent['name']} record(s)")
    return [{"delete_records": {"entity": ent["name"], "ids": added}}]


def op_delete_records(cx, a):
    ent = M.entity(cx.model, a["entity"])
    recs = R.records(cx.world, ent["id"])
    rc = cx.rctx()
    if "ids" in a:
        ids = [int(i) for i in a["ids"] if int(i) in recs]
    else:
        ids = [rid for rid in sorted(recs) if rc.test(str(a["where"]), False, record=R.Rec(rc, ent, rid))]
    removed = {str(i): recs.pop(i) for i in ids}
    cx.notes.append(f"deleted {len(removed)} {ent['name']} record(s)")
    return [{"add_raw_records": {"entity": ent["name"], "records": removed}}]


def op_add_raw_records(cx, a):
    ent = M.entity(cx.model, a["entity"])
    recs = R.records(cx.world, ent["id"])
    for rid, data in a["records"].items():
        recs[int(rid)] = data
    cx.notes.append(f"restored {len(a['records'])} {ent['name']} record(s)")
    return [{"delete_records": {"entity": ent["name"], "ids": [int(r) for r in a["records"]]}}]


# ------------------------------------------------------------------ behaviour operators
def _set_rule(ent, rname, src, message=None):
    if rname not in M.RULES:
        raise OpError(f"unknown rule {rname!r}; rules are {', '.join(M.RULES)}")
    ent["rules"][rname] = _expr_or_none(src)
    if message is not None:
        ent["guard_messages"][rname] = message


def op_set_rule(cx, a):
    ent = M.entity(cx.model, a["entity"])
    old = ent["rules"].get(a["rule"])
    old_msg = ent["guard_messages"].get(a["rule"])
    _set_rule(ent, a["rule"], a.get("expr"), a.get("message"))
    cx.notes.append(f"{ent['name']}: rule {a['rule']} is now `{a.get('expr')}`")
    inv = {"entity": ent["name"], "rule": a["rule"], "expr": old}
    if old_msg is not None or a.get("message") is not None:
        inv["message"] = old_msg
    return [{"set_rule": inv}]


def _add_constraint(cx, ent, name, c, existing="enforce"):
    if isinstance(c, str):
        c = {"expr": c}
    if any(x["name"] == name for x in ent["constraints"].values()):
        raise OpError(f"{ent['name']} already has a constraint {name!r}")
    cid = M.new_id(cx.model, "c")
    con = {"id": cid, "name": name, "expr": _expr_or_none(c["expr"]), "message": c.get("message"),
           "field": c.get("field"), "exempt": []}
    ent["constraints"][cid] = con
    policy = c.get("existing", existing)
    if policy == "exempt":
        rc = cx.rctx()
        for rid in sorted(R.records(cx.world, ent["id"])):
            try:
                ok = rc.test(con["expr"], True, record=R.Rec(rc, ent, rid))
            except (E.ExprError, TypeError, AttributeError, ValueError):
                ok = False
            if not ok:
                con["exempt"].append(rid)
        cx.notes.append(f"{ent['name']}: constraint {name} exempts {len(con['exempt'])} existing violating record(s)")
    elif policy != "enforce":
        raise OpError(f"constraint {name}: `existing` must be enforce or exempt")
    return con


def op_add_constraint(cx, a):
    ent = M.entity(cx.model, a["entity"])
    _add_constraint(cx, ent, a["name"], a, a.get("existing", "enforce"))
    cx.notes.append(f"{ent['name']}: added constraint {a['name']}: `{a['expr']}`")
    return [{"remove_constraint": {"entity": ent["name"], "name": a["name"]}}]


def _find(holder, name, what, ent):
    for x in holder.values():
        if x["name"] == name:
            return x
    raise OpError(f"{ent['name']} has no {what} {name!r}")


def op_remove_constraint(cx, a):
    ent = M.entity(cx.model, a["entity"])
    c = _find(ent["constraints"], a["name"], "constraint", ent)
    del ent["constraints"][c["id"]]
    cx.notes.append(f"{ent['name']}: removed constraint {a['name']}")
    return [{"restore_element": {"entity": ent["name"], "kind": "constraints", "definition": c}}]


def op_change_constraint(cx, a):
    ent = M.entity(cx.model, a["entity"])
    c = _find(ent["constraints"], a["name"], "constraint", ent)
    old = copy.deepcopy(c)
    for k in ("expr", "message", "field"):
        if k in a:
            c[k] = _expr_or_none(a[k]) if k == "expr" else a[k]
    if a.get("existing") == "exempt":
        rc = cx.rctx()
        c["exempt"] = [rid for rid in sorted(R.records(cx.world, ent["id"]))
                       if not _ok(rc, c["expr"], R.Rec(rc, ent, rid))]
    cx.notes.append(f"{ent['name']}: constraint {a['name']} changed")
    return [{"replace_element": {"entity": ent["name"], "kind": "constraints", "definition": old}}]


def _ok(rc, src, rec):
    try:
        return rc.test(src, True, record=rec)
    except (E.ExprError, TypeError, AttributeError, ValueError):
        return False


def _add_action(m, ent, name, spec):
    if any(x["name"] == name for x in ent["actions"].values()):
        raise OpError(f"{ent['name']} already has an action {name!r}")
    aid = M.new_id(m, "a")
    ent["actions"][aid] = {"id": aid, "name": name, "params": _params(m, spec.get("params")),
                           "allow": _expr_or_none(spec.get("allow")), "guard": _expr_or_none(spec.get("guard")),
                           "guard_message": _expr_or_none(spec.get("guard_message")),
                           "effects": _norm_effects(spec.get("effects"))}
    return ent["actions"][aid]


def op_add_action(cx, a):
    ent = M.entity(cx.model, a["entity"])
    _add_action(cx.model, ent, a["name"], a)
    cx.notes.append(f"{ent['name']}: added action {a['name']}")
    return [{"remove_action": {"entity": ent["name"], "name": a["name"]}}]


def op_remove_action(cx, a):
    ent = M.entity(cx.model, a["entity"])
    act = _find(ent["actions"], a["name"], "action", ent)
    del ent["actions"][act["id"]]
    cx.notes.append(f"{ent['name']}: removed action {a['name']}")
    return [{"restore_element": {"entity": ent["name"], "kind": "actions", "definition": act}}]


def op_change_action(cx, a):
    ent = M.entity(cx.model, a["entity"])
    act = _find(ent["actions"], a["name"], "action", ent)
    old = copy.deepcopy(act)
    for k, v in a.items():
        if k in ("entity", "name"):
            continue
        if k == "rename":
            if any(x["name"] == v for x in ent["actions"].values()):
                raise OpError(f"{ent['name']} already has an action {v!r}")
            act["name"] = v
        elif k == "params":
            act["params"] = _params(cx.model, v)
        elif k == "add_params":
            act["params"].update(_params(cx.model, v))
        elif k == "effects":
            act["effects"] = _norm_effects(v)
        elif k == "append_effects":
            act["effects"] = act["effects"] + _norm_effects(v)
        elif k == "prepend_effects":
            act["effects"] = _norm_effects(v) + act["effects"]
        elif k in ("allow", "guard", "guard_message"):
            act[k] = _expr_or_none(v)
        else:
            raise OpError(f"change_action: unknown key {k!r}")
    cx.notes.append(f"{ent['name']}: changed action {a['name']} ({', '.join(k for k in a if k not in ('entity', 'name'))})")
    return [{"replace_element": {"entity": ent["name"], "kind": "actions", "definition": old}}]


def _add_trigger(m, ent, name, spec):
    on = spec.get("on")
    if not on or not (on in M.EVENTS or on.startswith("action:")):
        raise OpError(f"trigger {name}: `on` must be create, update, delete or action:<name>")
    tid = M.new_id(m, "t")
    ent["triggers"][tid] = {"id": tid, "name": name, "on": on, "when": _expr_or_none(spec.get("when")),
                            "effects": _norm_effects(spec.get("effects"))}


def op_add_trigger(cx, a):
    ent = M.entity(cx.model, a["entity"])
    if any(x["name"] == a["name"] for x in ent["triggers"].values()):
        raise OpError(f"{ent['name']} already has a trigger {a['name']!r}")
    _add_trigger(cx.model, ent, a["name"], a)
    cx.notes.append(f"{ent['name']}: added trigger {a['name']} on {a['on']}")
    return [{"remove_trigger": {"entity": ent["name"], "name": a["name"]}}]


def op_remove_trigger(cx, a):
    ent = M.entity(cx.model, a["entity"])
    t = _find(ent["triggers"], a["name"], "trigger", ent)
    del ent["triggers"][t["id"]]
    cx.notes.append(f"{ent['name']}: removed trigger {a['name']}")
    return [{"restore_element": {"entity": ent["name"], "kind": "triggers", "definition": t}}]


def op_change_trigger(cx, a):
    ent = M.entity(cx.model, a["entity"])
    t = _find(ent["triggers"], a["name"], "trigger", ent)
    old = copy.deepcopy(t)
    for k, v in a.items():
        if k in ("entity", "name"):
            continue
        if k == "effects":
            t["effects"] = _norm_effects(v)
        elif k in ("when", "on"):
            t[k] = _expr_or_none(v) if k == "when" else v
        else:
            raise OpError(f"change_trigger: unknown key {k!r}")
    cx.notes.append(f"{ent['name']}: changed trigger {a['name']}")
    return [{"replace_element": {"entity": ent["name"], "kind": "triggers", "definition": old}}]


def op_restore_element(cx, a):
    ent = M.entity(cx.model, a["entity"])
    d = copy.deepcopy(a["definition"])
    holder = ent[a["kind"]]
    if any(x["name"] == d["name"] for x in holder.values()):
        raise OpError(f"cannot restore {a['kind'][:-1]} {d['name']}: it exists")
    holder[d["id"]] = d
    cx.notes.append(f"{ent['name']}: restored {a['kind'][:-1]} {d['name']}")
    remover = {"constraints": "remove_constraint", "actions": "remove_action", "triggers": "remove_trigger"}[a["kind"]]
    return [{remover: {"entity": ent["name"], "name": d["name"]}}]


def op_replace_element(cx, a):
    ent = M.entity(cx.model, a["entity"])
    d = copy.deepcopy(a["definition"])
    holder = ent[a["kind"]]
    if d["id"] not in holder:
        raise OpError(f"cannot restore {a['kind'][:-1]} {d['name']}: it no longer exists")
    old = copy.deepcopy(holder[d["id"]])
    holder[d["id"]] = d
    cx.notes.append(f"{ent['name']}: restored previous definition of {a['kind'][:-1]} {d['name']}")
    return [{"replace_element": {"entity": ent["name"], "kind": a["kind"], "definition": old}}]


def op_set_users(cx, a):
    m = cx.model
    old = copy.deepcopy(m.get("users"))
    ent = M.entity(m, a["entity"])
    f = M.field(ent, a["key"])
    m["users"] = {"entity": ent["id"], "key": f["id"]}
    cx.notes.append(f"users are {ent['name']} records identified by {f['name']}")
    return [{"restore_users": {"users": old}}]


def op_restore_users(cx, a):
    old = copy.deepcopy(cx.model.get("users"))
    cx.model["users"] = a["users"]
    return [{"restore_users": {"users": old}}]


# ------------------------------------------------------------------ macro operators
def expand_promote_field(model, a):
    """Turn a plain field into a reference to a new entity holding its distinct values."""
    ent, fname, to = a["entity"], a["field"], a["to"]
    key = a.get("key", "name")
    tmp = f"{fname}__ref"
    extra = a.get("fields") or {}
    return [
        {"add_entity": {"name": to, "fields": dict({key: "text required unique"}, **extra),
                        "rules": a.get("rules") or {}}},
        {"add_records_distinct": {"entity": to, "key": key, "source": ent, "field": fname}},
        {"add_field": {"entity": ent, "name": tmp, "type": "ref", "ref": to,
                       "backfill": f"first({to}, {key}=record.{fname}) if record.{fname} is not None else None"}},
        {"remove_field": {"entity": ent, "name": fname}},
        {"rename_field": {"entity": ent, "from": tmp, "to": fname}},
    ]


def op_add_records_distinct(cx, a):
    src = M.entity(cx.model, a["source"])
    f = M.field(src, a["field"])
    values = sorted({d.get(f["id"]) for d in R.records(cx.world, src["id"]).values() if d.get(f["id"]) is not None},
                    key=str)
    return op_add_records(cx, {"entity": a["entity"], "records": [{a["key"]: v} for v in values]})


MACROS = {"promote_field": expand_promote_field}

OPERATORS = {
    "add_entity": op_add_entity, "remove_entity": op_remove_entity, "restore_entity": op_restore_entity,
    "rename_entity": op_rename_entity, "add_field": op_add_field, "remove_field": op_remove_field,
    "restore_field": op_restore_field, "rename_field": op_rename_field, "change_field": op_change_field,
    "restore_field_def": op_restore_field_def, "update_records": op_update_records,
    "restore_values": op_restore_values, "add_records": op_add_records, "delete_records": op_delete_records,
    "add_raw_records": op_add_raw_records, "add_records_distinct": op_add_records_distinct,
    "set_rule": op_set_rule, "add_constraint": op_add_constraint, "remove_constraint": op_remove_constraint,
    "change_constraint": op_change_constraint, "add_action": op_add_action, "remove_action": op_remove_action,
    "change_action": op_change_action, "add_trigger": op_add_trigger, "remove_trigger": op_remove_trigger,
    "change_trigger": op_change_trigger, "restore_element": op_restore_element,
    "replace_element": op_replace_element, "set_users": op_set_users, "restore_users": op_restore_users,
}


def expand(ops):
    out = []
    for op in ops:
        if not isinstance(op, dict) or len(op) != 1:
            raise OpError(f"each operator must be a single-key mapping, got {op!r}")
        (name, args), = op.items()
        if name in MACROS:
            out += expand(MACROS[name](None, args))
        elif name in OPERATORS:
            out.append({name: args})
        else:
            raise OpError(f"unknown operator {name!r}; known: {', '.join(sorted(set(OPERATORS) | set(MACROS)))}")
    return out


def apply(cx, op):
    (name, args), = op.items()
    if not isinstance(args, dict):
        raise OpError(f"{name}: arguments must be a mapping")
    return OPERATORS[name](cx, args)


# ------------------------------------------------------------------ rename rewriting
def _rewrite_all(cx, kind, entity, old, new):
    """Rewrite every expression that refers to the renamed element. Types are resolved against
    the model *before* the rename. Returns the number of expressions rewritten."""
    m = cx.model
    count = 0
    unsure = []

    def fn(loc, ent, src, kw):
        nonlocal count
        try:
            tenv = M.tenv_for_location(m, ent, kw)
            new_src, changed, maybe = E.rename(src, tenv, kind, entity, old, new)
        except E.ExprError:
            return None
        if maybe:
            unsure.append(M.describe(m, loc))
        if changed:
            count += 1
            return new_src
        return None

    M.walk_expressions(m, fn)
    for u in unsure:
        cx.warnings.append(f"{u} reads `.{old}` on a value of unknown type; check it still means what you intend")
    return count
