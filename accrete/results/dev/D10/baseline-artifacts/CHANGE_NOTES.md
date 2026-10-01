# Claim history (`claim_events`)

**Interpretation.** New read-only collection `claim_events` (`claim`, `action`, `actor`, `at`,
`from_status`, `to_status`). Each successful submit/approve/reject/pay records exactly one event in the
same transaction as the status change (so failed actions record nothing); draft create/edit/delete record
nothing; no outbox messages. Events are readable exactly by the users who can read their claim (403 on
direct access otherwise, absent from lists); create/PATCH/DELETE are 403 for everyone (404 first for an
unknown event id, per the contract's precedence). Ids come from an AUTOINCREMENT key, so they increase in
recording order and are never reused. Because a finance user who paid a claim is now referenced, deleting
an employee who is an event actor is 409 like other referenced employees.

**Changes.** Migration `0002_claim_events.sql` creates the table and backfills existing claims claim by
claim (submit, decision, pay; `pay` with null actor/at); `repository.py` (event queries, actor in
`employee_is_referenced`), `permissions.py`, `services.py` (`_record_event`, list/get, read-only guard),
`routes_api.py` and `routes_ui.py` + templates (`/ui/claim_events` list/detail, History links).
`db.migrate(up_to=)` lets `seed.py` load the seed at schema 0001 and then run the later migrations, so a
rebuild gets the same backfill. Committed `data.db` migrated in place (139 backfilled events).

**Verification.** New `tests/test_expenses_claim_events.py` (backfill vs. every claim, recording, failed
actions, visibility, filters, read-only, UI, deletion guard); full suite passes (46 tests). Checked that
the migrated `data.db` keeps all prior rows unchanged and equals a fresh `seed.py` rebuild.
