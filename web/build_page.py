"""Build the shareable page: inline web/dmguard.js and the demo samples.

usage: python3 demo/make_demo_data.py && python3 web/build_page.py
writes web/dist/dmguard.html
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "..", "demo")

SAMPLES = [
    ("UK-style monthly prices", "cpi_uk_export.csv",
     "US consumer price index 2015-2019, exported day-first (60 rows)"),
    ("First trading day, 2000-2004", "sp500_first_trading_day_uk.csv",
     "S&P 500 close on the first trading day of each month, day-first (60 rows): proven by weekdays"),
    ("US-style jobs panel, shuffled", "unemployment_panel_us_shuffled.csv",
     "Unemployment by industry, 14 series x 24 months, month-first, rows shuffled (336 rows)"),
    ("Two linked date columns", "orders_start_end.csv",
     "An ambiguous column next to one whose values settle the order"),
    ("One year of monthly data", "bond_yields_one_year.csv",
     "12 values dated on the 1st: genuinely ambiguous"),
    ("Eight days in January", "daily_temps_short.csv",
     "8 consecutive daily values early in a month: too little evidence"),
    ("Timestamps + a bad cell", "sensor_log_uk.csv",
     "Fractional seconds kept exactly; an invalid cell is flagged"),
]


def main():
    tpl = open(os.path.join(HERE, "page_template.html"), encoding="utf-8").read()
    js = open(os.path.join(HERE, "dmguard.js"), encoding="utf-8").read()
    samples = []
    for label, fn, desc in SAMPLES:
        with open(os.path.join(DEMO, fn), encoding="utf-8") as fh:
            samples.append({"label": label, "desc": desc, "text": fh.read()})
    out = tpl.replace("/*DMGUARD_JS*/", js).replace(
        "/*SAMPLES_JSON*/", json.dumps(samples).replace("</", "<\\/"))
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    dst = os.path.join(HERE, "dist", "dmguard.html")
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("wrote", dst, len(out), "bytes")


if __name__ == "__main__":
    main()
