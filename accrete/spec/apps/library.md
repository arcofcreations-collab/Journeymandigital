# Application: Lending library (`library`)

A small community library tracks members, books and loans. Starting data: `library_seed.json`
(the same records, with the same ids, are loaded into every implementation).

## Collections and fields

**members**: `username` (text, required, unique), `name` (text, required),
`role` (`"member"` or `"librarian"`, required), `active` (boolean, default `true`).

**books**: `title` (text, required), `author` (text, required), `isbn` (text, required, unique),
`year` (integer, optional), `status` (derived: `"on_loan"` if the book has a loan with no
`returned_at`, otherwise `"available"`).

**loans**: `book` (reference to books), `member` (reference to members),
`borrowed_at` (datetime), `due_at` (date), `returned_at` (datetime or null),
`overdue` (derived: `true` when `returned_at` is null and the current date is after `due_at`).

## Actions

* `POST /api/books/{id}/borrow`: a member borrows the book for themselves. A librarian may
  instead pass `{"member": <member id>}` to lend to that member. Creates a loan with
  `borrowed_at` = now and `due_at` = today + 14 days. Fails with `409` if the book is on loan,
  the borrowing member is inactive, or the member already has 3 unreturned loans.
  A member passing a `member` other than themselves gets `403`. Emits outbox message on channel
  `loan_created` with payload `{"loan": id, "book": id, "member": id}`.
  Returns the book.
* `POST /api/loans/{id}/return`: by the borrowing member or any librarian. Sets
  `returned_at` = now. `409` if already returned. Returns the loan.

## Permissions

* Any authenticated user can read all books.
* Members can read their own member record and their own loans; librarians can read everything.
* Only librarians can create, update or delete books and members.
* Members can update only the `name` of their own member record (other fields: `403`).
* Nobody can create loans directly (`POST /api/loans` -> `403`) or delete loans (`403`);
  loans change only through the actions above. Nobody can PATCH loans (`403`).
* Deleting a book that has any loans -> `409`.

## Validation

* Required fields missing -> `400`. Duplicate `username` or `isbn` -> `400`.
* `role` must be one of the listed values -> `400`.
