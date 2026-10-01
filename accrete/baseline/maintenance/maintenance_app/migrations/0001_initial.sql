-- Initial schema for maintenance work orders.

CREATE TABLE staff (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT    NOT NULL UNIQUE,
    name     TEXT    NOT NULL,
    role     TEXT    NOT NULL CHECK (role IN ('requester', 'technician', 'supervisor')),
    site     TEXT    NOT NULL,
    active   INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE assets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tag         TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    site        TEXT    NOT NULL,
    criticality TEXT    NOT NULL CHECK (criticality IN ('low', 'medium', 'high')),
    retired     INTEGER NOT NULL DEFAULT 0 CHECK (retired IN (0, 1))
);

CREATE TABLE work_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets (id),
    title           TEXT    NOT NULL,
    description     TEXT,
    priority        TEXT    NOT NULL CHECK (priority IN ('low', 'normal', 'urgent')),
    status          TEXT    NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'assigned', 'in_progress', 'completed', 'cancelled')),
    requested_by_id INTEGER NOT NULL REFERENCES staff (id),
    created_at      TEXT    NOT NULL,  -- YYYY-MM-DDTHH:MM:SS (UTC)
    assignee_id     INTEGER REFERENCES staff (id),
    started_at      TEXT,              -- YYYY-MM-DDTHH:MM:SS (UTC)
    completed_at    TEXT,              -- YYYY-MM-DDTHH:MM:SS (UTC)
    resolution      TEXT,
    labor_minutes   INTEGER CHECK (labor_minutes IS NULL OR labor_minutes >= 1),
    cancel_reason   TEXT
);

CREATE INDEX work_orders_asset_id ON work_orders (asset_id);
CREATE INDEX work_orders_requested_by_id ON work_orders (requested_by_id);
CREATE INDEX work_orders_assignee_id ON work_orders (assignee_id);

-- Messages emitted to integrations (exposed read-only at /api/_outbox).
CREATE TABLE outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    payload    TEXT NOT NULL,  -- JSON object
    created_at TEXT NOT NULL   -- YYYY-MM-DDTHH:MM:SS (UTC)
);
