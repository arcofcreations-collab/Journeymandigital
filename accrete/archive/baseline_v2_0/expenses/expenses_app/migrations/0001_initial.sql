-- Initial schema for expense claims.

CREATE TABLE employees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT    NOT NULL UNIQUE,
    name       TEXT    NOT NULL,
    role       TEXT    NOT NULL CHECK (role IN ('employee', 'manager', 'finance')),
    manager_id INTEGER REFERENCES employees (id),
    department TEXT    NOT NULL
);

CREATE INDEX employees_manager_id ON employees (manager_id);

CREATE TABLE claims (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id      INTEGER NOT NULL REFERENCES employees (id),
    amount           REAL    NOT NULL CHECK (amount > 0 AND amount <= 5000),
    category         TEXT    NOT NULL CHECK (category IN ('travel', 'meals', 'equipment', 'other')),
    description      TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft', 'submitted', 'approved', 'rejected', 'paid')),
    submitted_at     TEXT,   -- YYYY-MM-DDTHH:MM:SS (UTC)
    decided_at       TEXT,   -- YYYY-MM-DDTHH:MM:SS (UTC)
    decided_by_id    INTEGER REFERENCES employees (id),
    rejection_reason TEXT
);

CREATE INDEX claims_employee_id ON claims (employee_id);
CREATE INDEX claims_decided_by_id ON claims (decided_by_id);

-- Messages emitted to integrations (exposed read-only at /api/_outbox).
CREATE TABLE outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    payload    TEXT NOT NULL,  -- JSON object
    created_at TEXT NOT NULL   -- YYYY-MM-DDTHH:MM:SS (UTC)
);
