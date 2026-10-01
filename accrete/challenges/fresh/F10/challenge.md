# F10 (library)

Size: small. Categories: rule_change, data_migration.

## 1. Requested outcome

Reference-only books exist in the catalogue but cannot be borrowed.

## 2. Observable acceptance criteria

- `reference_only` on every book; librarian create/PATCH with boolean validation; members 403.
- Borrow of a reference-only book: 409 for members and librarian lending; 403 for member-for-other still first; no loan/outbox.
- On-loan book flagged: loan returnable, then not borrowable.
- UI field, no borrow form, create-form input; boolean filter.

## 3. Behaviour that must remain intact

Other borrow rules (limit, inactive, on loan), returns, book deletion rules, outbox loan_created.

Superseded base tests (0): none.

## 4. Existing-data requirements

Books 9, 33, 36, 40 -> true; all others false; loan 54 of book 9 unchanged.

## 5. Failure and recovery conditions

Refused borrows create no loan and emit nothing; invalid flags leave the book unchanged.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
