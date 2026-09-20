from dataclasses import replace
from pathlib import Path

from metals_evidence.archive import Archive
from metals_evidence.demo import DEFAULT_CUTOFF, records
from metals_evidence.evidence import evaluate, markdown

ROOT = Path(__file__).resolve().parents[1]


def test_hypothesis_and_fixtures_use_india_bangladesh_scope(hypothesis):
    assert hypothesis.geography == "IN-BD"
    assert hypothesis.metal == "COPPER"
    assert hypothesis.id == "IN-BD-CU-AVAILABILITY-DEMO"
    for term in ("Bangladesh", "India", "cable", "conductor", "power", "industrial"):
        assert term in hypothesis.question
    assert {o.geography for o in records()} == {"IN-BD"}
    assert {o.source for o in records()} == {"synthetic-in-bd-metals"}
    assert {o.unit for o in records() if o.contract} == {"USD/tonne"}


def test_regional_report_preserves_conflict_and_separate_confidence(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    assert report["material_conflict"]
    assert report["overall_evidence_state"] == "INCONCLUSIVE"
    assert report["observation_confidence"] == "MODERATE"
    assert report["observation_quality"] == report["observation_confidence"]
    assert all("quality" in row for row in report["evidence"])
    rendered = markdown(report)
    assert "Observation confidence: MODERATE" in rendered
    assert "Provenance, revisions, and as_of reconstruction" in rendered
    assert "SYNTHETIC DEMONSTRATION ONLY" in rendered


def test_report_provenance_reaches_exact_as_of_envelopes(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    snapshot = {o.id: o for o in archive.as_of(DEFAULT_CUTOFF)}
    assert {p["observation_id"] for p in report["provenance"]} == set(report["snapshot_ids"])
    for provenance in report["provenance"]:
        observation = snapshot[provenance["observation_id"]]
        assert provenance["raw_payload_sha256"] == observation.raw_hash
        assert provenance["revision"] == observation.revision
        assert provenance["geography"] == "IN-BD"
        assert provenance["event_time"] <= report["as_of"]
        assert provenance["published_time"] <= report["as_of"]
        assert provenance["ingested_time"] <= report["as_of"]
    later = evaluate(archive, hypothesis, "2025-09-20T09:00:00Z")
    assert any(p["revision"] == 1 for p in later["provenance"])
    assert evaluate(archive, hypothesis, DEFAULT_CUTOFF) == report


def test_off_scope_observations_are_not_relabelled(hypothesis):
    with Archive() as archive:
        for original in records():
            archive.append(replace(original, geography="OUTSIDE-SCOPE"))
        report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    assert report["provenance"] == []
    assert report["snapshot_ids"] == []
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"


def test_published_docs_and_cases_do_not_reintroduce_old_region():
    paths = [ROOT / "README.md"]
    for folder in ("docs", "examples", "hypotheses"):
        paths.extend((ROOT / folder).rglob("*.md"))
        paths.extend((ROOT / folder).rglob("*.json"))
    for path in paths:
        text = path.read_text()
        assert "China" not in text, path
        assert "synthetic-cn-metals" not in text, path
        assert '"geography":"CN"' not in text, path
    readme = (ROOT / "README.md").read_text()
    assert "copper first, aluminum second" in readme
    assert "This is neither a trading strategy nor a live market-data platform." in readme
