"""Who is calling (``X-User``) and what time it is (``X-Now``).

Every request is authenticated before routing, so a missing or unknown user gets 401
even for unknown URLs (401 has the highest precedence in the contract).
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone

from flask import g, request

from . import repository
from .errors import Unauthenticated, ValidationError

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def format_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


@dataclass(frozen=True)
class RequestContext:
    user: dict  # the calling employee record
    now: datetime  # naive UTC, second precision

    @property
    def today(self) -> date:
        return self.now.date()

    @property
    def now_text(self) -> str:
        return format_datetime(self.now)

    @property
    def role(self) -> str:
        return self.user["role"]


def parse_now(header):
    if not header:
        return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    try:
        return datetime.strptime(header, DATETIME_FORMAT)
    except ValueError:
        raise ValidationError("X-Now must be YYYY-MM-DDTHH:MM:SS.", {"X-Now": "invalid datetime"})


def load_request_context():
    username = request.headers.get("X-User")
    user = repository.get_employee_by_username(username) if username else None
    if user is None:
        raise Unauthenticated()
    g.ctx = RequestContext(user=user, now=parse_now(request.headers.get("X-Now")))


def current_context() -> RequestContext:
    return g.ctx


def init_app(app):
    app.before_request(load_request_context)
