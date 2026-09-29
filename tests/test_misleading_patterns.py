"""Independent adversarial tests: calendar patterns that can mislead the method.

For each seeded, structured "true" date column (rendered day-first and
month-first) the default tool may resolve or abstain, but must never return
the wrong order. The families include mirror twins, where the wrong reading
is itself a regular calendar pattern ("the 1st of every month" vs "1-12
January every year"). These cases were written after the external review and
were not used to choose any threshold.
"""
import random
from datetime import date, timedelta

import pytest

from dmguard import resolve_column

RNG_SEED = 424242


def _dates_monthly_day(rng):
    k, n = rng.randint(1, 12), rng.randint(6, 60)
    y, m = rng.randint(1995, 2025), rng.randint(1, 12)
    out = []
    for i in range(n):
        mm = (m - 1 + i) % 12 + 1
        out.append(date(y + (m - 1 + i) // 12, mm, k))
    return out


def _dates_daily_run_each_year(rng):
    # e.g. 1-12 January every year (mirror twin of "the 1st of every month")
    m, a = rng.randint(1, 12), rng.randint(1, 6)
    b = rng.randint(a + 3, 12)
    y0, years = rng.randint(1995, 2020), rng.randint(1, 6)
    return [date(y, m, d) for y in range(y0, y0 + years) for d in range(a, b + 1)]


def _dates_quarterly(rng):
    k, n = rng.randint(1, 12), rng.randint(5, 40)
    y, q0 = rng.randint(1995, 2025), rng.randint(0, 3)
    return [date(y + (q0 + i) // 4, 3 * ((q0 + i) % 4) + 1, k) for i in range(n)]


def _dates_weekly(rng):
    start = date(rng.randint(1995, 2025), 1, 1) + timedelta(days=rng.randint(0, 365))
    ds = [start + timedelta(weeks=i) for i in range(rng.randint(20, 200))]
    return [d for d in ds if d.day <= 12]


def _dates_business_days(rng):
    start = date(rng.randint(1995, 2025), rng.randint(1, 12), 1)
    ds = [start + timedelta(days=i) for i in range(rng.randint(40, 700))]
    return [d for d in ds if d.weekday() < 5 and d.day <= 12]


def _dates_daily_short(rng):
    y, m, a = rng.randint(1995, 2025), rng.randint(1, 12), rng.randint(1, 8)
    return [date(y, m, d) for d in range(a, rng.randint(a + 2, 12) + 1)]


def _dates_irregular(rng):
    y = rng.randint(1995, 2025)
    return [date(y + rng.randint(0, 3), rng.randint(1, 12), rng.randint(1, 12))
            for _ in range(rng.randint(5, 300))]


FAMILIES = {
    "monthly_on_day_k": _dates_monthly_day,
    "daily_run_each_year": _dates_daily_run_each_year,
    "quarterly": _dates_quarterly,
    "weekly": _dates_weekly,
    "business_days": _dates_business_days,
    "daily_short": _dates_daily_short,
    "irregular": _dates_irregular,
}


def _cases(family, n=25):
    rng = random.Random(f"{RNG_SEED}-{family}")
    for i in range(n):
        ds = FAMILIES[family](rng)
        ds = [d for d in ds if d.day <= 12] or [date(2020, 1, 2)]
        if rng.random() < 0.4:
            rng.shuffle(ds)
        yield i, ds


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_never_returns_the_wrong_order(family):
    wrong = []
    for i, ds in _cases(family):
        for order, fmt in (("DMY", "%d/%m/%Y"), ("MDY", "%m/%d/%Y")):
            r = resolve_column([d.strftime(fmt) for d in ds])
            if r.resolved and r.verdict != order:
                wrong.append((i, order, r.verdict, r.method, [d.isoformat() for d in ds[:4]]))
    assert not wrong, wrong


def test_mirror_twins_are_reported_not_resolved():
    # the reviewer's case: US-format 1-12 January over several years
    ds = [date(y, 1, d) for y in range(2018, 2023) for d in range(1, 13)]
    r = resolve_column([d.strftime("%m/%d/%Y") for d in ds])
    assert r.verdict == "AMBIGUOUS" and r.method == "competing"
    assert r.likely == "DMY"  # the preference is wrong here, which is why it is not applied
    r = resolve_column([d.strftime("%m/%d/%Y") for d in ds], accept_likely=True)
    assert r.verdict == "DMY" and r.method == "likely-accepted"


def test_weekday_evidence_still_proves_business_days_despite_a_twin():
    ds = [d for d in (date(2019, 1, 1) + timedelta(days=i) for i in range(365))
          if d.weekday() < 5 and d.day <= 12]
    for order, fmt in (("DMY", "%d/%m/%Y"), ("MDY", "%m/%d/%Y")):
        r = resolve_column([d.strftime(fmt) for d in ds])
        assert (r.verdict, r.method) == (order, "structure")
        assert any("weekdays" in x for x in r.reasons)
