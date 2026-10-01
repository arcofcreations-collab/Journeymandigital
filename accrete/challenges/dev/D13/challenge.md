# D13 - Approval delegation (expenses)

Categories: new_concept, permissions, conflict_or_ambiguity. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Time-boxed approval delegation between managers, with self-approval and chaining excluded.

## 2. Observable acceptance criteria

- Managers create delegations; validation and 403 for non-managers.
- Active delegate reads the delegator's reports' claims and approves/rejects them with decided_by = delegate.
- Date window inclusive; deletion revokes; delegator keeps rights; state rules (409/400) apply to delegates.
- A delegate cannot decide their own claim (omar on 43) - 403; delegations do not chain.
- Delegation visibility (delegator, delegate, finance); immutable; UI forms.

## 3. Behaviour that must remain intact

- Approval/read rules without delegations unchanged.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- No seed delegations; no claim changes.

## 5. Failure and recovery conditions

- Rejected delegation creates nothing; out-of-window approvals change nothing.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Self-approval through delegation (should never succeed).
- Chained delegation leaks.

## Brief (exact text given to implementers)

Approval delegation

Managers going on leave want to hand over their approval duties.

New collection `delegations` with fields: `delegator` (reference to employees; set automatically to the creator; sending it -> 400), `delegate` (reference to employees, required), `starts_on` (date, required), `ends_on` (date, required).
- Only employees with role `manager` can create delegations (others -> 403). `delegate` must be a different employee whose role is `manager` (themselves, a non-manager or an unknown id -> 400). `ends_on` must not be before `starts_on` (-> 400).
- A delegation is readable by its delegator, its delegate and finance users; lists contain only those. Only the delegator can delete it (others -> 403). Nobody can PATCH a delegation (403).
- A delegation is active on every date from `starts_on` to `ends_on` inclusive (today = the date of the request).
- While a delegation is active, the delegate can read every claim of the delegator's direct reports and can approve and reject those claims under the same state rules as the delegator (`decided_by` = the delegate). The delegator keeps all rights.
- Segregation of duties: nobody may approve or reject their own claim, also not through a delegation (-> 403).
- Delegations do not chain: a delegate does not pass on rights they hold only through a delegation.
- When no delegation is active (before `starts_on`, after `ends_on`, or deleted), the delegate has no extra rights (403 as before).
- UI: a claim's detail page shows `approve` / `reject` to an active delegate exactly when they may use them.

Existing data: there are no delegations initially; nothing else changes.
