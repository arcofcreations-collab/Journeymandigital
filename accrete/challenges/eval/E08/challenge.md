# E08 (library): physical copies

## 1. Requested outcome
Books get physical `copies`; loans record the lent `copy`; a book's status and the new
`available_copies` are derived from its copies; borrowing lends the lowest-id available copy.
Existing data is migrated to one copy per book, plus two extra copies the library bought.

## 2. Observable acceptance criteria
- Copies 1-40 (copy i = book i, barcode C%04d) plus 41 (book 1, C0001-2) and 42 (book 22, C0022-2);
  copy status derived from open loans; every loan's `copy` equals its book id.
- Book status: available / on_loan / unavailable (no copies); books 1 and 22 now available with
  `available_copies` 1; the 13 other on-loan books have 0.
- Borrow picks the lowest available copy (book 1 -> copy 41 while copy 1 is out; copy 1 after
  loan 55 is returned); payload `{"loan","book","member","copy"}`; 409 with no available copy and no message.
- New books are `unavailable` until a librarian adds a copy; copies CRUD librarian-only with
  validation (unique barcode, existing book, no book change, derived status not settable),
  delete 409 when the copy has loans; deleting a loan-free book deletes its copies.
- UI: copies list/detail/new; borrow form only with an available copy.

## 3. Behaviour that must remain intact
3-open-loan limit, inactive member 409, member lending for others 403 (403 first), returns,
loans not writable directly, member read restrictions, book validation.

## 4. Existing-data requirements
42 copies exactly as specified; 60 loans get `copy`; nothing else changes. Superseded base tests (8):
those asserting that books 1/22 are on loan or unborrowable, the exact `loan_created` payload, and
the `available` status of a freshly created book.

## 5. Failure and recovery conditions
Refused borrows create no loan and emit nothing. Returning a loan frees exactly its copy, and the
next borrow can take it again. A refused copy delete leaves the copy and book status intact.

## 6. Measurements to collect
Standard harness measurements, plus whether the migration produced the exact ids/barcodes and
whether the lowest-id selection rule is followed after returns.
