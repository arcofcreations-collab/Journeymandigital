# F08 (maintenance)

Size: small. Categories: permissions, rule_change, conflict_or_ambiguity.

## 1. Requested outcome

Requesters can withdraw assigned (not started) orders, and cancellation of assigned work notifies the technician via the outbox.

## 2. Observable acceptance criteria

- Requester cancels own `assigned` order: 200; `in_progress`: 409; others 403; reason 400 after 403/409.
- `assignment_cancelled` {work_order, technician, reason} for assigned/in-progress cancels (also by supervisors, after re-assignment the current assignee); none for open orders or failures.
- UI cancel form for the requester on an assigned order.

## 3. Behaviour that must remain intact

Supervisor cancel rules, assignee kept, start/complete/assign, other operations emit nothing.

Superseded base tests (2): `test_cancel_permissions_and_states`, `test_ui_actions_per_role_and_state`.

## 4. Existing-data requirements

No migration.

## 5. Failure and recovery conditions

Refused cancels change no order and emit nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
