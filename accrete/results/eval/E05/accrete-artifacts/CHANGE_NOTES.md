# E05: withdraw technician self-dispatch, keep the workload cap

Interpretation: `claim` and the `dispatch` field are removed entirely. The `assign` cap stays exactly as in E02: 409 for a valid technician who already has 3 or more assigned/in_progress orders, not counting this one. Re-assignment to the current assignee is always allowed, and an invalid technician is 400. Every order with dispatch "self" and status "assigned" goes back to the pool (status open, assignee null). All other self-dispatched orders keep their status and assignee.

Change: ledger #6, `changes/0006-withdraw-self-dispatch.yaml`, applied with `accrete apply`. It has 4 ops:
- `update_records`: orders 72 and 75 become open and unassigned.
- `remove_action claim`.
- `change_action assign`: same checks and cap as before; it no longer sets dispatch.
- `remove_field dispatch`.

The migration emits no outbox messages and creates no time entries or part usages. Sara's workload drops from 3 to 2 and Olga's from 2 to 1. Sara and Olga are also the requesters of these two orders, so they can again edit title/description and cancel them.

Verification:
- The pipeline replayed 3493 requests with 0 unexplained differences, and the change's 30+ expectations passed.
- `accrete check` reports ok.
- Through `app_entry.py` with `accept_client`:
  - claim returns 401 without a user and 404 otherwise, and no claim form appears in the UI.
  - No record contains `dispatch`; sending it on create or PATCH gives 400.
  - The cap gives 409 (Ravi, or Sara once she is back at 3), an invalid technician gives 400, and re-assigning Ravi's own order 68 gives 200.
  - The outbox is empty after the migration.
  - A before/after diff of all 82 orders shows only orders 72 and 75 changed (status, assignee), apart from `dispatch` being gone.

Known runtime limitation: this accrete runtime answers a list filter on any unknown field with 200 and an empty list, not 400. That is already true for e.g. `?foo=1` on every collection. A model change cannot alter it, so `?dispatch=...` now behaves exactly like any other unknown field in this runtime: 200 with an empty list.
