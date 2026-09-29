"""Day/month order resolution for numeric date columns.

The two readings of a fully ambiguous column such as ``03/04/2021, 03/05/2021``
are value-for-value bijective, so nothing about the individual strings can
tell them apart. What differs is the *calendar structure* the column has
under each reading: real data is usually in date order, sits on a regular
grid (daily, business-daily, weekly, monthly…) and often favours particular
weekdays. The wrong reading scrambles all three. We measure that structure
as the number of bits an adaptive code needs to describe the column under
each reading and pick the more compressible one, abstaining when the margin
is small.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Sequence

__all__ = [
    "ColumnResult",
    "MIN_Z",
    "DEFAULT_THRESHOLD_BITS",
    "resolve_column",
    "parse_with_order",
]

# Minimum evidence (bits) before a structural verdict is issued. Chosen on the
# DEV split only (see docs/SPEC_v1_FROZEN.md and bench/tune_dev.py).
DEFAULT_THRESHOLD_BITS = 2.0

# Weight of the weekday component relative to the sequence component.
WEEKDAY_WEIGHT = 1.0

# Row-order/grid evidence whose paired z score reaches MIN_Z is accepted as
# significant without further testing (p ~ 0.001 under a normal
# approximation). Fixed a priori, not tuned.
MIN_Z = 3.0

# Randomisation test used when the evidence is not self-evidently significant:
# the column's evidence must exceed that of every one of N_SURROGATES
# structure-free surrogate columns (p < 1/(N+1)). Fixed a priori, not tuned.
N_SURROGATES = 39
SURROGATE_SEED = 20260929
SURROGATE_MAX_ROWS = 2000

MISSING = {"", "na", "n/a", "nan", "null", "none", "nat", "-", "--", "?"}

_DATE_RE = re.compile(
    r"""^\s*
    (?P<a>\d{1,4})(?P<sep>[/.\-])(?P<b>\d{1,2})(?P=sep)(?P<c>\d{1,4})
    (?:[ T](?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2})(?:[.,]\d+)?)?\s*(?P<ampm>[AaPp][Mm])?)?
    \s*$""",
    re.VERBOSE,
)

YEAR_LAST_ORDERS = ("DMY", "MDY")
YEAR_FIRST_ORDERS = ("YMD", "YDM")


@dataclass
class _Raw:
    a: int
    b: int
    c: int
    a_len: int
    c_len: int
    sep: str
    seconds: int  # seconds since midnight, 0 when no time given


def _parse_raw(text: str) -> Optional[_Raw]:
    m = _DATE_RE.match(text)
    if not m:
        return None
    seconds = 0
    if m.group("H") is not None:
        h, mi, s = int(m.group("H")), int(m.group("M")), int(m.group("S") or 0)
        ampm = m.group("ampm")
        if ampm:
            if not 1 <= h <= 12:
                return None
            h = h % 12 + (12 if ampm.lower() == "pm" else 0)
        if h > 23 or mi > 59 or s > 59:
            return None
        seconds = h * 3600 + mi * 60 + s
    return _Raw(
        int(m.group("a")), int(m.group("b")), int(m.group("c")),
        len(m.group("a")), len(m.group("c")), m.group("sep"), seconds,
    )


def _expand_year(y: int, digits: int) -> int:
    if digits == 2:
        # POSIX strptime %y pivot: 69-99 -> 1900s, 00-68 -> 2000s.
        return 1900 + y if y >= 69 else 2000 + y
    return y


def _layout(raw: _Raw) -> Optional[str]:
    """'Y-last' (a/b/YYYY or a/b/YY) or 'Y-first' (YYYY/b/c)."""
    if raw.a_len == 4 and raw.c_len <= 2:
        return "Y-first"
    if raw.a_len <= 2 and raw.c_len in (2, 4):
        return "Y-last"
    return None


def _canonical_key(raw: _Raw, layout: str) -> tuple:
    """Reading-independent identity of a value: (x, y, year, seconds)."""
    if layout == "Y-last":
        return (raw.a, raw.b, _expand_year(raw.c, raw.c_len), raw.seconds)
    return (raw.b, raw.c, raw.a, raw.seconds)


def _to_datetime(raw: _Raw, order: str) -> Optional[datetime]:
    if order == "DMY":
        d, mo, y = raw.a, raw.b, _expand_year(raw.c, raw.c_len)
    elif order == "MDY":
        mo, d, y = raw.a, raw.b, _expand_year(raw.c, raw.c_len)
    elif order == "YMD":
        y, mo, d = raw.a, raw.b, raw.c
    elif order == "YDM":
        y, d, mo = raw.a, raw.b, raw.c
    else:  # pragma: no cover - internal misuse
        raise ValueError(order)
    try:
        base = datetime(y, mo, d)
    except ValueError:
        return None
    return base + timedelta(seconds=raw.seconds)


# --------------------------------------------------------------------------
# Adaptive code lengths
# --------------------------------------------------------------------------

def _gamma_bits(n: int) -> float:
    """Elias-gamma length for a positive integer."""
    return 2 * math.floor(math.log2(n)) + 1


def _new_symbol_bits(sym: tuple) -> float:
    """Cost of spelling out a delta symbol never seen before."""
    kind, units, secs = sym
    bits = math.log2(4)  # which kind: T / M / E / D
    if kind != "T":
        bits += _gamma_bits(abs(units) + 1)  # magnitude (direction coded separately)
    bits += 1  # time part present?
    if secs:
        bits += 1 + _gamma_bits(abs(secs) // 60 + 1)
    return bits


def _month_end(d: datetime) -> bool:
    return (d + timedelta(days=1)).month != d.month


def _delta_symbol(x: datetime, y: datetime) -> tuple:
    """Calendar-aware step from x to y.

    Whole-month steps that keep the day of month (1st -> 1st, 15th -> 15th)
    or stay on month ends are expressed in months, everything else in days,
    so that monthly and quarterly grids are as regular as daily ones.
    """
    secs = (y.hour * 3600 + y.minute * 60 + y.second) - (
        x.hour * 3600 + x.minute * 60 + x.second
    )
    if x.date() == y.date():
        return ("T", 0, secs)
    months = (y.year - x.year) * 12 + (y.month - x.month)
    if months and x.day == y.day:
        return ("M", months, secs)
    if months and _month_end(x) and _month_end(y):
        return ("E", months, secs)
    return ("D", (y.date() - x.date()).days, secs)


def _sequence_bits(values: Sequence[datetime]) -> tuple[list, Counter]:
    """Adaptive code length, per step, of the delta sequence.

    Each step is coded as a direction (forward/backward, adaptive binary
    code; nothing for a zero step) plus a size (adaptive escape code over
    the step sizes seen so far). Coding direction on its own makes a file in
    date order cheap under the right reading (every step forward) and
    expensive under a wrong one that jumps backward at regular intervals.
    Forward and backward are treated alike, so descending files work too.
    """
    counts: Counter = Counter()
    n = 0
    dirs = [0, 0]
    items = []
    for x, y in zip(values, values[1:]):
        kind, units, secs = _delta_symbol(x, y)
        sign = (units > 0) - (units < 0) or (secs > 0) - (secs < 0)
        bits = 0.0
        if sign:
            d = 0 if sign > 0 else 1
            bits += -math.log2((dirs[d] + 0.5) / (dirs[0] + dirs[1] + 1))
            dirs[d] += 1
            units, secs = units * sign, secs * sign
        sym = (kind, units, secs)
        c = counts[sym]
        if c:
            bits += -math.log2(c / (n + 1))
        else:
            bits += -math.log2(1 / (n + 1)) + _new_symbol_bits(sym)
        items.append(bits)
        counts[sym] += 1
        n += 1
    return items, counts


def _weekday_bits(values: Sequence[datetime]) -> tuple[list, Counter]:
    """Krichevsky-Trofimov code length of the weekdays of the distinct dates.

    Repeated rows for the same day are not independent observations of the
    weekday pattern, so each calendar date is counted once.
    """
    counts: Counter = Counter()
    items = []
    for i, d in enumerate(sorted({v.date() for v in values})):
        wd = d.weekday()
        items.append(-math.log2((counts[wd] + 0.5) / (i + 3.5)))
        counts[wd] += 1
    return items, counts


def _arrangement_bits(values: Sequence[datetime]) -> float:
    """Bits to restore file order and multiplicities from the sorted distinct set.

    log2 of the number of distinct arrangements of the multiset, plus an
    Elias-gamma multiplicity per distinct value. Both readings are bijective
    images of the same raw strings, so this cost is identical for them; it
    only decides whether the file order is worth coding.
    """
    counts = Counter(values)
    n = len(values)
    perm = (math.lgamma(n + 1) - sum(math.lgamma(c + 1) for c in counts.values())) / math.log(2)
    return perm + sum(_gamma_bits(c) for c in counts.values())


@dataclass
class ReadingStats:
    order: str
    order_bits: float  # file order coded as calendar deltas
    grid_bits: float  # sorted distinct dates coded as calendar deltas
    arrangement_bits: float  # reading-independent cost of order + multiplicities
    weekday_bits: float
    forward_share: float  # share of non-zero file-order steps going forward
    top_step: str  # most common step between sorted distinct values
    top_step_share: float
    weekday_share_mon_fri: float
    distinct_weekdays: int
    order_items: list = field(default_factory=list, repr=False)
    grid_items: list = field(default_factory=list, repr=False)
    weekday_items: list = field(default_factory=list, repr=False)
    grid_by_key: dict = field(default_factory=dict, repr=False)
    weekday_by_key: dict = field(default_factory=dict, repr=False)

    @property
    def sequence_items(self) -> list:
        return self.order_items if self.uses_file_order else self.grid_items

    @property
    def sequence_bits(self) -> float:
        """Two-part code: the cheaper of coding the rows in file order, or
        the sorted grid followed by the arrangement."""
        return min(self.order_bits, self.grid_bits + self.arrangement_bits)

    @property
    def uses_file_order(self) -> bool:
        return self.order_bits <= self.grid_bits + self.arrangement_bits

    @property
    def total_bits(self) -> float:
        return self.sequence_bits + WEEKDAY_WEIGHT * self.weekday_bits


def _describe_step(sym: tuple) -> str:
    kind, units, secs = sym
    if kind == "T":
        return f"{secs // 60} min" if secs % 3600 else f"{secs // 3600} h"
    unit = {"M": "month", "E": "month (month-end)", "D": "day"}[kind]
    s = f"{units} {unit}{'s' if abs(units) != 1 and kind != 'E' else ''}"
    return s


def _reading_stats(order: str, values: Sequence[datetime], keys: Sequence) -> ReadingStats:
    """Code lengths of one reading. ``keys`` identify each row's raw value
    independently of the reading, so per-value costs can be paired."""
    order_items, _ = _sequence_bits(values)
    distinct = sorted(set(values))
    grid_items, grid_counts = _sequence_bits(distinct)
    wd_items, wd_counts = _weekday_bits(values)
    key_of = dict(zip(values, keys))
    grid_by_key = {key_of[v]: c for v, c in zip(distinct[1:], grid_items)}
    dkey_of = {v.date(): k[:3] for v, k in zip(values, keys)}
    wd_by_key = dict(zip((dkey_of[d] for d in sorted(dkey_of)), wd_items))
    fwd = back = 0
    for x, y in zip(values, values[1:]):
        if y > x:
            fwd += 1
        elif y < x:
            back += 1
    steps = fwd + back
    if grid_counts:
        top, top_n = grid_counts.most_common(1)[0]
        top_desc, top_share = _describe_step(top), top_n / sum(grid_counts.values())
    else:
        top_desc, top_share = "-", 0.0
    n = sum(wd_counts.values())
    return ReadingStats(
        order=order,
        order_bits=sum(order_items),
        grid_bits=sum(grid_items),
        arrangement_bits=_arrangement_bits(values),
        weekday_bits=sum(wd_items),
        forward_share=(max(fwd, back) / steps) if steps else 1.0,
        top_step=top_desc,
        top_step_share=top_share,
        weekday_share_mon_fri=(sum(wd_counts[i] for i in range(5)) / n) if n else 0.0,
        distinct_weekdays=len(wd_counts),
        order_items=order_items,
        grid_items=grid_items,
        weekday_items=wd_items,
        grid_by_key=grid_by_key,
        weekday_by_key=wd_by_key,
    )


def _var_sum(items: list) -> float:
    """Variance of a sum of len(items) terms, estimated from the items."""
    n = len(items)
    if n < 2:
        return 0.0
    mean = sum(items) / n
    return n * sum((x - mean) ** 2 for x in items) / (n - 1)


def sequence_z(best: "ReadingStats", other: "ReadingStats") -> float:
    """Sequence evidence divided by its standard error.

    A paired comparison of the two codes on the same items, as when two
    compressors are compared symbol by symbol: file-order steps are paired
    by row; grid steps are paired by the raw value they code (the same
    string is one item under both readings). A real calendar structure saves
    bits on most items (large z); a column without structure yields a margin
    of the same size as its noise, which grows with the column length. Only
    when one reading codes the file order and the other does not are the
    items treated as independent samples.
    """
    e = other.sequence_bits - best.sequence_bits
    if best.uses_file_order and other.uses_file_order:
        var = _var_sum([o - b for o, b in zip(other.order_items, best.order_items)])
    elif not best.uses_file_order and not other.uses_file_order:
        keys = other.grid_by_key.keys() | best.grid_by_key.keys()
        var = _var_sum([other.grid_by_key.get(k, 0.0) - best.grid_by_key.get(k, 0.0)
                        for k in keys])
    else:
        var = _var_sum(best.sequence_items) + _var_sum(other.sequence_items)
    if var <= 0:
        return math.inf if e > 0 else (-math.inf if e < 0 else 0.0)
    return e / math.sqrt(var)


def _describe_step(sym: tuple) -> str:
    kind, units, secs = sym
    if kind == "T":
        return f"{secs // 60} min" if secs % 3600 else f"{secs // 3600} h"
    unit = {"M": "month", "E": "month (month-end)", "D": "day"}[kind]
    s = f"{units} {unit}{'s' if abs(units) != 1 and kind != 'E' else ''}"
    return s


def _reading_stats(order: str, values: Sequence[datetime], keys: Sequence) -> ReadingStats:
    """Code lengths of one reading. ``keys`` identify each row's raw value
    independently of the reading, so per-value costs can be paired."""
    order_items, _ = _sequence_bits(values)
    distinct = sorted(set(values))
    grid_items, grid_counts = _sequence_bits(distinct)
    wd_items, wd_counts = _weekday_bits(values)
    key_of = dict(zip(values, keys))
    grid_by_key = {key_of[v]: c for v, c in zip(distinct[1:], grid_items)}
    dkey_of = {v.date(): k[:3] for v, k in zip(values, keys)}
    wd_by_key = dict(zip((dkey_of[d] for d in sorted(dkey_of)), wd_items))
    fwd = back = 0
    for x, y in zip(values, values[1:]):
        if y > x:
            fwd += 1
        elif y < x:
            back += 1
    steps = fwd + back
    if grid_counts:
        top, top_n = grid_counts.most_common(1)[0]
        top_desc, top_share = _describe_step(top), top_n / sum(grid_counts.values())
    else:
        top_desc, top_share = "-", 0.0
    n = sum(wd_counts.values())
    return ReadingStats(
        order=order,
        order_bits=sum(order_items),
        grid_bits=sum(grid_items),
        arrangement_bits=_arrangement_bits(values),
        weekday_bits=sum(wd_items),
        forward_share=(max(fwd, back) / steps) if steps else 1.0,
        top_step=top_desc,
        top_step_share=top_share,
        weekday_share_mon_fri=(sum(wd_counts[i] for i in range(5)) / n) if n else 0.0,
        distinct_weekdays=len(wd_counts),
        order_items=order_items,
        grid_items=grid_items,
        weekday_items=wd_items,
        grid_by_key=grid_by_key,
        weekday_by_key=wd_by_key,
    )


def _var_sum(items: list) -> float:
    """Variance of a sum of len(items) terms, estimated from the items."""
    n = len(items)
    if n < 2:
        return 0.0
    mean = sum(items) / n
    return n * sum((x - mean) ** 2 for x in items) / (n - 1)


def evidence_z(best: "ReadingStats", other: "ReadingStats") -> float:
    """Evidence divided by its standard error.

    A paired comparison of the two codes on the same items, as when two
    compressors are compared symbol by symbol: file-order steps are paired
    by row; grid steps and weekdays are paired by the raw value they code
    (the same string is one item under both readings). A real calendar
    structure saves bits on most items (large z); a column with no structure
    yields a margin of the same size as its noise. Only when one reading
    codes the file order and the other does not are the sequence items
    treated as independent samples.
    """
    e = other.total_bits - best.total_bits

    def paired(a: dict, b: dict) -> float:
        return _var_sum([a.get(k, 0.0) - b.get(k, 0.0) for k in a.keys() | b.keys()])

    if best.uses_file_order and other.uses_file_order:
        var = _var_sum([o - b for o, b in zip(other.order_items, best.order_items)])
    elif not best.uses_file_order and not other.uses_file_order:
        var = paired(other.grid_by_key, best.grid_by_key)
    else:
        var = _var_sum(best.sequence_items) + _var_sum(other.sequence_items)
    var += WEEKDAY_WEIGHT ** 2 * paired(other.weekday_by_key, best.weekday_by_key)
    if var <= 0:
        return math.inf if e > 0 else 0.0
    return e / math.sqrt(var)


# --------------------------------------------------------------------------
# Column resolution
# --------------------------------------------------------------------------

@dataclass
class ColumnResult:
    """Outcome for one column.

    verdict: one of DMY, MDY, YMD, YDM, AMBIGUOUS, NOT_DATE, INCONSISTENT, EMPTY
    method:  'validity' | 'identical' | 'structure' | 'file-consistency' |
             'abstained' | '' (non-date outcomes)
    """

    verdict: str
    method: str
    evidence_bits: float = 0.0
    evidence_z: float = 0.0
    components: dict = field(default_factory=dict)
    layout: Optional[str] = None
    separator: Optional[str] = None
    n_values: int = 0
    n_missing: int = 0
    n_unparsed: int = 0
    candidates: tuple = ()
    invalid_counts: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)  # order -> ReadingStats
    examples: list = field(default_factory=list)  # (raw, {order: iso})
    reasons: list = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.verdict in YEAR_LAST_ORDERS + YEAR_FIRST_ORDERS

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "method": self.method,
            "evidence_bits": round(self.evidence_bits, 2),
            "evidence_z": round(self.evidence_z, 2) if math.isfinite(self.evidence_z) else "inf",
            "components": {k: (round(v, 2) if math.isfinite(v) else str(v))
                           for k, v in self.components.items()},
            "layout": self.layout,
            "separator": self.separator,
            "n_values": self.n_values,
            "n_missing": self.n_missing,
            "n_unparsed": self.n_unparsed,
            "invalid_counts": self.invalid_counts,
            "reasons": self.reasons,
            "examples": [
                {"value": raw, "readings": readings} for raw, readings in self.examples
            ],
            "stats": {
                k: {
                    "order_bits": round(v.order_bits, 2),
                    "grid_bits": round(v.grid_bits, 2),
                    "arrangement_bits": round(v.arrangement_bits, 2),
                    "uses_file_order": v.uses_file_order,
                    "weekday_bits": round(v.weekday_bits, 2),
                    "total_bits": round(v.total_bits, 2),
                    "forward_share": round(v.forward_share, 4),
                    "top_step": v.top_step,
                    "top_step_share": round(v.top_step_share, 4),
                    "weekday_share_mon_fri": round(v.weekday_share_mon_fri, 4),
                }
                for k, v in self.stats.items()
            },
        }


def _is_missing(v) -> bool:
    return v is None or str(v).strip().lower() in MISSING


def _explain(best: ReadingStats, other: ReadingStats) -> list:
    reasons = []
    if best.uses_file_order and best.forward_share - other.forward_share >= 0.05:
        reasons.append(
            f"row order is chronological for {best.forward_share:.0%} of steps under "
            f"{best.order} vs {other.forward_share:.0%} under {other.order}"
        )
    if best.top_step_share - other.top_step_share >= 0.05:
        reasons.append(
            f"sorted dates step by '{best.top_step}' {best.top_step_share:.0%} of the time "
            f"under {best.order} vs '{other.top_step}' {other.top_step_share:.0%} under {other.order}"
        )
    if abs(best.weekday_share_mon_fri - other.weekday_share_mon_fri) >= 0.05 or (
        best.distinct_weekdays < other.distinct_weekdays
    ):
        reasons.append(
            f"weekdays: {best.distinct_weekdays} distinct, {best.weekday_share_mon_fri:.0%} Mon-Fri "
            f"under {best.order} vs {other.distinct_weekdays} distinct, "
            f"{other.weekday_share_mon_fri:.0%} Mon-Fri under {other.order}"
        )
    if not reasons:
        reasons.append("combined calendar regularity (see bit counts)")
    return reasons


def _signed_evidence(v1, v2, keys, o1, o2):
    s1, s2 = _reading_stats(o1, v1, keys), _reading_stats(o2, v2, keys)
    seq = s2.sequence_bits - s1.sequence_bits
    z = sequence_z(s1, s2) if seq >= 0 else -sequence_z(s2, s1)
    wd = WEEKDAY_WEIGHT * (s2.weekday_bits - s1.weekday_bits)
    return s1, s2, seq, z, wd


def _surrogate_best_bits(raws, layout, o1, o2, k, cap=SURROGATE_MAX_ROWS):
    """Structure test by randomisation.

    Returns (observed, null): the code length of the better reading of the
    column, and the same quantity for k surrogate columns. Each surrogate
    transposes a random half of the distinct values (day and month swapped),
    which destroys calendar structure under *both* readings while keeping
    the column's size, value set, duplicates and row order. If the column
    has no calendar structure it is exchangeable with its surrogates, so
    ``observed < min(null)`` happens with probability <= 1/(k+1).

    Long columns are compared on a fixed random subsample of ``cap`` rows.
    Coins are seeded and depend only on the unordered (day, month) pair, so
    DMY and MDY renderings of the same data get mirrored surrogates.
    """
    if len(raws) > cap:
        rng = random.Random(SURROGATE_SEED)
        raws = [raws[i] for i in sorted(rng.sample(range(len(raws)), cap))]

    def best_bits(rs):
        v1 = [_to_datetime(r, o1) for r in rs]
        v2 = [_to_datetime(r, o2) for r in rs]
        keys = [_canonical_key(r, layout) for r in rs]
        s1, s2 = _reading_stats(o1, v1, keys), _reading_stats(o2, v2, keys)
        return min(s1.total_bits, s2.total_bits)

    null = []
    for i in range(k):
        sraws = []
        for r in raws:
            x, y, year, secs = _canonical_key(r, layout)
            # Tuple-of-int hashes are deterministic across Python runs.
            if hash((SURROGATE_SEED, i, min(x, y), max(x, y), year, secs)) >> 11 & 1:
                if layout == "Y-last":
                    r = _Raw(r.b, r.a, r.c, r.a_len, r.c_len, r.sep, r.seconds)
                else:
                    r = _Raw(r.a, r.c, r.b, r.a_len, r.c_len, r.sep, r.seconds)
            sraws.append(r)
        null.append(best_bits(sraws))
    return best_bits(raws), null


def resolve_column(
    values: Iterable,
    threshold_bits: float = DEFAULT_THRESHOLD_BITS,
    min_date_share: float = 0.95,
    min_z: float = MIN_Z,
    n_surrogates: int = N_SURROGATES,
) -> ColumnResult:
    """Decide the component order of a column of numeric date strings."""
    raws: list[_Raw] = []
    raw_text: list[str] = []
    n_missing = n_unparsed = 0
    for v in values:
        if _is_missing(v):
            n_missing += 1
            continue
        r = _parse_raw(str(v))
        if r is None or _layout(r) is None:
            n_unparsed += 1
            continue
        raws.append(r)
        raw_text.append(str(v).strip())

    total = len(raws) + n_unparsed
    if total == 0:
        return ColumnResult("EMPTY", "", n_missing=n_missing)
    if len(raws) / total < min_date_share:
        return ColumnResult("NOT_DATE", "", n_values=len(raws), n_missing=n_missing,
                            n_unparsed=n_unparsed)

    layouts = Counter(_layout(r) for r in raws)
    seps = Counter(r.sep for r in raws)
    layout, layout_n = layouts.most_common(1)[0]
    sep, sep_n = seps.most_common(1)[0]
    if layout is None or layout_n != len(raws) or sep_n != len(raws):
        return ColumnResult(
            "INCONSISTENT", "", n_values=len(raws), n_missing=n_missing,
            n_unparsed=n_unparsed,
            reasons=[f"mixed layouts {dict(layouts)} / separators {dict(seps)}"],
        )

    candidates = YEAR_LAST_ORDERS if layout == "Y-last" else YEAR_FIRST_ORDERS
    parsed: dict = {}
    invalid: dict = {}
    for order in candidates:
        vals = [_to_datetime(r, order) for r in raws]
        invalid[order] = sum(v is None for v in vals)
        parsed[order] = vals

    res = ColumnResult(
        "AMBIGUOUS", "", layout=layout, separator=sep, n_values=len(raws),
        n_missing=n_missing, n_unparsed=n_unparsed, candidates=candidates,
        invalid_counts=invalid,
    )
    # Show values whose readings differ first: they are the informative ones.
    seen = set()
    ex_idx = [i for i, r in enumerate(raws) if r.a != (r.b if layout == "Y-last" else r.c)]
    for i in ex_idx + list(range(len(raws))):
        if raw_text[i] in seen:
            continue
        seen.add(raw_text[i])
        res.examples.append((raw_text[i], {
            o: (parsed[o][i].isoformat(sep=" ") if parsed[o][i] else None) for o in candidates
        }))
        if len(res.examples) >= 3:
            break

    valid = [o for o in candidates if invalid[o] == 0]
    if not valid:
        res.verdict = "INCONSISTENT"
        res.reasons.append(
            "no single order reads every value as a real date: "
            + ", ".join(f"{o}: {invalid[o]} impossible" for o in candidates)
        )
        return res
    if len(valid) == 1:
        res.verdict, res.method = valid[0], "validity"
        other = [o for o in candidates if o != valid[0]][0]
        res.reasons.append(f"{invalid[other]} value(s) are impossible dates under {other}")
        return res

    o1, o2 = candidates
    if parsed[o1] == parsed[o2]:
        res.verdict, res.method = o1, "identical"
        res.reasons.append("both orders give identical dates (day equals month in every value)")
        return res

    keys = [_canonical_key(r, layout) for r in raws]
    s1, s2, seq, z, wd = _signed_evidence(parsed[o1], parsed[o2], keys, o1, o2)
    res.stats = {o1: s1, o2: s2}
    total = seq + wd  # positive favours o1
    best, other = (s1, s2) if total >= 0 else (s2, s1)
    res.evidence_bits = abs(total)
    res.evidence_z = abs(z)
    res.components = {"sequence_bits": seq, "sequence_z": z, "weekday_bits": wd}
    conflict = seq * wd < 0 and min(abs(seq), abs(wd)) >= threshold_bits

    why = None
    if res.evidence_bits < threshold_bits:
        why = f"it favours {best.order} by only {res.evidence_bits:.1f} bits (< {threshold_bits:g})"
    elif conflict:
        why = ("row order/grid and weekday pattern point in opposite directions "
               f"({seq:+.1f} vs {wd:+.1f} bits)")
    elif not (abs(z) >= min_z and seq * total > 0):
        # Not self-evidently significant: is there calendar structure at all?
        observed, null = _surrogate_best_bits(raws, layout, o1, o2, n_surrogates)
        res.components.update(structure_bits=observed, surrogate_min_bits=min(null),
                              surrogates=len(null))
        if not observed < min(null):
            why = (f"the column is no more regular than {len(null)} scrambled copies of itself "
                   f"({observed:.1f} vs best scrambled {min(null):.1f} bits), so the "
                   f"{res.evidence_bits:.1f}-bit lean towards {best.order} may be chance")
    if why is None:
        res.verdict, res.method = best.order, "structure"
        res.reasons = _explain(best, other)
    else:
        res.verdict, res.method = "AMBIGUOUS", "abstained"
        res.reasons.append(f"calendar structure is not conclusive: {why}; refusing to guess")
    return res


def parse_with_order(values: Iterable, order: str) -> list:
    """Parse values with a known order; missing/unparseable -> None."""
    out = []
    for v in values:
        if _is_missing(v):
            out.append(None)
            continue
        r = _parse_raw(str(v))
        out.append(_to_datetime(r, order) if r else None)
    return out
