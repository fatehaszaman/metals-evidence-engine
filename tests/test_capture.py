import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from metals_evidence.archive import Archive
from metals_evidence.capture import Intake, SeriesPolicy, load_policy, now, scan, watch
from metals_evidence.cli import main
from metals_evidence.demo import records
from metals_evidence.model import canonical, utc

RECEIPT = "2025-09-19T09:00:00Z"


@pytest.fixture
def candidate():
    return records()[4].to_dict()


@pytest.fixture
def policy(candidate):
    return SeriesPolicy(
        **{
            k: candidate[k]
            for k in ("source", "series", "metal", "geography", "unit", "definition")
        },
        max_age_seconds=10 * 86400,
        max_relative_change="0.5",
    )


def delivery(candidate, method="deterministic"):
    return canonical({"extraction_method": method, "observations": [candidate]}).encode()


def outcome(report):
    return report["decisions"][0]["status"]


def test_raw_capture_and_receipt_clock(candidate, policy):
    raw = delivery(candidate)
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        report = intake.capture(raw, [policy])
        assert outcome(report) == "ACCEPTED"
        payload, policy_snapshot = archive.connection.execute(
            "SELECT payload, policy FROM deliveries"
        ).fetchone()
        assert payload == raw
        assert json.loads(policy_snapshot) == [asdict(policy)]
        assert not archive.as_of(candidate["ingested_time"])
        stored = archive.as_of(RECEIPT)[0]
        assert stored.ingested_time == utc(RECEIPT)
        assert stored.published_time == candidate["published_time"]
        assert stored.raw_payload == candidate["raw_payload"]


def test_retry_uses_original_receipt_and_policy(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        report = intake.capture(delivery(candidate), [policy])
        intake.clock = lambda: "2025-10-01T00:00:00Z"
        assert intake.capture(delivery(candidate), []) == report
        assert archive.count() == 1


def test_duplicate_different_delivery_does_not_rewrite_receipt(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        intake.capture(delivery(candidate), [policy])
        intake.clock = lambda: "2025-09-20T09:00:00Z"
        report = intake.capture(delivery(candidate) + b"\n", [policy])
        assert outcome(report) == "DUPLICATE"
        assert archive.count() == 1
        assert archive.as_of(RECEIPT)[0].ingested_time == utc(RECEIPT)


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "1,234"},
        {"value": "NaN"},
        {"value": None, "quality": "MISSING"},
        {"quality": "SUSPECT"},
        {"geography": "OUTSIDE-SCOPE"},
        {"unit": "USD/lb"},
        {"definition": "new-definition"},
        {"series": "unknown"},
        {"metal": "ALUMINUM"},
        {"published_time": "2025-09-20T00:00:00Z"},
        {"event_time": "2026-01-01T00:00:00Z"},
    ],
)
def test_bad_rows_quarantined_without_losing_raw(candidate, policy, changes):
    raw = delivery(candidate | changes)
    with Archive() as archive:
        report = Intake(archive, lambda: RECEIPT).capture(raw, [policy])
        assert outcome(report) == "QUARANTINED"
        assert archive.count() == 0
        assert archive.connection.execute("SELECT payload FROM deliveries").fetchone()[0] == raw


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"\xff",
        b"[]",
        b"{}",
        b'{"extraction_method":"llm","observations":[]}',
        b'{"extraction_method":"deterministic","observations":[]}',
        b'{"extraction_method":"deterministic","observations":{} }',
        b'{"extraction_method":"deterministic","observations":[null]}',
        b'{"extraction_method":"deterministic","observations":[{}],"extra":1}',
    ],
)
def test_invalid_deliveries_preserved(raw):
    with Archive() as archive:
        assert outcome(Intake(archive, lambda: RECEIPT).capture(raw, [])) == "QUARANTINED"
        assert archive.count() == 0


def test_large_raw_capture_is_preserved_but_not_processed():
    with Archive() as archive:
        result = Intake(archive, lambda: RECEIPT).capture(b"x" * (10 * 1024 * 1024 + 1), [])
        assert outcome(result) == "QUARANTINED"
        assert "processing limit" in result["decisions"][0]["reason"]


def test_empty_policy_denies_everything(candidate):
    with Archive() as archive:
        report = Intake(archive, lambda: RECEIPT).capture(delivery(candidate), [])
        assert outcome(report) == "QUARANTINED"
        assert "allowlisted" in report["decisions"][0]["reason"]


def test_conflicting_duplicate_quarantined(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        intake.capture(delivery(candidate), [policy])
        result = intake.capture(delivery(candidate | {"value": "101000"}), [policy])
        assert outcome(result) == "QUARANTINED"
        assert "conflicting duplicate" in result["decisions"][0]["reason"]


def test_staleness_is_explicit(candidate, policy):
    with Archive() as archive:
        result = Intake(archive, lambda: RECEIPT).capture(
            delivery(candidate), [replace(policy, max_age_seconds=1)]
        )
        assert "stale observation" in result["decisions"][0]["reason"]


def test_jump_requires_review_not_automatic_correction(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        intake.capture(delivery(candidate), [policy])
        newer = candidate | {
            "event_time": "2025-09-18T00:00:00Z",
            "published_time": "2025-09-18T01:00:00Z",
            "value": "900000",
        }
        result = intake.capture(delivery(newer), [policy])
        assert outcome(result) == "QUARANTINED"
        assert "may be economic" in result["decisions"][0]["reason"]
        assert archive.count() == 1


def test_revision_order_and_replay(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        intake.capture(delivery(candidate), [policy])
        bad = candidate | {"revision": 1, "published_time": "2025-09-15T06:00:00Z"}
        # Model catches event > publication before the order check.
        assert outcome(intake.capture(delivery(bad), [policy])) == "QUARANTINED"
        intake.clock = lambda: "2025-09-20T00:00:00Z"
        revised = candidate | {
            "revision": 1,
            "published_time": "2025-09-19T12:00:00Z",
            "value": "90000",
            "quality": "REVISED",
        }
        assert outcome(intake.capture(delivery(revised), [policy])) == "ACCEPTED"
        assert archive.as_of(RECEIPT)[0].value == candidate["value"]
        assert archive.as_of("2025-09-20T00:00:00Z")[0].value == "90000"


def test_source_revision_publication_order(candidate, policy):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        later_publication = candidate | {"published_time": "2025-09-17T07:00:00Z"}
        intake.capture(delivery(later_publication), [policy])
        earlier_revision = candidate | {"revision": 1, "published_time": "2025-09-16T07:00:00Z"}
        result = intake.capture(delivery(earlier_revision), [policy])
        assert outcome(result) == "QUARANTINED"
        assert "revision and publication order" in result["decisions"][0]["reason"]


@pytest.mark.parametrize("value,status", [("0", "ACCEPTED"), ("1", "QUARANTINED")])
def test_zero_baseline_requires_review(candidate, policy, value, status):
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        intake.capture(delivery(candidate | {"value": "0"}), [policy])
        newer = candidate | {
            "event_time": "2025-09-18T00:00:00Z",
            "published_time": "2025-09-18T01:00:00Z",
            "value": value,
        }
        assert outcome(intake.capture(delivery(newer), [policy])) == status


def test_receipt_clock_has_timezone():
    assert utc(now()).endswith("Z")


def test_mixed_batch_preserves_each_decision(candidate, policy):
    payload = canonical(
        {
            "extraction_method": "deterministic",
            "observations": [candidate, candidate | {"series": "unknown"}],
        }
    ).encode()
    with Archive() as archive:
        report = Intake(archive, lambda: RECEIPT).capture(payload, [policy])
        assert [d["status"] for d in report["decisions"]] == ["ACCEPTED", "QUARANTINED"]
        assert archive.count() == 1


@pytest.mark.parametrize("table", ["deliveries", "intake_decisions"])
def test_intake_audit_is_append_only(candidate, policy, table):
    with Archive() as archive:
        Intake(archive, lambda: RECEIPT).capture(delivery(candidate), [policy])
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            archive.connection.execute(f"DELETE FROM {table}")


def test_file_watcher_and_restart(candidate, policy, tmp_path):
    (tmp_path / "partial.tmp").write_bytes(b"incomplete")
    (tmp_path / "input.ready").write_bytes(delivery(candidate))
    (tmp_path / "symlink.ready").symlink_to(tmp_path / "input.ready")
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        first = scan(intake, tmp_path, [policy])
        assert len(first) == 1
        assert scan(intake, tmp_path, [policy]) == first
        assert archive.count() == 1


def test_watcher_loop_and_once(tmp_path):
    emitted = []
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIPT)
        watch(intake, tmp_path, [], 1, once=True, emit=emitted.append)
        assert len(emitted) == 1
        with pytest.raises(KeyboardInterrupt):
            watch(
                intake,
                tmp_path,
                [],
                1,
                emit=emitted.append,
                sleeper=lambda _: (_ for _ in ()).throw(KeyboardInterrupt()),
            )
        with pytest.raises(ValueError, match="interval"):
            watch(intake, tmp_path, [], float("nan"), once=True)
        with pytest.raises(ValueError, match="existing directory"):
            scan(intake, tmp_path / "missing", [])


def test_changed_file_deferred(monkeypatch, tmp_path):
    path = tmp_path / "input.ready"
    path.write_bytes(b"original")
    original = Path.read_bytes

    def changing_read(self):
        raw = original(self)
        self.write_bytes(b"different length")
        return raw

    monkeypatch.setattr(Path, "read_bytes", changing_read)
    with Archive() as archive:
        assert scan(Intake(archive), tmp_path, [])[0]["status"] == "DEFERRED"


def test_io_error_visible(monkeypatch, tmp_path):
    (tmp_path / "input.ready").write_bytes(b"data")
    monkeypatch.setattr(
        Path, "read_bytes", lambda _: (_ for _ in ()).throw(OSError("permission denied"))
    )
    with Archive() as archive:
        assert scan(Intake(archive), tmp_path, [])[0]["status"] == "IO_ERROR"


def test_policy_validation(policy, tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(canonical({"series": [asdict(policy)]}))
    assert load_policy(path) == [policy]
    for data in ([], {"wrong": []}, {"series": {}}, {"series": [asdict(policy)] * 2}):
        path.write_text(canonical(data))
        with pytest.raises(ValueError):
            load_policy(path)
    for changes in ({"max_age_seconds": 0}, {"source": ""}, {"max_relative_change": "-1"}):
        with pytest.raises(ValueError):
            replace(policy, **changes)


def test_capture_cli_empty_inbox(tmp_path, capsys):
    policy = tmp_path / "policy.json"
    policy.write_text('{"series":[]}')
    assert (
        main(
            [
                "capture",
                "--db",
                str(tmp_path / "intake.db"),
                "--inbox",
                str(tmp_path),
                "--policy",
                str(policy),
                "--once",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["mode"] == "local_delivery_watch"
