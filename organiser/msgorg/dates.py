"""Resolve work-date references in a message relative to its timestamp.

Returns a list of (start_date, end_date, matched_text, ambiguity_note|None). Rules are deliberately
conservative: anything ambiguous carries a note instead of being silently resolved.
"""
from __future__ import annotations

import datetime as dt
import re

WD = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# full names (+ common unambiguous short forms); "sat", "sun", "wed" alone are too ambiguous in prose
WD_RE = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|tues|thurs|weds)"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MON_RE = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"


def _wd(s):
    s = s.lower()[:3]
    return [w[:3] for w in WD].index(s)


def _mon(s):
    return [m[:3] for m in MONTHS].index(s.lower()[:3]) + 1


def _next_wd(base, wd, strictly_after=True):
    delta = (wd - base.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return base + dt.timedelta(days=delta)


def _safe(y, m, d):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def resolve(text, sent: dt.datetime, day_first=True):
    t = " " + text.lower() + " "
    base = sent.date()
    out = []
    used = []

    def add(a, b, span, note=None):
        if a is None or b is None:
            return
        if any(not (span[1] <= u[0] or span[0] >= u[1]) for u in used):
            return
        used.append(span)
        out.append((a, b, t[span[0]:span[1]].strip(), note))

    # ranges of weekdays: "monday to wednesday", "mon-wed"
    for m in re.finditer(rf"\b{WD_RE}\s*(?:-|to|through|thru|until|till)\s*{WD_RE}\b", t):
        a = _next_wd(base, _wd(m.group(1)), strictly_after=False)
        b = a + dt.timedelta(days=(_wd(m.group(2)) - _wd(m.group(1))) % 7)
        add(a, b, m.span(), "weekday range resolved to the next occurrence")
    # explicit "12 march", "march 12", "march 12th - 14th"
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MON_RE}\b(?:\s*(?:-|to)\s*(\d{{1,2}})(?:st|nd|rd|th)?\b)?", t):
        d, mo = int(m.group(1)), _mon(m.group(2))
        a = _year_near(base, mo, d)
        b = _year_near(base, mo, int(m.group(3))) if m.group(3) else a
        add(a, b, m.span())
    for m in re.finditer(rf"\b{MON_RE}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:\s*(?:-|to)\s*(\d{{1,2}})(?:st|nd|rd|th)?\b)?", t):
        mo, d = _mon(m.group(1)), int(m.group(2))
        a = _year_near(base, mo, d)
        b = _year_near(base, mo, int(m.group(3))) if m.group(3) else a
        add(a, b, m.span())
    # numeric 12/3 or 12/03/2026
    for m in re.finditer(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t):
        x, y = int(m.group(1)), int(m.group(2))
        d, mo = (x, y) if day_first else (y, x)
        note = None
        if x <= 12 and y <= 12 and x != y:
            note = f"numeric date read as {'day/month' if day_first else 'month/day'}; the other order is possible"
        if m.group(3):
            yr = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
            a = _safe(yr, mo, d)
        else:
            a = _year_near(base, mo, d)
        add(a, a, m.span(), note)
    # "the 12th"
    for m in re.finditer(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b", t):
        d = int(m.group(1))
        a = _safe(base.year, base.month, d)
        if a is not None and a < base:
            nm = base.month % 12 + 1
            a = _safe(base.year + (base.month == 12), nm, d)
        add(a, a, m.span(), "day of month resolved to its next occurrence")
    # relative words
    for pat, off in ((r"\bday after tomorrow\b", 2), (r"\btomorrow\b|\btmrw\b|\btmr\b", 1),
                     (r"\btoday\b|\btonight\b|\bthis morning\b|\bthis afternoon\b|\bthis evening\b|\bright now\b", 0)):
        for m in re.finditer(pat, t):
            add(base + dt.timedelta(days=off), base + dt.timedelta(days=off), m.span())
    for m in re.finditer(r"\bnext week\b", t):
        mon = _next_wd(base, 0)
        add(mon, mon + dt.timedelta(days=4), m.span(), "'next week' taken as Monday-Friday")
    for m in re.finditer(r"\bthis week\b|\brest of the week\b", t):
        fri = base + dt.timedelta(days=(4 - base.weekday()) % 7)
        add(base, fri, m.span(), "'this week' taken as today until Friday")
    for m in re.finditer(r"\b(?:this )?weekend\b", t):
        sat = _next_wd(base, 5, strictly_after=False)
        add(sat, sat + dt.timedelta(days=1), m.span())
    # single weekdays, optionally "next"/"this"
    for m in re.finditer(rf"\b(next|this|on|coming)?\s*{WD_RE}\b", t):
        q = (m.group(1) or "").strip()
        wd = _wd(m.group(2))
        if q == "this" and wd == base.weekday():
            a, note = base, None
        else:
            a = _next_wd(base, wd)
            note = None
            if q == "next" and (a - base).days < 7:
                note = f"'next {WD[wd]}' read as {a.isoformat()}; it may mean {(a + dt.timedelta(days=7)).isoformat()}"
        add(a, a, m.span(), note)
    out.sort(key=lambda x: x[0])
    return out


def _year_near(base, mo, d):
    """Month/day without a year: the occurrence closest to the message date (within +-6 months)."""
    cands = [c for c in (_safe(base.year - 1, mo, d), _safe(base.year, mo, d), _safe(base.year + 1, mo, d)) if c]
    return min(cands, key=lambda c: abs((c - base).days)) if cands else None
