# F06 (expenses, depends on F05)

Size: small. Categories: permissions, rule_change, interaction, sequence.

## 1. Requested outcome

Finance users can no longer pay themselves, advance money to themselves, or change their own employee record.

## 2. Observable acceptance criteria

- Finance paying own claim: 403, before 409; another finance user pays successfully with advance recovery.
- Advance to self: 403, winning over 400 in the same body.
- PATCH/DELETE of own employee record by finance: 403 before 400; other finance user may.
- Role change to finance is effective immediately (reads, pay rights).
- UI pay form hidden on own claim.

## 3. Behaviour that must remain intact

All F01-F05 behaviour; employee writes by finance on other records; non-finance 403s.

Superseded base tests (13): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`, `test_claim_fields_match_seed`, `test_create_claim_amount_bounds`, `test_finance_pays_approved_claim_and_emits_payment`, `test_claim_list_filters`, `test_delete_rules`, `test_approve_wrong_state_is_409`, `test_reject_permission_and_state_precedence`, `test_pay_permissions_and_state`, `test_outbox_readable_by_any_user`, `test_ui_claim_detail_manager_and_finance_actions`.

## 4. Existing-data requirements

No migration; seed state from F01-F05 unchanged.

## 5. Failure and recovery conditions

Refused self-payment leaves claims, advances and outbox unchanged; refused advance creates nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
