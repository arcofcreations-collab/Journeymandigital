"""List filtering for ``GET /api/{collection}?field=value``.

Filtering happens on API-shaped records (after permission checks), so derived fields such
as ``open_orders``, ``due_date`` or ``overdue`` can be filtered like stored ones.
"""
from .errors import ValidationError


def apply_filters(records, filters, fields):
    """Return the records whose ``field`` exactly matches every ``filters`` entry."""
    unknown = {name: "unknown field" for name in filters if name not in fields}
    if unknown:
        raise ValidationError("Unknown filter field.", unknown)
    return [r for r in records if all(_matches(r.get(name), text) for name, text in filters.items())]


def _matches(value, text):
    if value is None:
        return text in ("", "null")
    if isinstance(value, bool):
        return text == ("true" if value else "false")
    if isinstance(value, (int, float)):
        try:
            return float(text) == value
        except ValueError:
            return False
    return str(value) == text
