#!/usr/bin/env python3
"""Developer tool for this application. Run it from anywhere: ``python dev.py <command>``.

    overview                      one screen: migrations, schema (live data.db), API routes with
                                  their checks in order, UI routes, rule constants, users by role,
                                  two sample records per collection, outbox channels, tests
    check [-k EXPR] [--full]      the whole verification: test suite, data.db fully migrated and
          [--no-scan] [TESTS...]  equal to a seed rebuild, integrity, plus a contract/UI scan
                                  (UI lists/detail/forms agree with the API for every user)
    call METHOD PATH --as USER [--body JSON] [--form k=v ...] [--now TS] [--raw]
                                  one request against a throwaway copy (data.db is never touched;
                                  pending migrations are applied to the copy); prints the response
                                  (HTML pages summarised as the contract sees them) and the rows
                                  the request changed
    call --steps "USER METHOD PATH [JSON]" ...
                                  several requests in sequence on the same throwaway copy
    new-migration NAME            create migrations/NNNN_NAME.sql (next number) from a template
    migrate                       apply pending migrations to the committed data.db
    snapshot                      record files + data.db before a change (overview does it once)
    dbdiff                        row-level diff of data.db against the snapshot
    notes                         write CHANGE_NOTES.md: changed files, migrations, data changes,
                                  last check result

Everything here is development tooling; the application never imports this file.
"""
import argparse
import ast
import contextlib
import difflib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import quote
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

sys.dont_write_bytecode = True  # keep the app directory free of __pycache__ from this tool

# --- the only app-specific lines ---------------------------------------------------------
PACKAGE = "expenses_app"
USER_TABLE = "employees"  # the table X-User usernames are looked up in
# -----------------------------------------------------------------------------------------

NOW = "2026-03-01T12:00:00"  # X-Now used by call/check unless --now is given (the tests use it too)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.join(APP_DIR, PACKAGE)
MIGRATIONS_DIR = os.path.join(PKG_DIR, "migrations")
DATA_DB = os.path.join(APP_DIR, "data.db")
HARNESS_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "..", "harness"))
DEV_DIR = os.path.join(APP_DIR, ".dev")
SNAPSHOT_FILES = os.path.join(DEV_DIR, "snapshot.json")
SNAPSHOT_DB = os.path.join(DEV_DIR, "snapshot.db")
LAST_CHECK = os.path.join(DEV_DIR, "last_check.txt")
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".dev"}
ERROR_CLASSES = {"NotFound": "404", "Forbidden": "403", "Conflict": "409", "ValidationError": "400"}


# =========================================================================================
# helpers: throwaway copies, requests, HTML summary
# =========================================================================================

def display(value):
    """How templates render a value (the package's ``display`` filter)."""
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return json.dumps(value)
    return str(value)


class Copy:
    """A throwaway copy of this app directory, loaded through app_entry.create_app()."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="devpy-")
        self.dir = os.path.join(self.root, "app")
        shutil.copytree(APP_DIR, self.dir, ignore=shutil.ignore_patterns(*IGNORED_DIRS, "tests"))
        self.db = os.path.join(self.dir, "data.db")
        spec = importlib.util.spec_from_file_location(f"app_entry_{uuid.uuid4().hex}",
                                                      os.path.join(self.dir, "app_entry.py"))
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, self.dir)
        old = os.getcwd()
        try:
            os.chdir(self.dir)
            spec.loader.exec_module(module)
            self.app = module.create_app()
        finally:
            os.chdir(old)
            sys.path.remove(self.dir)
        self.client = self.app.test_client()

    def request(self, method, path, user, body=None, form=None, now=NOW):
        headers = {}
        if user:
            headers["X-User"] = user
        if now:
            headers["X-Now"] = now
        kwargs = {"headers": headers}
        if form is not None:
            kwargs["data"] = form
        elif body is not None:
            kwargs["json"] = body
        elif method in ("POST", "PATCH"):
            kwargs["json"] = {}
        return self.client.open(path, method=method, **kwargs)

    def users(self):
        conn = sqlite3.connect(self.db)
        try:
            return [r[0] for r in conn.execute(f"SELECT username FROM {USER_TABLE} ORDER BY id")]
        finally:
            conn.close()

    def save_db(self):
        with open(self.db, "rb") as fh:
            return fh.read()

    def restore_db(self, data):
        with open(self.db, "wb") as fh:
            fh.write(data)

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


class UiPage(HTMLParser):
    """The contract's view of a page: rows, fields, actions, creates, inputs (+ title/error)."""

    def __init__(self, html):
        super().__init__()
        self.rows, self.fields, self.actions, self.inputs, self.creates = [], {}, [], [], []
        self.title, self.error = "", ""
        self._field, self._buf, self._in = None, [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and "data-id" in a:
            self.rows.append(int(a["data-id"]))
        if "data-field" in a:
            self._field, self._buf = a["data-field"], []
        if tag == "form" and "data-action" in a:
            self.actions.append(a["data-action"])
        if tag == "form" and "data-create" in a:
            self.creates.append(a["data-create"])
        if tag in ("input", "select", "textarea") and a.get("name"):
            self.inputs.append(a["name"])
        if tag == "title" or (tag == "p" and "error" in (a.get("class") or "")):
            self._in, self._buf2 = tag, []

    def handle_data(self, data):
        if self._field is not None:
            self._buf.append(data)
        if self._in:
            self._buf2.append(data)

    def handle_endtag(self, tag):
        if self._field is not None:
            self.fields[self._field] = "".join(self._buf).strip()
            self._field = None
        if self._in == tag:
            text = " ".join("".join(self._buf2).split())
            if tag == "title":
                self.title = text
            else:
                self.error = text
            self._in = None


def is_html(resp):
    return "text/html" in (resp.headers.get("Content-Type") or "")


def short(value, limit=160):
    text = value if isinstance(value, str) else json.dumps(value, separators=(", ", ": "))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_response(resp, raw=False):
    status = resp.status_code
    location = resp.headers.get("Location")
    print(f"<- {status}" + (f"  Location: {location}" if location else ""))
    body = resp.get_data(as_text=True)
    if raw:
        print(body)
        return
    if is_html(resp):
        page = UiPage(body)
        if page.error:
            print(f"   error page: {page.error}")
        if page.rows or "<table" in body:
            print(f"   rows (data-id): {page.rows}")
        if page.fields:
            print("   fields (data-field):")
            for k, v in page.fields.items():
                print(f"     {k} = {v!r}")
        if page.actions or page.fields:
            print(f"   action forms (data-action): {page.actions}")
        if page.creates:
            print(f"   create forms (data-create): {page.creates}  inputs: {page.inputs}")
        elif page.inputs:
            print(f"   inputs: {page.inputs}")
        return
    data = resp.get_json(silent=True)
    if data is None:
        if body:
            print("   " + short(body, 400))
        return
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = data["items"]
        print(f"   {len(items)} items" + (f"  ids: {[i.get('id') for i in items]}" if items and isinstance(items[0], dict) else ""))
        for item in items[:30]:
            print("   " + short(item, 400))
        if len(items) > 30:
            print(f"   ... {len(items) - 30} more")
        return
    print("   " + json.dumps(data, indent=None, separators=(", ", ": ")))


# =========================================================================================
# database helpers: dumps and diffs
# =========================================================================================

def db_tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def dump_db(path, skip_applied_at=False):
    """{table: (columns, {rowid-or-id: row tuple})} plus schema and sqlite_sequence."""
    conn = sqlite3.connect(path)
    try:
        out = {}
        for table in db_tables(conn):
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")]
            key = "id" if "id" in cols else ("version" if "version" in cols else "rowid")
            rows = {}
            for row in conn.execute(f"SELECT {key}, * FROM '{table}'"):
                values = list(row[1:])
                if skip_applied_at and table == "schema_version":
                    values = [v for c, v in zip(cols, values) if c != "applied_at"]
                rows[row[0]] = tuple(values)
            if skip_applied_at and table == "schema_version":
                cols = [c for c in cols if c != "applied_at"]
            out[table] = (cols, rows)
        schema = {r[0]: " ".join((r[1] or "").replace('"', "").split()) for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL")}
        seq = dict(conn.execute("SELECT name, seq FROM sqlite_sequence").fetchall()) if \
            conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone() else {}
        return out, schema, seq
    finally:
        conn.close()


def diff_dumps(before, after, detail=3, ignore=()):
    """Lines describing how ``after`` differs from ``before`` (both from dump_db)."""
    (b_tables, b_schema, b_seq), (a_tables, a_schema, a_seq) = before, after
    lines = []
    for table in sorted(set(b_tables) | set(a_tables)):
        if table in ignore:
            continue
        if table not in a_tables:
            lines.append(f"{table}: table dropped ({len(b_tables[table][1])} rows)")
            continue
        if table not in b_tables:
            cols, rows = a_tables[table]
            lines.append(f"{table}: new table, {len(rows)} rows, columns {cols}")
            for key in list(rows)[:detail]:
                lines.append(f"    + {short(dict(zip(cols, rows[key])), 200)}")
            continue
        b_cols, b_rows = b_tables[table]
        a_cols, a_rows = a_tables[table]
        parts = []
        added_cols = [c for c in a_cols if c not in b_cols]
        removed_cols = [c for c in b_cols if c not in a_cols]
        if added_cols:
            parts.append(f"columns added {added_cols}")
        if removed_cols:
            parts.append(f"columns removed {removed_cols}")
        new = [k for k in a_rows if k not in b_rows]
        gone = [k for k in b_rows if k not in a_rows]
        common = [c for c in a_cols if c in b_cols]
        changed = []
        for k in a_rows:
            if k in b_rows:
                old = dict(zip(b_cols, b_rows[k]))
                cur = dict(zip(a_cols, a_rows[k]))
                delta = {c: (old[c], cur[c]) for c in common if old[c] != cur[c]}
                if delta:
                    changed.append((k, delta))
        if new:
            parts.append(f"+{len(new)} rows (ids {compact_ids(new)})")
        if gone:
            parts.append(f"-{len(gone)} rows (ids {compact_ids(gone)})")
        if changed:
            cols_changed = sorted({c for _, d in changed for c in d})
            parts.append(f"~{len(changed)} rows changed in {cols_changed} (ids {compact_ids([k for k, _ in changed])})")
        if added_cols and b_rows:
            values = {}
            for k, row in a_rows.items():
                for c in added_cols:
                    values.setdefault(c, {}).setdefault(repr(dict(zip(a_cols, row))[c]), 0)
                    values[c][repr(dict(zip(a_cols, row))[c])] += 1
            for c, counts in values.items():
                top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
                parts.append(f"{c} values: " + ", ".join(f"{v} x{n}" for v, n in top) + (" ..." if len(counts) > 6 else ""))
        if parts:
            lines.append(f"{table}: " + "; ".join(parts))
            for k in new[:detail]:
                lines.append(f"    + {short(dict(zip(a_cols, a_rows[k])), 200)}")
            for k in gone[:detail]:
                lines.append(f"    - {short(dict(zip(b_cols, b_rows[k])), 200)}")
            for k, delta in changed[:detail]:
                lines.append(f"    ~ id {k}: " + ", ".join(f"{c}: {o!r} -> {n!r}" for c, (o, n) in delta.items()))
    for name in sorted(set(b_schema) | set(a_schema)):
        if name in b_tables or name in a_tables:
            if b_schema.get(name) != a_schema.get(name) and name in b_schema and name in a_schema:
                old_parts, new_parts = sql_parts(b_schema[name]), sql_parts(a_schema[name])
                gone = [p for p in old_parts if p not in new_parts]
                added = [p for p in new_parts if p not in old_parts]
                lines.append(f"schema of {name} changed: " + "; ".join(
                    [f"- {short(p, 100)}" for p in gone] + [f"+ {short(p, 100)}" for p in added]))
            continue
        if name not in a_schema:
            lines.append(f"index/trigger {name} dropped")
        elif name not in b_schema:
            lines.append(f"index/trigger {name} added")
        elif b_schema[name] != a_schema[name]:
            lines.append(f"index/trigger {name} changed")
    for name in sorted(set(b_seq) | set(a_seq)):
        if b_seq.get(name) != a_seq.get(name) and name in b_tables and name in a_tables:
            lines.append(f"sqlite_sequence {name}: {b_seq.get(name)} -> {a_seq.get(name)}")
    return lines


def sql_parts(sql):
    """Top-level comma-separated parts of a CREATE TABLE body (column and constraint definitions)."""
    body = sql[sql.find("(") + 1: sql.rfind(")")] if "(" in sql else sql
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
            continue
        depth += (ch == "(") - (ch == ")")
        cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def compact_ids(ids, limit=12):
    ids = sorted(ids, key=lambda x: (str(type(x)), x))
    text = ", ".join(str(i) for i in ids[:limit])
    return text + (f", ... ({len(ids)} total)" if len(ids) > limit else "")


def table_snapshot(path):
    return dump_db(path)


# =========================================================================================
# source introspection (for overview)
# =========================================================================================

def import_package():
    """Import this app's package from APP_DIR (dropping a copy loaded from elsewhere)."""
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    module = sys.modules.get(PACKAGE)
    if module is not None and os.path.dirname(os.path.dirname(os.path.abspath(module.__file__))) != APP_DIR:
        for name in [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]:
            del sys.modules[name]
    return importlib.import_module(PACKAGE)


def parse_module(name):
    path = os.path.join(PKG_DIR, name + ".py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    return ast.parse(source), source


def function_defs(tree):
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def check_events(fn_name, funcs, depth=0, via=None, call=None):
    """Ordered checks/effects in a services function: (kind, text).

    ``call`` is the call expression that reached a helper; a raise whose message is not a
    literal is then shown with that call (``_require_status(claim, "draft", "...")``)."""
    node = funcs.get(fn_name)
    if node is None:
        return []
    nodes = [n for n in ast.walk(node) if isinstance(n, (ast.Raise, ast.Call, ast.With))]
    nodes.sort(key=lambda n: (n.lineno, n.col_offset))
    consumed, out = set(), []
    tag = f" (via {via})" if via else ""
    for n in nodes:
        if id(n) in consumed:
            continue
        if isinstance(n, ast.With):
            for item in n.items:
                expr = item.context_expr
                if isinstance(expr, ast.Call) and getattr(expr.func, "id", None) == "transaction":
                    out.append(("tx", "in transaction"))
                    consumed.add(id(expr))
            continue
        if isinstance(n, ast.Raise):
            exc = n.exc
            if isinstance(exc, ast.Call):
                consumed.add(id(exc))
                cls = getattr(exc.func, "id", None) or getattr(exc.func, "attr", None)
                msg = ""
                if exc.args and isinstance(exc.args[0], ast.Constant) and isinstance(exc.args[0].value, str):
                    msg = exc.args[0].value
                elif exc.args and isinstance(exc.args[0], ast.JoinedStr):
                    msg = ast.unparse(exc.args[0])[2:-1]
                if not msg and exc.args and call is not None:
                    msg_text = short(ast.unparse(call), 120)
                else:
                    msg_text = f'"{msg}"' if msg else ""
                out.append((ERROR_CLASSES.get(cls, cls), msg_text + ("" if msg_text.startswith(via or "\0") else tag)))
            continue
        func = n.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            mod, attr = func.value.id, func.attr
            if mod == "permissions" and not attr.startswith("is_"):
                out.append(("perm", f"permissions.{attr}{tag}"))
            elif mod == "validation" and attr.startswith("clean"):
                out.append(("400", f"validation.{attr}{tag}"))
            elif mod == "repository" and attr == "add_outbox_message":
                channel = n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else "?"
                out.append(("outbox", f"{channel}{tag}"))
        elif isinstance(func, ast.Name) and func.id in funcs and func.id != fn_name and depth < 2:
            out.extend(check_events(func.id, funcs, depth + 1, via=func.id if not via else via, call=n))
        elif isinstance(func, ast.Name) and func.id == "authorize" and depth < 2:
            out.append(("perm", "per-action _authorize_* (see *_ACTIONS)" + tag))
    return out


def format_events(events):
    parts, i = [], 0
    while i < len(events):
        kind, text = events[i]
        if kind == "perm" and i + 1 < len(events) and events[i + 1][0] == "403":
            msg = events[i + 1][1]
            via = re.search(r" \(via \w+\)$", text)
            if via and msg.endswith(via.group(0)):
                text = text[: via.start()]
            parts.append(" ".join(p.strip() for p in ("403", text, msg) if p.strip()))
            i += 2
            continue
        if kind == "perm":
            parts.append(f"perm {text}")
        elif kind == "tx":
            parts.append("[tx]")
        elif kind == "outbox":
            parts.append(f"outbox:{text}")
        else:
            parts.append(" ".join(f"{kind} {text}".split()))
        i += 1
    return parts


def view_services(view_func):
    try:
        src = inspect.getsource(view_func)
    except (OSError, TypeError):
        return [], []
    calls = re.findall(r"services\.(\w+)\(", src)
    templates = re.findall(r"render_template\(\s*\"([^\"]+)\"", src)
    seen, ordered = set(), []
    for c in calls:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered, templates


def line_of(funcs, name):
    node = funcs.get(name)
    return node.lineno if node else "?"


def wrap(parts, indent, width=110, cont=None):
    """Join ``parts`` with " | " into lines of at most ``width`` characters."""
    cont = cont if cont is not None else " " * len(indent) + "  "
    lines, cur, first = [], indent, True
    for p in parts:
        piece = p if first else " | " + p
        if not first and len(cur) + len(piece) > width:
            lines.append(cur)
            cur, piece = cont, p
        cur += piece
        first = False
    if not first:
        lines.append(cur)
    return lines


def module_constants(name):
    tree, source = parse_module(name)
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if target.isupper() and not target.startswith("_"):
                text = " ".join(ast.get_source_segment(source, node.value).split())
                out.append(f"{name}.{target} = {short(text, 120)}  (:{node.lineno})")
    return out


# =========================================================================================
# commands
# =========================================================================================

def cmd_overview(args):
    take_snapshot(quiet=True, only_if_missing=True)
    package = import_package()
    db = importlib.import_module(PACKAGE + ".db")

    # --- migrations
    files = db.available_migrations(MIGRATIONS_DIR)
    conn = sqlite3.connect(DATA_DB)
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")} if \
        conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'schema_version'").fetchone() else set()
    pending = [os.path.basename(p) for v, _, p in files if v not in applied]
    print(f"== {PACKAGE} ({APP_DIR})")
    print(f"migrations: {', '.join(os.path.basename(p) for _, _, p in files)}"
          f"  | data.db at version {max(applied) if applied else 0}"
          + (f"  | PENDING: {pending} (python dev.py migrate)" if pending else "  | up to date"))

    # --- schema
    print("\n== schema (data.db)   col TYPE [nn] [=default] [->ref] ; CHECKs ; indexes")
    for table in db_tables(conn):
        if table == "schema_version":
            continue
        count = conn.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
        fks = {r[3]: f"{r[2]}.{r[4]}" for r in conn.execute(f"PRAGMA foreign_key_list('{table}')")}
        cols = []
        for cid, name, ctype, notnull, default, pk in conn.execute(f"PRAGMA table_info('{table}')"):
            text = f"{name} {ctype}" + (" pk" if pk else "") + (" nn" if notnull and not pk else "")
            if default is not None:
                text += f" ={default}"
            if name in fks:
                text += f" ->{fks[name]}"
            cols.append(text)
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0] or ""
        checks = re.findall(r"CHECK\s*\((.*?)\)\s*(?:,|\n|$)", sql)
        idx = [f"{r[1]}{'(unique)' if r[2] else ''}" for r in conn.execute(f"PRAGMA index_list('{table}')")
               if not r[1].startswith("sqlite_autoindex")]
        uniques = [r[1] for r in conn.execute(f"PRAGMA index_list('{table}')") if r[1].startswith("sqlite_autoindex")]
        for line in wrap(cols, f"{table} [{count} rows]: ", 120, cont="    "):
            print(line)
        if checks:
            print("    CHECK: " + " ; ".join(" ".join(c.split()) for c in checks))
        if idx or uniques:
            extra = [f"UNIQUE({', '.join(r[2] for r in conn.execute(f'PRAGMA index_info({chr(39)}{u}{chr(39)})'))})" for u in uniques]
            print("    " + ", ".join(extra + idx))
    conn.close()

    # --- routes
    copy = Copy()
    try:
        services_tree, _ = parse_module("services")
        funcs = function_defs(services_tree)
        rules = sorted(copy.app.url_map.iter_rules(), key=lambda r: (r.rule.split("/")[1:3], r.rule.count("/"), r.rule))
        print("\n== API routes -> services function (services.py line): checks in source order")
        print("   (404/403/409/400 = raises; perm = permissions.* call; [tx] = inside transaction(); outbox:<channel>)")
        for rule in rules:
            if not rule.rule.startswith("/api"):
                continue
            methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
            view = copy.app.view_functions[rule.endpoint]
            called, _ = view_services(view)
            target = called[0] if called else None
            head = f"{'/'.join(methods):6} {rule.rule}"
            if target:
                head += f"  -> services.{target}:{line_of(funcs, target)}"
            events = format_events(check_events(target, funcs)) if target else []
            if methods == ["GET"]:
                perms = [e for e in events if e.startswith(("perm", "403"))]
                print(head + (f"   [{'; '.join(perms)}]" if perms else ""))
            else:
                print(head)
                for line in wrap(events, "         ", cont="           "):
                    print(line)
        print("\n== UI routes -> template [services used]")
        for rule in rules:
            if not rule.rule.startswith("/ui"):
                continue
            methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
            called, templates = view_services(copy.app.view_functions[rule.endpoint])
            print(f"{'/'.join(methods):6} {rule.rule:34} {', '.join(templates) or '(redirect/form post)':26}"
                  f" [{', '.join(called)}]")

        # --- rule constants
        print("\n== rule constants")
        for name in ("services", "validation", "permissions"):
            for line in module_constants(name):
                print(line)

        # --- users
        users = copy.users()
        conn = sqlite3.connect(copy.db)
        conn.row_factory = sqlite3.Row
        by_role = {}
        for row in conn.execute(f"SELECT * FROM {USER_TABLE} ORDER BY id"):
            d = dict(row)
            extra = {k: v for k, v in d.items() if k not in ("id", "username", "name", "role")}
            extra_text = ",".join(f"{k}={v}" for k, v in extra.items())
            by_role.setdefault(d.get("role"), []).append(f"{d['username']}#{d['id']}" + (f"({extra_text})" if extra_text else ""))
        conn.close()
        print(f"\n== users ({USER_TABLE}) by role")
        for role, names in by_role.items():
            for line in wrap(names, f"{role}: ", 120, cont="    "):
                print(line)

        # --- samples
        collections = api_collections(copy.app)
        reader = best_reader(copy, collections, users)
        print(f"\n== sample records (GET /api/<collection> as {reader}; X-Now {NOW})")
        for coll in collections:
            resp = copy.request("GET", f"/api/{coll}", reader)
            items = (resp.get_json(silent=True) or {}).get("items", [])
            fields = list(items[0].keys()) if items else []
            print(f"{coll}: {len(items)} readable; fields: {', '.join(fields) if fields else '(no records)'}")
            for item in items[:2]:
                print("    " + short(item, 700))
        channels = sorted(set(re.findall(r"add_outbox_message\(\s*\"(\w+)\"", open(os.path.join(PKG_DIR, "services.py")).read())))
        print(f"outbox channels emitted in services.py: {', '.join(channels) or '(none)'}")
    finally:
        copy.close()

    # --- tests
    tests_dir = os.path.join(APP_DIR, "tests")
    counts = []
    for name in sorted(os.listdir(tests_dir)):
        if name.startswith("test_") and name.endswith(".py"):
            with open(os.path.join(tests_dir, name), encoding="utf-8") as fh:
                counts.append(f"{name} ({len(re.findall(r'^def test_', fh.read(), re.M))})")
    print("\n== tests: " + ", ".join(counts))
    print("next: README.md has the file map and recipes; `python dev.py check` verifies everything.")


def api_collections(app):
    names = []
    for rule in app.url_map.iter_rules():
        m = re.fullmatch(r"/api/([a-z_]+)", rule.rule)
        if m and "GET" in rule.methods and not m.group(1).startswith("_") and m.group(1) not in names:
            names.append(m.group(1))
    return sorted(names)


def api_actions(app):
    """[(collection, action)] for every POST /api/<collection>/<id>/<action> route."""
    out = []
    for rule in app.url_map.iter_rules():
        m = re.fullmatch(r"/api/([a-z_]+)/<[^>]+>/([a-z_]+)", rule.rule)
        if m and "POST" in rule.methods:
            out.append((m.group(1), m.group(2)))
    return sorted(out)


def has_route(app, path, method):
    adapter = app.url_map.bind("localhost")
    try:
        adapter.match(path, method=method)
        return True
    except Exception:
        return False


def best_reader(copy, collections, users):
    """The user who can read the most records overall (used for samples and the UI scan)."""
    best, best_count = users[0] if users else None, -1
    for user in users:
        total = 0
        for coll in collections:
            resp = copy.request("GET", f"/api/{coll}", user)
            if resp.status_code == 200:
                total += len(resp.get_json()["items"])
        if total > best_count:
            best, best_count = user, total
    return best


def cmd_call(args):
    copy = Copy()
    try:
        steps = []
        if args.steps:
            for text in args.steps:
                parts = text.split(None, 3)
                if len(parts) < 3:
                    sys.exit(f"bad step {text!r}: expected 'USER METHOD PATH [JSON]'")
                body = json.loads(parts[3]) if len(parts) > 3 else None
                steps.append((parts[0], parts[1].upper(), parts[2], body, None))
        else:
            if not args.method or not args.path:
                sys.exit("usage: python dev.py call METHOD PATH --as USER [--body JSON]")
            body = json.loads(args.body) if args.body else None
            form = dict(kv.split("=", 1) for kv in args.form) if args.form else None
            steps.append((args.user, args.method.upper(), args.path, body, form))
        for user, method, path, body, form in steps:
            before = dump_db(copy.db)
            print(f"-> {method} {path}  X-User: {user or '(none)'}  X-Now: {args.now}"
                  + (f"  body: {json.dumps(body)}" if body is not None else "")
                  + (f"  form: {form}" if form else ""))
            resp = copy.request(method, path, user, body=body, form=form, now=args.now)
            print_response(resp, raw=args.raw)
            changes = diff_dumps(before, dump_db(copy.db), detail=5)
            print("   db changes:" + (" none" if not changes else ""))
            for line in changes:
                print("     " + line)
    finally:
        copy.close()


# --- check -------------------------------------------------------------------------------

def run_tests(extra, tests, full):
    """Run the suite in a subprocess; return (ok, summary line, failure lines)."""
    if not os.path.exists(os.path.join(HARNESS_DIR, "accept_client.py")):
        return False, f"harness not found at {HARNESS_DIR} (tests import accept_client from there)", []
    xml_path = os.path.join(tempfile.mkdtemp(prefix="devpy-junit-"), "junit.xml")
    env = dict(os.environ)
    env.pop("ACCEPT_TARGET", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    targets = tests or ["tests"]
    cmd = [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider", "--tb=short",
           f"--junitxml={xml_path}", "-o", "junit_family=xunit1", *extra]
    started = time.time()
    proc = subprocess.run(cmd, cwd=APP_DIR, env=env, capture_output=True, text=True)
    elapsed = time.time() - started
    if not os.path.exists(xml_path):
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-25:]
        return False, f"pytest did not run (exit {proc.returncode})", tail
    root = ET.parse(xml_path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    total = int(suite.get("tests", 0))
    failures, lines = [], []
    for case in suite.iter("testcase"):
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        if problem is None:
            continue
        name = f"{case.get('file') or case.get('classname')}::{case.get('name')}"
        failures.append(name)
        text = problem.text or ""
        lines.append(f"FAIL {name}")
        if full:
            lines.extend("     " + l for l in text.splitlines())
            continue
        locs = [l.strip() for l in text.splitlines() if re.match(r"^\S+\.py:\d+", l.strip())]
        test_locs = [l for l in locs if "tests" in l.split(":")[0]]
        if test_locs:
            lines.append(f"     at {test_locs[-1]}")
        app_locs = [l for l in locs if PACKAGE in l]
        if app_locs:
            lines.append(f"     raised in {app_locs[-1]}")
        e_lines = [l[1:].strip() for l in text.splitlines() if l.startswith("E ")]
        for l in (e_lines or [problem.get("message", "")])[:8]:
            lines.append(f"     {short(l, 220)}")
    skipped = sum(1 for c in suite.iter("testcase") if c.find("skipped") is not None)
    passed = total - len(failures) - skipped
    summary = f"tests: {passed} passed, {len(failures)} failed" + (f", {skipped} skipped" if skipped else "") + f" ({elapsed:.1f}s)"
    if proc.returncode not in (0, 1) and not failures:
        lines.extend((proc.stdout + proc.stderr).strip().splitlines()[-15:])
        return False, summary + f" - pytest exit {proc.returncode}", lines
    return not failures and proc.returncode == 0, summary, lines


def check_database():
    """data.db: fully migrated, equal to a seed rebuild, integrity and references OK."""
    problems = []
    import_package()
    db = importlib.import_module(PACKAGE + ".db")
    try:
        files = db.available_migrations(MIGRATIONS_DIR)
    except RuntimeError as exc:
        return [str(exc)]
    for _, _, path in files:
        with open(path, encoding="utf-8") as fh:
            sql = fh.read()
        if "<one line: what this migration does and why>" in sql:
            problems.append(f"{os.path.basename(path)}: replace the template's placeholder header line with a description")
        sql = re.sub(r"--[^\n]*", "", sql)
        if re.search(r"^\s*(BEGIN|COMMIT|ROLLBACK|END)\b", sql, re.I | re.M):
            problems.append(f"{os.path.basename(path)}: contains BEGIN/COMMIT/ROLLBACK (the runner adds the transaction)")
        if re.search(r"PRAGMA\s+foreign_keys", sql, re.I):
            problems.append(f"{os.path.basename(path)}: PRAGMA foreign_keys has no effect inside a migration (the runner turns them off and checks them afterwards)")
    conn = sqlite3.connect(DATA_DB)
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    known = {v for v, _, _ in files}
    pending = [os.path.basename(p) for v, _, p in files if v not in applied]
    if pending:
        problems.append(f"data.db is behind: pending {pending} -> run `python dev.py migrate` (or `python seed.py`)")
    if applied - known:
        problems.append(f"data.db has versions {sorted(applied - known)} with no migration file (renamed/removed migration?) -> `python seed.py`")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        problems.append(f"data.db integrity_check: {integrity}")
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    if broken:
        problems.append(f"data.db has dangling references (table, rowid, parent, fk): {broken[:5]}")
    conn.close()
    if pending or applied - known:
        return problems
    # rebuild from seed in a temp dir and compare
    tmp = tempfile.mkdtemp(prefix="devpy-seed-")
    try:
        spec = importlib.util.spec_from_file_location("seed_for_check", os.path.join(APP_DIR, "seed.py"))
        seed = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(io.StringIO()):
            spec.loader.exec_module(seed)
            rebuilt = os.path.join(tmp, "rebuilt.db")
            try:
                seed.build(rebuilt)
            except Exception as exc:  # noqa: BLE001 - report any failure of the rebuild
                problems.append(f"seed rebuild failed: {type(exc).__name__}: {exc}")
                return problems
        diff = diff_dumps(dump_db(DATA_DB, skip_applied_at=True), dump_db(rebuilt, skip_applied_at=True), detail=2)
        if diff:
            problems.append("data.db differs from a fresh rebuild (seed_data.json + all migrations); "
                            "rebuild side shown as the 'after' state:")
            problems.extend("   " + l for l in diff[:20])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return problems


def scan_contract(max_records=40):
    """Compare UI and API for every user. Returns (errors, warnings, stats); errors are 5xx answers."""
    warnings, errors, stats = [], [], {"requests": 0}
    copy = Copy()
    try:
        app = copy.app
        app.logger.disabled = True  # 5xx are reported below; `dev.py call` shows the traceback
        users = copy.users()
        collections = api_collections(app)
        actions = api_actions(app)
        pristine = copy.save_db()

        def req(method, path, user, **k):
            stats["requests"] += 1
            resp = copy.request(method, path, user, **k)
            if resp.status_code >= 500 and len(errors) < 10:
                errors.append(f"{method} {path} as {user} -> {resp.status_code} (unhandled exception; "
                              f"reproduce with `python dev.py call {method} {path} --as {user}`)")
            return resp

        # routes parity
        for coll in collections:
            if not has_route(app, f"/ui/{coll}", "GET"):
                warnings.append(f"no UI list route /ui/{coll}")
            if not has_route(app, f"/ui/{coll}/1", "GET"):
                warnings.append(f"no UI detail route /ui/{coll}/<id>")
        for coll, action in actions:
            if not has_route(app, f"/ui/{coll}/1/{action}", "POST"):
                warnings.append(f"API action {coll}.{action} has no UI form handler POST /ui/{coll}/<id>/{action}")

        readable = {}  # (user, coll) -> [records]
        for user in users:
            for coll in collections:
                r = req("GET", f"/api/{coll}", user)
                items = r.get_json()["items"] if r.status_code == 200 else []
                readable[(user, coll)] = items
                if has_route(app, f"/ui/{coll}", "GET"):
                    page = req("GET", f"/ui/{coll}", user)
                    rows = UiPage(page.get_data(as_text=True)).rows if page.status_code == 200 else None
                    ids = [i["id"] for i in items]
                    if rows != ids:
                        warnings.append(f"/ui/{coll} as {user}: rows {short(rows, 60)} != API ids {short(ids, 60)}")

        reader = max(users, key=lambda u: sum(len(readable[(u, c)]) for c in collections))
        # detail pages and filters (as the user who reads the most)
        for coll in collections:
            items = readable[(reader, coll)]
            missing, extra, differs = set(), set(), {}
            for item in items:
                if not has_route(app, f"/ui/{coll}/{item['id']}", "GET"):
                    break
                page = UiPage(req("GET", f"/ui/{coll}/{item['id']}", reader).get_data(as_text=True))
                api_fields = {k for k in item if k != "id"}
                missing |= api_fields - set(page.fields)
                extra |= set(page.fields) - set(item)
                for k in api_fields & set(page.fields):
                    if not isinstance(item[k], (list, dict)) and page.fields[k] != display(item[k]):
                        differs.setdefault(k, (item["id"], page.fields[k], display(item[k])))
            if missing:
                warnings.append(f"/ui/{coll}/<id>: no data-field for API field(s) {sorted(missing)}")
            if extra:
                warnings.append(f"/ui/{coll}/<id>: data-field(s) {sorted(extra)} are not API fields")
            for k, (rid, shown, api) in differs.items():
                warnings.append(f"/ui/{coll}/{rid} data-field {k!r} shows {shown!r}, API value {api!r}"
                                " (fine only if the spec asks for a different display)")
            if items:
                sample = items[len(items) // 2]
                for k, v in sample.items():
                    if isinstance(v, (list, dict)):
                        continue
                    text = "null" if v is None else display(v)
                    r = req("GET", f"/api/{coll}?{k}={quote(text)}", reader)
                    if r.status_code != 200:
                        warnings.append(f"filter ?{k}= on {coll} -> {r.status_code} (add {k!r} to the collection's *_FIELDS tuple?)")
                    elif sample["id"] not in [i["id"] for i in r.get_json()["items"]]:
                        warnings.append(f"filter ?{k}={text} on {coll} does not return record {sample['id']}")

        # action forms: shown on the detail page <=> the API does not answer 403/409 to {}
        mismatches = {}
        checked = 0
        by_collection = {}
        for coll, action in actions:
            by_collection.setdefault(coll, []).append(action)
        for coll, coll_actions in by_collection.items():
            if not has_route(app, f"/ui/{coll}/1", "GET"):
                continue
            for user in users:
                items = readable[(user, coll)]
                if len(items) > max_records:
                    step = len(items) / max_records
                    items = [items[int(i * step)] for i in range(max_records)]
                for item in items:
                    page = req("GET", f"/ui/{coll}/{item['id']}", user)
                    if page.status_code != 200:
                        continue
                    shown_actions = UiPage(page.get_data(as_text=True)).actions
                    for action in coll_actions:
                        shown = action in shown_actions
                        r = req("POST", f"/api/{coll}/{item['id']}/{action}", user, body={})
                        checked += 1
                        if r.status_code < 300:
                            copy.restore_db(pristine)
                        allowed = r.status_code not in (403, 409)
                        if shown != allowed:
                            msg = (r.get_json(silent=True) or {}).get("message", "")
                            kind = "form shown but API says" if shown else "form hidden but API says"
                            mismatches.setdefault((coll, action, kind), []).append(
                                f"{user} {coll}/{item['id']} -> {r.status_code} {short(msg, 70)}")
        for (coll, action, kind), cases in sorted(mismatches.items()):
            warnings.append(f"'{action}' form on /ui/{coll}/<id>: {kind} {len(cases)}x (with body {{}}): "
                            + "; ".join(cases[:3]))
        stats["action_checks"] = checked

        # deletes: no record may produce a 5xx (e.g. a new reference without a 409 check)
        for coll in collections:
            for item in readable[(reader, coll)]:
                if not has_route(app, f"/api/{coll}/{item['id']}", "DELETE"):
                    break
                r = req("DELETE", f"/api/{coll}/{item['id']}", reader)
                if r.status_code < 300:
                    copy.restore_db(pristine)

        # create forms: /ui/<coll>/new is 200 <=> POST /api/<coll> {} is not 403
        for coll in collections:
            if not has_route(app, f"/ui/{coll}/new", "GET"):
                continue
            sample_fields = set()
            for user in users:
                for item in readable[(user, coll)][:1]:
                    sample_fields |= set(item)
            bad = []
            for user in users:
                page = req("GET", f"/ui/{coll}/new", user)
                r = req("POST", f"/api/{coll}", user, body={})
                if r.status_code < 300:
                    copy.restore_db(pristine)
                if (page.status_code == 200) != (r.status_code != 403):
                    bad.append(f"{user}: page {page.status_code}, POST {{}} {r.status_code}")
                if page.status_code == 200 and sample_fields:
                    ui = UiPage(page.get_data(as_text=True))
                    if coll not in ui.creates:
                        warnings.append(f"/ui/{coll}/new as {user}: no <form data-create=\"{coll}\">")
                    unknown = [i for i in ui.inputs if i not in sample_fields]
                    if unknown:
                        warnings.append(f"/ui/{coll}/new inputs {unknown} are not fields of {coll}")
            if bad:
                warnings.append(f"/ui/{coll}/new vs POST /api/{coll}: " + "; ".join(bad[:4]))
    finally:
        copy.close()
    # de-duplicate, keep order
    seen, unique = set(), []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return errors, unique, stats


def cmd_check(args):
    take_snapshot(quiet=True, only_if_missing=True)
    started = time.time()
    out = []
    ok_tests, summary, fail_lines = run_tests(args.pytest_args, args.tests, args.full)
    out.append(("PASS " if ok_tests else "FAIL ") + summary)
    out.extend("  " + l for l in fail_lines)
    db_problems = check_database()
    if db_problems:
        out.append("FAIL data.db:")
        out.extend("  " + p for p in db_problems)
    else:
        out.append("PASS data.db: fully migrated, equals seed rebuild (seed_data.json + migrations), integrity/foreign keys ok")
    warnings, errors = [], []
    if not args.no_scan:
        errors, warnings, stats = scan_contract()
        if errors:
            out.append("FAIL server errors during the contract/UI scan:")
            out.extend("  " + e for e in errors)
        if warnings:
            out.append(f"WARN contract/UI scan: {len(warnings)} finding(s) ({stats['requests']} requests, every user):")
            out.extend("  - " + w for w in warnings[:40])
            if len(warnings) > 40:
                out.append(f"  ... {len(warnings) - 40} more")
        elif not errors:
            out.append(f"PASS contract/UI scan ({stats['requests']} requests, every user): UI lists = API lists, "
                       "detail pages show every API field, every field filters, action/create forms match API "
                       "permissions, no 5xx (incl. DELETE of every record)")
    ok = ok_tests and not db_problems and not errors
    verdict = ("CHECK PASSED" if ok else "CHECK FAILED") + (f" with {len(warnings)} scan warning(s) to review" if warnings else "")
    if args.pytest_args or args.tests or args.no_scan:
        verdict += "  (partial run: finish with a plain `python dev.py check`)"
    out.append(f"{verdict}  [{time.time() - started:.1f}s]")
    text = "\n".join(out)
    print(text)
    os.makedirs(DEV_DIR, exist_ok=True)
    with open(LAST_CHECK, "w", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f"  python dev.py check {' '.join(args.pytest_args + args.tests)}\n" + text + "\n")
    return 0 if ok else 1


# --- migrations --------------------------------------------------------------------------

MIGRATION_TEMPLATE = """-- {number}_{name}: <one line: what this migration does and why>
--
-- Runs inside one transaction with the schema_version row; do not add BEGIN/COMMIT.
-- Foreign keys are OFF while it runs and checked (PRAGMA foreign_key_check) before commit.
-- Data changes (backfills, fixed new records, renamed values) belong here, not in seed_data.json:
-- seed.py replays every migration over the baseline seed, so `python dev.py check` can verify
-- that data.db equals a rebuild.
--
-- Add a column (NOT NULL needs a DEFAULT; then backfill):
--   ALTER TABLE things ADD COLUMN flag INTEGER NOT NULL DEFAULT 0 CHECK (flag IN (0, 1));
--   UPDATE things SET flag = 1 WHERE ...;
--
-- Change a CHECK / drop or retype a column (rebuild the table; indexes must be recreated):
--   CREATE TABLE things_new (... full new definition ...);
--   INSERT INTO things_new (id, a, b) SELECT id, a, b FROM things;
--   DROP TABLE things;
--   ALTER TABLE things_new RENAME TO things;
--   CREATE INDEX things_a ON things (a);
--   -- keep the AUTOINCREMENT counter if rows were ever deleted:
--   -- UPDATE sqlite_sequence SET seq = <old seq> WHERE name = 'things';
--
-- New table with fixed ids: INSERT INTO t (id, ...) VALUES (1, ...), (2, ...);
--   (AUTOINCREMENT continues above the highest inserted id.)

"""


def cmd_new_migration(args):
    name = args.name.strip().lower()
    if not re.fullmatch(r"[a-z0-9_]+", name):
        sys.exit("NAME must match [a-z0-9_]+ (e.g. add_book_shelf)")
    numbers = [int(f[:4]) for f in os.listdir(MIGRATIONS_DIR) if re.match(r"^\d{4}_", f)]
    number = f"{max(numbers, default=0) + 1:04d}"
    path = os.path.join(MIGRATIONS_DIR, f"{number}_{name}.sql")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(MIGRATION_TEMPLATE.format(number=number, name=name))
    print(f"created {os.path.relpath(path, APP_DIR)}")
    print("next: write the SQL; `python dev.py call ...` already sees it (copies apply pending migrations);")
    print("      `python dev.py migrate` applies it to data.db; `python dev.py dbdiff` shows the data change.")


def cmd_migrate(args):
    import_package()
    db = importlib.import_module(PACKAGE + ".db")
    applied = db.migrate(DATA_DB)
    print("applied: " + (", ".join(applied) if applied else "nothing (data.db is up to date)"))
    if applied and os.path.exists(SNAPSHOT_DB):
        print("data changes since snapshot (python dev.py dbdiff for details):")
        for line in diff_dumps(dump_db(SNAPSHOT_DB, True), dump_db(DATA_DB, True), detail=0, ignore=("schema_version",)):
            print("  " + line)


# --- snapshot / dbdiff / notes ------------------------------------------------------------

def app_files():
    out = {}
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for name in sorted(files):
            if name.endswith((".pyc",)) or name == "CHANGE_NOTES.md":
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, APP_DIR)
            with open(path, "rb") as fh:
                data = fh.read()
            entry = {"sha": hashlib.sha256(data).hexdigest()}
            if rel != "data.db":
                try:
                    entry["text"] = data.decode("utf-8")
                except UnicodeDecodeError:
                    pass
            out[rel] = entry
    return out


def take_snapshot(quiet=False, only_if_missing=False):
    if only_if_missing and os.path.exists(SNAPSHOT_FILES):
        return
    os.makedirs(DEV_DIR, exist_ok=True)
    with open(SNAPSHOT_FILES, "w", encoding="utf-8") as fh:
        json.dump({"taken": time.strftime("%Y-%m-%d %H:%M:%S"), "files": app_files()}, fh)
    shutil.copyfile(DATA_DB, SNAPSHOT_DB)
    if not quiet or only_if_missing:
        print(f"snapshot saved ({os.path.relpath(DEV_DIR, APP_DIR)}/): `python dev.py notes` / `dbdiff` compare against it")


def cmd_snapshot(args):
    take_snapshot()


def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILES):
        sys.exit("no snapshot yet: run `python dev.py snapshot` before changing anything")
    with open(SNAPSHOT_FILES, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_dbdiff(args):
    load_snapshot()
    lines = diff_dumps(dump_db(SNAPSHOT_DB, True), dump_db(DATA_DB, True), detail=args.rows, ignore=("schema_version",))
    print("data.db vs snapshot: " + ("no changes" if not lines else ""))
    for line in lines:
        print("  " + line)


def cmd_notes(args):
    snap = load_snapshot()
    before, now = snap["files"], app_files()
    changed = []
    for rel in sorted(set(before) | set(now)):
        if rel not in now:
            changed.append(f"- `{rel}` (deleted)")
        elif rel not in before:
            n = len(now[rel].get("text", "").splitlines())
            changed.append(f"- `{rel}` (new, {n} lines)")
        elif before[rel]["sha"] != now[rel]["sha"]:
            if "text" in before[rel] and "text" in now[rel]:
                diff = list(difflib.unified_diff(before[rel]["text"].splitlines(), now[rel]["text"].splitlines(), lineterm="", n=0))
                plus = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
                minus = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
                changed.append(f"- `{rel}` (+{plus} -{minus})")
            else:
                changed.append(f"- `{rel}` (binary, changed)")
    migrations = []
    for rel in sorted(now):
        if rel.startswith(os.path.join(PACKAGE, "migrations")) and rel not in before:
            first = next((l[2:].strip() for l in now[rel].get("text", "").splitlines() if l.startswith("--")), "")
            first = re.sub(r"^\d{4}_[a-z0-9_]+:\s*", "", first)
            migrations.append(f"- `{os.path.basename(rel)}`: {first}")
    data_lines = diff_dumps(dump_db(SNAPSHOT_DB, True), dump_db(DATA_DB, True), detail=0, ignore=("schema_version",))
    check_text = "(not run yet: `python dev.py check`)"
    if os.path.exists(LAST_CHECK):
        newest_change = max((os.path.getmtime(os.path.join(APP_DIR, r)) for r in now), default=0)
        stale = os.path.getmtime(LAST_CHECK) < newest_change
        with open(LAST_CHECK, encoding="utf-8") as fh:
            check_text = fh.read().strip()
        if stale:
            check_text = "(files changed after this run; re-run `python dev.py check`)\n" + check_text
    doc = [
        "# Change notes", "",
        "**Interpretation.** TODO: what the request asks, in one paragraph; every ambiguity and the",
        "choice made (error precedence 401 > 404 > 403 > 409 > 400, what counts as derived/read-only, data policy).", "",
        "**Changes.**",
        *(changed or ["- (no file changes)"]), "",
        "**Migrations.**",
        *(migrations or ["- (none)"]), "",
        "**Data changes in data.db** (vs snapshot of " + snap["taken"] + ")",
        "```", *(data_lines or ["no changes"]), "```", "",
        "**Verification.**",
        "```", check_text, "```", "",
    ]
    path = os.path.join(APP_DIR, "CHANGE_NOTES.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(doc))
    print(f"wrote {os.path.relpath(path, APP_DIR)}: {len(changed)} changed files, {len(migrations)} new migrations, "
          f"{len(data_lines)} data-change lines. Fill in the Interpretation paragraph.")


# =========================================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(prog="python dev.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("overview", help="one-screen map of schema, routes, rules, users, samples")
    p = sub.add_parser("check", help="tests + data.db rebuild/migration checks + contract/UI scan")
    p.add_argument("--full", action="store_true", help="full tracebacks for failing tests")
    p.add_argument("--no-scan", action="store_true", help="skip the contract/UI scan")
    p.add_argument("-k", dest="k", help="only tests matching this pytest -k expression")
    p.add_argument("tests", nargs="*", help="test files/node ids to run instead of the whole tests/ directory")
    p = sub.add_parser("call", help="request(s) against a throwaway copy")
    p.add_argument("method", nargs="?")
    p.add_argument("path", nargs="?")
    p.add_argument("--as", dest="user")
    p.add_argument("--body", help="JSON body (POST/PATCH default to {})")
    p.add_argument("--form", action="append", help="form field k=v (for /ui form posts); repeatable")
    p.add_argument("--now", default=NOW)
    p.add_argument("--raw", action="store_true", help="print the raw response body")
    p.add_argument("--steps", nargs="+", help='"USER METHOD PATH [JSON]" requests run in order on one copy')
    p = sub.add_parser("new-migration", help="create the next numbered migration file")
    p.add_argument("name")
    sub.add_parser("migrate", help="apply pending migrations to data.db")
    sub.add_parser("snapshot", help="record files and data.db before a change")
    p = sub.add_parser("dbdiff", help="row-level diff of data.db against the snapshot")
    p.add_argument("--rows", type=int, default=5, help="example rows per table (default 5)")
    sub.add_parser("notes", help="write CHANGE_NOTES.md from the snapshot diff")
    args = parser.parse_args(argv)
    if args.command == "check":
        args.pytest_args = ["-k", args.k] if args.k else []
    handler = {"overview": cmd_overview, "check": cmd_check, "call": cmd_call,
               "new-migration": cmd_new_migration, "migrate": cmd_migrate, "snapshot": cmd_snapshot,
               "dbdiff": cmd_dbdiff, "notes": cmd_notes}[args.command]
    return handler(args) or 0


if __name__ == "__main__":
    if hasattr(__import__("signal"), "SIGPIPE"):  # `python dev.py ... | head` exits quietly
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    sys.exit(main())
