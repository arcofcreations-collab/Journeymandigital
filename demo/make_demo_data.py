"""Build the demo CSVs from the real benchmark sources (run bench/fetch_data.py first).

The values are real; only the date *rendering* (DD/MM/YYYY or MM/DD/YYYY) and
the row selection are ours, to reproduce what a UK/EU or US export looks like.
"""
import csv
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "bench", "data")


def rows_csv(path):
    with open(os.path.join(DATA, path), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write(name, header, rows):
    with open(os.path.join(HERE, name), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print("wrote", name, len(rows), "rows")


def dmy(iso):
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def mdy(iso):
    y, m, d = iso[:10].split("-")
    return f"{m}/{d}/{y}"


# 1. Ordinary: US CPI index, monthly, 2015-2019, exported day-first (UK style)
cpi = [r for r in rows_csv("cpi-us/data/cpiai.csv") if "2015-01-01" <= r["Date"] <= "2019-12-01"]
write("cpi_uk_export.csv", ["Date", "Index", "Inflation"],
      [[dmy(r["Date"]), r["Index"], r["Inflation"]] for r in cpi])

# 2. Challenging: unemployment by industry (panel: 14 series x monthly),
#    US-style month-first, rows shuffled (e.g. sorted by another column)
un = json.load(open(os.path.join(DATA, "vega/data/unemployment-across-industries.json")))
rows = [[mdy(r["date"]), r["series"], r["count"], r["rate"]] for r in un if r["date"][:4] in ("2005", "2006")]
random.Random(7).shuffle(rows)
write("unemployment_panel_us_shuffled.csv", ["date", "series", "count", "rate"], rows)

# 3. Genuinely ambiguous: one year of monthly data dated on the 1st (12 rows)
bond = [r for r in rows_csv("bond-yields-us-10y/data/monthly.csv") if r["Date"].startswith("2019")]
write("bond_yields_one_year.csv", ["Date", "Rate"], [[dmy(r["Date"]), r["Rate"]] for r in bond])

# 4. Representative miss: 8 consecutive days inside the first 12 days of a month
temps = rows_csv("jbrownlee/daily-max-temperatures.csv")[3:11]
write("daily_temps_short.csv", ["Date", "Temperature"], [[dmy(r["Date"]), r["Temperature"]] for r in temps])

# 5. File-level consistency: an ambiguous column next to one that settles the order
write("orders_start_end.csv", ["Order start", "Invoice date", "Amount"],
      [[dmy(r["Date"]), dmy(r["Date"][:8] + "28"), r["Rate"]] for r in bond])

# 7. Proof despite a mirror pattern: S&P 500 close on the first trading day of each
#    month, 2000-2004 (60 rows, real values), exported day-first
sp = rows_csv("vega/data/sp500-2000.csv")
first = {}
for r in sp:
    first.setdefault(r["date"][:7], r)
fm = [r for r in first.values() if r["date"] < "2005-01-01"]
write("sp500_first_trading_day_uk.csv", ["Date", "Close"], [[dmy(r["date"]), r["close"]] for r in fm])

# 8. Timestamps with fractional seconds, and one invalid cell
write("sensor_log_uk.csv", ["Reading time", "Value"], [
    ["13/04/2021 12:30:00.123456", "4.1"], ["13/04/2021 12:30:01.5", "4.3"],
    ["14/04/2021 08:00", "3.9"], ["n/k", "4.0"], ["15/04/2021 1:05 PM", "4.4"]])

# 6. Invalid inputs
write("mixed_formats.csv", ["when"], [["01/02/2020"], ["2020-03-04"], ["05/06/2020"]] * 5)
write("not_dates.csv", ["version", "ratio"], [["1.2.3", "1/2"], ["2.0.1", "3/4"]])
open(os.path.join(HERE, "empty.csv"), "w").close()
