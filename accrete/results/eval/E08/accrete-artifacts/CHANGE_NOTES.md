# Change: physical copies of books

Interpretation: as stated. A copy's `book` is fixed at creation (any `book` in a PATCH -> 400, even the same value); an empty or whitespace-only barcode counts as empty (400).

Changed (one accrete change, `changes/0002-copies.yaml`, ledger #2):
- New entity `copies` (`book` ref books required, on_delete cascade; `barcode` text required unique + non-empty constraint; computed `status`). Everyone can read; only librarians can create/update/delete. An update trigger fails with 400 when `book` is sent; delete_guard returns 409 when the copy has any loan.
- `loans.copy` (required ref copies), backfilled with the book's original copy (id = book id). Loans still can't be created, patched or deleted directly.
- `books.status` is now unavailable/available/on_loan, derived from copies; new computed `books.available_copies`.
- `borrow` lends the available copy with the lowest id, and `loan_created` now includes `copy`. Returning a loan frees its copy because copy status is derived. Deleting a book with loans is still 409; otherwise its copies are deleted too (cascade).
- Data: copies 1-40 (barcode C0001..C0040, one per book), copy 41 (book 1, C0001-2) and copy 42 (book 22, C0022-2). New copies get ids from 43.

Verified: the dry-run replay (697 requests, 0 unexplained differences) and about 45 expectations in the change file, covering permissions, 400/403/409 cases, borrow copy choice, the outbox, return, cascade delete and migrated data. `accrete check` passes. A manual run through app_entry.py with harness/accept_client.py checked the UI (/ui/copies list and detail, /ui/copies/new: 403 for members, inputs book and barcode for librarians, borrow form only when a copy is available) and the API.
