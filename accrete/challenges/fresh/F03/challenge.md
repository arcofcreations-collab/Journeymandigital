# F03 (expenses, depends on F02)

Size: medium. Categories: rule_change, data_migration, interaction, sequence, conflict_or_ambiguity.

## 1. Requested outcome

Managers can approve a lower amount with a mandatory explanation; finance pays the approved amount; existing approvals that exceed the new policy maximums are capped.

## 2. Observable acceptance criteria

- approve without parameters approves the full amount (`approved_amount` = amount, note null).
- approve with amount < claim amount requires a non-empty note; amount must be a number in (0, amount]; 403 -> 409 -> 400 ordering.
- payment payload amount = approved_amount.
- `approved_amount`/`approval_note` are protected (400 on create/PATCH) and visible in API and UI.

## 3. Behaviour that must remain intact

F01/F02 rules (submit requirements, category maximum on create), reject, read rules, payment payload keys.

Superseded base tests (6): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`, `test_claim_fields_match_seed`, `test_create_claim_amount_bounds`, `test_finance_pays_approved_claim_and_emits_payment`.

## 4. Existing-data requirements

Paid claims: approved_amount = amount. Approved claims: approved_amount = amount except 21 (meals 1644.21 -> 400), 22 (meals 1455.12 -> 400) and 38 (other 1207.79 -> 1000), which get note "Capped at policy maximum". Others null.

## 5. Failure and recovery conditions

Invalid approve parameters change nothing (claim stays submitted, no decision fields set).

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
