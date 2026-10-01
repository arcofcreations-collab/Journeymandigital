# F13 (expenses)

Size: small. Categories: data_migration, rule_change.

## 1. Requested outcome

The category `other` is called `miscellaneous` everywhere.

## 2. Observable acceptance criteria

- Create/PATCH accept `miscellaneous` and reject `other` (400).
- Filters by the new name; old name returns an empty list.
- UI shows the new name.

## 3. Behaviour that must remain intact

The other three categories, amount validation, workflow, payment payload.

Superseded base tests (2): `test_create_claim_required_fields_and_category`, `test_employee_patches_own_draft`.

## 4. Existing-data requirements

26 claims (1 4 11 13 16 18 23 24 30 36 38 39 40 41 51 54 56 60 67 70 71 73 75 76 77 80) become miscellaneous; nothing else changes.

## 5. Failure and recovery conditions

A 400 create/PATCH changes nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
