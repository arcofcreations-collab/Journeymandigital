# D09 - Withdraw second approval (expenses)

Categories: reversal, data_migration, sequence, permissions. Depends on: D08. Expect rejection: no.

## 1. Requested outcome

The two-level approval is removed and the data returns to a single-approval state without losing the first approval.

## 2. Observable acceptance criteria

- Claims 21, 22, 44 are `approved` again with decided_by 4 and their original decided_at.
- No claim has first_approved_* keys or the removed status; approved lists/filters equal the original ones.
- Large claims are approved in one step again.
- Marco's extra read access is gone (list equals the original reading set; 403 on 21/22/44).
- Restored claims can be paid; approving them again is 409; UI shows `pay` and no first_approved_* fields.

## 3. Behaviour that must remain intact

- Every base behaviour (all base tests apply again).
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- Restored decided_at: 21 2026-01-28T08:00:00, 22 2026-01-11T13:00:00, 44 2026-01-19T14:00:00.

## 5. Failure and recovery conditions

- Marco approving restored claims -> 403; failed calls change nothing.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Fidelity of the reversal: original decided_at/decided_by restored; leftover fields/permissions.
- Full base-suite pass rate after reversal (should be 100%).

## Brief (exact text given to implementers)

Withdraw the second-approval rule

The second-approval rule for large claims (status `awaiting_second_approval`, claim fields `first_approved_by` and `first_approved_at`, extra read access for the second approver) is withdrawn. From now on every claim needs exactly one approval by the employee's manager, whatever the amount - exactly as before that rule was introduced.

- `approve` by the employee's manager on a `submitted` claim sets `status` = `approved`, `decided_at` = now and `decided_by` = the manager, for any amount.
- The status `awaiting_second_approval` and the fields `first_approved_by` / `first_approved_at` no longer exist: they are not returned on claims and not shown in the UI.
- A claim is again readable only by its employee, the employee's manager and finance users; the second approver's extra read access is removed.

Existing data (required): every claim currently in `awaiting_second_approval` becomes `approved`, with `decided_by` = its `first_approved_by` and `decided_at` = its `first_approved_at` (the first approval stands). Claims that were already decided (approved or rejected by a second approver, or paid) keep their `status`, `decided_by`, `decided_at` and `rejection_reason`.
