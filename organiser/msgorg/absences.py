"""Find work absences in conversations and classify them from the evidence.

Interpretations are derived (recomputable) and kept apart from the source messages.
Status vocabulary (what the messages establish, never more):
  requested  - you asked for time off; no reply found that settles it
  proposed   - tentative ("might", "may need", "not sure if I can")
  stated     - you said you can't work; no acknowledgement found
  confirmed  - the other party acknowledged/approved it in a later message
  declined   - the other party refused
  cancelled  - you (or they) later withdrew it
  rescheduled- moved to another date (the new date is recorded)
  uncertain  - the date or the meaning could not be established
Whether you actually took the day off is never asserted: messages rarely establish it.
"""
from __future__ import annotations

import datetime as dt
import re

from . import dates as D

RULE_VERSION = "abs-1"

NEG_AVAIL = [r"\bcan'?t\b|\bcannot\b|\bcan not\b|\bwon'?t be able\b|\bwon'?t make it\b|\bnot able to\b|\bunable to\b",
             r"\bnot (?:going to|gonna) (?:make it|be (?:in|there|able))\b", r"\bwon'?t be (?:in|there|coming|around)\b"]
WORK_CTX = r"\b(work|come in|coming in|make it|shift|job|clean|the job|be there|be in|start|cover|do (?:it|the)|attend|show up|appointment|session|booking)\b"
SICK = r"\b(i'?m|i am|feeling|been|got|off) (?:sick|ill|unwell|poorly)\b|\bcall(?:ing)? in sick\b|\bsick day\b|\bin hospital\b|\bdoctor'?s? appointment\b"
REQUEST = r"\b(can|could|may) i (?:have|take|get|book|request)\b.*\boff\b|\bis it ok(?:ay)? if i (?:don'?t|take|miss|skip|have)\b|\bwould it be (?:ok|possible)\b|\brequest(?:ing)? (?:the day|time|a day|days) off\b|\bneed (?:the day|a day|\w+day|the \w+|some time|time|days) off\b|\bcan i (?:skip|miss|swap)\b|\bday off\b|\btime off\b"
TENTATIVE = r"\bmight\b|\bmay need\b|\bmay not\b|\bpossibly\b|\bprobably\b|\bnot sure (?:if|whether) i can\b|\bmaybe\b|\bthinking of\b|\bmight have to\b"
OFF = r"\b(?:off|holiday|vacation|leave|away)\b"
RETRACT = r"\bactually i can\b|\bnever ?mind\b|\bscratch that\b|\bafter all\b|\bi(?:'ll| will) be there\b|\bi can (?:come|make it|work) (?:in )?(?:after all|now)\b|\bignore (?:my|that|the) (?:last|previous)\b|\bcan still (?:come|make it|work)\b"
RESCHED = r"\breschedul\w*\b|\bmove (?:it|that|the \w+) to\b|\bswap\b|\binstead\b|\bpush (?:it )?(?:back|to)\b|\bcan (?:we|i) do\b"
THEIR_CANCEL = r"\b(?:don'?t|do not) need you\b|\bcancel(?:l?ed|ling)?\b.*\b(?:shift|booking|job|session|clean|appointment)\b|\bno work\b|\bnot needed\b"
ACK = r"^\s*(ok|okay|k|kk|sure|fine|no problem|no worries|np|noted|understood|got it|that'?s fine|that'?s ok|thats fine|thanks for letting me know|approved|yes|yep|of course|all good|sounds good)\b|\bget well\b|\bfeel better\b|\bhope you feel\b|\bthat'?s (?:fine|ok|okay|no problem)\b|\bno problem\b|\bapproved\b|\bwe'?ll manage\b|\bi'?ll cover\b|\bwe'?ll cover\b"
DENY = r"^\s*no\b(?! problem| worries)|\bneed you (?:in|there|to come)\b|\bcan'?t (?:let|give|approve|allow)\b|\bnot possible\b|\bwe really need\b|\bdenied\b|\bplease come in\b"


def _has(p, t):
    return re.search(p, t, re.I) is not None


def classify_message(text):
    """Return the absence kind of one message body, or None."""
    t = text.lower()
    if _has(RETRACT, t):
        return "retract"
    neg = any(_has(p, t) for p in NEG_AVAIL) and _has(WORK_CTX, t)
    sick = _has(SICK, t)
    req = _has(REQUEST, t)
    tent = _has(TENTATIVE, t) and (neg or req or sick or _has(OFF, t))
    if tent:
        return "tentative"
    if req:
        return "request"
    if neg or sick:
        return "statement"
    if _has(RESCHED, t) and (_has(OFF, t) or _has(WORK_CTX, t)):
        return "reschedule"
    return None


def _dt(ms):
    return dt.datetime.fromtimestamp(ms / 1000)


def analyse_conversation(msgs, day_first=True, reply_window_h=72, revision_days=21):
    """msgs: list of dicts (id, key, date_ms, direction, body) of ONE contact, any order.
    Returns findings (dicts) with evidence and revisions."""
    msgs = sorted(msgs, key=lambda m: (m["date_ms"], m["id"]))
    findings = []
    for i, m in enumerate(msgs):
        body = m["body"] or ""
        kind = None
        if m["direction"] == "sent":
            kind = classify_message(body)
            if kind in ("retract", None):
                continue
        elif m["direction"] == "received" and _has(THEIR_CANCEL, body):
            kind = "their_cancellation"
        else:
            continue
        when = _dt(m["date_ms"])
        refs = D.resolve(body, when, day_first=day_first)
        notes = [r[3] for r in refs if r[3]]
        inline_resched = None
        if refs and len(refs) > 1 and _has(RESCHED, body):
            # "I can't do Wednesday, can we do Friday instead?" -> absence Wednesday, moved to Friday
            inline_resched = refs[1]
            refs = refs[:1]
        if refs:
            start, end = refs[0][0], refs[-1][1]
            date_basis = "; ".join(r[2] for r in refs)
        else:
            # look one message back for the date being discussed (e.g. "Can you do Friday?" -> "Sorry I can't")
            prev = next((p for p in reversed(msgs[:i]) if (m["date_ms"] - p["date_ms"]) < 24 * 3600e3), None)
            prefs = D.resolve(prev["body"] or "", _dt(prev["date_ms"]), day_first) if prev else []
            if prefs:
                start, end, date_basis = prefs[0][0], prefs[0][1], f"from the preceding message: {prefs[0][2]}"
                notes.append("work date taken from the preceding message")
            else:
                start = end = when.date()
                date_basis = "no date mentioned; assumed the day of the message"
                notes.append("work date not stated in the message")
        f = {"first_msg": m["id"], "msg_key": m["key"], "sent_at": when.isoformat(timespec="minutes"),
             "work_start": start.isoformat(), "work_end": end.isoformat(), "kind": kind, "date_basis": date_basis,
             "notes": notes, "evidence": [_ev(m, "statement" if kind != "their_cancellation" else "their message")],
             "revisions": [], "status": None, "actually_taken": "not established by these messages"}
        if inline_resched:
            f["status_override"] = "rescheduled"
            f["rescheduled_to"] = [inline_resched[0].isoformat(), inline_resched[1].isoformat()]
        # replies from the other party within the window
        reply_status = None
        for n in msgs[i + 1:]:
            if (n["date_ms"] - m["date_ms"]) > reply_window_h * 3600e3:
                break
            if n["direction"] == "sent" and classify_message(n["body"] or "") in ("statement", "request", "tentative"):
                if D.resolve(n["body"] or "", _dt(n["date_ms"]), day_first):
                    break  # a new, separately dated absence starts; stop attributing replies
            if n["direction"] == "received" and kind != "their_cancellation":
                if _has(DENY, n["body"] or ""):
                    reply_status = "declined"
                    f["evidence"].append(_ev(n, "reply: refusal"))
                    break
                if _has(ACK, n["body"] or ""):
                    reply_status = "confirmed"
                    f["evidence"].append(_ev(n, "reply: acknowledgement"))
                    break
        # later revisions: retractions / reschedules / contradicting messages within revision_days
        for n in msgs[i + 1:]:
            if (n["date_ms"] - m["date_ms"]) > revision_days * 86400e3:
                break
            nb = n["body"] or ""
            k = classify_message(nb) if n["direction"] == "sent" else None
            nrefs = D.resolve(nb, _dt(n["date_ms"]), day_first)
            same_date = any(r[0] <= end and r[1] >= start for r in nrefs)
            near = (n["date_ms"] - m["date_ms"]) < 48 * 3600e3
            if k == "retract" and (same_date or (near and not nrefs)):
                f["revisions"].append(_ev(n, "you withdrew it"))
                f["status_override"] = "cancelled"
            elif _has(RESCHED, nb) and (same_date or near) and n["id"] != m["id"]:
                other = [r for r in nrefs if not (r[0] <= end and r[1] >= start)]
                lab = "rescheduled" + (f" to {other[0][0].isoformat()}" if other else "")
                f["revisions"].append(_ev(n, lab))
                if other:
                    f["status_override"] = "rescheduled"
                    f["rescheduled_to"] = [other[0][0].isoformat(), other[0][1].isoformat()]
            elif n["direction"] == "received" and same_date and _has(DENY, nb) and reply_status != "declined":
                f["revisions"].append(_ev(n, "later refusal"))
                f["status_override"] = "declined"
        base = {"statement": "stated", "request": "requested", "tentative": "proposed", "reschedule": "uncertain",
                "their_cancellation": "cancelled"}[kind]
        status = reply_status if (reply_status and kind != "tentative") else base
        if kind == "tentative" and reply_status == "confirmed":
            notes.append("the other party replied positively, but your message was tentative")
        status = f.pop("status_override", status)
        if "work date not stated in the message" in notes and status in ("stated", "requested"):
            status = "uncertain"
        f["status"] = status
        findings.append(f)
    return _merge(findings)


def _merge(fs):
    """One finding per (work date, statement thread): drop findings that are just later messages of the same absence."""
    out = []
    for f in fs:
        dup = next((g for g in out if g["work_start"] == f["work_start"] and g["kind"] == f["kind"]
                    and abs(_iso(g["sent_at"]) - _iso(f["sent_at"])) < dt.timedelta(hours=12)), None)
        if dup:
            dup["evidence"].extend(e for e in f["evidence"] if e not in dup["evidence"])
            continue
        out.append(f)
    return out


def _iso(s):
    return dt.datetime.fromisoformat(s)


def _ev(m, role):
    return {"msg": m["id"], "key": m["key"], "at": _dt(m["date_ms"]).isoformat(timespec="minutes"),
            "direction": m["direction"], "role": role, "excerpt": (m["body"] or "")[:300]}
