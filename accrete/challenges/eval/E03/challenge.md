# E03 (maintenance, after E02): priority scale p1-p4

## 1. Requested outcome
Work-order priorities move from `urgent/normal/low` to `p1..p4` with new due-date offsets
(1/3/7/30 days). Normal orders on high-criticality assets become `p2`. `p4` may not be set on
high-criticality assets. Self-dispatch (E02) is limited to `p3`/`p4` orders.

## 2. Observable acceptance criteria
- Every seed order has the migrated code (16 p1, 12 p2, 27 p3, 27 p4); filters by code work; old
  values filter to empty lists.
- `due_date`/`overdue` use the new offsets for all orders (overdue at 2026-03-01 becomes
  30 37 38 47 52 54 56 61 62 65 68 73 76; order 74 is due 2026-03-01).
- Create/PATCH accept only p1-p4 (400 otherwise); p4 on a high-criticality asset is 400, even if
  the order already has p4; existing precedence (site 403, finished-order 409) still wins.
- `claim` on p1/p2 orders is 403 (wins over 409), based on the current priority; the UI claim form
  follows; supervisors still assign any priority.

## 3. Behaviour that must remain intact
E01 parts/use_parts/`work_completed` payload, E02 dispatch values and the workload cap, requester
403 on priority PATCH, supervisor PATCH rules, read permissions, UI conventions.

## 4. Existing-data requirements
All 82 orders migrated by the urgent/normal/low + criticality rule. Low orders on high-criticality
assets (6, 26, 42, 64, 67) keep `p4` (stated policy) and remain editable except for setting p4.
No other field changes. Cumulative superseded base tests: 17 (all base tests that send or compare
the old priority values or the old due dates).

## 5. Failure and recovery conditions
Rejected creates/PATCHes leave the order unchanged (priority checked after refusals). A refused
claim leaves the order open and unassigned.

## 6. Measurements to collect
Standard harness measurements, plus correctness of the migrated priority map (82 values), and
whether the claim restriction is evaluated as 403 before 409.
