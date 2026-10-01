# D02 - Holds on books (library)

Categories: new_concept, cross_cutting, rule_change. Depends on: none. Expect rejection: no.

## 1. Requested outcome

A FIFO hold queue per book that changes book status, borrowing rules and the return flow.

## 2. Observable acceptance criteria

- Hold placement rules (on_loan/reserved only; 409 for available, own loan, duplicate, inactive; 403 for other member).
- Queue order by `placed_at` (not by id); return promotes the first waiting hold, sets `ready_at`, emits `hold_ready`.
- Book shows `reserved`; only the ready member may borrow; success marks hold `fulfilled`.
- A ready member who fails the 3-loan limit keeps the hold.
- Cancel: permissions, state (409 on cancelled/fulfilled), passing a ready hold on to the next waiting one or freeing the book.
- Read permissions on holds; no direct create/patch/delete; UI hold/borrow/cancel forms.

## 3. Behaviour that must remain intact

- Return of a book without holds frees it with no hold_ready message; normal borrow/return/limits unchanged.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- No seed holds; no seed book is `reserved`.

## 5. Failure and recovery conditions

- Failed holds create nothing; failed borrow of a reserved book leaves the hold `ready` and the book `reserved`.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Whether queue order uses placed_at (not id).
- Regressions in borrow/return base tests.

## Brief (exact text given to implementers)

Holds (reservations) for books that are on loan

Members want to queue for a book that is currently out.

New collection `holds` with fields: `book` (reference to books), `member` (reference to members), `placed_at` (datetime), `status` (`"waiting"`, `"ready"`, `"fulfilled"` or `"cancelled"`), `ready_at` (datetime or null).

Placing a hold: `POST /api/books/{id}/hold` (body `{}`; a librarian may pass `{"member": <member id>}`).
- A member places a hold for themselves; a librarian may place one for any member by passing `member`. A member passing a `member` other than themselves -> 403.
- Allowed only while the book's status is `on_loan` or `reserved` (see below). On an `available` book -> 409.
- 409 if the member is inactive, already has a `waiting` or `ready` hold on this book, or currently has this book on loan. (The 3-loan limit does not apply to placing holds.)
- Creates a hold with `status` = `waiting`, `placed_at` = now, `ready_at` = null. Returns the book. Emits no outbox message.

Queue order: a book's holds are served in order of `placed_at`, ties broken by ascending hold id.

Returning: when a loan is returned and its book has `waiting` holds, the first hold in the queue becomes `ready` with `ready_at` = now, and an outbox message is emitted on channel `hold_ready` with payload `{"hold": <hold id>, "book": <book id>, "member": <member id>}`.

Book status: `books.status` gets a third value, `"reserved"`: the book is not on loan and has a `ready` hold. Otherwise it is `on_loan` or `available` as before.

Borrowing a reserved book: only the member of the `ready` hold may borrow it (for themselves, or a librarian lending to that member); anyone else -> 409. All existing borrow rules still apply (inactive member, 3-loan limit); if the borrow fails, the hold stays `ready`. When that member borrows the book, the hold becomes `fulfilled`.

Cancelling: `POST /api/holds/{id}/cancel` (body `{}`), by the hold's member or any librarian; another member -> 403. Only from `waiting` or `ready` (otherwise 409). Sets `status` = `cancelled` and returns the hold. If a `ready` hold is cancelled, the next `waiting` hold on that book becomes `ready` (with `ready_at` = now and a `hold_ready` message as above); if there is none, the book becomes `available`.

Permissions: members can read only their own holds; librarians can read all holds. Nobody can create holds directly (`POST /api/holds` -> 403) or PATCH or DELETE them (403).

UI: the book detail page shows a `hold` form when the caller could place a hold on that book for themselves right now. On a `reserved` book, the `borrow` form is shown only to the member whose hold is ready (and to librarians). A hold's detail page shows a `cancel` form when the caller may cancel it.

Existing data: there are no holds initially. Everything not mentioned behaves as before.
