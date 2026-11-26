from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    deck TEXT NOT NULL,
    source_file TEXT NOT NULL,
    card_type TEXT NOT NULL,
    module TEXT NOT NULL,
    unit TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS card_state (
    card_id TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'forward',
    repetitions INTEGER NOT NULL DEFAULT 0,
    interval_days INTEGER NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    lapses INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    last_reviewed_at TEXT,
    PRIMARY KEY (card_id, direction),
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    mode TEXT NOT NULL,
    rating INTEGER NOT NULL,
    elapsed_ms INTEGER,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cards_filter ON cards(deck, module, unit, card_type, archived);
CREATE INDEX IF NOT EXISTS idx_state_due ON card_state(due_at, direction);
"""


def create_connection(path: str) -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement enabled and dict-like rows."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not exist, and record the schema version."""
    conn.executescript(SCHEMA_SQL)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
