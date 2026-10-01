"""Private reference implementation core (author tooling only).

A tiny WSGI framework implementing CONTRACT.md. Each application subclasses RefApp.
Every mutating request runs against the live state; on any HttpError the state is
restored from a deep copy, so failed operations never leave a trace.
"""
import copy
import datetime as dt
import html
import json
import re
from urllib.parse import parse_qsl

CODES = {400: "validation", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 409: "conflict"}
REASONS = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request", 401: "Unauthorized",
           403: "Forbidden", 404: "Not Found", 409: "Conflict"}


class HttpError(Exception):
    def __init__(self, status, message="", fields=None):
        super().__init__(message)
        self.status = status
        self.message = message or CODES[status]
        self.fields = fields or {}


def fail(status, message="", fields=None):
    raise HttpError(status, message, fields)


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_text(v):
    return isinstance(v, str) and v.strip() != ""


def is_date(v):
    if not isinstance(v, str) or not DATE_RE.match(v):
        return False
    try:
        dt.date.fromisoformat(v)
        return True
    except ValueError:
        return False


def add_days(datestr, n):
    return (dt.date.fromisoformat(datestr) + dt.timedelta(days=n)).isoformat()


def r2(x):
    return round(x + 0.0, 2)


def matches(value, param):
    if value is None:
        return param == "null"
    if isinstance(value, bool):
        return param == ("true" if value else "false")
    if isinstance(value, (int, float)):
        try:
            return float(param) == float(value)
        except ValueError:
            return False
    if isinstance(value, list):
        return False
    return str(value) == param


def display(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


class RefApp:
    user_collection = None
    strict_filters = False

    def __init__(self, seed, features=()):
        self.features = list(features)
        self.state = {k: copy.deepcopy(v) for k, v in seed.items()}
        self.state.setdefault("_outbox", [])
        self.init_state()
        for f in self.features:
            m = getattr(self, "migrate_" + f, None)
            if m:
                m()

    def has(self, f):
        return f in self.features

    # ------------------------------------------------------------- hooks
    def init_state(self):
        pass

    def collections(self):
        raise NotImplementedError

    def actions(self, coll):
        return []

    def serialize(self, coll, rec, user):
        return dict(rec)

    def can_read(self, coll, rec, user):
        return True

    def create(self, coll, body, user):
        fail(403)

    def patch(self, coll, rec, body, user):
        fail(403)

    def delete(self, coll, rec, user):
        fail(403)

    def run_action(self, coll, rec, action, body, user):
        fail(404)

    def create_form(self, coll, user):
        """Return list of input names, or raise 403."""
        fail(403)

    def action_probe_body(self, coll, rec, action, user):
        return {}

    # ------------------------------------------------------------- helpers
    def recs(self, coll):
        return self.state[coll]

    def get(self, coll, rid):
        for r in self.state[coll]:
            if r["id"] == rid:
                return r
        return None

    def next_id(self, coll):
        return max([r["id"] for r in self.state[coll]] + [0]) + 1

    def emit(self, channel, payload):
        ob = self.state["_outbox"]
        ob.append({"id": len(ob) + 1, "channel": channel, "payload": payload, "created_at": self.now})

    @property
    def today(self):
        return self.now[:10]

    # ------------------------------------------------------------- WSGI
    def __call__(self, environ, start_response):
        status, body, ctype = self.handle(environ)
        hdrs = [("Content-Type", ctype)]
        start_response(f"{status} {REASONS.get(status, 'X')}", hdrs)
        return [body]

    def handle(self, environ):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "")
        query = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        self.now = environ.get("HTTP_X_NOW") or dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = environ["wsgi.input"].read(length) if length else b""
        saved = copy.deepcopy(self.state)
        try:
            username = environ.get("HTTP_X_USER")
            user = self.authenticate(username)
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 1 and parts[0] == "api":
                status, payload = self.api(method, parts[1:], query, raw, user)
                if status == 204:
                    return 204, b"", "application/json"
                return status, json.dumps(payload).encode(), "application/json"
            if len(parts) >= 1 and parts[0] == "ui":
                status, text = self.ui(parts[1:], user)
                return status, text.encode(), "text/html; charset=utf-8"
            fail(404)
        except HttpError as e:
            self.state = saved
            return e.status, json.dumps({"error": CODES[e.status], "message": e.message,
                                         "fields": e.fields}).encode(), "application/json"

    def authenticate(self, username):
        if hook := getattr(self, "authenticate_hook", None):
            r = hook(username)
            if r is not None:
                return r
        if not username:
            fail(401)
        for r in self.state[self.user_collection]:
            if r.get("username") == username:
                return r
        fail(401)

    def parse_body(self, raw):
        if not raw:
            return {}
        try:
            b = json.loads(raw)
        except ValueError:
            fail(400, "invalid json")
        if not isinstance(b, dict):
            fail(400, "body must be an object")
        return b

    def find(self, coll, sid):
        if coll not in self.collections():
            fail(404)
        try:
            rid = int(sid)
        except ValueError:
            fail(404)
        rec = self.get(coll, rid)
        if rec is None:
            fail(404)
        return rec

    def listing(self, coll, query, user):
        items = [self.serialize(coll, r, user) for r in sorted(self.state[coll], key=lambda r: r["id"])
                 if self.can_read(coll, r, user)]
        for k, v in query:
            if self.strict_filters:
                if not any(k in it for it in items) and k not in self.filter_fields(coll):
                    fail(400, f"unknown filter {k}")
            items = [it for it in items if k in it and matches(it[k], v)]
        return items

    def filter_fields(self, coll):
        return set()

    def api(self, method, parts, query, raw, user):
        if not parts:
            fail(404)
        coll = parts[0]
        if coll == "_outbox" and len(parts) == 1 and method == "GET":
            return 200, {"items": list(self.state["_outbox"])}
        if coll not in self.collections():
            fail(404)
        if len(parts) == 1:
            if method == "GET":
                return 200, {"items": self.listing(coll, query, user)}
            if method == "POST":
                body = self.parse_body(raw)
                rec = self.create(coll, body, user)
                return 201, self.serialize(coll, rec, user)
            fail(404)
        rec = self.find(coll, parts[1])
        if len(parts) == 2:
            if method == "GET":
                if not self.can_read(coll, rec, user):
                    fail(403)
                return 200, self.serialize(coll, rec, user)
            if method == "PATCH":
                body = self.parse_body(raw)
                rec = self.patch(coll, rec, body, user)
                return 200, self.serialize(coll, rec, user)
            if method == "DELETE":
                self.delete(coll, rec, user)
                return 204, None
            fail(404)
        if len(parts) == 3 and method == "POST":
            action = parts[2]
            if action not in self.actions(coll):
                fail(404)
            body = self.parse_body(raw)
            out = self.run_action(coll, rec, action, body, user)
            out_coll, out_rec = out if isinstance(out, tuple) else (coll, out)
            return 200, self.serialize(out_coll, self.get(out_coll, out_rec["id"]) or out_rec, user)
        fail(404)

    # ------------------------------------------------------------- UI
    def allowed_actions(self, coll, rec, user):
        allowed = []
        for a in self.actions(coll):
            saved = copy.deepcopy(self.state)
            saved_outbox_len = len(self.state["_outbox"])
            try:
                cur = self.get(coll, rec["id"])
                self.run_action(coll, cur, a, self.action_probe_body(coll, rec, a, user), user)
                ok = True
            except HttpError as e:
                ok = e.status == 400
            finally:
                self.state = saved
            if ok:
                allowed.append(a)
        return allowed

    def ui(self, parts, user):
        if not parts:
            fail(404)
        coll = parts[0]
        if coll not in self.collections():
            fail(404)
        if len(parts) == 1:
            rows = self.listing(coll, [], user)
            out = ["<html><body><table>"]
            for it in rows:
                out.append(f'<tr data-id="{it["id"]}"><td>{html.escape(display(it.get("id")))}</td></tr>')
            out.append("</table></body></html>")
            return 200, "".join(out)
        if parts[1] == "new" and len(parts) == 2:
            inputs = self.create_form(coll, user)
            out = [f'<html><body><form data-create="{coll}">']
            for n in inputs:
                out.append(f'<input name="{n}">')
            out.append("</form></body></html>")
            return 200, "".join(out)
        if len(parts) != 2:
            fail(404)
        rec = self.find(coll, parts[1])
        if not self.can_read(coll, rec, user):
            fail(403)
        data = self.serialize(coll, rec, user)
        out = ["<html><body>"]
        for k, v in data.items():
            out.append(f'<div data-field="{k}">{html.escape(display(v))}</div>')
        for a in self.allowed_actions(coll, rec, user):
            out.append(f'<form data-action="{a}"></form>')
        out.append("</body></html>")
        return 200, "".join(out)
