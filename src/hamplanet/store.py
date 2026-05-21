"""SQLite-backed record of URLs we've already acted on."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    url        TEXT PRIMARY KEY,
    site       TEXT NOT NULL,
    channel    TEXT,
    action     TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_site_channel ON actions(site, channel);
"""


class ActionStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def acted_urls(self) -> set[str]:
        cur = self._conn.execute("SELECT url FROM actions")
        return {row[0] for row in cur}

    def record(
        self,
        *,
        url: str,
        site: str,
        channel: str | None,
        action: str,
        result: str,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO actions "
            "(url, site, channel, action, result, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, site, channel, action, result, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
