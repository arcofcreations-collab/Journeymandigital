# Change notes: authors as records

**Interpretation.** New `authors` collection (`name` required/unique by exact text, derived `book_count`);
readable by any authenticated user, written only by librarians (403), delete with books -> 409.
`books.author` is now the author's integer id (missing/null/text/unknown id/non-integer -> 400) and
books gain derived `author_name` (current name, follows renames). `?author=<id>` filters books.
Error precedence stays 404 > 403 > 409 > 400. Everything else is unchanged.

**Changes.**
- `library_app/migrations/0002_authors.sql`: creates `authors` from the distinct book author texts
  (ids 1, 2, ... by first appearance in ascending book id), rebuilds `books` with
  `author_id NOT NULL REFERENCES authors` (+ index). `loans` is set aside and recreated (same rows,
  indexes) because foreign keys can't be disabled inside the migration's transaction;
  AUTOINCREMENT counters are preserved. Committed `data.db` migrated by starting the app once.
- `repository.py`, `validation.py`, `permissions.py`, `services.py`, `routes_api.py`, `routes_ui.py`:
  author CRUD + book reference/existence check, `author_name`, `book_count`.
- Templates: `authors/{list,detail,new}.html`; book detail shows `author` as the author's name
  (linked) plus `author_name`; book list shows names; book create form's `author` is a select of
  authors; nav link. `seed_data.json` gains `authors` and books reference them; `seed.py` loads them.
- README notes; tests updated and `tests/test_library_authors.py` added (API, permissions, UI and a
  migration test that upgrades a schema-v1 database with tricky data).

**Verification.** Full suite: 64 passed (run with a minimal local stand-in for `harness/accept_client.py`,
which is not present in this workspace). Checked that the migrated `data.db` equals a fresh
`python seed.py` rebuild (all tables, schema, sqlite_sequence), that every book/loan/member row is
unchanged apart from author text -> id, and `PRAGMA foreign_key_check`/`integrity_check` are clean.
