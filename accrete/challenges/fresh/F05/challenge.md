# F05 (expenses, depends on F04)

Size: medium. Categories: reversal, data_migration, interaction, sequence.

## 1. Requested outcome

The partial-approval feature is removed again and claims that were only partially approved go back to their manager.

## 2. Observable acceptance criteria

- approve with `amount` or `note` is 400 (after 403/409); approve with {} approves the claim.
- `approved_amount` and `approval_note` are absent from records and UI.
- Payments recover advances from the full amount; payload amount = amount - recovered.

## 3. Behaviour that must remain intact

Advances (F04) including read rules and recovery order, policies/lodging (F02), incurred_on (F01).

Superseded base tests (13): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`, `test_claim_fields_match_seed`, `test_create_claim_amount_bounds`, `test_finance_pays_approved_claim_and_emits_payment`, `test_claim_list_filters`, `test_delete_rules`, `test_approve_wrong_state_is_409`, `test_reject_permission_and_state_precedence`, `test_pay_permissions_and_state`, `test_outbox_readable_by_any_user`, `test_ui_claim_detail_manager_and_finance_actions`.

## 4. Existing-data requirements

Claims 21, 22 and 38 become submitted with decided_at/decided_by null and unchanged submitted_at; other approved claims (4 12 13 18 27 33 34 37 41 44 50 59 61 65 66 68 69 74 76 78) and all paid claims unchanged (paid_amount = amount, advance_recovered 0).

## 5. Failure and recovery conditions

Refused approvals leave the claim submitted; refused payments change nothing (as in F04).

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
