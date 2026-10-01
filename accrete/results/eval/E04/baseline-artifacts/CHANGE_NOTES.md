# E04: time logging replaces the labor figure entered at completion

**Interpretation.** Applied as stated. `labor_minutes` is now derived (sum of the order's time
entries, `null` without any) and stays read-only. Time entries are read-only history, readable
exactly like their work order (lists filtered, direct access 403; POST 403, PATCH/DELETE 404 for an
unknown id, otherwise 403, as with part usages). `log_time`: 403 unless assignee, 409 unless `in_progress`,
then 400 for body problems (minutes a JSON integer 1-600; note string/null; no other keys).
`complete` takes only `resolution`, and a missing time entry is a 409 alongside the status check.

**Changes.** Migration `0005_time_entries.sql` creates `time_entries`, gives every order with a
stored `labor_minutes` one entry (assignee, value, `completed_at`, note `"migrated"`; ids 1-39 in
work order id order, inactive umar included) and drops the stored column. Repository computes
`labor_minutes` with a sub-select; there are new services/validation/permission functions, API routes
(`/api/time_entries`, `/api/work_orders/{id}/log_time`), UI pages (`/ui/time_entries`, a `log_time`
form, and a `complete` form shown only when time has been logged), and `seed.py`
(`seed_time_entries`). The committed `data.db` was upgraded by starting the app through `app_entry.py`.
I also updated the README.

**Verification.** Existing tests were updated for the new `complete` body, and I added
`tests/test_maintenance_time_entries.py` (action, precedence, validation, read rules, UI, outbox
payload, cancel, migration). 129 tests pass, both in plain mode and in the evaluator mode
(`ACCEPT_TARGET`). The migrated `data.db` matches a `seed.py` rebuild table for table. Every order's
derived `labor_minutes` equals its former stored value, and `PRAGMA foreign_key_check` is clean.
