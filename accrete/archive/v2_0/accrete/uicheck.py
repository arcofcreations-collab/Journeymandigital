"""Read the generated HTML the way the contract describes it (rows, fields, action forms, inputs).

Used by `expect:` entries that check UI pages, so a change can state its UI consequences as
examples instead of the implementer writing a separate test script.
"""
from __future__ import annotations

from html.parser import HTMLParser


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


def parse(html: str) -> dict:
    c = _Collect()
    c.feed(html)
    return {"rows": c.rows, "fields": c.fields, "actions": c.actions, "inputs": c.inputs, "creates": c.creates}


def check(page: dict, spec: dict) -> str:
    """Compare a parsed page with `ui:` expectations; return '' or a description of the mismatch.

    spec keys: rows (exact list of ids or a count), fields ({name: text}), actions (exact set),
    actions_include / actions_exclude (lists), inputs (exact set), inputs_include (list)."""
    problems = []
    if "rows" in spec:
        want = spec["rows"]
        got = page["rows"]
        if isinstance(want, int) and len(got) != want:
            problems.append(f"expected {want} rows, got {len(got)}")
        elif isinstance(want, list) and sorted(got) != sorted(want):
            problems.append(f"expected rows {sorted(want)}, got {sorted(got)}")
    for k, v in (spec.get("fields") or {}).items():
        if page["fields"].get(k) != str(v):
            problems.append(f"field {k}: expected {str(v)!r}, got {page['fields'].get(k)!r}")
    if "actions" in spec and sorted(page["actions"]) != sorted(spec["actions"]):
        problems.append(f"actions: expected {sorted(spec['actions'])}, got {sorted(page['actions'])}")
    for a in spec.get("actions_include") or []:
        if a not in page["actions"]:
            problems.append(f"action form {a!r} missing (has {page['actions']})")
    for a in spec.get("actions_exclude") or []:
        if a in page["actions"]:
            problems.append(f"action form {a!r} should not be offered")
    if "inputs" in spec and sorted(set(page["inputs"])) != sorted(set(spec["inputs"])):
        problems.append(f"inputs: expected {sorted(set(spec['inputs']))}, got {sorted(set(page['inputs']))}")
    for i in spec.get("inputs_include") or []:
        if i not in page["inputs"]:
            problems.append(f"input {i!r} missing (has {page['inputs']})")
    return "; ".join(problems)
