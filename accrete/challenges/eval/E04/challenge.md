# E04 (maintenance, after E03): time entries and derived labor_minutes

## 1. Requested outcome
Labor is no longer typed in at completion. Assignees log time (`log_time`) into a new read-only
`time_entries` collection while the order is in progress; `labor_minutes` becomes the derived sum;
`complete` takes only a resolution and requires at least one entry. Historic labor figures are
converted into one migrated entry per completed order.

## 2. Observable acceptance criteria
- 39 migrated entries, ids 1-39 in ascending work-order id, technician = assignee, minutes =
  old labor_minutes, logged_at = completed_at, note "migrated"; every order's derived labor_minutes
  equals the old value (null for orders without one).
- Entries readable exactly like their work order (mei sees [1, 4], ruth [6, 21, 34], ...); no direct writes.
- `log_time`: assignee only (403), in_progress only (409), minutes integer 1-600, note string/null,
  no other keys (400); returns the order with the updated total.
- `complete {"resolution"}`: 409 without entries (even with a bad body), 400 for `labor_minutes`
  or other keys, payload labor = derived total, payload keys unchanged.
- UI: `log_time` form for the assignee of an in-progress order; `complete` form only once an entry exists.

## 3. Behaviour that must remain intact
E01 use_parts and parts_cost in the payload, E02 claim/cap/dispatch, E03 priority codes; inactive
assignee can still work an order; labor_minutes and other derived fields cannot be sent.

## 4. Existing-data requirements
Exactly one migrated entry per order with labor (39), totals unchanged. Cumulative superseded base
tests: 19 (E03's 17 plus `test_complete_validation` and `test_ui_actions_per_role_and_state`,
which complete orders with a labor figure / expect a complete form without time entries).

## 5. Failure and recovery conditions
Refused `log_time` and `complete` calls create no entry, change no order and emit nothing (snapshot
of entries, orders and outbox compared). Cancelled orders keep their entries; no further logging.

## 6. Measurements to collect
Standard harness measurements, plus back-fill exactness (ids/order/values) and the 409-before-400
ordering of `complete` without entries.
