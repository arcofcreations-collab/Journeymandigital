#!/usr/bin/env bash
# Live demo walkthrough (dmguard 1.1). Run from the repository root:  bash demo/run_demo.sh
# Prints every command before running it; exit codes are shown.
cd "$(dirname "$0")/.."
run() { echo; echo "\$ $*"; "$@"; echo "[exit code $?]"; }

echo "=== 1. UK-style export of monthly US CPI (01/02/2015 = 1 Feb 2015) ==="
run python3 demo/what_others_see.py demo/cpi_uk_export.csv Date
run python3 -m dmguard check demo/cpi_uk_export.csv
echo "# 'the 1st of every month' and '1-12 January every year' are both regular: a preference, not proof."
echo "# Knowing the file is monthly, the user accepts the likely order explicitly:"
run python3 -m dmguard fix demo/cpi_uk_export.csv -o /tmp/cpi_clean.csv --accept-likely
run head -3 /tmp/cpi_clean.csv

echo; echo "=== 2. Proof: S&P 500 close on the first trading day of each month, 2000-2004, UK style ==="
run python3 demo/what_others_see.py demo/sp500_first_trading_day_uk.csv Date
run python3 -m dmguard check demo/sp500_first_trading_day_uk.csv

echo; echo "=== 3. US-style panel (14 industries x 24 months), rows shuffled ==="
run python3 demo/what_others_see.py demo/unemployment_panel_us_shuffled.csv date
run python3 -m dmguard check demo/unemployment_panel_us_shuffled.csv

echo; echo "=== 4. Two date columns: a hint, and an explicit assumption ==="
run python3 -m dmguard check demo/orders_start_end.csv
run python3 -m dmguard check demo/orders_start_end.csv --assume-same-convention

echo; echo "=== 5. Genuinely ambiguous: 12 monthly values of a single year ==="
run python3 -m dmguard check demo/bond_yields_one_year.csv
run python3 -m dmguard fix demo/bond_yields_one_year.csv -o /tmp/bond.csv --assume DMY

echo; echo "=== 6. Representative miss: 8 consecutive days early in a month ==="
run python3 -m dmguard check demo/daily_temps_short.csv

echo; echo "=== 7. Lossless timestamps and an invalid cell ==="
run python3 -m dmguard fix demo/sensor_log_uk.csv -o /tmp/sensor.csv
run cat /tmp/sensor.csv

echo; echo "=== 8. Invalid inputs ==="
run python3 -m dmguard check demo/mixed_formats.csv
run python3 -m dmguard check demo/not_dates.csv
run python3 -m dmguard check demo/empty.csv
run python3 -m dmguard check demo/does_not_exist.csv
