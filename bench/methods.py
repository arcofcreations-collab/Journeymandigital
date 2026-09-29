"""The five methods compared in the benchmark.

Each method takes a Case and returns (status, parsed) where status is one of
  'parsed'  - the method returned dates (compared with truth afterwards)
  'abstain' - the method explicitly declined / asked the user
  'error'   - the method raised or left the column unparsed (not silent)
"""

from __future__ import annotations

import os
import sys
import tempfile
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dmguard.core import (  # noqa: E402
    DEFAULT_THRESHOLD_BITS,
    parse_with_order,
    resolve_column,
)


def _to_py(ts_list):
    out = []
    for t in ts_list:
        if t is None or (hasattr(t, "isnan") and t.isnan()) or str(t) == "NaT":
            out.append(None)
        else:
            out.append(t.to_pydatetime() if hasattr(t, "to_pydatetime") else t)
    return out


def pandas_default(case, dayfirst=False):
    import pandas as pd

    s = pd.Series([v if v else None for v in case.strings], dtype="object")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(s, dayfirst=dayfirst)
    except (ValueError, TypeError, OverflowError):
        return "error", None
    return "parsed", _to_py(list(parsed))


def pandas_dayfirst(case):
    return pandas_default(case, dayfirst=True)


_TMP = tempfile.mkdtemp(prefix="dmguard-bench-")


def duckdb_sniffer(case):
    import duckdb

    path = os.path.join(_TMP, "case.csv")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("value,row\n")
        for i, v in enumerate(case.strings):
            fh.write(f"{v},{i}\n")
    con = duckdb.connect()
    try:
        rel = con.read_csv(path)
        types = [str(t) for t in rel.types]
        rows = rel.fetchall()
    except Exception:  # noqa: BLE001 - any failure counts as a visible error
        return "error", None
    finally:
        con.close()
    if not (types[0].startswith("DATE") or types[0].startswith("TIMESTAMP")):
        return "error", None  # left as text: nothing silently wrong
    import datetime as dt

    out = []
    for v, _ in rows:
        if v is None:
            out.append(None)
        elif isinstance(v, dt.datetime):
            out.append(v)
        else:
            out.append(dt.datetime(v.year, v.month, v.day))
    return "parsed", out


def range_rule(case):
    """Whole-column value-range rule; ask the user when it cannot decide."""
    res = resolve_column(case.strings, threshold_bits=float("inf"))
    if res.resolved:
        return "parsed", parse_with_order(case.strings, res.verdict)
    return "abstain", None


def dmguard_method(case, threshold_bits=DEFAULT_THRESHOLD_BITS):
    """dmguard (current version), default settings."""
    res = resolve_column(case.strings, threshold_bits=threshold_bits)
    if res.resolved:
        return "parsed", parse_with_order(case.strings, res.verdict)
    return "abstain", None


def dmguard_accept_likely(case):
    """dmguard with --accept-likely: also applies preferences between two regular patterns."""
    res = resolve_column(case.strings, accept_likely=True)
    if res.resolved:
        return "parsed", parse_with_order(case.strings, res.verdict)
    return "abstain", None


def dmguard_v1_0_0(case):
    """The frozen 1.0.0 resolver (commit 26bfe0e method; vendored unchanged)."""
    from legacy import dmguard_1_0_0_core as legacy

    res = legacy.resolve_column(case.strings)
    if res.resolved:
        return "parsed", legacy.parse_with_order(case.strings, res.verdict)
    return "abstain", None


METHODS = {
    "pandas_default": pandas_default,
    "pandas_dayfirst": pandas_dayfirst,
    "duckdb_sniffer": duckdb_sniffer,
    "range_rule_ask": range_rule,
    "dmguard_v1_0_0": dmguard_v1_0_0,
    "dmguard": dmguard_method,
    "dmguard_accept_likely": dmguard_accept_likely,
}


def outcome(case, status, parsed):
    """correct | silent_wrong | abstain | error"""
    if status != "parsed":
        return status
    for t, p in zip(case.truth, parsed):
        if t is None:
            continue
        if p is None:
            return "silent_wrong"  # value dropped to missing without notice
        if case.has_time:
            if p.replace(tzinfo=None) != t:
                return "silent_wrong"
        elif p.date() != t.date():
            return "silent_wrong"
    return "correct"
