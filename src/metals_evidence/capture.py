"""Continuous local-delivery capture. No network feed or LLM is implied."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from metals_evidence.archive import Archive
from metals_evidence.model import Observation, canonical, number, utc
from metals_evidence.quality import assess, rejected_delivery

SCHEMA = """
CREATE TABLE IF NOT EXISTS deliveries (
    hash TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    payload BLOB NOT NULL,
    policy TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intake_decisions (
    delivery_hash TEXT NOT NULL REFERENCES deliveries(hash),
    item INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    observation_id TEXT,
    PRIMARY KEY(delivery_hash, item)
);
CREATE TABLE IF NOT EXISTS intake_scorecards (
    delivery_hash TEXT NOT NULL,
    item INTEGER NOT NULL,
    scorecard TEXT NOT NULL,
    PRIMARY KEY(delivery_hash, item),
    FOREIGN KEY(delivery_hash, item) REFERENCES intake_decisions(delivery_hash, item)
);
CREATE TRIGGER IF NOT EXISTS delivery_no_update BEFORE UPDATE ON deliveries
BEGIN SELECT RAISE(ABORT, 'raw deliveries are append-only'); END;
CREATE TRIGGER IF NOT EXISTS delivery_no_delete BEFORE DELETE ON deliveries
BEGIN SELECT RAISE(ABORT, 'raw deliveries are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decision_no_update BEFORE UPDATE ON intake_decisions
BEGIN SELECT RAISE(ABORT, 'intake decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS decision_no_delete BEFORE DELETE ON intake_decisions
BEGIN SELECT RAISE(ABORT, 'intake decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS scorecard_no_update BEFORE UPDATE ON intake_scorecards
BEGIN SELECT RAISE(ABORT, 'scorecards are append-only'); END;
CREATE TRIGGER IF NOT EXISTS scorecard_no_delete BEFORE DELETE ON intake_scorecards
BEGIN SELECT RAISE(ABORT, 'scorecards are append-only'); END;
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class SeriesPolicy:
    source: str
    series: str
    metal: str
    geography: str
    unit: str
    definition: str
    max_age_seconds: int
    max_relative_change: str | None = None

    def __post_init__(self):
        for field in ("source", "series", "metal", "geography", "unit", "definition"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"policy {field} must be nonempty")
        if type(self.max_age_seconds) is not int or self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be a positive integer")
        if self.max_relative_change is not None and number(self.max_relative_change) < 0:
            raise ValueError("max_relative_change must be nonnegative")


def load_policy(path: str | Path) -> list[SeriesPolicy]:
    data = json.loads(Path(path).read_text())
    if (
        not isinstance(data, dict)
        or set(data) != {"series"}
        or not isinstance(data["series"], list)
    ):
        raise ValueError("policy requires exactly a series list")
    rules = [SeriesPolicy(**row) for row in data["series"]]
    if len({(r.source, r.series) for r in rules}) != len(rules):
        raise ValueError("duplicate source/series policy")
    return rules


class Intake:
    """Record raw bytes before parsing. Only deterministic, validated rows reach Archive."""

    def __init__(self, archive: Archive, clock: Callable[[], str] = now):
        self.archive = archive
        self.clock = clock
        archive.connection.executescript(SCHEMA)

    def _decision(
        self,
        delivery_hash: str,
        item: int,
        status: str,
        reason: str,
        observation_id: str | None = None,
        scorecard: dict | None = None,
    ):
        with self.archive.connection:
            self.archive.connection.execute(
                "INSERT OR IGNORE INTO intake_decisions VALUES (?, ?, ?, ?, ?)",
                (delivery_hash, item, status, reason, observation_id),
            )
            if scorecard is not None:
                self.archive.connection.execute(
                    "INSERT OR IGNORE INTO intake_scorecards VALUES (?, ?, ?)",
                    (delivery_hash, item, canonical(scorecard)),
                )

    def capture(self, payload: bytes, policies: list[SeriesPolicy]) -> dict:
        delivery_hash = hashlib.sha256(payload).hexdigest()
        received = utc(self.clock())
        connection = self.archive.connection
        # Persist before any JSON parsing, validation or candidate processing.
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO deliveries VALUES (?, ?, ?, ?)",
                (delivery_hash, received, payload, canonical([asdict(p) for p in policies])),
            )
        received, policy_text = connection.execute(
            "SELECT received_at, policy FROM deliveries WHERE hash=?", (delivery_hash,)
        ).fetchone()
        # A retry uses the original receipt time AND original policy snapshot.
        original_policies = [SeriesPolicy(**p) for p in json.loads(policy_text)]
        try:
            if len(payload) > 10 * 1024 * 1024:
                raise ValueError("delivery exceeds 10 MiB processing limit; raw bytes preserved")
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise ValueError("delivery must be a JSON object")
            if document.get("extraction_method") != "deterministic":
                raise ValueError("unverified extraction: LLM/ML candidates require human review")
            if set(document) != {"extraction_method", "observations"}:
                raise ValueError("unexpected delivery fields")
            rows = document["observations"]
            if not isinstance(rows, list) or not rows:
                raise ValueError("observations must be a nonempty list")
        except (ValueError, TypeError, UnicodeError) as exc:
            self._decision(
                delivery_hash,
                -1,
                "QUARANTINED",
                str(exc),
                scorecard=rejected_delivery(str(exc)),
            )
            return self.result(delivery_hash)
        for index, candidate in enumerate(rows):
            if connection.execute(
                "SELECT 1 FROM intake_decisions WHERE delivery_hash=? AND item=?",
                (delivery_hash, index),
            ).fetchone():
                continue
            scorecard = None
            try:
                # Scores and acceptance share the exact same deterministic checks.
                observation, scorecard = assess(
                    self.archive, candidate, original_policies, received
                )
                if scorecard["mandatory_failures"]:
                    failed = next(
                        c
                        for c in scorecard["requirements"]
                        if c["mandatory"] and c["status"] != "PASS"
                    )
                    raise ValueError(failed["reason"])
                existing = self._existing_revision(observation)
                if existing:
                    comparable = replace(observation, ingested_time=existing.ingested_time)
                    if comparable != existing:
                        raise ValueError("conflicting duplicate revision; preserve and investigate")
                    self._decision(
                        delivery_hash,
                        index,
                        "DUPLICATE",
                        "identical original version",
                        existing.id,
                        scorecard,
                    )
                    continue
                self.archive.append(observation)
                self._decision(
                    delivery_hash,
                    index,
                    "ACCEPTED",
                    "deterministic checks passed",
                    observation.id,
                    scorecard,
                )
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                if scorecard is None or scorecard["disposition"] != "QUARANTINE":
                    scorecard = rejected_delivery(str(exc))
                self._decision(delivery_hash, index, "QUARANTINED", str(exc), scorecard=scorecard)
        return self.result(delivery_hash)

    def _existing_revision(self, observation: Observation) -> Observation | None:
        row = self.archive.connection.execute(
            "SELECT envelope FROM observations "
            "WHERE source=? AND series=? AND event_time=? AND revision=?",
            (observation.source, observation.series, observation.event_time, observation.revision),
        ).fetchone()
        return Observation.from_dict(json.loads(row[0])) if row else None

    def result(self, delivery_hash: str) -> dict:
        rows = self.archive.connection.execute(
            "SELECT d.item, d.status, d.reason, d.observation_id, s.scorecard "
            "FROM intake_decisions d LEFT JOIN intake_scorecards s "
            "ON d.delivery_hash=s.delivery_hash AND d.item=s.item "
            "WHERE d.delivery_hash=? ORDER BY d.item",
            (delivery_hash,),
        ).fetchall()
        received = self.archive.connection.execute(
            "SELECT received_at FROM deliveries WHERE hash=?", (delivery_hash,)
        ).fetchone()[0]
        return {
            "delivery_sha256": delivery_hash,
            "received_at": received,
            "decisions": [
                dict(zip(("item", "status", "reason", "observation_id"), row[:4], strict=True))
                | {"quality_scorecard": json.loads(row[4]) if row[4] else None}
                for row in rows
            ],
        }


def scan(intake: Intake, inbox: Path, policies: list[SeriesPolicy]) -> list[dict]:
    """Producers must atomically rename complete deliveries to *.ready files."""
    if not inbox.is_dir():
        raise ValueError("inbox must be an existing directory")
    results = []
    for path in sorted(inbox.glob("*.ready")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            before = path.stat()
            payload = path.read_bytes()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                results.append({"file": path.name, "status": "DEFERRED", "reason": "file changed"})
                continue
            results.append({"file": path.name, **intake.capture(payload, policies)})
        except OSError as exc:
            results.append({"file": path.name, "status": "IO_ERROR", "reason": str(exc)})
    return results


def watch(
    intake: Intake,
    inbox: Path,
    policies: list[SeriesPolicy],
    interval: float,
    once: bool = False,
    emit: Callable[[str], None] = print,
    sleeper: Callable[[float], None] = time.sleep,
):
    if not 1 <= interval <= 86400:
        raise ValueError("poll interval must be between 1 and 86400 seconds")
    while True:
        emit(canonical({"mode": "local_delivery_watch", "results": scan(intake, inbox, policies)}))
        if once:
            return
        sleeper(interval)
