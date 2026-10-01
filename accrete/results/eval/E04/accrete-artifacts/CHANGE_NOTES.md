# E04: time logging (change 0005-time-logging.yaml, ledger #5)

Interpretation: technicians log time with a new `log_time` action; `labor_minutes` is derived from those entries.

Changes (all through `accrete apply`):
- New read-only collection `time_entries` (`work_order`, `technician`, `minutes`, `logged_at`, `note`). It uses the work-order read rule applied to `record.work_order`. POST, PATCH and DELETE return 403 for everyone.
- New action `log_time(minutes: int required, note: text optional)`:
  - Only the assignee may call it (403), and only while the order is `in_progress` (409).
  - The body is validated next (400): `minutes` must be a JSON integer from 1 to 600, `note` must be a string or null, and unknown keys are rejected.
  - It creates one entry with `technician` = the caller and `logged_at` = now. It emits nothing.
- `work_orders.labor_minutes` is now computed: the sum of the entries' minutes, or null when there are none. It still cannot be set (400).
- `complete` now takes only `resolution`. Its guard also requires at least one time entry (409). The precedence is 403, then 409, then 400.
  - The `work_completed` payload keeps its 5 keys, with `labor_minutes` = the derived total.
- UI forms follow allow + guard: `log_time` is shown to the assignee of an `in_progress` order. `complete` is shown only when it is allowed right now. Cancelling an order leaves its entries untouched.
- Migration: the 39 orders that had a stored `labor_minutes` each got one entry (assignee, minutes, logged_at = `completed_at`, note "migrated"). The entries have ids 1-39 in ascending work-order id, and 11 of them belong to the inactive technician umar. New entries start at id 40.

Verification:
- The pipeline replay ran 694 requests: 693 were identical, 1 changed as intended, and nothing was unexplained. Derived `labor_minutes` equals the old stored values.
- 50+ expectations in the change file passed.
- A harness script ran against `app_entry.py` (via `accept_client.fresh_app`). It checked the UI forms and lists, a full claim → start → log_time → complete lifecycle, and the outbox payload.
