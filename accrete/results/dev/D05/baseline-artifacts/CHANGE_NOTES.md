# Change notes: new staff role `assistant`

**Interpretation.** `assistant` is a third `members.role` value. Assistants are staff for
lending only: they read all members/books/loans, lend any book to any member via
`POST /api/books/{id}/borrow {"member": id}` (same 409/400 rules as librarians) and return any
loan. They may PATCH only `active`, and only on records whose role is `member`; on their own
record only `name`. Any other field or target -> 403 with no change (403 precedes 400). They cannot
manage books, create/delete members, or create/PATCH/delete loans; the three `/ui/*/new` pages
are 403. Librarian and member permissions are unchanged; only librarians create members or set roles.

**Changes.**
- `library_app/migrations/0002_add_assistant_role.sql`: rebuilds `members` with the widened
  `role` CHECK (and `loans`, its only FK child, since FK enforcement can't be disabled inside the
  migration transaction). Keeps every row, id, index and AUTOINCREMENT counter. Committed `data.db` is migrated.
- `validation.MEMBER_ROLES` adds `assistant` (the new-member form picks it up automatically).
- `permissions.py`: `is_staff` (librarian or assistant) for reading members/loans, returning and
  lending to others; `can_update_member` has the assistant rules. Book and member management stays librarian-only.
- `services.book_actions` and `routes_ui.show_book`: staff get the borrow form with a member picker.
  Assistants see the return form through `can_return_loan`.
- README interpretations updated; new `tests/test_library_assistants.py` (API, UI, migration of a v1 database).

**Verification.** The full pytest suite passes (70 tests: the 52 existing ones and 18 new),
with each test loading a fresh copy through `app_entry.create_app()`. I also checked
`PRAGMA foreign_key_check` and `integrity_check` on a migrated database. The real
`harness/` sits outside this workspace, so I ran the tests with a minimal local stand-in
for `accept_client` (`fresh_app` and `parse_ui`).
