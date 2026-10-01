-- Initial schema for the lending library.

CREATE TABLE members (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    name     TEXT    NOT NULL,
    role     TEXT    NOT NULL CHECK (role IN ('member', 'librarian')),
    active   INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE books (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    title  TEXT    NOT NULL,
    author TEXT    NOT NULL,
    isbn   TEXT    NOT NULL UNIQUE,
    year   INTEGER
);

CREATE TABLE loans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL REFERENCES books (id),
    member_id   INTEGER NOT NULL REFERENCES members (id),
    borrowed_at TEXT    NOT NULL,  -- YYYY-MM-DDTHH:MM:SS (UTC)
    due_at      TEXT    NOT NULL,  -- YYYY-MM-DD
    returned_at TEXT               -- YYYY-MM-DDTHH:MM:SS (UTC) or NULL while on loan
);

CREATE INDEX loans_book_id ON loans (book_id);
CREATE INDEX loans_member_id ON loans (member_id);
-- A book can be on loan to at most one member at a time.
CREATE UNIQUE INDEX loans_one_open_loan_per_book ON loans (book_id) WHERE returned_at IS NULL;

-- Messages emitted to integrations (exposed read-only at /api/_outbox).
CREATE TABLE outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    payload    TEXT NOT NULL,  -- JSON object
    created_at TEXT NOT NULL   -- YYYY-MM-DDTHH:MM:SS (UTC)
);
