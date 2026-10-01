# E06 (maintenance, after E05): site-scoped supervisors and the manager role

## 1. Requested outcome
A new `manager` role inherits the former company-wide supervisor rights. Supervisors are limited to
their own site for reading and managing work orders, for creating work orders, and for managing
assets and parts. Only managers manage staff. sofia becomes the manager.

## 2. Observable acceptance criteria
- sofia's role is `manager`; she reads all 82 orders and all time entries; `?role=supervisor` -> [2, 16].
- tomas reads exactly the 31 South orders, yara the 14 East orders; cross-site reads 403; time
  entries / part usages follow.
- Supervisor assign/cancel/PATCH only on own-site orders (403 first, before 409/400); manager on all.
- Supervisor creates work orders only for own-site assets (403 wins over 400).
- Assets/parts: supervisor create only with own `site`, PATCH/DELETE only own-site records, no site
  change to another site (403 before 400); create without site 400; manager unrestricted.
- Staff writes: managers only (403 for supervisors, also for an empty body); `manager` is a valid role;
  a newly created or promoted manager immediately has global rights.
- UI forms: staff/new managers only; assets/new and parts/new managers and supervisors.

## 3. Behaviour that must remain intact
Workload cap, no claim (404), E04 time logging and completion, E03 p4 rule, requester rights
(cancel/edit open orders), technician site visibility, reads of staff/assets/parts for everyone.

## 4. Existing-data requirements
Only staff 1 changes (role -> manager). Cumulative superseded base tests: 27 (E05's 19 plus 8 base
tests in which South/East supervisors act on North data, write staff, or list all orders).

## 5. Failure and recovery conditions
Forbidden cross-site operations change nothing and emit nothing (outbox compared); records stay as
they were (asset names, part quantities checked afterwards).

## 6. Measurements to collect
Standard harness measurements, plus number of places where supervisor scoping was applied
consistently (orders, creation, assets, parts, staff, UI) and whether the promotion of a
supervisor to manager takes effect immediately.
