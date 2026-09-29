import random
from datetime import date, datetime, timedelta

import pytest

from dmguard import parse_with_order, resolve_column


def render(dates, order, fmt_time=False):
    f = {"DMY": "%d/%m/%Y", "MDY": "%m/%d/%Y", "YMD": "%Y-%m-%d", "YDM": "%Y-%d-%m"}[order]
    return [d.strftime(f) for d in dates]


def weekly(start, n):
    return [start + timedelta(weeks=i) for i in range(n)]


def test_validity_decides_when_a_day_exceeds_12():
    r = resolve_column(["01/02/2020", "13/02/2020"])
    assert (r.verdict, r.method) == ("DMY", "validity")
    r = resolve_column(["02/01/2020", "02/13/2020"])
    assert (r.verdict, r.method) == ("MDY", "validity")


def test_identical_readings():
    r = resolve_column(["01/01/2020", "02/02/2020", "03/03/2021"])
    assert r.resolved and r.method == "identical"


@pytest.mark.parametrize("order", ["DMY", "MDY"])
def test_weekly_mondays_resolved_by_structure(order):
    dates = [d for d in weekly(date(2021, 1, 4), 60) if d.day <= 12]
    r = resolve_column(render(dates, order))
    assert (r.verdict, r.method) == (order, "structure")
    assert r.evidence_bits > 50


@pytest.mark.parametrize("order", ["DMY", "MDY"])
def test_multi_year_monthly_first_of_month(order):
    dates = [date(2018 + i // 12, i % 12 + 1, 1) for i in range(36)]
    r = resolve_column(render(dates, order))
    assert r.verdict == order


def test_single_year_monthly_is_genuinely_ambiguous_and_abstains():
    dates = [date(2020, m, 1) for m in range(1, 13)]
    r = resolve_column(render(dates, "DMY"))
    assert r.verdict == "AMBIGUOUS" and r.method == "abstained"


@pytest.mark.parametrize("order", ["DMY", "MDY"])
def test_shuffled_business_days_use_weekday_evidence(order):
    rng = random.Random(3)
    dates = [date(2019, m, d) for m in range(1, 13) for d in range(1, 13)
             if date(2019, m, d).weekday() < 5]
    rng.shuffle(dates)
    r = resolve_column(render(dates, order))
    assert r.verdict == order


@pytest.mark.parametrize("order", ["YMD", "YDM"])
def test_year_first_layout(order):
    dates = [d for d in weekly(date(2022, 1, 3), 50) if d.day <= 12]
    r = resolve_column(render(dates, order))
    assert r.verdict == order


def test_two_digit_years_and_times():
    base = datetime(2021, 3, 1, 9, 30)
    vals = [(base + timedelta(days=7 * i)).strftime("%d.%m.%y %H:%M") for i in range(40)]
    vals = [v for v in vals if int(v[:2]) <= 12]
    r = resolve_column(vals)
    assert r.verdict == "DMY"
    parsed = parse_with_order(vals, "DMY")
    assert parsed[0] == datetime(2021, 3, 1, 9, 30)


def test_am_pm_times():
    r = resolve_column(["03/04/2021 1:05 PM", "03/05/2021 12:00 AM"])
    assert r.n_values == 2
    assert parse_with_order(["03/04/2021 1:05 PM"], "MDY")[0] == datetime(2021, 3, 4, 13, 5)


def test_symmetry_of_the_model():
    rng = random.Random(7)
    for _ in range(30):
        start = date(2000, 1, 1) + timedelta(days=rng.randrange(8000))
        step = rng.choice([1, 7, 14, 30])
        dates = [start + timedelta(days=step * i) for i in range(rng.randrange(5, 80))]
        dates = [d for d in dates if d.day <= 12] or [date(2020, 1, 2)]
        if rng.random() < 0.5:
            rng.shuffle(dates)
        a = resolve_column(render(dates, "DMY"))
        b = resolve_column(render(dates, "MDY"))
        assert abs(a.evidence_bits - b.evidence_bits) < 1e-9
        swap = {"DMY": "MDY", "MDY": "DMY"}
        assert swap.get(a.verdict, a.verdict) == b.verdict


def test_non_date_and_mixed_and_empty():
    assert resolve_column(["apple", "pear", "1.5"]).verdict == "NOT_DATE"
    assert resolve_column(["1.2.3", "1.2.4", "2.0.0"]).verdict == "NOT_DATE"
    assert resolve_column(["", "NA", None]).verdict == "EMPTY"
    r = resolve_column(["01/02/2020", "2020-02-03", "04/05/2020"] * 10)
    assert r.verdict == "INCONSISTENT"
    r = resolve_column(["01/02/2020", "01-03-2020"])
    assert r.verdict == "INCONSISTENT"


def test_impossible_under_both_orders():
    r = resolve_column(["31/02/2020", "02/31/2020"])
    assert r.verdict == "INCONSISTENT"
    assert "impossible" in r.reasons[0]


def test_leap_day_validity():
    assert resolve_column(["29/02/2020", "01/03/2020"]).verdict == "DMY"
    assert resolve_column(["02/29/2021"]).verdict == "INCONSISTENT"


def test_missing_values_are_ignored():
    dates = [d for d in weekly(date(2021, 1, 4), 60) if d.day <= 12]
    vals = render(dates, "MDY")
    vals[3] = ""
    vals[7] = "NA"
    r = resolve_column(vals)
    assert r.verdict == "MDY" and r.n_missing == 2
