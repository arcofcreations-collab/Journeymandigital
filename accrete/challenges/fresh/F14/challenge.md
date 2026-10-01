# F14 (expenses)

Size: medium. Categories: rule_change, permissions, conflict_or_ambiguity.

## 1. Requested outcome

Finance can send an approved claim back to the manager once, with a question, before paying it.

## 2. Observable acceptance criteria

- query by finance on approved claims: submitted, decision cleared, finance_query set, query_count 1, claim_queried message with the current manager.
- 403 (non-finance) -> 409 (not approved / already queried) -> 400 (question).
- Re-approval/rejection by the manager clears finance_query; pay blocked until re-approved; second query 409.
- Fields protected, visible, filterable; UI query form for finance when allowed.

## 3. Behaviour that must remain intact

Approve/reject/pay rules and payment payload, read permissions.

Superseded base tests (0): none.

## 4. Existing-data requirements

All existing claims get finance_query null, query_count 0.

## 5. Failure and recovery conditions

Refused queries change no claim and emit nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
