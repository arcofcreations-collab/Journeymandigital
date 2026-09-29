"""Show how pandas and DuckDB read a demo file's date column (for comparison)."""
import sys
import warnings

import duckdb
import pandas as pd

path, col = sys.argv[1], sys.argv[2]
df = pd.read_csv(path, dtype=str)
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    try:
        parsed = pd.to_datetime(df[col])
        note = (f"warnings: {[str(w.message)[:80] for w in caught]}" if caught
                else "no warning emitted")
        print(f"pandas {pd.__version__} to_datetime: {df[col].iloc[0]} -> {parsed.iloc[0].date()}, "
              f"{df[col].iloc[1]} -> {parsed.iloc[1].date()}, ... "
              f"span {parsed.min().date()} .. {parsed.max().date()}  ({note})")
    except Exception as exc:  # noqa: BLE001
        print(f"pandas raised: {type(exc).__name__}: {str(exc)[:100]}")
rel = duckdb.read_csv(path)
names = rel.columns
i = names.index(col)
vals = [r[i] for r in rel.fetchall()]
print(f"duckdb {duckdb.__version__} read_csv: column type {rel.types[i]}; "
      f"{df[col].iloc[0]} -> {vals[0]}, {df[col].iloc[1]} -> {vals[1]}, span {min(vals)} .. {max(vals)}")
