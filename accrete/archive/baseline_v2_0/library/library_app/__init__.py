"""Lending library web application (Flask app factory)."""
import json

from flask import Flask, g

from . import auth, db, errors, routes_api, routes_ui


def display(value):
    """Render a field value as text the way the API serialises it (true/false, empty for null)."""
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return json.dumps(value)
    return str(value)


def create_app(database_path):
    """Build the app serving the SQLite database at ``database_path``.

    Pending migrations are applied on startup, so an existing database is upgraded in place.
    """
    app = Flask(__name__)
    app.config["DATABASE"] = database_path
    app.json.sort_keys = False

    db.migrate(database_path)
    db.init_app(app)
    auth.init_app(app)
    errors.init_app(app)

    app.add_template_filter(display)
    app.context_processor(lambda: {"ctx": g.get("ctx")})

    app.register_blueprint(routes_api.bp)
    app.register_blueprint(routes_ui.bp)
    return app
