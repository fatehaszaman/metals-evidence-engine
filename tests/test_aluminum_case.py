"""Aluminum case: built the same way as copper, with a different synthetic evidence pattern."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from metals_evidence.archive import Archive
from metals_evidence.cli import main
from metals_evidence.demo import DEFAULT_CUTOFF, parity_audit, records, scenario
from metals_evidence.evidence import Hypothesis, evaluate, json_report, markdown

ROOT = Path(__file__).resolve().parents[1]
REVISION_CUTOFF = "2025-09-20T09:00:00Z"


@pytest.fixture
def aluminum():
    return Hypothesis.load(ROOT / "hypotheses/in_bd_aluminum_availability.json")


@pytest.fixture
def al_archive():
    with Archive() as archive:
        for record in records("ALUMINUM"):
            archive.append(record)
        yield archive


def statuses(report):
    return {row["name"]: row["status"] for row in report["evidence"]}


def test_hypothesis_scope_and_rules(aluminum):
    assert aluminum.id == "IN-BD-AL-AVAILABILITY-DEMO"
    assert aluminum.metal == "ALUMINUM"
    assert aluminum.geography == "IN-BD"
    for term in ("Bangladesh", "India", "cable", "conductor", "power", "industrial"):
        assert term in aluminum.question
    assert aluminum.boundary.startswith("SYNTHETIC DEMONSTRATION ONLY.")
    assert [r.name for r in aluminum.rules if r.material] == [
        "Nearby spread",
        "Visible inventory",
        "Primary production",
    ]
    assert {r.source for r in aluminum.rules} == {"synthetic-in-bd-metals"}


def test_fixtures_are_synthetic_aluminum_only():
    data = records("ALUMINUM")
    assert {o.metal for o in data} == {"ALUMINUM"}
    assert {o.geography for o in data} == {"IN-BD"}
    assert {o.source for o in data} == {"synthetic-in-bd-metals"}
    assert {o.contract.code for o in data if o.contract} == {"DEMO-AL-202510", "DEMO-AL-202511"}
    assert {o.contract.exchange for o in data if o.contract} == {"SYNTHETIC"}
    assert all(json.loads(o.raw_payload)["dataset"] == "SYNTHETIC" for o in data)
    assert all(json.loads(o.raw_payload)["metal"] == "ALUMINUM" for o in data)


def test_copper_payloads_unchanged_by_aluminum_case():
    # Copper raw payloads must not gain the new key, or archived hashes would change.
    assert all("metal" not in json.loads(o.raw_payload) for o in records())
    assert not {o.id for o in records()} & {o.id for o in records("ALUMINUM")}


def test_unknown_metal_has_no_fixture():
    with pytest.raises(ValueError, match="no synthetic case"):
        records("NICKEL")


def test_base_case_is_bounded_support(al_archive, aluminum):
    report = evaluate(al_archive, aluminum, DEFAULT_CUTOFF)
    assert statuses(report) == {
        "Nearby spread": "SUPPORTS",
        "Visible inventory": "SUPPORTS",
        "Primary production": "SUPPORTS",
        "Primary imports": "INSUFFICIENT",
        "Shipments": "UNAVAILABLE",
    }
    changes = {row["name"]: row.get("change") for row in report["evidence"]}
    assert changes["Nearby spread"] == "45"
    assert changes["Visible inventory"] == "-30000"
    assert changes["Primary production"] == "-5000"
    assert not report["material_conflict"]
    assert report["overall_evidence_state"] == "BOUNDED_SUPPORT"
    # Preliminary inputs keep confidence below HIGH even when every comparison agrees.
    assert report["observation_confidence"] == "MODERATE"
    assert "not causality" in report["why"]


def test_revision_flips_inventory_without_rewriting_history(al_archive, aluminum):
    before = evaluate(al_archive, aluminum, DEFAULT_CUTOFF)
    after = evaluate(al_archive, aluminum, REVISION_CUTOFF)
    assert statuses(after)["Visible inventory"] == "WEAKENS"
    assert after["material_conflict"]
    assert after["overall_evidence_state"] == "INCONCLUSIVE"
    assert any(p["revision"] == 1 for p in after["provenance"])
    assert all(p["revision"] == 0 for p in before["provenance"])
    assert evaluate(al_archive, aluminum, DEFAULT_CUTOFF) == before


def test_shipments_wait_for_local_receipt(al_archive, aluminum):
    assert statuses(evaluate(al_archive, aluminum, DEFAULT_CUTOFF))["Shipments"] == "UNAVAILABLE"
    received = evaluate(al_archive, aluminum, "2025-09-21T09:00:00Z")
    assert statuses(received)["Shipments"] == "INSUFFICIENT"


def test_provenance_reaches_exact_as_of_envelopes(al_archive, aluminum):
    report = evaluate(al_archive, aluminum, DEFAULT_CUTOFF)
    snapshot = {o.id: o for o in al_archive.as_of(DEFAULT_CUTOFF)}
    assert {p["observation_id"] for p in report["provenance"]} == set(report["snapshot_ids"])
    for provenance in report["provenance"]:
        observation = snapshot[provenance["observation_id"]]
        assert provenance["raw_payload_sha256"] == observation.raw_hash
        assert provenance["metal"] == "ALUMINUM"
        assert provenance["ingested_time"] <= report["as_of"]


def test_metals_do_not_cross_contaminate(hypothesis, aluminum):
    with Archive() as copper_only, Archive() as aluminum_only, Archive() as mixed:
        for record in records():
            copper_only.append(record)
            mixed.append(record)
        for record in records("ALUMINUM"):
            aluminum_only.append(record)
            mixed.append(record)
        for cutoff in (DEFAULT_CUTOFF, REVISION_CUTOFF):
            assert evaluate(mixed, hypothesis, cutoff) == evaluate(copper_only, hypothesis, cutoff)
            assert evaluate(mixed, aluminum, cutoff) == evaluate(aluminum_only, aluminum, cutoff)


def test_copper_hypothesis_ignores_aluminum_data(hypothesis):
    with Archive() as archive:
        for record in records("ALUMINUM"):
            archive.append(record)
        report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    assert report["snapshot_ids"] == []
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"


def test_definition_break_withholds_inventory_direction(aluminum):
    data, cutoff = scenario("definition-break", "ALUMINUM")
    with Archive() as archive:
        for record in data:
            archive.append(record)
        report = evaluate(archive, aluminum, cutoff)
    assert statuses(report)["Visible inventory"] == "INSUFFICIENT"
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"


def test_stale_cutoff_is_insufficient(aluminum):
    data, cutoff = scenario("stale", "ALUMINUM")
    with Archive() as archive:
        for record in data:
            archive.append(record)
        report = evaluate(archive, aluminum, cutoff)
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert report["observation_confidence"] == "LOW"


def test_contract_roll_is_not_compared(aluminum):
    data = [
        replace(o, contract=replace(o.contract, code="DEMO-AL-202512"))
        if o.contract
        and o.contract.code == "DEMO-AL-202511"
        and o.event_time.startswith("2025-09-18")
        else o
        for o in records("ALUMINUM")
    ]
    with Archive() as archive:
        for record in data:
            archive.append(record)
        report = evaluate(archive, aluminum, DEFAULT_CUTOFF)
    assert statuses(report)["Nearby spread"] == "INSUFFICIENT"
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"


def test_replay_parity(aluminum):
    audit = parity_audit(aluminum)
    assert audit["passed"]
    assert audit["dataset"] == "SYNTHETIC"
    assert len(audit["checkpoints"]) == len({o.ingested_time for o in records("ALUMINUM")})


def test_checked_in_aluminum_cases_are_reproducible(aluminum):
    folder = ROOT / "examples/aluminum"
    for name, cutoff, filename in [
        ("base", None, "base"),
        ("base", REVISION_CUTOFF, "revision"),
        ("definition-break", None, "definition-break"),
        ("stale", None, "stale"),
    ]:
        data, default = scenario(name, "ALUMINUM")
        with Archive() as archive:
            for record in data:
                archive.append(record)
            report = evaluate(archive, aluminum, cutoff or default)
        assert (folder / f"{filename}.md").read_text() == markdown(report)
        if filename == "base":
            assert (folder / "base.json").read_text() == json_report(report)
    assert json.loads((folder / "replay-audit.json").read_text()) == parity_audit(aluminum)


def test_cli_aluminum_demo_and_audit(capsys):
    assert main(["demo", "--case", "aluminum"]) == 0
    out = capsys.readouterr().out
    assert "BOUNDED_SUPPORT" in out
    assert "SYNTHETIC DEMONSTRATION ONLY" in out
    assert main(["demo", "--case", "aluminum", "--as-of", REVISION_CUTOFF]) == 0
    assert "INCONCLUSIVE" in capsys.readouterr().out
    assert main(["audit", "--case", "aluminum"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"]


def test_cli_rejects_mismatched_case_and_hypothesis(capsys):
    args = [
        "demo",
        "--case",
        "aluminum",
        "--hypothesis",
        "hypotheses/in_bd_copper_availability.json",
    ]
    assert main(args) == 2
    assert "does not match" in capsys.readouterr().err


def test_cli_aluminum_ingest_evaluate(tmp_path, capsys):
    fixture = tmp_path / "al.jsonl"
    db = str(tmp_path / "al.db")
    assert main(["fixtures", "--case", "aluminum"]) == 0
    fixture.write_text(capsys.readouterr().out)
    assert main(["ingest", "--db", db, "--input", str(fixture)]) == 0
    assert json.loads(capsys.readouterr().out)["added"] == len(records("ALUMINUM"))
    hypothesis = "hypotheses/in_bd_aluminum_availability.json"
    args = ["evaluate", "--db", db, "--hypothesis", hypothesis, "--as-of", DEFAULT_CUTOFF]
    assert main(args) == 0
    assert "BOUNDED_SUPPORT" in capsys.readouterr().out


def test_archive_rejects_one_series_mixing_metals():
    copper = next(o for o in records() if o.series == "inventory")
    with Archive() as archive:
        archive.append(copper)
        with pytest.raises(ValueError, match="different metal or geography"):
            archive.append(replace(copper, metal="ALUMINUM", value="1"))
        with pytest.raises(ValueError, match="different metal or geography"):
            archive.append(replace(copper, geography="IN", value="1"))
        assert archive.count() == 1
