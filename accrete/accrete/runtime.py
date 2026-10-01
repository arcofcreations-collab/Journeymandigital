"""The generic runtime: serves any accrete model through the external contract.

Nothing here is application-specific. Every request is answered by interpreting the model:
permissions, validation, derived fields, actions, triggers and integration messages are all
expressions in the model. The same functions run live requests and sandboxed replays.
"""
from __future__ import annotations

import copy
import datetime as dt
import json

from . import expr as E
from . import model as M

ROLE_ORDER = {401: 0, 404: 1, 403: 2, 409: 3, 400: 4}


class Halt(Exception):
    """An error response."""

    def __init__(self, status, code, message, fields=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields = status, code, message, fields or {}

    def body(self):
        return {"error": self.code, "message": self.message, "fields": self.fields}


CODES = {400: "validation", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict"}


def halt(status, message, fields=None):
    raise Halt(status, CODES[status], message, fields)


# ------------------------------------------------------------------ data ("world")
def empty_world():
    return {"records": {}, "next_id": {}, "outbox": [], "outbox_next": 1}


def records(world, eid):
    return world["records"].setdefault(eid, {})


# ------------------------------------------------------------------ value conversion
def to_storage(f, v):
    """Convert an expression result to the stored representation for field f."""
    if v is None:
        return None
    t = f["type"]
    if t == "list":
        if isinstance(v, (str, bytes, dict)) or not hasattr(v, "__iter__"):
            v = [v]
        el = M.element(f)
        return [to_storage(el, x) for x in v]
    if isinstance(v, Rec):
        return v.id
    if t == "date":
        return E._to_date(v).isoformat()
    if t == "datetime":
        d = E._to_datetime(v)
        return d.replace(microsecond=0).isoformat()
    if t == "int":
        return int(v)
    if t == "number":
        return round(float(v), 6) if not isinstance(v, bool) else float(v)
    if t == "bool":
        return bool(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def from_storage(f, v, ctx):
    if v is None:
        return None
    t = f["type"]
    if t == "list":
        el = M.element(f)
        out = [from_storage(el, x, ctx) for x in (v if isinstance(v, list) else [v])]
        return [x for x in out if x is not None] if el["type"] == "ref" else out
    if t == "ref":
        target = ctx.model["entities"].get(f["ref"])
        if target is None or v not in records(ctx.world, f["ref"]):
            return None
        return Rec(ctx, target, v)
    if t == "date":
        return E._to_date(v)
    if t == "datetime":
        return E._to_datetime(v)
    return v


def to_json(v):
    if isinstance(v, Rec):
        return v.id
    if isinstance(v, dt.datetime):
        return v.replace(microsecond=0).isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (list, tuple, set)):
        return [to_json(x) for x in v]
    if isinstance(v, dict):
        return {k: to_json(x) for k, x in v.items()}
    if isinstance(v, float) and v.is_integer() and False:
        return int(v)
    return v


def parse_input(f, v, ctx):
    """Validate a client-provided value for field f; returns (stored_value, error).

    For lists the returned value holds the valid elements even when there is an error, so that
    guards (409) can still be evaluated before input errors (400) are reported."""
    if v is None:
        return None, None
    t = f["type"]
    if t == "list":
        if not isinstance(v, list):
            return None, "must be a list"
        el = M.element(f)
        out, errs = [], []
        for i, x in enumerate(v):
            sv, err = parse_input(el, x, ctx) if x is not None else (None, "must not be null")
            if err:
                errs.append(f"item {i + 1} {err}")
            else:
                out.append(sv)
        if not errs and f.get("distinct") and len(set(map(json.dumps, out))) != len(out):
            errs.append("must not contain duplicates")
        return out, ("; ".join(errs) or None)
    try:
        if t in ("text",):
            if not isinstance(v, str):
                return None, "must be text"
            return v, None
        if t == "int":
            if isinstance(v, bool) or not isinstance(v, int):
                return None, "must be an integer"
            return v, None
        if t == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None, "must be a number"
            return float(v), None
        if t == "bool":
            if not isinstance(v, bool):
                return None, "must be true or false"
            return v, None
        if t == "date":
            return dt.date.fromisoformat(str(v)).isoformat(), None
        if t == "datetime":
            return dt.datetime.fromisoformat(str(v)).replace(microsecond=0).isoformat(), None
        if t == "enum":
            if v not in f.get("values", []):
                return None, f"must be one of {', '.join(map(str, f.get('values', [])))}"
            return v, None
        if t == "ref":
            if isinstance(v, bool) or not isinstance(v, int):
                return None, "must be a record id"
            if v not in records(ctx.world, f["ref"]):
                return None, "refers to a record that does not exist"
            return v, None
    except (ValueError, TypeError):
        return None, f"must be a valid {t}"
    return v, None


# ------------------------------------------------------------------ record wrapper
class Rec:
    """A record as seen by expressions: attributes by field name, refs followed lazily."""

    __slots__ = ("_ctx", "_ent", "id", "_override")

    def __init__(self, ctx, ent, rid, override=None):
        self._ctx, self._ent, self.id = ctx, ent, rid
        self._override = override  # dict of stored values for not-yet-saved candidates

    def _data(self):
        if self._override is not None:
            return self._override
        return records(self._ctx.world, self._ent["id"]).get(self.id, {})

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        ent = self._ent
        f = None
        for cand in ent["fields"].values():
            if cand["name"] == name:
                f = cand
                break
        if f is None:
            raise E.ExprError(f"{ent['name']} has no field {name!r}")
        if f.get("computed"):
            return self._ctx.computed(self, f)
        return from_storage(f, self._data().get(f["id"]), self._ctx)

    def __eq__(self, other):
        if isinstance(other, Rec):
            return self._ent["id"] == other._ent["id"] and self.id == other.id
        if isinstance(other, int) and not isinstance(other, bool):
            return self.id == other
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self._ent["id"], self.id))

    def __repr__(self):
        return f"<{self._ent['name']} {self.id}>"

    def __str__(self):
        return str(self.id)


class Params:
    """Action parameters as attributes (missing ones are None)."""

    def __init__(self, values):
        self._values = values

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._values.get(name)


# ------------------------------------------------------------------ request context
class Ctx:
    def __init__(self, model, world, user_name, now):
        self.model, self.world, self.now = model, world, now
        self.user = None
        self.user_name = user_name
        self._collections = None
        self._computing = set()
        self.journal = []  # (eid, rid, previous stored dict or None)
        self.outbox_mark = len(world["outbox"])
        self.next_id_mark = (dict(world["next_id"]), world["outbox_next"])
        ue = M.user_entity(model)
        if ue and user_name is not None:
            key = model["users"]["key"]
            for rid, data in records(world, ue["id"]).items():
                if data.get(key) == user_name:
                    self.user = Rec(self, ue, rid)
                    break

    # environment for expressions
    def env(self, **extra):
        if self._collections is None:
            self._collections = {}
            for e in self.model["entities"].values():
                self._collections[e["name"]] = [Rec(self, e, rid) for rid in sorted(records(self.world, e["id"]))]
        scope = dict(self._collections)
        scope.update({"user": self.user, "now": self.now, "today": self.now.date(),
                      "record": None, "old": None, "params": Params({}), "input": {}})
        scope.update(extra)
        return scope

    def invalidate(self):
        self._collections = None

    def eval(self, src, **extra):
        return E.evaluate(src, self.env(**extra))

    def test(self, src, default=True, **extra):
        if src in (None, ""):
            return default
        return bool(self.eval(src, **extra))

    def computed(self, rec, f):
        key = (rec._ent["id"], rec.id, f["id"])
        if key in self._computing:
            raise E.ExprError(f"computed field {rec._ent['name']}.{f['name']} depends on itself")
        self._computing.add(key)
        try:
            return self.eval(f["computed"], record=rec)
        finally:
            self._computing.discard(key)

    # mutation with journal (for atomic requests)
    def write(self, ent, rid, data):
        recs = records(self.world, ent["id"])
        self.journal.append((ent["id"], rid, copy.deepcopy(recs.get(rid))))
        if data is None:
            recs.pop(rid, None)
        else:
            recs[rid] = data
        self.invalidate()

    def next_id(self, ent):
        recs = records(self.world, ent["id"])
        n = max([self.world["next_id"].get(ent["id"], 1)] + [r + 1 for r in recs])
        self.world["next_id"][ent["id"]] = n + 1
        return n

    def rollback(self):
        for eid, rid, prev in reversed(self.journal):
            recs = records(self.world, eid)
            if prev is None:
                recs.pop(rid, None)
            else:
                recs[rid] = prev
        del self.world["outbox"][self.outbox_mark:]
        self.world["next_id"] = dict(self.next_id_mark[0])
        self.world["outbox_next"] = self.next_id_mark[1]
        self.journal.clear()
        self.invalidate()


# ------------------------------------------------------------------ serialisation & visibility
def visible_fields(ctx, ent, rec):
    out = []
    for f in M.ordered_fields(ent):
        if f.get("read_if") and not _safe_test(ctx, f["read_if"], record=rec):
            continue
        out.append(f)
    return out


def _safe_test(ctx, src, default=False, **extra):
    try:
        return ctx.test(src, default, **extra)
    except (E.ExprError, AttributeError, TypeError, ValueError):
        return default


def serialize(ctx, ent, rid):
    rec = Rec(ctx, ent, rid)
    out = {"id": rid}
    for f in visible_fields(ctx, ent, rec):
        try:
            v = getattr(rec, f["name"])
        except (E.ExprError, TypeError, AttributeError, ValueError):
            v = None
        out[f["name"]] = to_json(v)
    return out


def can_read_any(ctx, ent):
    return ctx.user is not None


def can_read(ctx, ent, rid):
    return _safe_test(ctx, ent["rules"].get("read"), True, record=Rec(ctx, ent, rid))


# ------------------------------------------------------------------ validation of stored records
def validate_record(ctx, ent, rid, data, is_new):
    """Return {field: message} problems for a stored record (required, types, unique, constraints)."""
    errors = {}
    for f in ent["fields"].values():
        if f.get("computed"):
            continue
        v = data.get(f["id"])
        if v is None or (f["type"] == "list" and f.get("required") and v == []):
            if f.get("required"):
                errors[f["name"]] = "is required"
            continue
        if f["type"] == "list":
            el = M.element(f)
            vals = v if isinstance(v, list) else [v]
            if el["type"] == "enum" and any(x not in (el.get("values") or []) for x in vals):
                errors[f["name"]] = f"items must be one of {', '.join(map(str, el['values']))}"
            if el["type"] == "ref" and any(x not in records(ctx.world, el["ref"]) for x in vals):
                errors[f["name"]] = "refers to a record that does not exist"
            if f.get("distinct") and len(set(map(json.dumps, vals))) != len(vals):
                errors[f["name"]] = "must not contain duplicates"
        if f["type"] == "enum" and v not in f.get("values", []):
            errors[f["name"]] = f"must be one of {', '.join(map(str, f['values']))}"
        if f["type"] == "ref" and v not in records(ctx.world, f["ref"]):
            errors[f["name"]] = "refers to a record that does not exist"
        if f.get("unique"):
            for orid, odata in records(ctx.world, ent["id"]).items():
                if orid != rid and odata.get(f["id"]) == v:
                    errors[f["name"]] = "must be unique"
                    break
    rec = Rec(ctx, ent, rid, override=data)
    for c in ent["constraints"].values():
        if not is_new and rid in c.get("exempt", ()):
            continue  # grandfathered: existed and violated it when the constraint was introduced
        try:
            ok = ctx.test(c["expr"], True, record=rec)
        except (E.ExprError, TypeError, AttributeError, ValueError) as exc:
            ok = False
            c = dict(c, message=f"{c.get('message') or c['name']} ({exc})")
        if not ok:
            errors[c.get("field") or c["name"]] = c.get("message") or f"violates {c['name']}"
    return errors


# ------------------------------------------------------------------ effects
def run_effects(ctx, ent, rec, effects, env_extra):
    env_extra = dict(env_extra)
    touched = []
    for eff in effects or []:
        if "if" in eff:
            branch = eff.get("then") if ctx.test(eff["if"], False, record=rec, **env_extra) else eff.get("else")
            touched += run_effects(ctx, ent, rec, branch, env_extra)
            continue
        if "for" in eff:
            items = ctx.eval(eff["in"], record=rec, **env_extra)
            if isinstance(items, Rec):
                items = [items]
            for item in list(items or []):
                touched += run_effects(ctx, ent, rec, eff.get("do"), dict(env_extra, **{eff["for"]: item}))
            continue
        if "fail" in eff:
            if eff.get("when") is None or ctx.test(eff["when"], False, record=rec, **env_extra):
                msg = ctx.eval(eff["fail"], record=rec, **env_extra)
                halt(int(eff.get("status", 409)), str(msg))
            continue
        if "update" in eff:
            targets = ctx.eval(eff["update"], record=rec, **env_extra)
            if isinstance(targets, Rec):
                targets = [targets]
            for t in list(targets or []):
                data = copy.deepcopy(records(ctx.world, t._ent["id"]).get(t.id))
                if data is None:
                    continue
                for fname, ex in eff.get("set", {}).items():
                    f = M.field(t._ent, fname)
                    data[f["id"]] = to_storage(f, ctx.eval(ex, record=rec, it=t, **env_extra))
                ctx.write(t._ent, t.id, data)
                touched.append((t._ent, t.id))
            continue
        if "set" in eff:
            data = copy.deepcopy(records(ctx.world, ent["id"]).get(rec.id))
            for fname, ex in eff["set"].items():
                f = M.field(ent, fname)
                data[f["id"]] = to_storage(f, ctx.eval(ex, record=rec, **env_extra))
            ctx.write(ent, rec.id, data)
            touched.append((ent, rec.id))
        if "create" in eff:
            tent = M.entity(ctx.model, eff["create"])
            nid = ctx.next_id(tent)
            data = {}
            for fname, ex in eff.get("values", {}).items():
                f = M.field(tent, fname)
                data[f["id"]] = to_storage(f, ctx.eval(ex, record=rec, **env_extra))
            apply_defaults(ctx, tent, data, provided=set(data))
            ctx.write(tent, nid, data)
            touched.append((tent, nid))
            fire_triggers(ctx, tent, nid, "create", None)
            if eff.get("as"):
                env_extra[eff["as"]] = Rec(ctx, tent, nid)
        if "delete" in eff:
            targets = ctx.eval(eff["delete"], record=rec, **env_extra)
            if isinstance(targets, Rec):
                targets = [targets]
            for t in list(targets or []):
                ctx.write(t._ent, t.id, None)
        if "emit" in eff:
            payload = {k: to_json(ctx.eval(ex, record=rec, **env_extra)) for k, ex in eff.get("payload", {}).items()}
            ctx.world["outbox"].append({"id": ctx.world["outbox_next"], "channel": eff["emit"], "payload": payload,
                                        "created_at": ctx.now.replace(microsecond=0).isoformat()})
            ctx.world["outbox_next"] += 1
    return touched


def apply_defaults(ctx, ent, data, provided, errors=None):
    """Fill defaults. With ``errors`` (a dict), a default that cannot be computed from incomplete
    input is reported there (and left empty) instead of raising."""
    cand = Rec(ctx, ent, None, override=data)
    for f in M.ordered_fields(ent):
        if f.get("computed") or f["id"] in provided:
            continue
        if f.get("default") not in (None, ""):
            try:
                data[f["id"]] = to_storage(f, ctx.eval(f["default"], record=cand))
            except (E.ExprError, TypeError, AttributeError, ValueError) as exc:
                if errors is None:
                    raise
                data[f["id"]] = None
                errors[f["name"]] = f"cannot be computed from this input ({exc})"
        else:
            data.setdefault(f["id"], None)


def fire_triggers(ctx, ent, rid, event, old):
    for t in ent["triggers"].values():
        if t["on"] != event:
            continue
        rec = Rec(ctx, ent, rid)
        if t.get("when") and not ctx.test(t["when"], False, record=rec, old=old):
            continue
        run_effects(ctx, ent, rec, t["effects"], {"old": old})


def check_touched(ctx, touched, status=409):
    seen = set()
    for ent, rid in touched:
        if (ent["id"], rid) in seen:
            continue
        seen.add((ent["id"], rid))
        data = records(ctx.world, ent["id"]).get(rid)
        if data is None:
            continue
        errs = validate_record(ctx, ent, rid, data, is_new=False)
        if errs:
            halt(status, f"{ent['name']} {rid} would become invalid", errs)


# ------------------------------------------------------------------ operations
def _entity_or_404(ctx, coll):
    try:
        ent = M.entity(ctx.model, coll)
    except M.ModelError:
        halt(404, f"unknown collection {coll!r}")
    return ent


def _require_user(ctx):
    if ctx.user is None:
        halt(401, "unknown or missing user")


def op_list(ctx, coll, query):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    items = []
    for rid in sorted(records(ctx.world, ent["id"])):
        if not can_read(ctx, ent, rid):
            continue
        item = serialize(ctx, ent, rid)
        ok = True
        for k, v in query.items():
            if k not in item:
                ok = False
                break
            iv = item[k]
            if isinstance(iv, list):
                if v not in [json.dumps(x) if isinstance(x, bool) else str(x) for x in iv]:
                    ok = False
                    break
                continue
            sval = json.dumps(iv) if isinstance(iv, bool) else ("" if iv is None else str(iv))
            if sval != v and not (iv is None and v in ("null", "")):
                ok = False
                break
        if ok:
            items.append(item)
    return 200, {"items": items}


def _record_or_404(ctx, ent, rid):
    try:
        rid = int(rid)
    except ValueError:
        halt(404, "no such record")
    if rid not in records(ctx.world, ent["id"]):
        halt(404, f"{ent['name']} {rid} does not exist")
    return rid


def op_get(ctx, coll, rid):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    rid = _record_or_404(ctx, ent, rid)
    if not can_read(ctx, ent, rid):
        halt(403, f"you may not read {ent['name']} {rid}")
    return 200, serialize(ctx, ent, rid)


def _check_input_fields(ctx, ent, body, rec_for_rules, errs403, errs400, creating):
    data = {}
    for name, value in body.items():
        try:
            f = M.field(ent, name)
        except M.ModelError:
            errs400[name] = "unknown field"
            continue
        if f.get("computed") or f.get("system"):
            errs400[name] = "cannot be set"
            continue
        if f.get("write_if") and not _safe_test(ctx, f["write_if"], False, record=rec_for_rules, input=body):
            errs403[name] = "you may not set this field"
            continue
        stored, err = parse_input(f, value, ctx)
        if err:
            errs400[name] = err
            if f["type"] == "list" and stored is not None:
                data[f["id"]] = stored  # valid items, so guards can still be evaluated
            continue
        data[f["id"]] = stored
    return data


def op_create(ctx, coll, body):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    errs403, errs400 = {}, {}
    if not isinstance(body, dict):
        errs400["_body"] = "the request body must be a JSON object"
        body = {}
    cand_data = {}
    cand = Rec(ctx, ent, None, override=cand_data)
    data = _check_input_fields(ctx, ent, body, cand, errs403, errs400, True)
    cand_data.update(data)
    default_errs = {}
    apply_defaults(ctx, ent, cand_data, provided=set(data), errors=default_errs)
    if not _safe_test(ctx, ent["rules"].get("create"), True, record=cand, input=body):
        halt(403, f"you may not create {ent['name']}")
    if errs403:
        halt(403, "you may not set some fields", errs403)
    if not _safe_test(ctx, ent["rules"].get("create_guard"), True, record=cand, input=body):
        halt(409, ent.get("guard_messages", {}).get("create_guard") or f"{ent['name']} cannot be created now")
    errs400 = dict(default_errs, **errs400)  # input errors explain failed defaults best
    if errs400:
        halt(400, "invalid input", errs400)
    rid = ctx.next_id(ent)
    errs = validate_record(ctx, ent, rid, cand_data, is_new=True)
    if errs:
        halt(400, "invalid input", errs)
    ctx.write(ent, rid, cand_data)
    fire_triggers(ctx, ent, rid, "create", None)
    return 201, serialize(ctx, ent, rid)


def op_update(ctx, coll, rid, body):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    rid = _record_or_404(ctx, ent, rid)
    if not isinstance(body, dict):
        halt(400, "the request body must be a JSON object")
    rec = Rec(ctx, ent, rid)
    if not can_read(ctx, ent, rid) or not _safe_test(ctx, ent["rules"].get("update"), True, record=rec, input=body):
        halt(403, f"you may not change {ent['name']} {rid}")
    errs403, errs400 = {}, {}
    old = Rec(ctx, ent, rid, override=copy.deepcopy(records(ctx.world, ent["id"])[rid]))
    data = _check_input_fields(ctx, ent, body, rec, errs403, errs400, False)
    if errs403:
        halt(403, "you may not change some fields", errs403)
    if not _safe_test(ctx, ent["rules"].get("update_guard"), True, record=rec, input=body):
        halt(409, ent.get("guard_messages", {}).get("update_guard") or f"{ent['name']} {rid} cannot be changed now")
    if errs400:
        halt(400, "invalid input", errs400)
    new = copy.deepcopy(records(ctx.world, ent["id"])[rid])
    new.update(data)
    errs = validate_record(ctx, ent, rid, new, is_new=False)
    if errs:
        halt(400, "invalid input", errs)
    ctx.write(ent, rid, new)
    fire_triggers(ctx, ent, rid, "update", old)
    return 200, serialize(ctx, ent, rid)


def op_delete(ctx, coll, rid):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    rid = _record_or_404(ctx, ent, rid)
    rec = Rec(ctx, ent, rid)
    if not can_read(ctx, ent, rid) or not _safe_test(ctx, ent["rules"].get("delete"), True, record=rec):
        halt(403, f"you may not delete {ent['name']} {rid}")
    if not _safe_test(ctx, ent["rules"].get("delete_guard"), True, record=rec):
        halt(409, ent.get("guard_messages", {}).get("delete_guard") or f"{ent['name']} {rid} cannot be deleted now")
    for other in ctx.model["entities"].values():
        for f in other["fields"].values():
            if f["type"] == "ref" and f.get("ref") == ent["id"] and not f.get("computed"):
                if any(d.get(f["id"]) == rid for d in records(ctx.world, other["id"]).values()):
                    halt(409, f"{ent['name']} {rid} is still referenced by {other['name']}")
    old = Rec(ctx, ent, rid, override=copy.deepcopy(records(ctx.world, ent["id"])[rid]))
    fire_triggers(ctx, ent, rid, "delete", old)
    ctx.write(ent, rid, None)
    return 204, None


def _action(ent, name):
    for a in ent["actions"].values():
        if a["name"] == name:
            return a
    return None


def parse_params(ctx, action, body):
    values, errs = {}, {}
    if not isinstance(body, dict):
        return {}, {"_": "the request body must be a JSON object"}
    for pname, spec in action["params"].items():
        v = body.get(pname)
        if v is None or (spec.get("type") == "text" and isinstance(v, str) and spec.get("required") and not v.strip()) \
                or (spec.get("type") == "list" and v == [] and spec.get("required")):
            if spec.get("required"):
                errs[pname] = "is required"
            values[pname] = None
            continue
        f = {"type": spec.get("type", "text"), "values": spec.get("values"), "ref": spec.get("ref"),
             "of": spec.get("of"), "distinct": spec.get("distinct")}
        if M.is_reference(f):
            f["ref"] = M.entity(ctx.model, spec["ref"])["id"]
        stored, err = parse_input(f, v, ctx)
        if err:
            errs[pname] = err
            values[pname] = from_storage(f, stored, ctx) if f["type"] == "list" and stored is not None else None
            continue
        values[pname] = from_storage(f, stored, ctx)
    for k in body:
        if k not in action["params"]:
            errs[k] = "unknown parameter"
    return values, errs


def action_allowed(ctx, ent, rec, action, params):
    return _safe_test(ctx, action.get("allow"), True, record=rec, params=Params(params))


def action_possible(ctx, ent, rec, action, params):
    return _safe_test(ctx, action.get("guard"), True, record=rec, params=Params(params))


def op_action(ctx, coll, rid, name, body):
    _require_user(ctx)
    ent = _entity_or_404(ctx, coll)
    action = _action(ent, name)
    if action is None:
        halt(404, f"{ent['name']} has no action {name!r}")
    rid = _record_or_404(ctx, ent, rid)
    rec = Rec(ctx, ent, rid)
    params, perrs = parse_params(ctx, action, body if body is not None else {})
    if not can_read(ctx, ent, rid) or not action_allowed(ctx, ent, rec, action, params):
        halt(403, f"you may not {name} {ent['name']} {rid}")
    if not action_possible(ctx, ent, rec, action, params):
        msg = None
        if action.get("guard_message"):
            try:
                msg = str(ctx.eval(action["guard_message"], record=rec, params=Params(params)))
            except (E.ExprError, TypeError, AttributeError, ValueError):
                msg = None
        halt(409, msg or f"{name} is not possible for {ent['name']} {rid} now")
    if perrs:
        halt(400, "invalid parameters", perrs)
    touched = run_effects(ctx, ent, rec, action["effects"], {"params": Params(params)})
    check_touched(ctx, touched, status=409)
    fire_triggers(ctx, ent, rid, f"action:{name}", None)
    if rid not in records(ctx.world, ent["id"]):
        return 200, {"id": rid}
    return 200, serialize(ctx, ent, rid)


def op_outbox(ctx, query=None):
    _require_user(ctx)
    items = copy.deepcopy(ctx.world["outbox"])
    for k, v in (query or {}).items():  # same exact-match filtering as collections (e.g. ?channel=payment)
        items = [m for m in items if k in m and str(m[k]) == v]
    return 200, {"items": items}


# ------------------------------------------------------------------ dispatcher
def handle(model, world, method, path, query, body, user, now):
    """Run one request against (model, world). Mutations are atomic. Returns (status, body)."""
    status, out, _ = handle_full(model, world, method, path, query, body, user, now)
    return status, out


def handle_full(model, world, method, path, query, body, user, now):
    """Like handle(), also returning the request context (journal of writes, outbox mark)."""
    ctx = Ctx(model, world, user, now)
    status, out = _dispatch(ctx, method, path, query, body)
    return status, out, ctx


def _dispatch(ctx, method, path, query, body):
    parts = [p for p in path.split("/") if p]
    try:
        if not parts or parts[0] != "api":
            halt(404, "not found")
        parts = parts[1:]
        if parts == ["_outbox"] and method == "GET":
            return op_outbox(ctx)
        if len(parts) == 1 and method == "GET":
            return op_list(ctx, parts[0], query)
        if len(parts) == 1 and method == "POST":
            return op_create(ctx, parts[0], body)
        if len(parts) == 2 and method == "GET":
            return op_get(ctx, parts[0], parts[1])
        if len(parts) == 2 and method == "PATCH":
            return op_update(ctx, parts[0], parts[1], body)
        if len(parts) == 2 and method == "DELETE":
            return op_delete(ctx, parts[0], parts[1])
        if len(parts) == 3 and method == "POST":
            return op_action(ctx, parts[0], parts[1], parts[2], body)
        halt(404, "not found")
    except Halt as h:
        ctx.rollback()
        return h.status, h.body()
    except (E.ExprError, TypeError, AttributeError, ValueError, KeyError, M.ModelError) as exc:
        ctx.rollback()
        return 500, {"error": "internal", "message": f"{type(exc).__name__}: {exc}", "fields": {}}


def parse_now(header):
    if header:
        try:
            return dt.datetime.fromisoformat(header).replace(tzinfo=None)
        except ValueError:
            pass
    return dt.datetime.utcnow().replace(microsecond=0)
