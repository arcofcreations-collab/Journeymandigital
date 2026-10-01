"""Contract-level test client used by every acceptance check.

Acceptance tests import only this module. They talk to an application instance through
the external contract (spec/CONTRACT.md) and never import implementation code.

    from accept_client import fresh_app
    app = fresh_app()                       # fresh copy of the instance named by $ACCEPT_TARGET
    r = app.post("/api/books/3/borrow", {}, user="chen", now="2026-03-01T10:00:00")
    assert r.status == 200 and r.json["status"] == "on_loan"

Defaults: user=None (no X-User header), now="2026-03-01T12:00:00".
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import uuid
from html.parser import HTMLParser
from urllib.parse import urlsplit

DEFAULT_NOW = "2026-03-01T12:00:00"


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.text = body.decode("utf-8", "replace")
        try:
            self.json = json.loads(self.text) if self.text.strip() else None
        except ValueError:
            self.json = None

    def __repr__(self):
        return f"<Response {self.status} {self.text[:200]!r}>"


class App:
    def __init__(self, wsgi, workdir):
        self.wsgi = wsgi
        self.workdir = workdir

    def request(self, method, path, body=None, user=None, now=DEFAULT_NOW, headers=None):
        parts = urlsplit(path)
        data = b"" if body is None else json.dumps(body).encode()
        environ = {
            "REQUEST_METHOD": method, "PATH_INFO": parts.path, "QUERY_STRING": parts.query,
            "SERVER_NAME": "test", "SERVER_PORT": "80", "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0), "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(data),
            "wsgi.errors": sys.stderr, "wsgi.multithread": False, "wsgi.multiprocess": False,
            "wsgi.run_once": False, "CONTENT_LENGTH": str(len(data)),
            "CONTENT_TYPE": "application/json" if body is not None else "",
        }
        if user is not None:
            environ["HTTP_X_USER"] = user
        if now is not None:
            environ["HTTP_X_NOW"] = now
        for k, v in (headers or {}).items():
            environ["HTTP_" + k.upper().replace("-", "_")] = v
        captured = {}

        def start_response(status, hdrs, exc_info=None):
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(hdrs)

        chunks = self.wsgi(environ, start_response)
        try:
            body_bytes = b"".join(chunks)
        finally:
            if hasattr(chunks, "close"):
                chunks.close()
        return Response(captured["status"], captured["headers"], body_bytes)

    def get(self, path, user=None, now=DEFAULT_NOW):
        return self.request("GET", path, None, user, now)

    def post(self, path, body=None, user=None, now=DEFAULT_NOW):
        return self.request("POST", path, {} if body is None else body, user, now)

    def patch(self, path, body=None, user=None, now=DEFAULT_NOW):
        return self.request("PATCH", path, {} if body is None else body, user, now)

    def delete(self, path, user=None, now=DEFAULT_NOW):
        return self.request("DELETE", path, None, user, now)


def fresh_app(target=None):
    """Copy the application instance to a temporary directory and load it."""
    src = os.path.abspath(target or os.environ["ACCEPT_TARGET"])
    work = os.path.join(tempfile.mkdtemp(prefix="accept-"), "app")
    shutil.copytree(src, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    spec = importlib.util.spec_from_file_location(f"app_entry_{uuid.uuid4().hex}", os.path.join(work, "app_entry.py"))
    mod = importlib.util.module_from_spec(spec)
    old = os.getcwd()
    sys.path.insert(0, work)
    try:
        os.chdir(work)
        spec.loader.exec_module(mod)
        wsgi = mod.create_app()
    finally:
        os.chdir(old)
        sys.path.remove(work)
    return App(wsgi, work)


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.fields, self.actions, self.inputs, self.creates = [], {}, [], [], []
        self._field = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and "data-id" in a:
            self.rows.append(int(a["data-id"]))
        if "data-field" in a:
            self._field = a["data-field"]
            self._buf = []
        if tag == "form" and "data-action" in a:
            self.actions.append(a["data-action"])
        if tag == "form" and "data-create" in a:
            self.creates.append(a["data-create"])
        if tag in ("input", "select", "textarea") and a.get("name"):
            self.inputs.append(a["name"])

    def handle_data(self, data):
        if self._field is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._field is not None:
            self.fields[self._field] = "".join(self._buf).strip()
            self._field = None


def parse_ui(html):
    """Return an object with .rows (ids), .fields {name: text}, .actions, .inputs, .creates."""
    p = _Collect()
    p.feed(html)
    return p
