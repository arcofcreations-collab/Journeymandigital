# Change notes: bulk checkout at the desk

**Interpretation.** `POST /api/members/{id}/checkout` with `{"books": [ids]}` lends every listed book to
the member in one transaction. Precedence: 404 unknown member, 403 non-librarian (even for themselves),
409 (member inactive; any listed id that names an existing book that is on loan; open loans + number of
list entries > 3; entries are counted as listed, so duplicates/unknown ids count too), then 400 (body not an
object, unknown fields, `books` missing/not a list/empty, non-integer or duplicate ids, unknown book ids).
On success one loan + one `loan_created` message per book, in list order; the member record is returned.
The member detail page shows a `checkout` form (multi-select of available books) to librarians when the
member could borrow right now (active, < 3 open loans), consistent with the borrow form. No schema or data
change is needed (members can already sign in with their `username`), so no migration was added.

**Changes.** `services.checkout_books` / `member_actions` / `_ensure_may_check_out`, and a shared `_lend`
helper now used by `borrow_book` too (single borrow behaviour unchanged); `permissions.can_checkout_for`;
`validation.clean_checkout_params` / `distinct_record_ids` / `is_record_id` (ids outside SQLite's integer
range are now a 400 instead of an overflow); API route and UI route + form in `members/detail.html`; README.

**Verification.** New `tests/test_library_checkout.py` (success order, loans/outbox payloads, new member,
403/404, every 400 case, 409 cases, 409-beats-400, all-or-nothing, single borrow/return unchanged, UI form
and form post). Full suite: 62 passed, run through `app_entry.create_app()` on a fresh copy per test.
