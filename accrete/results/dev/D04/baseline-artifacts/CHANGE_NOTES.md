# Change notes: late-return fines

**Interpretation.** `fine` = 0.50 per day late, max 5.00, from the loan's current (renewed) `due_at`: for a
returned loan up to the calendar date of `returned_at`, for an open loan up to today (X-Now). `fine_paid` is
stored; member `fines_due` sums `fine` over returned loans with `fine_paid` = false. While `fines_due` > 0 the
member gets 409 on borrow (also when a librarian lends to them, and on their `ready` hold, which stays
ready), renew (also by a librarian) and placing a hold (also by a librarian). Amounts are JSON floats.
`fine_charged` is emitted on a late return (before any `hold_ready`); `pay_fine` is librarians-only
(404 → 403 → 409 → 400) and emits one `fine_paid` message.

**Changes.** Migration `0004_loan_fines.sql` adds `loans.fine_paid` (0/1) and sets it to 1 for loans already
returned late, so nobody owes anything at release; committed `data.db` migrated, `seed.py` applies the same
rule. `services.py`: `loan_fine`, `present_member`/`member_fines_due`, `_owes_fines` in the borrow/hold/renew
rules, `fine_charged` in `return_loan`, new `pay_fine` + `pay_fine` in `loan_actions`; `permissions.can_pay_fine`;
`repository` (`fine_paid`, `mark_fine_paid`, `returned_unpaid_loans`); API and UI routes for `pay_fine`;
templates show `fine`, `fine_paid`, `fines_due` and the `pay_fine` form. README updated.

**Verification.** New `tests/test_library_fines.py` (14 tests: fine growth/cap, renewal-extended due date,
migrated data, blocking rules incl. ready holds, pay_fine precedence and outbox, UI forms); existing tests
updated for the new fields/messages. Full suite: 96 passed. Checked that `seed.py` rebuilds a database
identical to the migrated committed `data.db`.
