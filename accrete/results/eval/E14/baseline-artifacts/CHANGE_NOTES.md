# E14: lost copies

Interpretation: a loan is *open* while `returned_at` and `lost_at` are both null; everything that
counted unreturned loans (3-loan limit, copy `on_loan`, `overdue`, `return`'s 409) now uses "open".
Copy `status` is `lost` > `on_loan` > `available`; book status/`available_copies`/borrow ignore lost
copies. `declare_lost` (librarians, open loans) and `found` (librarians, lost copies) follow the usual
404 > 403 > 409 > 400 precedence; their body must be `{}`. Deleting copies/books with loans stays 409.

Changes: migration `0003_lost_copies.sql` adds `loans.lost_at` and `copies.lost`, rebuilds the
"one open loan per copy" unique index to exclude lost loans (so a found copy can be lent again), and
marks loans 46/50 lost at 2026-02-28T10:00:00 and copies 4/16 lost (no outbox messages). Updated
repository (open-loan SQL, copy/book status), services (`declare_loan_lost`, `mark_copy_found`,
`copy_actions`, `loan_actions`), permissions, API/UI routes, templates (new fields, `declare_lost`
and `found` forms), seed_data.json/seed.py, README; committed data.db migrated via `create_app()`.

Verification: updated the existing tests whose fixtures relied on loans 46/50 being open (jo's 3 loans,
book 4 on loan, overdue list) and added tests/test_library_lost.py (migrated data, upgrade of an E08
database, declare_lost/found effects, refusals changing nothing, limits, book status, UI forms).
83 tests pass, also when run from harness/ with ACCEPT_TARGET.
