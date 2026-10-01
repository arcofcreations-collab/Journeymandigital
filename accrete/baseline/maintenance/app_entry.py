"""Application instance entry point: serves the database stored next to this file."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(HERE, "data.db")
PACKAGE = "maintenance_app"


def _forget_package_loaded_from_elsewhere():
    """Test harnesses load several copies of this directory into one process. Drop a
    previously imported ``maintenance_app`` that came from another copy so this instance runs
    its own code, migrations and templates."""
    module = sys.modules.get(PACKAGE)
    if module is not None and os.path.dirname(os.path.dirname(os.path.abspath(module.__file__))) != HERE:
        for name in [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]:
            del sys.modules[name]


def create_app():
    _forget_package_loaded_from_elsewhere()
    from maintenance_app import create_app as build_app

    return build_app(DATABASE_PATH)
