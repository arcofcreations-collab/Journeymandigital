# F04 (expenses, depends on F03)

Size: large. Categories: new_concept, new_relationship, cross_cutting, failure_atomicity, permissions, data_migration, interaction, sequence.

## 1. Requested outcome

Finance can issue cash advances, and outstanding advances are recovered automatically (oldest first) from the employee's next reimbursements.

## 2. Observable acceptance criteria

- `advances` seeded with ids 1-3 as in the brief; finance-only creation with `advance_issued` message; no PATCH/DELETE; read by finance, the employee and their direct manager.
- pay recovers outstanding advances oldest-first from approved_amount; sets claim `advance_recovered` / `paid_amount` and advance `recovered`/`outstanding`; payload {claim, employee, amount: paid_amount, advance_recovered}.
- Fully offset payments emit amount 0; employees without advances get advance_recovered 0.
- UI list/detail/create form for advances; claim UI shows the payment fields.

## 3. Behaviour that must remain intact

Partial approval (F03), policies and lodging (F02), incurred_on (F01), pay permissions and states.

Superseded base tests (6): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`, `test_claim_fields_match_seed`, `test_create_claim_amount_bounds`, `test_finance_pays_approved_claim_and_emits_payment`.

## 4. Existing-data requirements

Advances 1-3 created exactly as listed; 21 paid claims get advance_recovered 0 and paid_amount = approved_amount (= amount); others null.

## 5. Failure and recovery conditions

Refused payments (403/409) leave claims, advances and the outbox byte-for-byte unchanged; refused advance creations add no advance and emit nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- Refused operations that left any trace (records, related collections or outbox) in the snapshot tests.
- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
