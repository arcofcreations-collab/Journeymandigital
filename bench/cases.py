"""Load ground-truth date columns and generate benchmark cases.

SEMI-SYNTHETIC: the dates, their order, duplicates and gaps are real; the
DD/MM/YYYY and MM/DD/YYYY renderings and the row windows are generated here.
"""

from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime

from fetch_data import local_path
from sources import SOURCES

SEED = 20260929
WINDOW_SIZES = (6, 12, 24, 60, 250)
WINDOWS_PER_SIZE = 8
FULL_CAP = 20000
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _parse_truth(text: str, parser: str):
    t = (text or "").strip()
    if not t or t.lower() in ("null", "none", "nan"):
        return None
    try:
        if parser == "iso":
            if len(t) == 10:
                return datetime.strptime(t, "%Y-%m-%d")
            return datetime.fromisoformat(t.replace("Z", ""))
        if parser == "iso_datepart":
            return datetime.strptime(t[:10], "%Y-%m-%d")
        if parser == "ymd_slash_time":
            return datetime.strptime(t, "%Y/%m/%d %H:%M:%S")
        if parser == "mon_d_y":
            mon, d, y = t.split()
            return datetime(int(y), MONTHS[mon[:3]], int(d))
    except (ValueError, KeyError):
        return None
    raise ValueError(parser)


def load_truth(repo, path, column, parser):
    fn = local_path(repo, path)
    if fn.endswith(".json"):
        with open(fn, encoding="utf-8") as fh:
            records = json.load(fh)
        raw = [r.get(column) for r in records]
    else:
        with open(fn, encoding="utf-8-sig", newline="") as fh:
            raw = [row[column] for row in csv.DictReader(fh)]
    return [_parse_truth(str(v) if v is not None else "", parser) for v in raw]


@dataclass
class Case:
    case_id: str
    split: str
    source: str  # repo/path:column
    kind: str  # full | window
    size: int
    shuffled: bool
    render: str  # DMY | MDY
    truth: list  # datetime | None
    strings: list  # rendered strings ('' for missing)
    has_time: bool
    klass: str  # ambiguous | unambiguous | degenerate | empty


def render(truth, order, has_time):
    fmt = "%d/%m/%Y" if order == "DMY" else "%m/%d/%Y"
    if has_time:
        fmt += " %H:%M:%S"
    return [t.strftime(fmt) if t else "" for t in truth]


def classify(truth):
    vals = [t for t in truth if t]
    if not vals:
        return "empty"
    if any(t.day > 12 for t in vals):
        return "unambiguous"
    if all(t.day == t.month for t in vals):
        return "degenerate"
    return "ambiguous"


def generate(split=None):
    rng = random.Random(SEED)
    cases = []
    for sp, repo, path, column, parser in SOURCES:
        truth_all = load_truth(repo, path, column, parser)
        # Consume RNG identically regardless of the requested split.
        src = f"{repo}/{path}:{column}"
        has_time = any(t and (t.hour or t.minute or t.second) for t in truth_all)
        if parser == "iso_datepart":
            has_time = False
        variants = [("full", len(truth_all[:FULL_CAP]), False, truth_all[:FULL_CAP])]
        for n in WINDOW_SIZES:
            if len(truth_all) <= n:
                continue
            for k in range(WINDOWS_PER_SIZE):
                start = rng.randrange(0, len(truth_all) - n + 1)
                win = truth_all[start:start + n]
                variants.append(("window", n, False, win))
                shuffled = list(win)
                rng.shuffle(shuffled)
                variants.append(("window", n, True, shuffled))
        if split and sp != split:
            continue
        for vi, (kind, n, shuf, truth) in enumerate(variants):
            klass = classify(truth)
            for order in ("DMY", "MDY"):
                cases.append(Case(
                    case_id=f"{src}#{vi}:{order}", split=sp, source=src, kind=kind,
                    size=n, shuffled=shuf, render=order, truth=truth,
                    strings=render(truth, order, has_time), has_time=has_time,
                    klass=klass,
                ))
    return cases


if __name__ == "__main__":
    from collections import Counter
    for sp in ("DEV", "TEST"):
        cs = generate(sp)
        print(sp, len(cs), Counter(c.klass for c in cs))
