import json
import sqlite3
from dataclasses import asdict, replace

import pytest

from metals_evidence.archive import Archive
from metals_evidence.capture import Intake, SeriesPolicy
from metals_evidence.cli import main
from metals_evidence.demo import records
from metals_evidence.model import canonical, digest
from metals_evidence.quality import assess

RECEIVED = "2025-09-19T09:00:00Z"


def inputs():
    candidate = records()[4].to_dict()
    policy = SeriesPolicy(
        **{
            k: candidate[k]
            for k in ("source", "series", "metal", "geography", "unit", "definition")
        },
        max_age_seconds=10 * 86400,
        max_relative_change="0.5",
    )
    return candidate, policy


def delivery(candidate):
    return canonical({"extraction_method": "deterministic", "observations": [candidate]}).encode()


def test_good_data_reports_gaps_not_perfect_certainty():
    candidate, policy = inputs()
    with Archive() as archive:
        observation, score = assess(archive, candidate, [policy], RECEIVED)
        assert observation is not None
        assert score["disposition"] == "ELIGIBLE_FOR_INTAKE"
        assert score["requirements_score"] == 83.33
        assert score["assessment_coverage"] == 83.33
        assert score["assessed_pass_rate"] == 100
        unassessed = [c for c in score["requirements"] if c["score"] is None]
        assert {c["requirement"] for c in unassessed} == {"change_guard", "source_authenticity"}
        assert archive.count() == 0
        assert score["policy_hash"]
        assert score["scorecard_hash"] == digest(
            {k: v for k, v in score.items() if k != "scorecard_hash"}
        )


def test_a_high_score_cannot_override_a_mandatory_failure():
    candidate, policy = inputs()
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIVED)
        intake.capture(delivery(candidate), [policy])
        newer = candidate | {
            "event_time": "2025-09-18T00:00:00Z",
            "published_time": "2025-09-18T01:00:00Z",
            "geography": "WRONG",
            "value": "101000",
        }
        decision = intake.capture(delivery(newer), [policy])["decisions"][0]
        assert decision["status"] == "QUARANTINED"
        score = decision["quality_scorecard"]
        assert score["requirements_score"] == 83.33
        assert score["mandatory_failures"] == ["geography"]
        assert archive.count() == 1


def test_multiple_failures_are_all_visible():
    candidate, policy = inputs()
    bad = candidate | {"unit": "USD/lb", "geography": "WRONG", "quality": "SUSPECT"}
    with Archive() as archive:
        _, score = assess(archive, bad, [replace(policy, max_age_seconds=1)], RECEIVED)
        assert set(score["mandatory_failures"]) == {"unit", "geography", "quality", "freshness"}
        assert all(c["score"] == 0 for c in score["requirements"] if c["status"] == "FAIL")


def test_missing_policy_does_not_get_credit_for_unchecked_fields():
    candidate, _ = inputs()
    with Archive() as archive:
        _, score = assess(archive, candidate, [], RECEIVED)
        fields = {c["requirement"]: c for c in score["requirements"]}
        assert fields["unit"]["status"] == "NOT_ASSESSED"
        assert "unit" in score["mandatory_failures"]
        assert fields["source_series"]["score"] == 0


@pytest.mark.parametrize("candidate", [None, {"value": "NaN"}])
def test_invalid_candidate_never_scores_clean(candidate):
    with Archive() as archive:
        observation, score = assess(archive, candidate, [], RECEIVED)
        assert observation is None
        assert score["requirements_score"] == 0
        assert score["disposition"] == "QUARANTINE"


def test_scores_are_immutable_and_retries_preserve_first_assessment():
    candidate, policy = inputs()
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIVED)
        first = intake.capture(delivery(candidate), [policy])
        intake.clock = lambda: "2026-01-01T00:00:00Z"
        assert intake.capture(delivery(candidate), []) == first
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            archive.connection.execute("DELETE FROM intake_scorecards")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            archive.connection.execute("UPDATE intake_scorecards SET scorecard='{}'")


def test_bad_delivery_has_scorecard_and_no_observations():
    with Archive() as archive:
        result = Intake(archive, lambda: RECEIVED).capture(b"bad json", [])
        score = result["decisions"][0]["quality_scorecard"]
        assert score["requirements_score"] == 0
        assert score["requirements"][0]["status"] == "FAIL"
        assert archive.count() == 0


def test_prior_schema_decisions_are_not_retroactively_scored():
    candidate, policy = inputs()
    with Archive() as archive:
        intake = Intake(archive, lambda: RECEIVED)
        intake._decision("old-delivery", 0, "QUARANTINED", "old validation result")
        # Internal migration compatibility: legacy rows have no invented score history.
        assert not archive.connection.execute("SELECT * FROM intake_scorecards").fetchall()


def test_future_revisions_do_not_enter_historical_score():
    candidate, policy = inputs()
    with Archive() as archive:
        old = records()[4]
        archive.append(replace(old, revision=2, ingested_time="2025-09-21T00:00:00Z"))
        _, score = assess(archive, candidate, [policy], RECEIVED)
        revision = next(c for c in score["requirements"] if c["requirement"] == "revision")
        assert revision["status"] == "PASS"


def test_stored_score_matches_output():
    candidate, policy = inputs()
    with Archive() as archive:
        report = Intake(archive, lambda: RECEIVED).capture(delivery(candidate), [policy])
        saved = json.loads(
            archive.connection.execute("SELECT scorecard FROM intake_scorecards").fetchone()[0]
        )
        assert saved == report["decisions"][0]["quality_scorecard"]


def test_score_cli_previews_without_approval(tmp_path, capsys):
    candidate, policy = inputs()
    input_path = tmp_path / "candidate.json"
    policy_path = tmp_path / "policy.json"
    input_path.write_text(canonical(candidate))
    policy_path.write_text(canonical({"series": [asdict(policy)]}))
    args = ["score", "--input", str(input_path), "--policy", str(policy_path), "--as-of", RECEIVED]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["requirements_score"] == 83.33
    input_path.write_text(canonical(candidate | {"geography": "WRONG"}))
    assert main(args) == 1
    assert "geography" in json.loads(capsys.readouterr().out)["mandatory_failures"]
    assert main(args + ["--db", str(tmp_path / "absent.db")]) == 2
    assert "does not exist" in capsys.readouterr().err
