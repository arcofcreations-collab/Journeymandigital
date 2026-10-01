# E07 (maintenance, after E06): preventive maintenance schedules

## 1. Requested outcome
A `schedules` collection describes recurring maintenance per asset. The action `generate` turns a
due schedule into an ordinary work order (linked through a new read-only `schedule` field),
advances the schedule and announces it on a `preventive_generated` channel. Retiring an asset
deactivates its schedules.

## 2. Observable acceptance criteria
- Schedules 1-5 exactly as in the brief, readable by everyone; existing orders have `schedule` null.
- `generate` creates the order with the specified fields (description "Preventive maintenance",
  requested_by = caller, created_at = X-Now, priority from the schedule, due date from E03 offsets),
  advances `next_due` by `interval_days` from its previous value (once), emits the payload
  `{"schedule", "work_order", "next_due"}` and returns the schedule.
- 409 for inactive schedule / retired asset / unfinished generated order / today < next_due - 7;
  403 for anyone but managers and same-site supervisors (403 before 409).
- Schedule CRUD with site-scoped permissions (E06), validation (p4 on high, interval 1-365, real
  date, existing non-retired asset, no asset change), delete 409 once it generated orders; asset
  delete 409 when it has schedules.
- Retiring an asset sets its schedules inactive; un-retiring does not reactivate.
- UI: schedules lists/detail, `generate` form only when it would succeed, schedules/new for managers
  and supervisors.

## 3. Behaviour that must remain intact
Generated orders behave like any work order: technician visibility by site, supervisor scoping,
workload-capped assign, start, use_parts (parts_cost), log_time, complete payload, cancel.

## 4. Existing-data requirements
Schedules 1-5 as listed (including an inactive one on a retired asset and an overdue one that
advances only once); all 82 orders get `schedule` = null. Cumulative superseded base tests: 27
(same as E06; the new collection falsifies no further base test).

## 5. Failure and recovery conditions
Failed generates leave schedules, work orders and outbox unchanged (snapshot). After a generated
order is finished (completed or cancelled) the schedule can generate again once its date window opens.

## 6. Measurements to collect
Standard harness measurements, plus whether the 7-day window and once-only advance are applied
from `next_due` (not from now), and whether retirement cascades to schedules.
