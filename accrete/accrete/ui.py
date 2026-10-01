"""Generic HTML interface derived from the model (no per-application templates)."""
from __future__ import annotations

import html

from . import model as M
from . import runtime as R

STYLE = """<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:960px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:.3rem .5rem;text-align:left}
form{margin:.6rem 0;padding:.6rem;border:1px solid #ddd;border-radius:4px}label{display:block;margin:.2rem 0}
.err{color:#b42318}nav a{margin-right:1rem}</style>"""


def esc(v):
    return html.escape("" if v is None else str(v))


def page(title, body, ctx):
    nav = " ".join(f'<a href="/ui/{esc(e["name"])}">{esc(e["name"])}</a>' for e in ctx.model["entities"].values()
                   if R.can_read_any(ctx, e))
    user = esc(ctx.user_name or "anonymous")
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>{STYLE}</head>"
            f"<body><nav>{nav}</nav><p>Signed in as {user}</p><h1>{esc(title)}</h1>{body}</body></html>")


def _input(name, f, value=None):
    t = f.get("type", "text")
    if t == "enum":
        opts = "".join(f'<option{" selected" if v == value else ""}>{esc(v)}</option>' for v in f.get("values", []))
        return f'<label>{esc(name)} <select name="{esc(name)}">{opts}</select></label>'
    if t == "bool":
        return f'<label>{esc(name)} <input type="checkbox" name="{esc(name)}"></label>'
    kind = {"int": "number", "number": "number", "date": "date", "datetime": "datetime-local"}.get(t, "text")
    return f'<label>{esc(name)} <input type="{kind}" name="{esc(name)}" value="{esc(value)}"></label>'


def ui_list(ctx, coll):
    R._require_user(ctx)
    ent = R._entity_or_404(ctx, coll)
    status, body = R.op_list(ctx, coll, {})
    names = [f["name"] for f in M.ordered_fields(ent)]
    head = "".join(f"<th>{esc(n)}</th>" for n in ["id"] + names)
    rows = []
    for item in body["items"]:
        cells = "".join(f"<td>{esc(item.get(n))}</td>" for n in names)
        rows.append(f'<tr data-id="{item["id"]}"><td><a href="/ui/{esc(coll)}/{item["id"]}">{item["id"]}</a></td>{cells}</tr>')
    new = f'<p><a href="/ui/{esc(coll)}/new">New</a></p>'
    return 200, page(coll, f"{new}<table><tr>{head}</tr>{''.join(rows)}</table>", ctx)


def ui_detail(ctx, coll, rid):
    status, item = R.op_get(ctx, coll, rid)
    ent = M.entity(ctx.model, coll)
    rid = item["id"]
    rec = R.Rec(ctx, ent, rid)
    fields = "".join(f'<tr><th>{esc(k)}</th><td data-field="{esc(k)}">{esc(v)}</td></tr>'
                     for k, v in item.items() if k != "id")
    forms = []
    for a in ent["actions"].values():
        if R.action_allowed(ctx, ent, rec, a, {}) and R.action_possible(ctx, ent, rec, a, {}):
            inputs = "".join(_input(p, spec) for p, spec in a["params"].items())
            forms.append(f'<form data-action="{esc(a["name"])}" method="post" action="/api/{esc(coll)}/{rid}/{esc(a["name"])}">'
                         f'{inputs}<button>{esc(a["name"])}</button></form>')
    return 200, page(f"{coll} {rid}", f"<table>{fields}</table>{''.join(forms)}", ctx)


def ui_new(ctx, coll):
    R._require_user(ctx)
    ent = R._entity_or_404(ctx, coll)
    cand_data = {}
    cand = R.Rec(ctx, ent, None, override=cand_data)
    try:
        R.apply_defaults(ctx, ent, cand_data, provided=set())
    except Exception:  # noqa: BLE001 - defaults needing input are fine to skip here
        pass
    if not R._safe_test(ctx, ent["rules"].get("create"), True, record=cand, input={}):
        R.halt(403, f"you may not create {ent['name']}")
    inputs = []
    for f in M.ordered_fields(ent):
        if f.get("computed") or f.get("system"):
            continue
        if f.get("write_if") and not R._safe_test(ctx, f["write_if"], False, record=cand, input={}):
            continue
        inputs.append(_input(f["name"], f))
    return 200, page(f"New {coll}", f'<form data-create="{esc(coll)}" method="post" action="/api/{esc(coll)}">'
                                     f'{"".join(inputs)}<button>Create</button></form>', ctx)


def handle(model, world, path, user, now):
    ctx = R.Ctx(model, world, user, now)
    parts = [p for p in path.split("/") if p][1:]
    try:
        if len(parts) == 1:
            return ui_list(ctx, parts[0])
        if len(parts) == 2 and parts[1] == "new":
            return ui_new(ctx, parts[0])
        if len(parts) == 2:
            return ui_detail(ctx, parts[0], parts[1])
        R.halt(404, "not found")
    except R.Halt as h:
        return h.status, page(f"Error {h.status}", f'<p class="err">{esc(h.message)}</p>', ctx)
