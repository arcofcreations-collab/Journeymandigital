"""Build the three reviewer variants from the organiser baseline and render their deltas (no model calls)."""
import os, shutil, subprocess, sys
ORG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "organiser"))
OUT = sys.argv[1]
OLD = '''                start = end = when.date()
                date_basis = "no date mentioned; assumed the day of the message"
                notes.append("work date not stated in the message")'''
NEW = '''                late = when.hour >= 18
                start = end = when.date() + dt.timedelta(days=1 if late else 0)
                date_basis = f"no date mentioned; sent at {when:%H:%M} so taken as {'next day' if late else 'same day'}"
                notes.append("work date not stated in the message")
                notes.append(date_basis)'''
BUG_OLD = '''            start, end = refs[0][0], refs[-1][1]
            date_basis = "; ".join(r[2] for r in refs)'''
BUG_NEW = '''            start, end = refs[0][0], refs[-1][1]
            date_basis = "; ".join(r[2] for r in refs)
            if when.hour >= 18 and refs[0][2] in ("today", "tonight"):  # evening rule (wrongly) also applied to "today"
                start, end = start + dt.timedelta(days=1), end + dt.timedelta(days=1)'''
RCS_OLD = '''    if r["rcs"] and not sent_rcs:
        gaps.insert(1, f"{r['rcs']} RCS-like messages imported but none of them sent by you: outgoing RCS is likely missing.")'''
VARIANTS = {"V1_legit": [("msgorg/absences.py", OLD, NEW)],
            "V2_legit_plus_subtle_bug": [("msgorg/absences.py", OLD, NEW), ("msgorg/absences.py", BUG_OLD, BUG_NEW)],
            "V3_legit_plus_unseen_fault": [("msgorg/absences.py", OLD, NEW), ("msgorg/store.py", RCS_OLD, "")]}
for name, patches in VARIANTS.items():
    d = os.path.join(OUT, name)
    shutil.copytree(ORG, d, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    for f, a, b in patches:
        p = os.path.join(d, f); s = open(p).read(); assert a in s, (name, f); open(p, "w").write(s.replace(a, b, 1))
    delta = subprocess.run([sys.executable, "dr/dr.py", "diff"], cwd=d, capture_output=True, text=True).stdout
    open(os.path.join(OUT, name + ".delta.txt"), "w").write(delta)
    tests = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=d, capture_output=True, text=True).stdout.strip().splitlines()[-1]
    hid = subprocess.run([sys.executable, "-m", "pytest", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hidden_check.py"), "-q"],
                         cwd=d, env=dict(os.environ, ORG=d), capture_output=True, text=True).stdout.strip().splitlines()[-1]
    print(f"{name}: delta {len(delta)} chars, {delta.splitlines()[-1]} | existing tests: {tests} | hidden check: {hid}")
