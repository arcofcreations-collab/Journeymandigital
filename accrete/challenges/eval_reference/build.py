"""Build a reference app instance directory: python build.py <app> <outdir> [level]"""
import json, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)

ENTRY = '''import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, {ref!r})
from {mod} import {cls}
def create_app():
    return {cls}(HERE)
'''
APPS = {"maintenance": ("ref_maintenance", "MaintenanceApp"),
        "library": ("ref_library", "LibraryApp"),
        "expenses": ("ref_expenses", "ExpensesApp")}

def build(app, out, level=None):
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    data = json.load(open(os.path.join(WS, "spec", "apps", f"{app}_seed.json")))
    if level:
        import importlib
        mig = importlib.import_module(f"mig_{app}")
        data = mig.migrate(data, level)
        data["_level"] = level
    json.dump(data, open(os.path.join(out, "data.json"), "w"))
    mod, cls = APPS[app]
    open(os.path.join(out, "app_entry.py"), "w").write(ENTRY.format(ref=HERE, mod=mod, cls=cls))

if __name__ == "__main__":
    sys.path.insert(0, HERE)
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
