# F01 (expenses)

Size: small. Categories: rule_change, data_migration, sequence.

## 1. Requested outcome

Claims carry the date the expense was incurred (`incurred_on`); a claim can only be submitted once that date is known.

## 2. Observable acceptance criteria

- `incurred_on` present on every claim, settable on create (default null) and by the owner's PATCH of a draft.
- Validation 400 for wrong format, impossible date, future date (relative to X-Now), non-strings, empty string; today and null accepted.
- Submit of a draft with null `incurred_on` is 409; order 403 -> 409 (state) -> 409 (missing date).
- UI: `incurred_on` input on the create form and data-field on details; submit form only when submit would succeed.
- Filter `?incurred_on=` works with read permissions.

## 3. Behaviour that must remain intact

Approve/reject/pay, payment payload, read rules, protected fields, amount/category rules, 403/409-before-400 ordering for PATCH.

Superseded base tests (3): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`.

## 4. Existing-data requirements

68 claims with `submitted_at` get its date part (e.g. 2 -> 2026-01-25, 7 -> 2026-01-28, 22 -> 2026-01-09); the 12 drafts (1 8 9 19 20 29 39 46 54 73 75 79) get null; nothing else changes.

## 5. Failure and recovery conditions

Invalid `incurred_on` (create/PATCH) and refused submits leave the claim unchanged; a 400 create adds no claim.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
