# E14 (library, after E08): lost copies

## 1. Requested outcome
Librarians can declare an open loan lost (closing it and taking its copy out of circulation) and
mark a lost copy as found. Book availability, borrowing limits, overdue status and returns take lost
loans/copies into account. Two historic loans are migrated to "lost".

## 2. Observable acceptance criteria
- Loans 46 and 50 have `lost_at` 2026-02-28T10:00:00, copies 4 and 16 `lost: true` / status
  `lost`; books 4 and 16 `unavailable`; all other loans/copies unchanged with null/false.
- Lost loans are not overdue (overdue set becomes 47 48 49), cannot be returned (409) and do not
  count towards the 3-loan limit (jo can borrow two more books, then 409).
- `declare_lost` (librarian, open loans only, 403 before 409): sets `lost_at`, copy lost, emits
  `copy_lost {"loan","copy","book","member"}`; the book stays available if another copy is.
- `found` (librarian, lost copies only): copy available again and lendable; the loan stays closed.
- New fields read-only; deleting a copy with loans still 409; UI forms as specified.

## 3. Behaviour that must remain intact
E08 copy model, lowest-id selection, `loan_created` payload with `copy`; member permissions and
the 3-loan limit for open loans; returns of normal loans.

## 4. Existing-data requirements
Exactly two loans and two copies transformed. Cumulative superseded base tests: 12 (E08's 8 plus 4
that rely on loans 46/50 being open and overdue, on jo holding 3 loans, and on book 4 being on loan).

## 5. Failure and recovery conditions
Refused `declare_lost` calls leave loans, copies, books and outbox identical (snapshot). A found
copy can be lent again, recovering availability.

## 6. Measurements to collect
Standard harness measurements, plus consistency of the "closed loan" notion across limit, overdue,
return and book status.
