# Change notes: Borrowing restrictions (ledger #2)

**Interpretation.** A borrower (the caller, or the `member` a librarian lends to) who has an unreturned loan with `due_at < today` is blocked: borrow returns 409. This is the same definition as the `overdue` field, so a loan due today does not block. Librarians cannot override it. A book whose `year` is `today.year` or `today.year - 1` (taken from X-Now, UTC) is lent for 7 days. Every other book, including one with a null year, is lent for 14 days. Returns, the 3-loan limit, inactive members and the `loan_created` message are unchanged. Existing loans are not touched.

**Change.** `changes/0002-borrowing-restrictions.yaml` uses one `change_action` on `books.borrow`. It adds the no-overdue-loan clause to the guard and makes the `due_at` effect depend on the book's year. No data migration was needed.

**Verification.** The accrete pipeline passed. Replay ran 253 requests: 8 changed as intended and none were unexplained. 10 expectations passed, covering these cases:
- a member is blocked, and so is a librarian lending to them
- the due-today boundary
- returning loans lifts the block (and a return is never blocked)
- 14 days for an old book and for a book with no year
- 7 days for a previous-year book and for a current-year book
- a 2-year-old book gets 14 days

I also ran manual WSGI checks through `app_entry.create_app()` on a copy of the app:
- the 2025-12-31 year boundary
- an inactive member still gets 409
- the outbox payload is unchanged
