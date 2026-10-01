# D01 - Authors become records (library)

Categories: data_migration, new_relationship, new_concept, cross_cutting. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Authors are first-class records; `books.author` is a reference; existing free-text authors are migrated deterministically.

## 2. Observable acceptance criteria

- `GET /api/authors` returns ids 1..6 named M. Reyes, T. Okoye, S. Lindqvist, R. Banerjee, J. Moreau, K. Tanaka (first appearance order).
- `book_count` is 8, 8, 5, 5, 8, 6 respectively and changes when books are created, re-assigned or deleted.
- Every seed book has `author` = migrated id and `author_name` = previous text; `?author=<id>` filters.
- Creating/updating a book with a text author, null, missing or unknown id -> 400; with a valid id -> stored.
- Author name uniqueness on create and rename (400); rename propagates to `author_name`.
- Members get 403 on author writes (403 before 400); deleting an author with books -> 409, without books -> 204.
- UI: book detail `author` shows the name; `/ui/authors` lists 1..6; `/ui/authors/new` is 403 for members.

## 3. Behaviour that must remain intact

- Borrowing/returning and loans unchanged; other book fields unchanged; book create form keeps an `author` input; members still cannot write books.
- Base tests intentionally superseded: test_book_fields_and_derived_status, test_books_filter_by_text_and_integer, test_librarian_creates_book, test_book_year_is_optional, test_librarian_updates_book; every other base test must still pass.

## 4. Existing-data requirements

- 40 books keep ids/titles/isbn/year; 6 authors created with deterministic ids; per-author counts as above.

## 5. Failure and recovery conditions

- Invalid author references are rejected with 400 and leave the catalogue unchanged.
- Deleting an author that still has books is refused (409) and nothing is deleted.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Whether the 6 authors get exactly the deterministic ids (first-appearance order).
- Number of book-related base tests broken beyond the 5 superseded ones.

## Brief (exact text given to implementers)

Authors as records

Today a book's `author` is free text. We want authors to be records of their own, and every book to point to one.

New collection `authors` with fields:
- `name` (text, required, unique). Missing or duplicate name (on create or update) -> 400.
- `book_count` (derived, read-only): the number of books whose `author` is this author.
Permissions: any authenticated user can read all authors. Only librarians can create, update or delete authors (others -> 403). Deleting an author who still has at least one book -> 409.

Books:
- `books.author` becomes a reference to `authors` (serialised as the author's integer id). On create and update, `author` must be the id of an existing author; anything else (missing, null, a text name, an unknown id) -> 400.
- Books get a new derived, read-only field `author_name`: the referenced author's current `name` (it follows renames).
- `GET /api/books?author=<author id>` filters by author.
- HTML UI: on the book detail page the `author` field displays the author's name (not the id). The book create form still has an input named `author`. `/ui/authors` lists authors like any other collection.

Existing data (required): every distinct author text found in the existing books becomes exactly one author record whose `name` is that text. Author ids are 1, 2, 3, ... in order of first appearance when the existing books are read in ascending book id order. Every existing book's `author` must reference the author whose `name` equals its previous author text. Book ids, titles, ISBNs, years, loans and members do not change.

Everything else (borrowing, returning, loans, members, who may write books) behaves exactly as before.
