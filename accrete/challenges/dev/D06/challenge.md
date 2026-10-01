# D06 - Atomic bulk checkout (library)

Categories: failure_atomicity, new_concept, cross_cutting. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Several loans are created atomically, or none at all.

## 2. Observable acceptance criteria

- Successful checkout creates loans in list order with correct dates and emits ordered `loan_created` messages; returns the member.
- Limit counts existing open loans + listed books; inactive member 409; any unavailable book (even last in the list) 409.
- Validation (missing/empty/not list/duplicates/unknown id) 400; 409 wins over 400.
- Members 403 (also with invalid bodies); unknown member 404; unauthenticated 401.
- Loans created by checkout behave like normal loans (return, limit).

## 3. Behaviour that must remain intact

- Single borrow/return unchanged.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- No seed changes.

## 5. Failure and recovery conditions

- Every failure leaves loans, book statuses and the outbox byte-for-byte identical (snapshot comparison).

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Partial-write incidents: failing requests that leave loans, statuses or messages behind.
- Ordering of loans and messages.

## Brief (exact text given to implementers)

Bulk checkout at the desk

Librarians want to lend a stack of books to one member in one step.

New action `POST /api/members/{id}/checkout` with body `{"books": [<book id>, ...]}` lends every listed book to member `{id}`.
- Librarians only; members (also for themselves) -> 403.
- `books` must be a non-empty list of distinct ids of existing books; otherwise -> 400 (missing, empty, not a list, duplicate ids, unknown book id).
- 409 if the member is inactive, if any listed book is not `available`, or if the member's unreturned loans plus the number of listed books would exceed 3.
- When both a 409 and a 400 condition apply, the 409 wins (as everywhere in the API).
- All or nothing: if the request fails for any reason, no loan is created, no book changes status and no outbox message is emitted.
- On success: one loan per book is created, in the order listed (ascending loan ids in list order), exactly as a single borrow would create it (`borrowed_at` = now, `due_at` = today + 14 days, `returned_at` = null), and one `loan_created` message per loan is emitted, in the same order, with the usual payload `{"loan", "book", "member"}`. Returns the member record.
- UI: the member detail page shows a `checkout` form to librarians.

Newly created members can authenticate with their `username`. Single borrowing and returning are unchanged.
