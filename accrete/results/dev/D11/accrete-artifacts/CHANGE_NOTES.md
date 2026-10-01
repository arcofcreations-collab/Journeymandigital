# Payment runs (change #3, app/changes/0003-payment-runs.yaml)

Interpretation: new collection `payment_runs` (`claims` = list of claim refs, required/non-empty, distinct, order kept;
`total` = system, round(sum of amounts, 2); `created_by` = system, caller; `created_at` = system, now). Rules: read and
create are for finance only; update and delete are False (403 for everyone). `create_guard` requires every listed existing claim to be
`approved` (409, checked before any 400). Constraint `total <= 10000` gives 400. A create trigger runs inside the create transaction
(all or nothing): for each claim in list order it records a `pay` claim_event (actor = caller, at = now, approved -> paid), sets
status `paid` and `payment_run` = the run, and emits `payment` {claim, employee, amount}. After that it emits one `payment_run`
{run, claims, total}. Claims get a new system field `payment_run` (ref payment_runs). Existing claims stay null, the single
`pay` action is unchanged, and clients get 400 if they send it.

Verification: `accrete apply` committed with 0 unexplained or unacknowledged replay differences, and all expectations passed
(success path, ordering of events and outbox, 403/400/409 precedence, all-or-nothing on failure, read/PATCH/DELETE rules, single pay
unchanged, payment_run not settable). I also ran a separate WSGI check through app_entry.py on a copy of the app, covering the API
and the /ui pages.

Note (existing runtime behaviour, not changed here): `GET /api/_outbox?channel=...` ignores the filter and returns all messages.
This was already the case before this change.
