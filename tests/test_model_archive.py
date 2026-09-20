import sqlite3
from contextlib import closing
from dataclasses import replace

import pytest

from metals_evidence.archive import Archive
from metals_evidence.demo import DEFAULT_CUTOFF, observation, records
from metals_evidence.model import Contract, Observation, number, utc


def test_round_trip_and_hash():
    for item in records():
        assert Observation.from_dict(item.to_dict()) == item
        assert len(item.id) == len(item.raw_hash) == 64


@pytest.mark.parametrize(
    "change",
    [
        {"event_time": "2025-09-01"},
        {"value": 1.1},
        {"value": "NaN"},
        {"value": "Infinity"},
        {"value": "-1"},
        {"value": "not-a-number"},
        {"revision": -1},
        {"revision": True},
        {"metal": "UNKNOWN"},
        {"unit": "kg"},
        {"quality": "GUESS"},
        {"value": None},
        {"quality": "MISSING"},
        {"source": ""},
        {"definition": ""},
        {"raw_payload": ""},
        {"published_time": "2025-01-01T00:00:00Z"},
        {"ingested_time": "2025-01-01T00:00:00Z"},
    ],
)
def test_invalid_envelopes_fail(change):
    with pytest.raises(ValueError):
        replace(records()[0], **change)


def test_missing_is_explicit():
    item = replace(records()[0], value=None, quality="MISSING")
    assert item.value is None


def test_timezone_normalization():
    assert utc("2025-09-19T17:00:00+08:00") == utc(DEFAULT_CUTOFF)


def test_exact_decimal():
    assert number("0.1") + number("0.2") == number("0.3")


def test_invalid_contract():
    with pytest.raises(ValueError):
        Contract("", "TEST", "2025-10", "2025-10-15T00:00:00Z")
    with pytest.raises(ValueError):
        Contract("A", "TEST", "2025-13", "2025-10-15T00:00:00Z")


def test_before_publication_is_empty(archive):
    assert archive.as_of("2025-01-01T00:00:00Z") == []


def test_revision_does_not_leak(archive):
    before = [o for o in archive.as_of(DEFAULT_CUTOFF) if o.series == "inventory"]
    after = [o for o in archive.as_of("2025-09-20T09:00:00Z") if o.series == "inventory"]
    assert before[-1].value == "120000"
    assert before[-1].revision == 0
    assert after[-1].value == "90000"
    assert after[-1].revision == 1
    assert archive.count() == 13


def test_future_observation_excluded(archive):
    assert all(o.event_time <= utc(DEFAULT_CUTOFF) for o in archive.as_of(DEFAULT_CUTOFF))
    assert not any(o.value == "85000" for o in archive.as_of(DEFAULT_CUTOFF))


def test_late_receipt_excluded_until_ingestion(archive):
    assert not any(o.series == "shipments" for o in archive.as_of(DEFAULT_CUTOFF))
    exact = archive.as_of("2025-09-21T08:00:00Z")
    assert any(o.series == "shipments" for o in exact)


def test_duplicate_idempotence_and_conflicting_version(archive):
    existing = records()[0]
    assert not archive.append(existing)
    with pytest.raises(ValueError, match="conflicting"):
        archive.append(replace(existing, value="99"))
    assert archive.count() == 13


def test_append_only_enforced_by_sqlite(archive):
    for sql in ("DELETE FROM observations", "UPDATE observations SET revision=5"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            archive.connection.execute(sql)


def test_source_identity_is_not_blended(archive):
    other = replace(records()[4], source="different-source", value="1")
    archive.append(other)
    selected = archive.as_of(DEFAULT_CUTOFF)
    assert other in selected and records()[4] in selected


def test_late_lower_revision_cannot_roll_back():
    original = observation("stock", "2025-01-01T00:00:00Z", "1")
    newer = replace(
        original,
        revision=2,
        value="3",
        published_time="2025-01-03T00:00:00Z",
        ingested_time="2025-01-03T00:00:00Z",
    )
    delayed = replace(
        original,
        revision=1,
        value="2",
        published_time="2025-01-02T00:00:00Z",
        ingested_time="2025-01-04T00:00:00Z",
    )
    with Archive() as archive:
        for item in (newer, original, delayed):
            archive.append(item)
        assert archive.as_of("2025-01-05T00:00:00Z") == [newer]


def test_persistent_archive(tmp_path):
    path = tmp_path / "archive.db"
    with Archive(path) as archive:
        archive.append(records()[0])
    with Archive(path) as archive:
        assert archive.count() == 1
        assert archive.as_of(DEFAULT_CUTOFF) == [records()[0]]


def test_unsupported_schema(tmp_path):
    path = tmp_path / "future.db"
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA user_version = 999")
    with pytest.raises(ValueError, match="unsupported"):
        Archive(path)
