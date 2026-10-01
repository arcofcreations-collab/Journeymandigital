# Change: new staff role `assistant`

Interpretation: `members.role` gains the value `assistant` (other values still 400; only librarians may set role or create members). Assistants read all members/loans (books were already public), may run `borrow` (with `{"member": id}`, same 409 guard) and `return` on any loan, and may PATCH only `active` of records whose role is `member`; on their own record only `name`. Create/update/delete of books, create/delete of members, and loan create/PATCH/delete stay forbidden (403, incl. `/ui/*/new`). Librarian and member permissions unchanged. No data migration needed (no existing value changes).

Changed (via `accrete apply`, ledger #2, `changes/0002-assistant-role.yaml`): role enum values; members read/update rules; `active` write_if (librarian, or assistant on a `member`-role record); `name` write_if (non-assistant, or own record); loans read rule; `borrow` and `return` allow expressions.

Verified: dry run replay of 253 recorded requests unchanged for existing users; expectations in the change file (enum 400, assistant reads, lending incl. 409 cases + outbox, active toggling and the 403 cases with no change, forbidden CRUD) all pass; additionally exercised a copy through `app_entry.py` WSGI: `/ui/{books,members,loans}/new` -> 403 for assistant, borrow form on available book, return form on unreturned loan only.
