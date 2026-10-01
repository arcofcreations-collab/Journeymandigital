# Change notes: holds (reservations)

**Interpretation.** New `holds` collection (`book`, `member`, `placed_at`, `status`, `ready_at`), placed via
`POST /api/books/{id}/hold` only while the book is `on_loan` or `reserved`; queue order is `placed_at`, then id.
Returning a loan (or cancelling a `ready` hold) makes the head `waiting` hold `ready` and emits `hold_ready`.
Book `status` is derived: `on_loan` > `reserved` (has a `ready` hold) > `available`. Only the ready hold's member
can borrow a reserved book (fulfilling the hold); a failed borrow leaves it `ready`. Checks follow the
existing precedence (404, 403, 409, 400), mirroring borrow. Additional decisions: deleting a member who has
holds → 409 (otherwise a foreign-key error); a cancelled `ready` hold keeps its `ready_at`.

**Changes.** Migration `0002_holds.sql` (table, indexes, partial unique indexes: one `ready` hold per book,
one open hold per member and book; no data to migrate) applied to `data.db`. `repository.py` (holds SQL,
`reserved` status), `permissions.py` (`can_act_for`, hold read/cancel), `validation.py`
(`clean_member_params` shared by borrow/hold), `services.py` (`place_hold`, `cancel_hold`, hold
list/get/403 operations, `_serve_next_hold`, reserved-book borrow rule, book/hold UI actions),
`routes_api.py`, `routes_ui.py`, templates (`books/detail.html` hold form, `holds/` list + detail, nav link),
README.

**Verification.** New `tests/test_library_holds.py` (placement rules, permissions, queue order, return/cancel
promotion and outbox, reserved borrowing, UI forms) plus a hold form-post UI test; the existing UI test
for an on-loan book now expects the `hold` form. Full suite: 70 passed, loading the app through
`app_entry.py`; `seed.py` rebuild also checked.
