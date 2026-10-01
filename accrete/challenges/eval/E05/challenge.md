# E05 (maintenance, after E04): withdraw self-dispatch, keep the workload cap

## 1. Requested outcome
Partial reversal of E02: the `claim` action and the `dispatch` field disappear, but the workload cap
for `assign` stays. Orders that technicians had self-claimed but not yet started go back to the
open pool.

## 2. Observable acceptance criteria
- `POST .../claim` -> 404 for everyone (401 still first); no `claim` UI form.
- No `dispatch` key in any work order; `?dispatch=...` -> 400; `dispatch` in bodies -> 400.
- Orders 72 and 75 (self-dispatched, still assigned) are `open` with no assignee, all other fields
  unchanged; self-dispatched orders in other states (56 in progress, 22/33 cancelled, completed ones)
  unchanged.
- Workloads drop (sara 2, olga 1) so supervisors can assign to them again up to the cap; the cap is
  still enforced (nils, ravi) with unchanged 400/409 ordering.
- Requesters of the returned orders can edit/cancel them again (they are open).

## 3. Behaviour that must remain intact
E01 parts and payload, E03 priorities and the p4 rule, E04 time entries / derived labor /
complete-requires-entry, read permissions, asset `open_orders` counts.

## 4. Existing-data requirements
Exactly two orders transformed (72, 75); dispatch removed everywhere; 39 time entries and all parts
unchanged. Cumulative superseded base tests stay at 19: the reversal does not make any base test
true again because the cap (which falsified `test_outbox_readable_by_any_user`) is kept and the
E03/E04 changes remain.

## 5. Failure and recovery conditions
Removed endpoints change nothing and emit nothing. Capped assigns still refuse without side effects.

## 6. Measurements to collect
Standard harness measurements, plus whether the implementer removed only the requested parts of E02
(claim, dispatch) and kept the cap, and whether the data rollback touched exactly the two
assigned self-dispatched orders.
