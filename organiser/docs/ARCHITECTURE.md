# Organiser: components and their relation to the invented programming system

| component | file | kind |
|---|---|---|
| Android backup import (SMS Backup & Restore XML) | msgorg/importer.py | **external adapter** (conventional Python; shared by every variant) |
| Local archive, dedupe, coverage | msgorg/store.py | conventional Python |
| Date resolution | msgorg/dates.py | conventional Python (rules) |
| Absence evidence engine, work/personal context | msgorg/absences.py | conventional Python (rules) |
| Search, context, jobs, corrections, export | msgorg/app.py | conventional Python |
| CLI / browser UI | msgorg/cli.py, msgorg/web.py | conventional Python (stdlib http.server, 127.0.0.1 only) |
| Tests | tests/ (pytest, synthetic fixtures only) | conventional verification |

**Status: the whole organiser is currently conventional Python. Nothing in it uses an invented mechanism yet.**
It is therefore the *conventional baseline* for the organiser experiment.

Accrete (the first invented system, now a failed candidate for the 5x target) cannot express this application's core:
XML parsing, free-text interpretation and date arithmetic would all be escape-hatch functions; forcing it in would
mostly measure the escape hatch. The next candidate, chosen from evidence (candidates/CANDIDATES.md; X1: reviewing a
system-computed behaviour delta caught 27-28/30 confirmed-harmful faults vs 21/30 for authored expectations, at ~5 s per
case; X3: specifying expected behaviour up front costs 2.4x a whole change), is **Delta Review**: changes are accepted by
reviewing the system-computed difference in observable behaviour over a declared behaviour space (for the organiser:
generated conversation corpora x the queries the app answers), instead of writing tests. It applies to the existing
Python code unchanged - the invention-based variant reuses every module above and replaces only the change workflow
(tests -> declared behaviour space + delta review). Prior art: approval/snapshot ("golden master") testing and
differential testing; the baseline's own improver independently built a similar `dev.py pin`. Novelty claims are
limited accordingly (see candidates/CANDIDATES.md).
