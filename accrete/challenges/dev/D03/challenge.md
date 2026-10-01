# D03 - Loan renewals (library)

Categories: rule_change, sequence, interaction. Depends on: D02. Expect rejection: no.

## 1. Requested outcome

Loans can be renewed up to twice, except when overdue, returned, or someone waits for the book.

## 2. Observable acceptance criteria

- Renew adds 14 days to the current due date, increments `renewals`, emits `loan_renewed`.
- Max 2 renewals; renewing on the due date works, the day after is 409; overdue/returned loans 409.
- A waiting hold on the book blocks renewal (409); cancelling it unblocks.
- Permissions: borrower or librarian; other member 403 (403 before 409).
- `overdue` follows the extended due date; UI `renew` form only when allowed.

## 3. Behaviour that must remain intact

- Holds queue and return flow unchanged by renewal; loans not PATCHable; new loans start at 0 renewals.
- Base tests intentionally superseded: test_unknown_collection_record_and_action_are_404; every other base test must still pass.

## 4. Existing-data requirements

- All 60 seed loans have `renewals` = 0 and unchanged due dates.

## 5. Failure and recovery conditions

- Failed renewals leave `due_at`/`renewals` unchanged and emit nothing.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Whether the earlier holds behaviour (D02 hidden tests) still passes after this change.
- Correct handling of the superseded 404 base test.

## Brief (exact text given to implementers)

Loan renewals

(This change is made on top of the holds feature: collection `holds`, `POST /api/books/{id}/hold`, `POST /api/holds/{id}/cancel`, book status `reserved`.)

Members want to keep a book longer when nobody else is waiting for it.

New action `POST /api/loans/{id}/renew` (body `{}`), by the borrowing member or any librarian; any other member -> 403.
- Extends `due_at` by 14 days counted from the loan's current `due_at` (not from today) and increments a new loan field `renewals` (integer).
- 409 if: the loan is already returned; the loan is overdue (today is after `due_at`; renewing on the due date itself is allowed); the loan already has `renewals` = 2; or someone is waiting for the book (the book has a hold with status `waiting`).
- On success emits exactly one outbox message, on channel `loan_renewed`, with payload `{"loan": <loan id>, "due_at": "<new due date YYYY-MM-DD>"}`, and returns the loan. A failed renewal changes nothing and emits nothing.
- `renewals` is 0 for every existing loan and for new loans. Loans still cannot be PATCHed by anyone.
- `overdue` and every rule that depends on `due_at` use the extended date.
- UI: the loan detail page shows a `renew` form exactly when the caller may renew that loan right now.

Holds keep working as before; a renewal does not change any hold.
