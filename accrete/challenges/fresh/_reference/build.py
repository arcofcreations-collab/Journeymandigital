"""Build reference application instance directories under _ref/states/."""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
SEQ = ["F01", "F02", "F03", "F04", "F05", "F06"]

STATES = {
    "library_base": ("library", []),
    "expenses_base": ("expenses", []),
    "maintenance_base": ("maintenance", []),
    "library_F10": ("library", ["F10"]),
    "library_F11": ("library", ["F11"]),
    "library_F12": ("library", ["F12"]),
    "maintenance_F07": ("maintenance", ["F07"]),
    "maintenance_F08": ("maintenance", ["F08"]),
    "maintenance_F09": ("maintenance", []),   # unchanged + CLARIFICATION.md
    "expenses_F13": ("expenses", ["F13"]),
    "expenses_F14": ("expenses", ["F14"]),
}
for i, f in enumerate(SEQ):
    STATES[f"expenses_{f}"] = ("expenses", SEQ[: i + 1])

CLASS = {"library": "Library", "expenses": "Expenses", "maintenance": "Maintenance"}

TEMPLATE = '''import json, os, sys
REF = {ref!r}
if REF not in sys.path:
    sys.path.insert(0, REF)
import {mod} as _m

def create_app():
    with open({seed!r}) as fh:
        seed = json.load(fh)
    return _m.{cls}(seed, {features!r})
'''


def main():
    root = os.path.join(HERE, "states")
    shutil.rmtree(root, ignore_errors=True)
    for name, (app, feats) in STATES.items():
        d = os.path.join(root, name)
        os.makedirs(d)
        seed = os.path.join(WS, "spec", "apps", f"{app}_seed.json")
        with open(os.path.join(d, "app_entry.py"), "w") as fh:
            fh.write(TEMPLATE.format(ref=HERE, mod=app, seed=seed, cls=CLASS[app], features=feats))
        if name == "maintenance_F09":
            with open(os.path.join(d, "CLARIFICATION.md"), "w") as fh:
                fh.write("Refused: requests without X-User cannot be both sofia and 401.\n")
    print("built", len(STATES), "states")


if __name__ == "__main__":
    main()
