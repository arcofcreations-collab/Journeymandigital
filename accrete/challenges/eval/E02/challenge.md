# E02 (maintenance, after E01): technician self-dispatch and workload cap

## 1. Requested outcome
Active technicians can `claim` open work orders at their own site. Every technician is limited to
3 active (assigned or in-progress) orders, for `claim` and for supervisor `assign`. A read-only
`dispatch` field records whether the current assignment came from a supervisor or was self-claimed,
and is back-filled for existing orders.

## 2. Observable acceptance criteria
- `claim` sets assignee/status/dispatch, emits `assignment` with the usual 3-key payload, returns the order.
- 403 for non-technicians, inactive technicians and technicians of another site; 409 when not `open`
  or when the caller already has 3+ active orders; 403 wins over 409.
- `assign` to a valid technician with 3+ active orders (not counting this order) -> 409 with no
  outbox message; re-assignment to the current assignee always allowed; an invalid technician is
  still 400 even if they would also be over the cap.
- Completing or cancelling orders lowers a technician's workload so they can receive work again.
- `dispatch` is read-only (400 in create/PATCH), filterable (`?dispatch=self`, `?dispatch=null`),
  set to `"supervisor"` by assign (also when re-assigning a claimed order) and `"self"` by claim.
- UI `claim` form only when the claim would succeed for the caller right now.

## 3. Behaviour that must remain intact
E01 parts consumption and `work_completed` payload with `parts_cost`; requester may cancel/edit only
while open (a claimed order is no longer open); start/complete rules; existing over-cap assignments
stay untouched.

## 4. Existing-data requirements
`dispatch` back-filled: 16 orders `self` (assignee = requester), 46 `supervisor`, 20 `null`.
ravi keeps his 4 active orders (policy: no automatic unassignment). Base test
`test_outbox_readable_by_any_user` becomes false (it assigns to nils, who is at the cap); together with
E01 that makes 3 superseded base tests.

## 5. Failure and recovery conditions
Refused claims and capped assigns change nothing and emit nothing (order, outbox compared).
Capacity is recovered when orders complete or are cancelled.

## 6. Measurements to collect
Standard harness measurements, plus whether the cap is checked after technician validation (400 vs
409 precedence) and whether the `dispatch` back-fill matches the requester=assignee rule.
