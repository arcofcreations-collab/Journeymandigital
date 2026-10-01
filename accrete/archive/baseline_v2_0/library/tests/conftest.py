"""Test setup: every test gets a fresh copy of the application instance (see harness/accept_client.py).

The instance under test is $ACCEPT_TARGET when set, otherwise this app's directory. The
committed data.db is never touched: fresh_app copies the whole directory first.
"""
import json
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "..", "harness"))
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)

from accept_client import fresh_app  # noqa: E402

NOW = "2026-03-01T12:00:00"


@pytest.fixture
def app():
    return fresh_app(os.environ.get("ACCEPT_TARGET") or APP_DIR)


@pytest.fixture(scope="session")
def seed():
    with open(os.path.join(APP_DIR, "seed_data.json"), encoding="utf-8") as fh:
        return json.load(fh)
