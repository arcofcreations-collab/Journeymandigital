# Baseline v2.1 improvements (isolated round)

All three apps share the same `dev.py` (only `PACKAGE` / `USER_TABLE` differ) and got the same
`seed.py` change. No application code, template, migration, test or data.db changed; the apps
behave exactly as before. New files: `<app>/tests/pinned_state.json` (the accepted state of the
unchanged baseline).

## 1. Stale change notes (finding 1)

*Cause.* The snapshot behind `dev.py notes` was taken only "if missing". A chained change starts
from a copy of the previous app, `.dev/` included, so the snapshot predated earlier changes.

*Change.* The snapshot records the directory it was taken in. Every command that starts or
continues work (`overview`, `check`, `call`, `new-migration`, `migrate`) retakes it when it cannot
belong to the current change: it was taken in another directory (the app was copied for the next
change), or CHANGE_NOTES.md existed after it was taken and has since been removed (the previous
change was handed over; dev.py remembers seeing the file in `.dev/notes_seen`). `migrate` now
takes the snapshot before migrating, so the pre-change data is kept. `notes` warns when its
snapshot looks stale. Removed the stale `.dev/` that shipped in `library/`.

*Apply times.* `python seed.py` keeps the recorded `applied_at` of every migration data.db already
had (same version and name); only new ones get the current time. (`check` ignores `applied_at`,
so this changes no check result.)

## 2. Less work to establish correctness (finding 2)

*Pinned state* (`python dev.py pin`, compared by `check`). A sweep asks the API, as every user,
everything an empty body can ask: lists, `POST /api/<c> {}`, GET of every record, every action
`POST {}` on every record, `PATCH {}` / DELETE on a sample; 2xx writes record a response and
outbox hash; plus the records as the best reader sees them, the schema, the AUTOINCREMENT counters
and a hash per stored row. `check` fails while this differs from `tests/pinned_state.json` and
prints the difference grouped by route and status change, with example users and ids. The
implementer reviews that list against the request (every line requested, nothing that must stay
intact touched), runs `pin`, and `notes` copies the accepted diff into CHANGE_NOTES.md.

This does three jobs: it is a complete regression check for "behaviour that must remain intact"
(the part tests rarely cover), it replaces hand-written permission/state matrix tests for empty
bodies (the README now says which tests are still needed: parameters, flows, payloads, UI), and it
writes the behavioural part of the notes. The bar is not lowered: the full suite still runs, and
every behaviour change now needs an explicit review step.

*Run time.* Tests now run in a subprocess while the data.db checks, sweep and scan run, and the
scan reuses the sweep's action results. Writes in the sweep restore the database only when
SQLite's file change counter moved.

## 3. Planted bugs that `check` missed (finding 3)

General rules added to the data.db stage (FAIL):

* AUTOINCREMENT counters: each `sqlite_sequence` row must name an existing table and hold an
  integer >= the table's highest id; an AUTOINCREMENT table with rows must have one; and, from a
  step-by-step replay (seed, then one migration at a time), no migration may lower a counter
  (a rebuild that forgets `UPDATE sqlite_sequence ...` lets deleted ids be reused).
* A partial-index or trigger predicate must not compare a column with a value that the column's
  `CHECK (col IN (...))` never allows (a dead or always-true predicate).
* WARN: a migration comparing a CHECK-enumerated column with a value no schema version allowed
  (a likely typo, e.g. `WHERE status = 'aproved'`).

The pinned state rejects all five misses in the evidence by construction: the two swapped error
classes changed hundreds of `POST {}` statuses (the oracle saw 540 and 2234); the partial-index
predicate changes the schema; the two `sqlite_sequence` edits change a counter (one to NULL, which
the new counter rule also rejects). Checked here on the library app by planting the same kinds of
bug (swapped error class in `return_loan`: `403 -> 409 x540`; `'readyx'` predicate; counter set
from a missing table; rebuild without restoring the counter): all rejected.

A counter set one higher than the request asks (81 instead of 80) is only caught if it differs
from what was pinned; the README now asks for one test that creates a record and checks its id
when the request names ids.

## Left as is

* Coverage of untested `raise` branches (WARN) was considered; the pinned state already covers
  every branch reachable with an empty body, so it was not added.
* No change to the contract/UI scan heuristics or to the existing test suites.
