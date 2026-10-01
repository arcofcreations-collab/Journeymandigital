# Change notes: Authors as records

Interpretation: `books.author` (free text) becomes a required reference to a new `authors`
collection (`name` text required unique; `book_count` computed = number of books referencing it).
Authors are readable by any authenticated user, written/deleted only by librarians (403 otherwise);
deleting an author still referenced by a book gives 409. Books gain computed read-only
`author_name` = `record.author.name` (follows renames). The UI shows authors by name where referenced.

Changed (via `accrete apply`, ledger #2, file changes/0002-authors-as-records.yaml):
`promote_field` books.author -> authors (key `name`, ids by first appearance in ascending book id:
1 M. Reyes, 2 T. Okoye, 3 S. Lindqvist, 4 R. Banerjee, 5 J. Moreau, 6 K. Tanaka), with rules and
`book_count`; `change_field` to keep books.author required (promotion had dropped it); `add_field`
books.author_name. Book/loan/member data untouched.

Verified: replay of 661 requests (0 unexplained, 0 unacknowledged consequences); 30 stated
expectations (author CRUD permissions, 400 on missing/duplicate name, 409 on delete with books,
book create/update rejecting missing/null/text/unknown author, ?author= filter, rename propagation);
plus a WSGI check through app_entry.py on a copy: author counts sum to 40, /ui/books/1 shows the
author's name, /ui/books/new has input `author`, /ui/authors lists 6 rows, borrow/permissions unchanged.
