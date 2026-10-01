# Bulk checkout at the desk

Interpretation: new action `POST /api/members/{id}/checkout` with `{"books": [...]}`, librarians only (403 otherwise).
409 (checked first, wins over 400) when the member is inactive, any listed existing book is not available, or
unreturned loans + number of listed entries > 3. Then 400 for missing / non-list / empty list, duplicate ids, or
entries that are not ids of existing books (exact integer match). On success one loan per book in list order
(borrowed_at = now, due_at = today + 14 days) and one `loan_created` message per loan with `{loan, book, member}`;
returns the member. Everything runs in one atomic action, so any failure leaves loans, book statuses and outbox untouched.

Changed: ledger #2 (`changes/0002-bulk-checkout.yaml`) adds action `members.checkout` (guard for 409, `fail`
effects for 400, loan creation + emit unrolled for list positions 1..3, since the guard caps the list at 3).
The member detail UI gets the `checkout` form automatically for librarians. No data migration was needed; new
members already authenticate by `username`, and single borrow/return are unchanged.

Verified: replay of 253 requests identical (no unintended change); expectations in the change file; `accrete check`;
plus a WSGI test through `app_entry.py` covering success order/ids/dates/outbox, 401/403/404, every 400 case,
409-over-400 combinations, all-or-nothing (no loans/status/outbox changes on any failure), UI form visibility,
and a newly created member authenticating, being checked out to, and borrowing.
