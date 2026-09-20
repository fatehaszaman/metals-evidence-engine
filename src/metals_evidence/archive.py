"""Append-only SQLite archive with an operational knowledge-time cutoff."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from metals_evidence.model import Observation, canonical, utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    series TEXT NOT NULL,
    event_time TEXT NOT NULL,
    published_time TEXT NOT NULL,
    ingested_time TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision >= 0),
    raw_hash TEXT NOT NULL,
    envelope TEXT NOT NULL,
    UNIQUE(source, series, event_time, revision)
);
CREATE INDEX IF NOT EXISTS knowledge_time
ON observations(ingested_time, published_time, event_time);
CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'archive is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'archive is append-only'); END;
PRAGMA user_version = 1;
"""


class Archive:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(path)
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise ValueError(f"unsupported archive schema version {version}")
        self.connection.executescript(SCHEMA)

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *args: object) -> None:
        self.connection.close()

    def append(self, observation: Observation) -> bool:
        """Exact duplicates are idempotent; conflicting same-version records fail closed."""
        with self.connection:
            if self.connection.execute(
                "SELECT 1 FROM observations WHERE id = ?", (observation.id,)
            ).fetchone():
                return False
            try:
                self.connection.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        observation.id,
                        observation.source,
                        observation.series,
                        observation.event_time,
                        observation.published_time,
                        observation.ingested_time,
                        observation.revision,
                        observation.raw_hash,
                        canonical(observation.to_dict()),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "conflicting source/series/event/revision; preserve and investigate upstream"
                ) from exc
        return True

    def as_of(self, cutoff: str) -> list[Observation]:
        """Filter availability BEFORE ranking revisions. Sources are never silently merged."""
        cutoff = utc(cutoff)
        rows = self.connection.execute(
            """
            WITH eligible AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY source, series, event_time
                    ORDER BY revision DESC, published_time DESC, ingested_time DESC, id
                ) AS rank
                FROM observations
                WHERE event_time <= ? AND published_time <= ? AND ingested_time <= ?
            )
            SELECT envelope FROM eligible WHERE rank = 1
            ORDER BY source, series, event_time, id
            """,
            (cutoff, cutoff, cutoff),
        ).fetchall()
        return [Observation.from_dict(json.loads(row[0])) for row in rows]

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
