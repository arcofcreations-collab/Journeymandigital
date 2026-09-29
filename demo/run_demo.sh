#!/usr/bin/env bash
# Live demo walkthrough. Run from the repository root:  bash demo/run_demo.sh
# Prints every command before running it; exit codes are shown.
cd "$(dirname "$0")/.."
run() { echo; echo "\$ $*"; "$@"; echo "[exit code $?]"; }

echo "=== 1. Ordinary case: a UK-style export of monthly US CPI (01/02/2015 = 1 Feb 2015) ==="
run python3 demo/what_others_see.py demo/cpi_uk_export.csv Date
run python3 -m dmguard check demo/cpi_uk_export.csv
run python3 -m dmguard fix demo/cpi_uk_export.csv -o /tmp/cpi_clean.csv
run head -4 /tmp/cpi_clean.csv

echo; echo "=== 2. Challenging case: US-style panel (14 industries x 24 months), rows shuffled ==="
run python3 demo/what_others_see.py demo/unemployment_panel_us_shuffled.csv date
run python3 -m dmguard check demo/unemployment_panel_us_shuffled.csv

echo; echo "=== 3. File-level consistency: one column settles the order for its neighbour ==="
run python3 -m dmguard check demo/orders_start_end.csv

echo; echo "=== 4. Genuinely ambiguous: 12 monthly values of a single year -> refuses to guess ==="
run python3 -m dmguard check demo/bond_yields_one_year.csv
run python3 -m dmguard fix demo/bond_yields_one_year.csv -o /tmp/bond.csv --assume DMY

echo; echo "=== 5. Representative miss: 8 consecutive days early in a month -> abstains (no help, no harm) ==="
run python3 -m dmguard check demo/daily_temps_short.csv

echo; echo "=== 6. Invalid inputs ==="
run python3 -m dmguard check demo/mixed_formats.csv
run python3 -m dmguard check demo/not_dates.csv
run python3 -m dmguard check demo/empty.csv
run python3 -m dmguard check demo/does_not_exist.csv
