# D08 - Second approval for large claims (expenses)

Categories: rule_change, permissions, data_migration, conflict_or_ambiguity. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Two-step approval above 1000.00 where a skip-level manager exists, including migration of open large approvals.

## 2. Observable acceptance criteria

- Claims 21, 22, 44 become `awaiting_second_approval` with first_approved_by 4 and first_approved_at = their old decided_at; decided_* null.
- No other claim changes; filter `status=approved&decided_by=4` gives 33, 41, 61.
- Omar approving 36 -> awaiting; marco approving -> approved (decided_by 2); then payable.
- Threshold strictly > 1000.00; managers without a manager (marco, nadia) still approve in one step (policy).
- Second approver can reject (reason required); permission/state matrix: omar 409 on awaiting, others 403, marco 403 outside the awaiting stage.
- Awaiting claims cannot be paid (409, no message); marco reads two-step claims (list and direct), not single-step ones.
- New workflow fields are protected (400); UI forms per role.

## 3. Behaviour that must remain intact

- Small claims, claims of employees whose manager has no manager, submit/patch/delete rules, pay of other approved claims.
- Base tests intentionally superseded: test_claim_lists_per_role, test_claim_list_filters, test_delete_rules, test_approve_wrong_state_is_409, test_finance_pays_approved_claim_and_emits_payment, test_pay_permissions_and_state, test_outbox_readable_by_any_user, test_ui_claim_detail_manager_and_finance_actions; every other base test must still pass.

## 4. Existing-data requirements

- Exactly 21, 22, 44 migrated (victor, sam, priya; all first-approved by omar).

## 5. Failure and recovery conditions

- Failed approve/reject/pay calls change nothing and emit nothing.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Correctness of the 403/409 matrix.
- Whether exactly claims 21, 22, 44 were migrated.

## Brief (exact text given to implementers)

Second approval for large claims

Audit wants a second sign-off on high-value claims.

Rule: a claim with `amount` greater than 1000.00 needs two approvals when the employee's manager has a manager: first the employee's manager, then that manager's own manager (the "second approver"). Claims of 1000.00 or less, and claims whose employee's manager has no manager, keep the single approval exactly as today.

New claim status `awaiting_second_approval`. New claim fields `first_approved_by` (reference to employees, or null) and `first_approved_at` (datetime, or null). Clients cannot set them (sending them on create or PATCH -> 400), like the other workflow fields.

- `POST /api/claims/{id}/approve` by the employee's manager on a `submitted` claim that needs two approvals: `status` = `awaiting_second_approval`, `first_approved_by` = that manager, `first_approved_at` = now; `decided_at` and `decided_by` stay null.
- On a claim in `awaiting_second_approval`, the second approver may `approve` (-> `approved`, `decided_at` = now, `decided_by` = the second approver) or `reject` with a reason (-> `rejected`, with `decided_at`, `decided_by`, `rejection_reason` set). `first_approved_by` / `first_approved_at` are kept in both cases.
- Who gets which error on approve/reject: a caller who is neither the employee's manager nor - for a claim currently in `awaiting_second_approval` - its second approver -> 403. In particular the second approver has no rights on the claim at any other stage (403). The employee's manager acting on a claim that is not `submitted` - including one awaiting second approval - -> 409. The reject reason rule is unchanged (400 when missing/empty, checked after 403 and 409).
- Single-approval claims keep `first_approved_by` / `first_approved_at` null.
- `pay` still requires `approved`; `awaiting_second_approval` -> 409.
- Reading: a claim whose `first_approved_by` is not null is also readable (directly and in lists) by its second approver, in addition to the existing readers, also after it has been decided.
- UI: on a claim awaiting second approval, the second approver sees `approve` and `reject` forms; the first approver sees neither; nobody sees `pay`.

Existing data (required): claims that are currently `approved` (not yet paid), with an amount over 1000.00, whose employee's manager has a manager, must now also get the second approval. Change each of them to `awaiting_second_approval` with `first_approved_by` = its current `decided_by`, `first_approved_at` = its current `decided_at`, and `decided_by` / `decided_at` set to null. All other claims keep their values, with `first_approved_by` / `first_approved_at` null.
