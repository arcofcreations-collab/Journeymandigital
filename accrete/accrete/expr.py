"""The accrete expression language.

A safe subset of Python expressions used for every piece of behaviour: derived fields,
defaults, permissions, guards, constraints and action effects. Expressions are written with
human names (``record.book.title``); the engine type-checks them against the model, records
which model elements they depend on, and rewrites them when an element is renamed.
"""
from __future__ import annotations

import ast
import datetime as _dt
import math

ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call,
    ast.Attribute, ast.Name, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.comprehension, ast.Subscript, ast.Slice,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.Load, ast.Store, ast.keyword, ast.JoinedStr,
    ast.FormattedValue,
)

# Methods callable on plain values (strings, dates, numbers)
SAFE_METHODS = {
    "lower", "upper", "strip", "startswith", "endswith", "replace", "split", "title",
    "date", "isoformat", "year", "month", "day", "hour", "minute", "weekday", "isoweekday",
    "days", "total_seconds", "get", "keys", "values", "items", "count", "index",
}


class ExprError(Exception):
    pass


def parse(src: str) -> ast.Expression:
    try:
        tree = ast.parse(str(src).strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"syntax error in expression {src!r}: {exc.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise ExprError(f"{type(node).__name__} is not allowed in expressions ({src!r})")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExprError(f"private attribute {node.attr!r} in {src!r}")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ExprError(f"private name {node.id!r} in {src!r}")
    return tree


# ---------------------------------------------------------------------------
# Built-in functions available to every expression
# ---------------------------------------------------------------------------
def _days(n):
    return _dt.timedelta(days=n)


def _hours(n):
    return _dt.timedelta(hours=n)


def _minutes(n):
    return _dt.timedelta(minutes=n)


def _to_date(v):
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _to_datetime(v):
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, _dt.date):
        return _dt.datetime(v.year, v.month, v.day)
    return _dt.datetime.fromisoformat(str(v))


def _count(items, **where):
    return len(_where(items, where))


def _where(items, where):
    out = []
    for it in items or []:
        if all(_eq(getattr(it, k), v) for k, v in where.items()):
            out.append(it)
    return out


def _eq(a, b):
    return a == b


def _find(items, **where):
    return _where(items, where)


def _first(items, **where):
    m = _where(items, where)
    return m[0] if m else None


def _sum(items):
    return sum(x for x in items if x is not None)


def _round(x, n=0):
    return None if x is None else round(x, n)


def _between(x, lo, hi):
    return x is not None and lo <= x <= hi


BUILTINS = {
    "days": _days, "hours": _hours, "minutes": _minutes, "date": _to_date, "datetime": _to_datetime,
    "len": len, "count": _count, "find": _find, "first": _first, "sum": _sum, "min": min, "max": max,
    "any": any, "all": all, "abs": abs, "round": _round, "str": str, "int": int, "float": float,
    "bool": bool, "sorted": sorted, "between": _between, "floor": math.floor, "ceil": math.ceil,
    "True": True, "False": False, "None": None,
}


class Undefined(Exception):
    pass


def evaluate(src_or_tree, env: dict):
    """Evaluate an expression with the given variables (plus built-ins)."""
    tree = parse(src_or_tree) if isinstance(src_or_tree, str) else src_or_tree
    code = compile(tree, "<expr>", "eval")
    scope = dict(BUILTINS)
    scope.update(env)
    scope["__builtins__"] = {}
    try:
        # names must live in globals so comprehensions can see them; the AST is validated
        return eval(code, scope)  # noqa: S307
    except ZeroDivisionError:
        return None
    except NameError as exc:
        raise ExprError(str(exc)) from None


# ---------------------------------------------------------------------------
# Static analysis: types, dependencies, renames
# ---------------------------------------------------------------------------
class TypeEnv:
    """What the checker knows: entity schemas (by name) and variable types.

    A type is ("entity", name), ("list", name), ("params", action), or None (unknown).
    """

    def __init__(self, entities: dict, variables: dict, params: dict | None = None):
        self.entities = entities  # name -> {"fields": {fname: {"type","ref"(entity name)}}}
        self.variables = variables
        self.params = params or {}


class Analysis:
    def __init__(self):
        self.reads = set()        # (entity name, field name) pairs read
        self.collections = set()  # entity names iterated as collections
        self.errors = []          # unresolved names
        self.unknown_attrs = set()  # attribute names read on values of unknown type


def analyse(src: str, tenv: TypeEnv) -> Analysis:
    tree = parse(src)
    a = Analysis()
    _infer(tree.body, tenv, dict(tenv.variables), a)
    return a


def _infer(node, tenv, scope, a):
    """Return the type of node, recording reads and errors."""
    if isinstance(node, ast.Name):
        if node.id in scope:
            return scope[node.id]
        if node.id in tenv.entities:
            a.collections.add(node.id)
            return ("list", node.id)
        if node.id in BUILTINS or node.id in ("now", "today"):
            return None
        a.errors.append(f"unknown name {node.id!r}")
        return None
    if isinstance(node, ast.Attribute):
        base = _infer(node.value, tenv, scope, a)
        if base and base[0] == "entity":
            ent = tenv.entities.get(base[1])
            if ent is None:
                return None
            if node.attr == "id":
                return None
            f = ent["fields"].get(node.attr)
            if f is None:
                a.errors.append(f"{base[1]} has no field {node.attr!r}")
                return None
            a.reads.add((base[1], node.attr))
            if f.get("type") == "ref":
                return ("entity", f.get("ref"))
            return None
        if base and base[0] == "params":
            if node.attr not in tenv.params:
                a.errors.append(f"action has no parameter {node.attr!r}")
                return None
            p = tenv.params[node.attr]
            return ("entity", p.get("ref")) if p.get("type") == "ref" else None
        if base and base[0] == "list":
            a.errors.append(f"cannot read .{node.attr} of the collection {base[1]}")
            return None
        if node.attr not in SAFE_METHODS:
            a.unknown_attrs.add(node.attr)
        return None
    if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
        inner = dict(scope)
        for gen in node.generators:
            it = _infer(gen.iter, tenv, inner, a)
            if isinstance(gen.target, ast.Name):
                inner[gen.target.id] = ("entity", it[1]) if it and it[0] == "list" else None
            for cond in gen.ifs:
                _infer(cond, tenv, inner, a)
        _infer(node.elt, tenv, inner, a)
        return None
    if isinstance(node, ast.Call):
        ftype = None
        fname = node.func.id if isinstance(node.func, ast.Name) else None
        if not isinstance(node.func, ast.Name):
            _infer(node.func, tenv, scope, a)
        elif fname not in BUILTINS:
            a.errors.append(f"unknown function {fname!r}")
        args = [_infer(x, tenv, scope, a) for x in node.args]
        if fname in ("find", "first", "count") and args and args[0] and args[0][0] == "list":
            ent = tenv.entities.get(args[0][1], {"fields": {}})
            for kw in node.keywords:
                if kw.arg not in ent["fields"] and kw.arg != "id":
                    a.errors.append(f"{args[0][1]} has no field {kw.arg!r}")
                else:
                    a.reads.add((args[0][1], kw.arg))
            if fname == "first":
                ftype = ("entity", args[0][1])
            elif fname == "find":
                ftype = args[0]
        for kw in node.keywords:
            _infer(kw.value, tenv, scope, a)
        if fname == "sorted" and args:
            ftype = args[0]
        return ftype
    if isinstance(node, ast.Compare):
        types = [_infer(x, tenv, scope, a) for x in [node.left] + node.comparators]
        operands = [node.left] + node.comparators
        for t, other in zip(types, operands[1:] + operands[:1]):
            if t and t[0] == "entity" and isinstance(other, ast.Constant) and isinstance(other.value, (str, float, bool)):
                a.errors.append(f"compares a {t[1]} record with the constant {other.value!r}")
        return None
    for child in ast.iter_child_nodes(node):
        _infer(child, tenv, scope, a)
    return None


class _Renamer(ast.NodeTransformer):
    """Rename field ``old`` of entity ``ent`` (or a collection) wherever types prove it."""

    def __init__(self, tenv, scope, ent, old, new, kind):
        self.tenv, self.scope, self.ent, self.old, self.new, self.kind = tenv, scope, ent, old, new, kind
        self.changed = 0
        self.unsure = 0

    def run(self, tree):
        a = Analysis()
        self._walk(tree.body, dict(self.scope), a)
        return tree

    def _walk(self, node, scope, a):
        # mirrors _infer, rewriting matching nodes in place
        if isinstance(node, ast.Name):
            if self.kind == "entity" and node.id == self.old and node.id not in scope:
                node.id = self.new
                self.changed += 1
                return ("list", self.new)
            return _infer(node, self.tenv, scope, a)
        if isinstance(node, ast.Attribute):
            base = self._walk(node.value, scope, a)
            if self.kind == "field" and node.attr == self.old:
                if base and base[0] == "entity" and base[1] == self.ent:
                    node.attr = self.new
                    self.changed += 1
                elif base is None:
                    self.unsure += 1
            if base and base[0] == "entity":
                ent = self.tenv.entities.get(base[1])
                if ent:
                    f = ent["fields"].get(node.attr)
                    if f and f.get("type") == "ref":
                        return ("entity", f.get("ref"))
            if base and base[0] == "params":
                p = self.tenv.params.get(node.attr, {})
                return ("entity", p.get("ref")) if p.get("type") == "ref" else None
            return None
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            inner = dict(scope)
            for gen in node.generators:
                it = self._walk(gen.iter, inner, a)
                if isinstance(gen.target, ast.Name):
                    inner[gen.target.id] = ("entity", it[1]) if it and it[0] == "list" else None
                for cond in gen.ifs:
                    self._walk(cond, inner, a)
            self._walk(node.elt, inner, a)
            return None
        if isinstance(node, ast.Call):
            fname = node.func.id if isinstance(node.func, ast.Name) else None
            if not isinstance(node.func, ast.Name):
                self._walk(node.func, scope, a)
            args = [self._walk(x, scope, a) for x in node.args]
            if fname in ("find", "first", "count") and args and args[0] and args[0][0] == "list":
                for kw in node.keywords:
                    if self.kind == "field" and args[0][1] == self.ent and kw.arg == self.old:
                        kw.arg = self.new
                        self.changed += 1
            for kw in node.keywords:
                self._walk(kw.value, scope, a)
            if fname == "first" and args and args[0] and args[0][0] == "list":
                return ("entity", args[0][1])
            if fname in ("find", "sorted") and args:
                return args[0]
            return None
        for child in ast.iter_child_nodes(node):
            self._walk(child, scope, a)
        return None


def rename(src: str, tenv: TypeEnv, kind: str, entity: str | None, old: str, new: str):
    """Rewrite an expression for a renamed field (kind='field') or collection (kind='entity').

    Returns (new_source, changed_count, unsure_count). ``tenv`` describes the model *before*
    the rename, so types resolve against the old names.
    """
    tree = parse(src)
    r = _Renamer(tenv, dict(tenv.variables), entity, old, new, kind)
    r.run(tree)
    if not r.changed:
        return src, 0, r.unsure
    return ast.unparse(tree), r.changed, r.unsure
