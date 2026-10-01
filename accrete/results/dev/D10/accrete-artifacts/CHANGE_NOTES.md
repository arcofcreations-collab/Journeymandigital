# Change: claim history (ledger #2, changes/0002-claim-history.yaml)

Interpretation: new read-only collection `claim_events` (claim, action, actor, at, from_status, to_status).
Each successful submit/approve/reject/pay writes exactly one event (actor = caller, at = now,
from_status = status before, to_status = status after). The event is created as the first effect of the
action, so it runs only after allow/guard/param checks pass and is rolled back with the action on any error.
Read rule mirrors the claims read rule through `record.claim`; create/update/delete rules are `False`
(403 for everyone). No outbox emits were added.

Backfill: 139 events added via `add_records`, generated from the existing 80 claims' fields, grouped by
claim id in the order submit -> decision (approve/reject) -> pay (pay with actor/at null). They occupy
ids 1..139, so every later event has a higher id.

Verification: `accrete apply` dry-run and commit passed (replay 265/265 identical, 8 expectations covering
backfill content/order, read visibility/403, create/PATCH/DELETE 403, events for submit/approve/reject/pay,
no event on failed actions, outbox unchanged except the existing payment message); `accrete check` ok;
also exercised a copy of the app through app_entry.py create_app() (WSGI) with the same scenarios.
