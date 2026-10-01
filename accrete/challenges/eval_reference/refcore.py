"""Tiny reference framework used only by the challenge author to validate hidden tests.

Not part of any deliverable for implementers.
"""
import html
import json
import os
from datetime import datetime, date, timedelta
from urllib.parse import parse_qsl

FMT = "%Y-%m-%dT%H:%M:%S"


class HttpError(Exception):
    CODES = {400: "validation", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict"}

    def __init__(self, status, message="", fields=None):
        super().__init__(message)
        self.status = status
        self.message = message or self.CODES[status]
        self.fields = fields or {}


def E400(msg="invalid", field=None):
    return HttpError(400, msg, {field: msg} if field else {})


def nonempty(v):
    return isinstance(v, str) and v.strip() != ""


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_dt(s):
    return datetime.strptime(s, FMT)


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def valid_date(s):
    try:
        parse_date(s)
        return isinstance(s, str) and len(s) == 10
    except Exception:
        return False


class Ctx:
    def __init__(self, user, now):
        self.user = user
        self.now = now

    @property
    def now_s(self):
        return self.now.strftime(FMT)

    @property
    def today(self):
        return self.now.date()


class Collection:
    name = None
    fields = ()          # all output fields (stored + derived), excluding id
    stored = ()          # stored fields
    create_fields = ()   # fields settable on create (for UI form)

    def __init__(self, app):
        self.app = app

    # hooks
    def derive(self, ctx, rec):
        return {}

    def can_read(self, ctx, rec):
        return True

    def visible(self, ctx, rec, out):
        return out

    def create(self, ctx, body):
        raise HttpError(403)

    def patch(self, ctx, rec, body):
        raise HttpError(403)

    def delete(self, ctx, rec):
        raise HttpError(403)

    def actions(self):
        return {}

    def ui_create_fields(self, ctx):
        """Return list of input names or raise 403."""
        raise HttpError(403)

    def ui_actions(self, ctx, rec):
        out = []
        for name, (perm, state, _run) in self.actions().items():
            try:
                perm(ctx, rec, None)
                state(ctx, rec, None)
            except HttpError:
                continue
            out.append(name)
        return out


class App:
    collections = {}

    def __init__(self, workdir):
        self.workdir = workdir
        self.path = os.path.join(workdir, "data.json")
        with open(self.path) as fh:
            self.db = json.load(fh)
        self.db.setdefault("_outbox", [])
        self.cols = {name: cls(self) for name, cls in self.collections.items()}

    # ---- storage helpers
    def recs(self, col):
        return self.db[col]

    def get(self, col, rid):
        for r in self.db[col]:
            if r["id"] == rid:
                return r
        return None

    def next_id(self, col):
        key = "_next_" + col
        cur = self.db.get(key)
        if cur is None:
            cur = max([r["id"] for r in self.db[col]] + [0]) + 1
        self.db[key] = cur + 1
        return cur

    def insert(self, col, rec):
        rec = dict(rec)
        rec["id"] = self.next_id(col)
        self.db[col].append(rec)
        self.db[col].sort(key=lambda r: r["id"])
        return rec

    def remove(self, col, rid):
        self.db[col] = [r for r in self.db[col] if r["id"] != rid]

    def emit(self, ctx, channel, payload):
        ob = self.db["_outbox"]
        ob.append({"id": (max([m["id"] for m in ob]) + 1) if ob else 1, "channel": channel,
                   "payload": payload, "created_at": ctx.now_s})

    def save(self):
        with open(self.path, "w") as fh:
            json.dump(self.db, fh)

    def user_by_name(self, username):
        raise NotImplementedError

    # ---- output
    def out(self, ctx, col, rec):
        c = self.cols[col]
        o = {"id": rec["id"]}
        for f in c.stored:
            o[f] = rec.get(f)
        o.update(c.derive(ctx, rec))
        return c.visible(ctx, rec, o)

    # ---- WSGI
    def __call__(self, environ, start_response):
        try:
            status, body, ctype = self.dispatch(environ)
        except HttpError as e:
            status, ctype = e.status, "application/json"
            body = json.dumps({"error": HttpError.CODES[e.status], "message": e.message, "fields": e.fields})
        reason = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request", 401: "Unauthorized",
                  403: "Forbidden", 404: "Not Found", 409: "Conflict"}[status]
        start_response(f"{status} {reason}", [("Content-Type", ctype)])
        return [b"" if body is None else body.encode()]

    def dispatch(self, environ):
        method = environ["REQUEST_METHOD"]
        path = environ["PATH_INFO"]
        qs = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        username = environ.get("HTTP_X_USER")
        user = self.user_by_name(username) if username else None
        if user is None:
            raise HttpError(401)
        nows = environ.get("HTTP_X_NOW")
        now = parse_dt(nows) if nows else datetime.utcnow().replace(microsecond=0)
        ctx = Ctx(user, now)
        parts = [p for p in path.split("/") if p]
        body = None
        if method in ("POST", "PATCH"):
            n = int(environ.get("CONTENT_LENGTH") or 0)
            raw = environ["wsgi.input"].read(n) if n else b""
            try:
                body = json.loads(raw) if raw.strip() else {}
            except ValueError:
                raise E400("invalid json")
            if not isinstance(body, dict):
                raise E400("body must be an object")
        if parts and parts[0] == "api":
            return self.api(ctx, method, parts[1:], qs, body)
        if parts and parts[0] == "ui":
            return self.ui(ctx, method, parts[1:], qs)
        raise HttpError(404)

    def _col(self, name):
        if name not in self.cols:
            raise HttpError(404)
        return self.cols[name]

    def _rec(self, col, rid):
        try:
            rid = int(rid)
        except ValueError:
            raise HttpError(404)
        r = self.get(col, rid)
        if r is None:
            raise HttpError(404)
        return r

    def readable(self, ctx, colname, qs=()):
        c = self._col(colname)
        items = []
        for r in self.db[colname]:
            if c.can_read(ctx, r):
                items.append(self.out(ctx, colname, r))
        allf = set(("id",) + tuple(c.fields))
        for k, v in qs:
            if k not in allf:
                raise E400("unknown filter", k)
        for k, v in qs:
            items = [i for i in items if k in i and self.match(i[k], v)]
        return items

    @staticmethod
    def match(val, s):
        if val is None:
            return s == "null"
        if isinstance(val, bool):
            return s == ("true" if val else "false")
        if isinstance(val, (int, float)):
            try:
                return float(s) == float(val)
            except ValueError:
                return False
        return str(val) == s

    def api(self, ctx, method, parts, qs, body):
        if not parts:
            raise HttpError(404)
        if parts[0] == "_outbox" and len(parts) == 1 and method == "GET":
            return 200, json.dumps({"items": self.db["_outbox"]}), "application/json"
        c = self._col(parts[0])
        name = parts[0]
        if len(parts) == 1:
            if method == "GET":
                return 200, json.dumps({"items": self.readable(ctx, name, qs)}), "application/json"
            if method == "POST":
                rec = c.create(ctx, body)
                self.save()
                return 201, json.dumps(self.out(ctx, name, rec)), "application/json"
            raise HttpError(404)
        rec = self._rec(name, parts[1])
        if len(parts) == 2:
            if method == "GET":
                if not c.can_read(ctx, rec):
                    raise HttpError(403)
                return 200, json.dumps(self.out(ctx, name, rec)), "application/json"
            if method == "PATCH":
                rec = c.patch(ctx, rec, body)
                self.save()
                return 200, json.dumps(self.out(ctx, name, rec)), "application/json"
            if method == "DELETE":
                c.delete(ctx, rec)
                self.save()
                return 204, None, "application/json"
            raise HttpError(404)
        if len(parts) == 3 and method == "POST":
            acts = c.actions()
            if parts[2] not in acts:
                raise HttpError(404)
            perm, state, run = acts[parts[2]]
            perm(ctx, rec, body)
            state(ctx, rec, body)
            snapshot = json.dumps(self.db)
            try:
                res = run(ctx, rec, body)
            except HttpError:
                self.db = json.loads(snapshot)
                raise
            self.save()
            col_out, rec_out = res if isinstance(res, tuple) else (name, res)
            return 200, json.dumps(self.out(ctx, col_out, rec_out)), "application/json"
        raise HttpError(404)

    def ui(self, ctx, method, parts, qs):
        if method != "GET" or not parts:
            raise HttpError(404)
        c = self._col(parts[0])
        name = parts[0]
        h = ["<html><body>"]
        if len(parts) == 1:
            h.append("<table>")
            for i in self.readable(ctx, name, qs):
                h.append(f'<tr data-id="{i["id"]}"><td>{html.escape(str(i))}</td></tr>')
            h.append("</table>")
        elif parts[1] == "new" and len(parts) == 2:
            inputs = c.ui_create_fields(ctx)
            h.append(f'<form data-create="{name}">')
            for f in inputs:
                h.append(f'<input name="{f}">')
            h.append("</form>")
        elif len(parts) == 2:
            rec = self._rec(name, parts[1])
            if not c.can_read(ctx, rec):
                raise HttpError(403)
            o = self.out(ctx, name, rec)
            for k, v in o.items():
                if k == "id":
                    continue
                txt = "" if v is None else (json.dumps(v) if isinstance(v, bool) else str(v))
                h.append(f'<div data-field="{k}">{html.escape(txt)}</div>')
            for a in c.ui_actions(ctx, rec):
                h.append(f'<form data-action="{a}"></form>')
        else:
            raise HttpError(404)
        h.append("</body></html>")
        return 200, "".join(h), "text/html"
