# Clarification needed: "Right to be forgotten (library)"

The change request was NOT applied. The application is unchanged. The four acceptance
points cannot all hold at the same time, so the request contradicts itself.

## The contradictions

1. **Loans are deleted, yet they must still be served unchanged.** Point 1 says all of the
   member's loans are "deleted permanently" and must not be anonymised or reassigned. Point 2
   says that afterwards `GET /api/loans?member=<forgotten id>` must "still return all of the
   member's former loans ... unchanged". A deleted record cannot be returned by the API.
   Keeping a hidden copy, or regenerating the loans on the fly, would mean they were not
   deleted.
2. **No record may contain the member's id, yet loans must show it.** Point 1 says afterwards
   "no record in the application may contain the forgotten member's id". Point 2 requires the
   returned loans to have `member` equal to that id. Both cannot be true.
3. **Books must stay `on_loan`, and those loans must still be returnable.** A book's `status` is
   derived from its open loans (REQUIREMENTS.md). Once the loans are deleted, those books
   become `available` straight away. `POST /api/loans/{id}/return` on a deleted loan returns
   404. The only ways to meet point 2 here are to keep the loans, to forge a status that no
   longer matches the data, or to create stand-in records, and point 1 rules out all three.
4. **`member` references a member that no longer exists.** `loans.member` is a required
   reference to `members`. Keeping loans that point to a deleted member breaks referential
   integrity. Point 1 forbids the usual fix (a placeholder or pseudonymous member).

Points 3 and 4 of the request (the `member_forgotten` outbox message, and returning the record
as it was before deletion) are straightforward. They are only blocked because points 1 and 2
cannot both be met.

## Decision needed (choose one)

- **A. Erase completely:** delete the member and all their loans. Loan statistics for that
  member are lost. Books with open loans become `available`, or the action is refused with
  409 while the member has open loans. Drop the parts of point 2 that conflict with this.
- **B. Keep statistics by pseudonymising:** delete the member's personal data (username, name)
  but keep the loans, linked to an anonymous member record or with `member` cleared. This is
  what point 1 forbids, and the loans would no longer show `member == <forgotten id>`.
- **C. Keep loans as anonymous aggregate statistics:** for example per-book or per-period
  counts with no member id, and delete the individual loans. This also requires changing the
  `GET /api/loans?member=` expectation.
- **D. Postpone erasure:** refuse `forget` (409) while the member has open loans, so books
  are returned normally first. Then choose A, B or C for the returned loans.

Also confirm whether keeping the forgotten member's id in the `member_forgotten` outbox
payload is acceptable. The outbox is itself a record in the application, so with point 1 read
literally, the message would breach "no record may contain the member's id or username".
