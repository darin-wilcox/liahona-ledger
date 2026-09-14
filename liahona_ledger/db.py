"""SQLite persistence layer for liahona-ledger.

One meeting = one row in `meetings`, with child rows for speakers,
musical numbers, and ward business items. Announcements are stored
independently with a validity date range so the same announcement can
be reused across several weeks without re-entering it, and with
per-channel flags (agenda / program / email) since not every
announcement goes everywhere.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path.home() / ".liahona-ledger" / "liahona_ledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_date            TEXT NOT NULL UNIQUE,          -- ISO 8601: YYYY-MM-DD
    meeting_type            TEXT NOT NULL DEFAULT 'sacrament',  -- sacrament | fast_and_testimony | stake_conference | general_conference | ward_conference
    presiding                TEXT,
    conducting               TEXT,
    chorister                TEXT,
    organist                 TEXT,
    pianist                  TEXT,
    opening_hymn_number      TEXT,
    opening_hymn_title       TEXT,
    sacrament_hymn_number    TEXT,
    sacrament_hymn_title     TEXT,
    closing_hymn_number      TEXT,
    closing_hymn_title       TEXT,
    opening_prayer           TEXT,
    closing_prayer           TEXT,
    presiding_notes          TEXT,   -- free-form agenda notes for the bishopric (timing, reminders, etc.)
    spiritual_thought        TEXT,   -- program cover page quote
    spiritual_thought_author TEXT,
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS speakers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    order_index     INTEGER NOT NULL DEFAULT 0,
    name            TEXT NOT NULL,
    topic           TEXT,
    is_youth        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS musical_numbers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    order_index     INTEGER NOT NULL DEFAULT 0,
    performer       TEXT NOT NULL,
    title           TEXT,
    slot            TEXT NOT NULL DEFAULT 'musical_number'  -- musical_number | special_number
);

CREATE TABLE IF NOT EXISTS ward_business (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    order_index     INTEGER NOT NULL DEFAULT 0,
    category        TEXT NOT NULL,   -- move_in | release | calling_sustaining | baby_blessing | confirmation | baptism | other
    person_name     TEXT NOT NULL,
    description     TEXT,
    set_apart       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS announcements (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    text                TEXT NOT NULL,
    start_date          TEXT NOT NULL,   -- ISO 8601, first Sunday it should appear
    expiration_date     TEXT NOT NULL,   -- ISO 8601, last Sunday it should appear (inclusive)
    include_in_agenda   INTEGER NOT NULL DEFAULT 1,
    include_in_program  INTEGER NOT NULL DEFAULT 1,
    include_in_email    INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_speakers_name ON speakers(name);
CREATE INDEX IF NOT EXISTS idx_ward_business_person ON ward_business(person_name);
CREATE INDEX IF NOT EXISTS idx_announcements_dates ON announcements(start_date, expiration_date);
"""


class Database:
    """Thin wrapper around sqlite3 with schema management."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
