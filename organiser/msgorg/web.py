"""Local browser interface (127.0.0.1 only; standard library only).

    python -m msgorg.web [--db PATH] [--port 8765]     then open http://127.0.0.1:8765
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from . import app as A
from . import store as S

DB = os.environ.get("MSGORG_DB", os.path.expanduser("~/.msgorg/archive.db"))
STATUSES = ["requested", "proposed", "stated", "confirmed", "declined", "cancelled", "rescheduled", "uncertain", "taken"]
CSS = """body{font:15px/1.45 system-ui,sans-serif;margin:0;color:#1d1d1f;background:#fafafa}
nav{background:#1f3a5f;padding:8px 16px}nav a{color:#fff;margin-right:16px;text-decoration:none}
main{max-width:1000px;margin:0 auto;padding:16px}.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:10px 14px;margin:10px 0}
.msg{padding:4px 8px;margin:3px 0;border-radius:6px;max-width:80%}.sent{background:#dcecff;margin-left:auto}.received{background:#eee}
.hl{outline:2px solid #e8a400}.st{font-weight:600;padding:1px 6px;border-radius:4px;background:#eee}
.st-confirmed{background:#cdeccd}.st-declined,.st-cancelled{background:#f5d0d0}.st-proposed,.st-uncertain,.st-requested,.st-stated{background:#fbeec2}
.st-rescheduled{background:#dcd6f5}small,.muted{color:#666}input,select{margin:2px}table{border-collapse:collapse}td,th{padding:3px 8px;border-bottom:1px solid #eee;text-align:left}
blockquote{margin:4px 0;padding:2px 8px;border-left:3px solid #bbb;background:#f6f6f6}"""


def e(x):
    return html.escape("" if x is None else str(x))


def t(ms):
    return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def page(title, body):
    nav = "".join(f'<a href="{h}">{n}</a>' for h, n in [("/", "Overview"), ("/import", "Import"), ("/contacts", "Contacts & jobs"),
                                                          ("/search", "Search"), ("/absences", "Absences"), ("/delete", "Delete data")])
    return f"<!doctype html><meta charset=utf-8><title>{e(title)}</title><style>{CSS}</style><nav>{nav}</nav><main><h2>{e(title)}</h2>{body}</main>"


class H(BaseHTTPRequestHandler):
    db_path = DB

    def log_message(self, *a):  # no request logging: URLs can contain search text
        pass

    def db(self):
        return S.open_db(self.db_path)

    def send(self, body, ctype="text/html; charset=utf-8", code=200, extra=()):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def form(self):
        n = int(self.headers.get("Content-Length") or 0)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items() if v and v[0] != ""}
        r = {"/": self.overview, "/import": self.import_page, "/contacts": self.contacts, "/search": self.search,
             "/absences": self.absences, "/export": self.export, "/delete": self.delete_page}.get(u.path)
        if u.path.startswith("/c/"):
            return self.conversation(int(u.path[3:]), q)
        if not r:
            return self.send(page("Not found", ""), code=404)
        return r(q)

    def overview(self, q):
        c = S.coverage(self.db())
        rows = "".join(f"<tr><td>{e(i['id'])}</td><td>{e(i['file'])}</td><td>{e(i['started'])}</td><td>{e(i['declared_count'])}</td>"
                       f"<td>{e(i['parsed'])}</td><td>{e(i['added'])}</td><td>{e(i['duplicates'])}</td><td>{e(i['errors'])}</td></tr>" for i in c["imports"])
        gaps = "".join(f"<li>{e(g)}</li>" for g in c["known_gaps"])
        body = (f"<div class=card><b>{c['messages'] or 0}</b> messages ({c['sms'] or 0} SMS, {c['mms'] or 0} MMS, of which "
                f"{c['rcs_like'] or 0} look like RCS) from <b>{c['contacts'] or 0}</b> contacts, {e(c['first'])} to {e(c['last'])}.</div>"
                f"<div class=card><b>Coverage limits</b><ul>{gaps}</ul></div>"
                f"<div class=card><b>Imports</b><table><tr><th>#</th><th>file</th><th>when</th><th>declared</th><th>parsed</th>"
                f"<th>added</th><th>duplicates</th><th>errors</th></tr>{rows}</table></div>")
        self.send(page("Overview", body))

    def import_page(self, q):
        msg = f"<div class=card>{e(q['done'])}</div>" if "done" in q else ""
        body = msg + """<div class=card><ol><li>On the phone: SMS Backup &amp; Restore &rarr; Back up &rarr; Messages &rarr; save to the phone's local storage.</li>
<li>Copy the <code>sms-*.xml</code> file to this computer over USB (File transfer).</li><li>Choose the file below and import. Importing the same file again adds nothing twice.</li></ol>
<input type=file id=f accept=".xml"> <label><input type=checkbox id=mf> dates in messages are month/day (US)</label> <button onclick="go()">Import</button> <span id=s></span></div>
<script>async function go(){const f=document.getElementById('f').files[0];if(!f)return;document.getElementById('s').textContent='importing...';
const r=await fetch('/import?mf='+(document.getElementById('mf').checked?1:0),{method:'POST',body:f});const t=await r.text();location='/import?done='+encodeURIComponent(t);}</script>"""
        self.send(page("Import from Android backup", body))

    def contacts(self, q):
        db = self.db()
        rows = "".join(
            f"<tr><td><a href='/c/{c['id']}'>{e(c['display'] or c['address_key'])}</a></td><td>{c['n']}</td><td>{e(c['last_ms'] and t(c['last_ms']))}</td>"
            f"<td>{e(c['jobs'] or '')}</td><td><form method=post action=/job style=display:inline><input type=hidden name=contact value='{c['id']}'>"
            f"<input name=job placeholder='job label' size=12 required><button>add</button></form>"
            + "".join(f"<form method=post action=/job style=display:inline><input type=hidden name=contact value='{c['id']}'><input type=hidden name=job value='{e(j)}'>"
                      f"<input type=hidden name=remove value=1><button title='remove label'>&times; {e(j)}</button></form>" for j in (c['jobs'] or '').split(',') if j)
            + "</td></tr>" for c in A.contacts(db))
        self.send(page("Contacts and job labels", "<p class=muted>Job labels mark a contact as a client or employer. "
                       "Absence findings for labelled contacts count as work context.</p>"
                       f"<table><tr><th>contact</th><th>messages</th><th>last</th><th>jobs</th><th>edit</th></tr>{rows}</table>"))

    def conversation(self, cid, q):
        db = self.db()
        c = db.execute("select * from contacts where id=?", (cid,)).fetchone()
        if not c:
            return self.send(page("Not found", ""), code=404)
        hl = int(q.get("m", 0))
        rows = db.execute("select * from messages where contact_id=? order by date_ms, id", (cid,)).fetchall()
        body = "".join(f"<div id='m{m['id']}' class='msg {m['direction']} {'hl' if m['id']==hl else ''}'><small>#{m['id']} {t(m['date_ms'])} "
                       f"{'me' if m['direction']=='sent' else e(c['display'])} &middot; {m['kind'].upper()}{' (RCS-like)' if m['rcs_like'] else ''}"
                       f"{' &middot; ' + e(m['direction']) if m['direction'] not in ('sent','received') else ''}</small><br>{e(m['body'])}"
                       + (f"<br><small>attachments: {e(', '.join(a.get('ct','') for a in json.loads(m['attachments'])))}</small>" if m['attachments'] != '[]' else "")
                       + "</div>" for m in rows)
        js = f"<script>document.getElementById('m{hl}')&&document.getElementById('m{hl}').scrollIntoView({{block:'center'}})</script>" if hl else ""
        self.send(page(f"Conversation with {c['display']}", f"<p class=muted>{len(rows)} messages, original text as imported.</p>{body}{js}"))

    def _search_form(self, q, extra=""):
        def i(n, p, typ="text"):
            return f"<input type={typ} name={n} placeholder='{p}' value='{e(q.get(n, ''))}'>"
        d = q.get("direction", "")
        return (f"<form class=card>{i('text','words')}{i('contact','contact')}{i('job','job label')} from {i('start','','date')} to {i('end','','date')}"
                f"<select name=direction><option value=''>sent+received</option><option value=sent {'selected' if d=='sent' else ''}>sent</option>"
                f"<option value=received {'selected' if d=='received' else ''}>received</option></select>{extra}<button>Go</button></form>")

    def search(self, q):
        res = A.search(self.db(), q.get("text"), q.get("contact"), q.get("start"), q.get("end"), q.get("job"), q.get("direction")) if q else []
        rows = "".join(f"<div class=card><small>{t(m['date_ms'])} &middot; <a href='/c/{m['contact_id']}?m={m['id']}#m{m['id']}'>{e(m['display'])}</a>"
                       f" &middot; {e(m['direction'])}</small><br>{e(m['body'])}</div>" for m in res)
        self.send(page("Search", self._search_form(q) + (f"<p>{len(res)} messages</p>" if q else "") + rows))

    def absences(self, q):
        ctxs = {"work": ("work",), "all": None, "personal": ("personal",)}.get(q.get("ctx", "default"), ("work", "unknown"))
        sts = [q["status"]] if q.get("status") else None
        fs = A.absences(self.db(), q.get("contact"), q.get("job"), q.get("start"), q.get("end"), sts, contexts=ctxs,
                        include_rejected=q.get("ctx") == "all")
        extra = ("<select name=status><option value=''>any status</option>" + "".join(f"<option {'selected' if q.get('status')==s else ''}>{s}</option>" for s in STATUSES)
                 + "</select><select name=ctx>" + "".join(f"<option value={v} {'selected' if q.get('ctx',v if v=='default' else '')==v else ''}>{n}</option>"
                 for v, n in [("default", "work + unclear"), ("work", "work only"), ("personal", "personal only"), ("all", "everything incl. rejected")]) + "</select>")
        out, month = [], None
        for f in fs:
            mo = f["work_start"][:7]
            if mo != month:
                out.append(f"<h3>{mo}</h3>")
                month = mo
            rng = f["work_start"] + ("" if f["work_end"] == f["work_start"] else f" &ndash; {f['work_end']}")
            ev = "".join(f"<blockquote><small>{e(x['at'])} &middot; {e(x['direction'])} &middot; {e(x['role'])} &middot; "
                         f"<a href='/c/{f['contact_id']}?m={x['msg']}#m{x['msg']}'>open in conversation</a></small><br>{e(x['excerpt'])}</blockquote>" for x in f["evidence"])
            rv = "".join(f"<blockquote><small>later: {e(x['role'])} &middot; {e(x['at'])} &middot; <a href='/c/{f['contact_id']}?m={x['msg']}#m{x['msg']}'>open</a></small><br>{e(x['excerpt'])}</blockquote>" for x in f["revisions"])
            notes = "".join(f"<li>{e(n)}</li>" for n in (f.get("notes") or []))
            corr = "".join(f"<li>you set {e(c['field'])} = {e(c['value'])} {('(' + e(c['note']) + ')') if c['note'] else ''} on {e(c['created'])}</li>" for c in f["corrections"])
            fix = (f"<form method=post action=/correct><input type=hidden name=id value={f['id']}><input type=hidden name=back value='{e(self.path)}'>"
                   "<select name=field><option value=status>status</option><option value=context>context</option><option value=work_date>work date (YYYY-MM-DD or A..B)</option>"
                   "<option value=job>job</option><option value=not_absence>not an absence</option></select><input name=value placeholder='new value' required>"
                   "<input name=note placeholder='note (optional)'><button>Correct</button></form>")
            out.append(f"<div class=card><b>{rng}</b> &middot; {e(f['display'])}{(' (' + e(f['jobs']) + ')') if f.get('jobs') else ''} &middot; "
                       f"<span class='st st-{e(f['status'])}'>{e(f['status'])}</span>{' &middot; corrected' if f['corrected'] else ''}"
                       f"<br><small>sent {e(f['sent_at'])} &middot; date from: {e(f['date_basis'])} &middot; context: {e(f.get('context'))} ({e(f.get('context_reason'))})"
                       f"{' &middot; rescheduled to ' + e(' – '.join(f['rescheduled_to'])) if f.get('rescheduled_to') else ''}"
                       f" &middot; actually taken: {e(f['actually_taken'])}</small>"
                       f"{ev}{rv}{'<ul>' + notes + '</ul>' if notes else ''}{'<ul>' + corr + '</ul>' if corr else ''}<details><summary>correct this</summary>{fix}</details></div>")
        qs = "&".join(f"{k}={quote(v)}" for k, v in q.items())
        body = (self._search_form(q, extra).replace("name=text", "name=_unused").replace("name=direction", "name=_d")
                + f"<p>{len(fs)} findings &middot; export <a href='/export?fmt=md&{qs}'>Markdown</a> | <a href='/export?fmt=csv&{qs}'>CSV</a></p>"
                "<p class=muted>Statuses say what the messages establish. Tentative messages are never shown as confirmed; whether you actually took a day off is not asserted.</p>"
                + "".join(out))
        self.send(page("Work absences", body))

    def export(self, q):
        ctxs = {"work": ("work",), "all": None, "personal": ("personal",)}.get(q.get("ctx", "default"), ("work", "unknown"))
        fs = A.absences(self.db(), q.get("contact"), q.get("job"), q.get("start"), q.get("end"),
                        [q["status"]] if q.get("status") else None, contexts=ctxs)
        fmt = q.get("fmt", "md")
        self.send(A.export(fs, fmt), "text/csv; charset=utf-8" if fmt == "csv" else "text/markdown; charset=utf-8",
                  extra=[("Content-Disposition", f"attachment; filename=absences.{fmt}")])

    def delete_page(self, q):
        self.send(page("Delete imported data", "<div class=card>This deletes the local archive, its search index, all findings and your corrections. "
                       "Messages on your phone are not affected.<form method=post action=/delete><label><input type=checkbox name=confirm value=yes required> "
                       "I understand</label> <button>Delete everything</button></form></div>"))

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        u = urlparse(self.path)
        if self.headers.get("Origin") and not self.headers["Origin"].startswith(("http://127.0.0.1", "http://localhost")):
            return self.send("cross-origin request refused", "text/plain", 403)
        if u.path == "/import":
            n = int(self.headers.get("Content-Length") or 0)
            fd, tmp = tempfile.mkstemp(suffix=".xml")
            with os.fdopen(fd, "wb") as fh:
                fh.write(self.rfile.read(n))
            try:
                db = self.db()
                r = S.import_file(db, tmp)
                A.recompute_absences(db, day_first=parse_qs(u.query).get("mf", ["0"])[0] != "1")
                txt = (f"parsed {r['parsed']} (backup declares {r['declared']}), added {r['added']}, duplicates skipped {r['duplicates']}, "
                       f"errors {r['errors']}; SMS {r['sms']}, MMS {r['mms']} (RCS-like {r['rcs_like']})")
            except Exception as exc:  # noqa: BLE001
                txt = f"import failed: {type(exc).__name__}: {exc}"
            finally:
                os.remove(tmp)  # the uploaded copy is not kept
            return self.send(txt, "text/plain")
        f = self.form()
        db = self.db()
        if u.path == "/job":
            (A.unset_job if f.get("remove") else A.set_job)(db, f["contact"], f["job"])
            A.recompute_absences(db)
            return self.redirect("/contacts")
        if u.path == "/correct":
            A.correct(db, int(f["id"]), f["field"], f["value"], f.get("note", ""))
            return self.redirect(f.get("back") or "/absences")
        if u.path == "/delete" and f.get("confirm") == "yes":
            db.close()
            S.delete_all(self.db_path)
            return self.redirect("/")
        self.send(page("Not found", ""), code=404)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DB)
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    H.db_path = a.db
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"organiser at http://127.0.0.1:{a.port} (local only; data: {a.db})")
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
