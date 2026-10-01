# Change notes: physical copies of books

**Interpretation.** Books now own physical `copies`; a loan lends one copy and the loan's `book`
is that copy's book. Book `status` is derived from copies (available / on_loan / unavailable)
plus `available_copies`; `borrow` lends the lowest-id available copy and is 409 when there is
none. Deleting a book (only possible when none of its copies was ever lent) deletes its copies.
Copy `book` given on PATCH is a 400 even if unchanged; `status`/`id`/unknown fields are 400.

**Changes.**
- `library_app/migrations/0002_copies.sql`: new `copies` table (unique barcode); one copy per
  existing book (id = book id, barcode `C%04d`), copies 41 (book 1) and 42 (book 22), copy
  sequence starts above 42; `loans` rebuilt with `copy_id` (= old `book_id`) replacing `book_id`
  (loan id counter kept), open-loan uniqueness now per copy. Committed `data.db` migrated in place.
- `repository.py` (copy queries, derived book status/available_copies, loans join copies),
  `validation.clean_copy`, `permissions` (copies readable by all, librarian-managed),
  `services.py` (copy CRUD, borrow picks a copy, outbox payload gains `copy`, book delete),
  `routes_api.py` (`/api/copies`), `routes_ui.py` + templates (`/ui/copies`, `/ui/copies/new`,
  `/ui/copies/<id>`, copy column/field on loans, `available_copies` and copy list on books).
- `seed_data.json` gains `copies` and loan `copy`; `seed.py` loads them.
- README business rules and interpretations updated.

**Verification.** `python -m pytest tests -q` (also run from `harness/` with `ACCEPT_TARGET`):
68 passed. Updated existing tests for the intended changes and added `tests/test_library_copies.py`
(migrated data, CRUD/permissions/precedence/validation, borrow copy choice, return, deletes, UI,
and a test that upgrades a pre-copies database through startup). Checked that the migrated
`data.db` is row-for-row and schema-identical to a fresh `seed.py` rebuild, and passes
`PRAGMA integrity_check` / `foreign_key_check`.
