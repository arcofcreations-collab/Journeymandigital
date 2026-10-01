# Change notes: borrowing restrictions

**Interpretation.** `POST /api/books/{id}/borrow` now returns 409 when the borrowing member (the caller,
or the member a librarian lends to) has an unreturned loan whose `due_at` is before X-Now's date (UTC);
a loan due today does not block, and returning the overdue loan(s) lifts the block. Returns are never
blocked. A book whose `year` equals X-Now's year or the year before is lent for 7 days; every other book
(older, without a `year`, or with a future `year`) keeps 14 days. Existing loans are untouched, the
3-loan limit, inactive-member rule and `loan_created` message are unchanged; precedence stays 404/403/409/400
(the overdue check sits with the other borrower-state 409 checks: inactive, overdue, loan limit).

**Changes.** `services.py`: `NEW_RELEASE_LOAN_PERIOD`, `loan_period(book, today)`, overdue check in
`_ensure_may_borrow`; `_may_borrow` (UI borrow form visibility) now reuses the same checks so the form is
hidden for members with overdue loans. `repository.py`: `has_overdue_loans(member_id, today)` (same
`due_at < today` rule as the derived `overdue` field). README business-rules table and interpretations
updated. No migration: no schema change and, per the request, no existing data is recalculated
(`data.db` unchanged).

**Verification.** Updated `tests/test_library_loans.py` (the old 3-loan test relied on ivan, who has an
overdue loan, borrowing; it now uses chen) and added tests for the overdue block (member and librarian,
due-today boundary, return lifts block, partial return keeps it, 403 still beats 409), 7- vs 14-day
periods (2026/2025/2024/no-year books, year window following X-Now incl. 2025-12-31), unchanged seed
due dates, and the UI borrow form for an overdue member. Ran the suite with a local stand-in for
`harness/accept_client.py` (the real harness is not in this workspace): all 60 tests pass. Also loaded the app through `app_entry.py` and checked requests.
