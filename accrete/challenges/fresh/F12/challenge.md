# F12 (library)

Size: large. Categories: new_concept, new_relationship, failure_atomicity, permissions, cross_cutting.

## 1. Requested outcome

Members can suggest purchases; librarians turn a suggestion into a catalogued book in one atomic step, or decline it.

## 2. Observable acceptance criteria

- Seeded suggestions 1-3 exactly; read rules (own + librarians); create by anyone with validation (isbn vs books and pending suggestions).
- Suggester-only PATCH/DELETE while pending (409 otherwise, 403 for others).
- accept: librarian, pending, isbn free -> new book (title/author/isbn/year), suggestion accepted with book id, one book_added message; book borrowable.
- decline with reason; 403/409/400 ordering for both actions.
- Book referenced by a suggestion cannot be deleted; UI forms and lists.

## 3. Behaviour that must remain intact

Books, members, loans, borrowing and deletion rules of spec/apps/library.md.

Superseded base tests (0): none.

## 4. Existing-data requirements

Three suggestions created as listed; the 40 seed books and 60 loans unchanged.

## 5. Failure and recovery conditions

Refused accepts (403, 409 non-pending, 409 isbn already catalogued, 400 year) leave books, suggestions and the outbox identical (snapshot comparison).

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Refused operations that left any trace (records, related collections or outbox) in the snapshot tests.
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
