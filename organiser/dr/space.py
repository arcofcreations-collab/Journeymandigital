"""Declared behaviour space for the organiser: a seeded synthetic conversation corpus + the questions the app answers.

The space is the *only* thing Delta Review can see: behaviour outside it is unverified by the review (by design;
the report says so). Everything is synthetic.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from msgorg import app as A, store as S  # noqa: E402

DATE_EXPR = ["tomorrow", "today", "on Friday", "Monday", "next Tuesday", "this Thursday", "on the 14th", "12/3", "March 20",
             "Monday to Wednesday", "this weekend", "next week", "", ""]
STATEMENT = ["Sorry I can't come in {d}", "I won't be able to work {d}", "I'm sick, can't make it {d}", "I can't do the shift {d}",
             "Not going to make it {d}, really sorry", "I'm unable to work {d}"]
REQUEST = ["Can I have {d} off?", "Is it ok if I don't come in {d}?", "Could I take {d} off please", "Would it be possible to have {d} off?"]
TENTATIVE = ["I might need {d} off", "I may not be able to work {d}", "Not sure if I can make it {d}", "Possibly can't come in {d}, will confirm"]
RETRACT = ["Actually I can come in after all", "Never mind, I'll be there", "Scratch that, I can make it"]
RESCHED = ["Can we move it to {d2} instead?", "Could I swap to {d2}?"]
ACK = ["Ok no problem", "Sure that's fine", "Get well soon", "Noted, thanks for letting me know", "No worries"]
DENY = ["No, we really need you", "Sorry, we need you in", "Not possible this time"]
CHAT = ["See you soon", "Thanks!", "What time do I start?", "Running 5 min late", "Did you get my invoice?", "Can you send the address?"]
PERSONAL = ["can't make it to the gym {d}", "can't do dinner {d} sorry", "won't make the party {d}"]
THEIR_CANCEL = ["We don't need you {d}, the place is closed", "Your shift {d} is cancelled"]


def corpus(seed=7, n_contacts=40, base=dt.datetime(2026, 2, 2, 8, 0)):
    rng = random.Random(seed)
    convs = []
    for c in range(n_contacts):
        kind = rng.choice(["work"] * 3 + ["personal"])
        name = f"{'Client' if kind == 'work' else 'Friend'} {c:02d}"
        addr = f"+1555{c:07d}"
        t = base + dt.timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 12))
        msgs = []
        for _ in range(rng.randint(3, 9)):
            t += dt.timedelta(hours=rng.choice([1, 3, 9, 20, 30, 50]), minutes=rng.randint(0, 59))
            d = rng.choice(DATE_EXPR)
            if kind == "personal":
                pool = [(PERSONAL, 2), (CHAT, 1), (ACK, 1)]
            else:
                pool = [(STATEMENT, 2), (REQUEST, 2), (TENTATIVE, 1), (CHAT, 2), (RETRACT, 1), (RESCHED, 1), (THEIR_CANCEL, 1)]
            tpl_set = rng.choices([p for p, _ in pool], [w for _, w in pool])[0]
            sent = tpl_set not in (THEIR_CANCEL,) and rng.random() < 0.9
            body = rng.choice(tpl_set).format(d=d, d2=rng.choice(["Friday", "Saturday", "the 20th"])).replace("  ", " ").strip()
            msgs.append((t, 2 if sent else 1, body))
            if tpl_set in (STATEMENT, REQUEST, TENTATIVE) and rng.random() < 0.7:
                t2 = t + dt.timedelta(minutes=rng.choice([5, 40, 300, 2000]))
                msgs.append((t2, 1, rng.choice(ACK if rng.random() < 0.75 else DENY)))
                t = t2
        convs.append({"name": name, "addr": addr, "kind": kind, "msgs": msgs})
    return convs


def write_xml(convs, path):
    from xml.sax.saxutils import quoteattr as q
    xs = []
    for cv in convs:
        for t, d, b in cv["msgs"]:
            xs.append(f'<sms address={q(cv["addr"])} date="{int(t.timestamp() * 1000)}" type="{d}" body={q(b)} contact_name={q(cv["name"])} />')
    with open(path, "w") as fh:
        fh.write(f'<?xml version="1.0"?>\n<smses count="{len(xs)}">\n' + "\n".join(xs) + "\n</smses>\n")


QUERIES = [dict(text="off"), dict(text="sick", direction="sent"), dict(contact="Client 03"), dict(start="2026-02-10", end="2026-02-14"),
           dict(text="can't", job="work")]


def observe(seed=7):
    """Run the app over the space; return {observation key: value} (JSON-able, deterministic)."""
    tmp = tempfile.mkdtemp(prefix="dr-space-")
    convs = corpus(seed)
    x = os.path.join(tmp, "b.xml")
    write_xml(convs, x)
    db = S.open_db(os.path.join(tmp, "a.db"))
    imp = S.import_file(db, x)
    for cv in convs:
        if cv["kind"] == "work":
            A.set_job(db, cv["name"], "work")
    A.recompute_absences(db)
    obs = {"import": {k: imp[k] for k in ("parsed", "added", "duplicates", "errors", "sms", "mms")}}
    imp2 = S.import_file(db, x)
    obs["reimport"] = {k: imp2[k] for k in ("added", "duplicates")}
    text = {m["id"]: m["body"] for m in map(dict, db.execute("select id, body from messages"))}
    for f in A.absences(db, contexts=None, include_rejected=True):
        k = f"absence|{f['display']}|{f['evidence'][0]['excerpt'][:50]}|{f['sent_at']}"
        obs[k] = {"work": [f["work_start"], f["work_end"]], "status": f["status"], "kind": f["kind"], "context": f.get("context"),
                  "evidence": [text.get(e["msg"], "")[:60] for e in f["evidence"]],
                  "revisions": [text.get(e["msg"], "")[:60] for e in f["revisions"]],
                  "rescheduled_to": f.get("rescheduled_to"), "notes": f.get("notes")}
    for qy in QUERIES:
        obs["search|" + json.dumps(qy, sort_keys=True)] = sorted(m["body"][:60] for m in A.search(db, **qy))
    obs["export_md_lines"] = len(A.export(A.absences(db), "md").splitlines())
    db.close()
    return obs
