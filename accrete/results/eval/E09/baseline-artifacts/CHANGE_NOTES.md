# Change notes: household guardians

**Interpretation.** `members.guardian` is a nullable reference to another member, set only by
librarians (create/PATCH; a member's self-edit stays `name`-only, so `guardian` there is 403). It is
validated as null or an existing member other than the member itself, who has no guardian, and a
member who already guards someone cannot get a guardian (400). A guardian G gets, for each
dependant X (X.guardian = G): read X's record and loans (lists, filters, detail pages), borrow for X
via `{"member": X}` (all normal borrow rules for X, outbox `loan_created` with X) and return X's
loans. No PATCH/DELETE of X, nothing for X over G, borrowing for anyone else stays 403 before 409.
Rights ignore `active` and are read from the database on every request. Deleting a guardian is 409.

**Changes.** Migration `0002_member_guardian.sql` adds `members.guardian_id` (FK + index) and sets
eli/jo -> dara, gus -> fatima, lena -> kemal; committed `data.db` migrated (no other data touched).
`seed_data.json`/`seed.py` carry the guardians so a rebuild matches. Code: `repository` (column,
`dependant_ids`), `validation` (`guardian` field), `auth.RequestContext.dependant_ids`,
`permissions` (read/borrow/return take the caller's dependants), `services` (guardian validation,
delete 409, `?guardian=` filter, borrow form choices), UI (guardian column/field, `guardian` select on
`/ui/members/new`, guardians get a dependant picker in the borrow form). README updated.

**Verification.** Updated 3 existing tests for the new field; added `tests/test_library_guardians.py`
(data, filter, validation, permissions, borrow/return rules, rights following changes, UI).
71 tests pass (also run from `harness/` with `ACCEPT_TARGET`); `python seed.py` on a copy reproduces
the committed database exactly; UI form posts checked through `app_entry.create_app()`.
