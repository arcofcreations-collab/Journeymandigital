# D05 - Assistant role (library)

Categories: permissions, rule_change. Depends on: none. Expect rejection: no.

## 1. Requested outcome

A third role with a precise, partial staff permission set.

## 2. Observable acceptance criteria

- Librarians create assistants; role validation still rejects unknown roles; non-librarians cannot create members.
- Assistants read all members/loans/books, lend (all borrow rules apply) and return any loan.
- Assistants toggle `active` of role-`member` records only; any other field or staff target -> 403 with no change.
- Assistants' own record: `name` only.
- Assistants cannot write books, create/delete members, or write loans; UI create forms 403; UI borrow/return forms shown.
- Promoting a member to assistant grants the rights immediately.

## 3. Behaviour that must remain intact

- Members still see only themselves and cannot lend; librarians keep full rights.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- No seed member changes role; 12 seed members unchanged.

## 5. Failure and recovery conditions

- Rejected assistant PATCHes leave records untouched; failed lends create no loans/messages.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Number of permission cells wrong (assistant x operation).
- Member/librarian permission regressions.

## Brief (exact text given to implementers)

New staff role: assistant

We are hiring desk assistants who should handle lending but not manage the catalogue or membership.

`members.role` accepts a third value, `"assistant"` (any other value is still 400). As before, only librarians can create members or change a member's role. Newly created members, including assistants, can authenticate with their `username` as `X-User`.

Assistants:
- can read all books, all members and all loans (like librarians);
- can lend any book to any member with `POST /api/books/{id}/borrow` and `{"member": <member id>}`, subject to all existing borrow rules (the same 409 cases), and can return any loan;
- can PATCH the `active` field of members whose role is `member` (to deactivate or reactivate them). A PATCH by an assistant that includes any other field, or that targets a librarian's or another assistant's record -> 403, and nothing changes. On their own record an assistant may change only their `name`, like any member;
- cannot create, update or delete books, cannot create or delete members, and cannot create, PATCH or delete loans (403). `GET /ui/books/new`, `/ui/members/new` and `/ui/loans/new` -> 403 for them.
- UI: assistants see the `return` form on any unreturned loan and the `borrow` form on available books.

Librarians' and members' permissions are unchanged.
