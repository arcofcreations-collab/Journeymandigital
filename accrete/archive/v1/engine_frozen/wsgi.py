"""WSGI adapter: serves an application instance directory through the external contract."""
from __future__ import annotations

import json
import threading
from urllib.parse import parse_qsl

from . import runtime as R
from . import ui
from .store import Store

READ_LOG = True  # record reads too: they make the replay corpus richer


def make_app(directory):
    store = Store(directory)
    model, world = store.load()
    if model is None:
        raise RuntimeError(f"{directory} has no application model; run `accrete apply` first")
    lock = threading.Lock()

    def app(environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "/")
        query = dict(parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True))
        user = environ.get("HTTP_X_USER") or query.pop("as", None)
        now_raw = environ.get("HTTP_X_NOW") or query.pop("now", None)
        now = R.parse_now(now_raw)
        body = None
        if method in ("POST", "PATCH", "PUT"):
            try:
                length = int(environ.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = 0
            raw = environ["wsgi.input"].read(length) if length else b""
            if raw.strip():
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = "__invalid__"
            else:
                body = {}
        with lock:
            if path.startswith("/ui/") and method == "GET":
                status, html = ui.handle(model, world, path, user, now)
                payload = html.encode()
                ctype = "text/html; charset=utf-8"
            else:
                if body == "__invalid__":
                    status, out = 400, {"error": "validation", "message": "invalid JSON", "fields": {}}
                    journal, mark = [], len(world["outbox"])
                else:
                    status, out, journal, mark = _run(model, world, method, path, query, body, user, now)
                if journal or len(world["outbox"]) > mark:
                    store.save_changes(model, world, journal, mark)
                if path.startswith("/api/") and (READ_LOG or method != "GET"):
                    store.record_request({"method": method, "path": path, "query": query, "body": body,
                                          "user": user, "now": now.isoformat(), "status": status, "response": out})
                payload = b"" if out is None else json.dumps(out).encode()
                ctype = "application/json"
        reason = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request", 401: "Unauthorized",
                  403: "Forbidden", 404: "Not Found", 409: "Conflict", 500: "Internal Server Error"}.get(status, "")
        start_response(f"{status} {reason}", [("Content-Type", ctype), ("Content-Length", str(len(payload)))])
        return [payload]

    app.store = store
    return app


def _run(model, world, method, path, query, body, user, now):
    """Run a request and report what it changed (for incremental persistence)."""
    status, out, ctx = R.handle_full(model, world, method, path, query, body, user, now)
    return status, out, ctx.journal, ctx.outbox_mark
