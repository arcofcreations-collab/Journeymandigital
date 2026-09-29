"""Check that web/dmguard.js gives the same verdicts as the Python reference.

Columns: every DEV and TEST benchmark case, the demo files, and synthetic
stress columns (structureless, sorted/unsorted, up to 6,000 rows so the
long-column subsampling path runs). Requires Node >= 16 and the benchmark
data (python3 bench/fetch_data.py).
"""
import csv
import glob
import json
import os
import random
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "bench"))
from cases import generate  # noqa: E402

from dmguard.core import resolve_column  # noqa: E402

cols = [c.strings for sp in ("DEV", "TEST") for c in generate(sp)]
for fn in sorted(glob.glob(os.path.join(HERE, "..", "demo", "*.csv"))):
    rows = list(csv.reader(open(fn, encoding="utf-8")))
    if len(rows) > 1:
        cols += [[r[j] if j < len(r) else "" for r in rows[1:]] for j in range(len(rows[0]))]
rng = random.Random(99)
for n in (6, 12, 24, 60, 250, 1000, 2500, 6000):
    for srt in (False, True):
        for _ in range(12 if n < 2500 else 3):
            ds = [date(2000 + rng.randrange(5), rng.randrange(1, 13), rng.randrange(1, 13)) for _ in range(n)]
            if srt:
                ds.sort()
            cols.append([d.strftime("%d/%m/%Y") for d in ds])
bd = [d for d in (date(2001, 1, 1) + timedelta(days=i) for i in range(4000)) if d.weekday() < 5 and d.day <= 12]
for n in (30, 300, 3000):
    cols.append([rng.choice(bd).strftime("%m/%d/%Y 09:%M:00".replace("%M", "30")) for _ in range(n)])

from dmguard.core import iso_with_order  # noqa: E402

cols.append(["13/04/2021 12:30:00.123456", "14/04/2021 08:00:00,5", "15/04/2021 07:05",
             "16/04/2021 1:05 PM", "17/04/2021 23:59:59.123456789", "BAD", ""])
py = []
for c in cols:
    r = resolve_column(c)
    ra = resolve_column(c, accept_likely=True)
    iso = iso_with_order(c, ra.verdict) if ra.resolved else None
    py.append([r.verdict, r.method, r.evidence_bits, r.likely, r.n_unparsed, ra.verdict, ra.method, iso])
proc = subprocess.run(["node", os.path.join(HERE, "parity_node.js")], input=json.dumps(cols),
                      capture_output=True, text=True, check=True)
js = json.loads(proc.stdout)

def same(p, j):
    return (p[:2] == j[:2] and abs(p[2] - j[2]) <= 1e-6 * max(1.0, abs(p[2])) and p[3:] == j[3:])


mism = [(i, p, j) for i, (p, j) in enumerate(zip(py, js)) if not same(p, j)]
summary = {"columns": len(cols), "verdict_or_method_mismatches": sum(p[:2] != j[:2] or p[3:] != j[3:] for _, p, j in mism),
           "evidence_bit_mismatches": len(mism)}
print(json.dumps(summary))
for i, p, j in mism[:10]:
    print("MISMATCH", i, p, j, cols[i][:5])
with open(os.path.join(HERE, "parity_result.json"), "w") as fh:
    json.dump(summary, fh, indent=1)
sys.exit(1 if mism else 0)
