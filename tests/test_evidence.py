from dataclasses import asdict, replace

import pytest

from metals_evidence.archive import Archive
from metals_evidence.demo import DEFAULT_CUTOFF, parity_audit, records, scenario
from metals_evidence.evidence import Hypothesis, Rule, evaluate, markdown
from metals_evidence.model import canonical, digest, utc


def report_for(data, hypothesis, cutoff=DEFAULT_CUTOFF):
    with Archive() as archive:
        for item in data:
            archive.append(item)
        return evaluate(archive, hypothesis, cutoff)


def test_conflicting_material_evidence_is_inconclusive(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    assert report["overall_evidence_state"] == "INCONCLUSIVE"
    assert report["material_conflict"]
    assert report["observation_quality"] == "MODERATE"
    assert [r["status"] for r in report["evidence"]] == [
        "SUPPORTS",
        "WEAKENS",
        "WEAKENS",
        "INSUFFICIENT",
        "UNAVAILABLE",
    ]
    assert report["evidence"][0]["change"] == "300"


def test_imports_not_forced_into_demand_direction(archive, hypothesis):
    row = evaluate(archive, hypothesis, DEFAULT_CUTOFF)["evidence"][3]
    assert not row["material"]
    assert row["status"] == "INSUFFICIENT"
    assert "Context only" in row["reason"]


def test_all_parent_ids_reachable(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    ids = set(report["snapshot_ids"])
    assert all(set(r["parent_ids"]) <= ids for r in report["evidence"])


def test_hash_verified_and_order_independent(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    other = report_for(list(reversed(records())), hypothesis)
    assert report == other
    hash_value = report.pop("report_hash")
    assert digest(report) == hash_value


def test_adding_future_data_cannot_change_past_report(hypothesis):
    eligible = [o for o in records() if o.ingested_time <= utc(DEFAULT_CUTOFF)]
    assert report_for(eligible, hypothesis) == report_for(records(), hypothesis)


def test_revision_changes_later_state_only(archive, hypothesis):
    before = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    later = evaluate(archive, hypothesis, "2025-09-20T09:00:00Z")
    assert before["evidence"][1]["status"] == "WEAKENS"
    assert later["evidence"][1]["status"] == "SUPPORTS"
    assert later["overall_evidence_state"] == "INCONCLUSIVE"  # production still weakens


def test_stale_data_withholds_direction(hypothesis):
    data, cutoff = scenario("stale")
    report = report_for(data, hypothesis, cutoff)
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert report["observation_quality"] == "LOW"
    assert all("STALE" in r["quality"] for r in report["evidence"])


def test_definition_break_withholds_inventory(hypothesis):
    data, cutoff = scenario("definition-break")
    row = report_for(data, hypothesis, cutoff)["evidence"][1]
    assert row["status"] == "INSUFFICIENT"
    assert "definition changed" in row["reason"]


def test_missing_required_input_cannot_create_bounded_conclusion(hypothesis):
    data = [o for o in records() if not o.series.startswith("settlement")]
    report = report_for(data, hypothesis)
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.parametrize("status", ["BOUNDED_SUPPORT", "BOUNDED_WEAKENING"])
def test_bounded_states_require_all_material_evidence(status, hypothesis):
    if status == "BOUNDED_SUPPORT":
        data = [
            replace(o, value="80000")
            if o.series == "inventory" and o.value == "120000"
            else replace(o, value="950000")
            if o.series == "refined_production" and o.value == "1050000"
            else o
            for o in records()
        ]
    else:
        data = [replace(o, value="69000") if o.value == "70400" else o for o in records()]
    assert report_for(data, hypothesis)["overall_evidence_state"] == status


def test_neutral_change_is_not_support(hypothesis):
    data = [replace(o, value="100000") if o.value == "120000" else o for o in records()]
    assert report_for(data, hypothesis)["evidence"][1]["status"] == "INSUFFICIENT"


def test_no_observations(hypothesis):
    report = report_for([], hypothesis)
    assert report["overall_evidence_state"] == "INSUFFICIENT_EVIDENCE"
    assert all(r["status"] == "UNAVAILABLE" for r in report["evidence"])


def test_suspect_and_missing_not_replaced_with_older_values(hypothesis):
    data = [replace(o, quality="SUSPECT") if o.value == "120000" else o for o in records()]
    assert report_for(data, hypothesis)["evidence"][1]["status"] == "INSUFFICIENT"


def test_rule_unit_enforced(hypothesis):
    data = [replace(o, unit="USD/tonne") if o.series == "inventory" else o for o in records()]
    row = report_for(data, hypothesis)["evidence"][1]
    assert row["status"] == "INSUFFICIENT"
    assert "rule unit" in row["reason"]


def test_future_hypothesis_version_rejected(archive, hypothesis):
    hypothesis = replace(hypothesis, effective_time=utc("2026-01-01T00:00:00Z"))
    with pytest.raises(ValueError, match="not effective"):
        evaluate(archive, hypothesis, DEFAULT_CUTOFF)


def test_wrong_scope_does_not_contaminate(hypothesis):
    data = [replace(o, geography="US") for o in records()]
    assert report_for(data, hypothesis)["snapshot_ids"] == []


def test_incremental_and_replay_parity(hypothesis):
    audit = parity_audit(hypothesis)
    assert audit["passed"]
    assert len(audit["checkpoints"]) >= 8
    assert all(c["incremental_hash"] == c["replay_hash"] for c in audit["checkpoints"])


def test_comparison_gap_guard(hypothesis):
    hypothesis = replace(hypothesis, rules=(replace(hypothesis.rules[2], max_gap_days=1),))
    report = report_for(records(), hypothesis)
    assert "gap exceeds" in report["evidence"][0]["reason"]


def test_one_comparison_period_insufficient(hypothesis):
    data = [o for o in records() if o.value != "100000"]
    assert "Two comparison periods" in report_for(data, hypothesis)["evidence"][1]["reason"]


def test_roll_transition_not_treated_as_economic_change(hypothesis):
    data = [
        replace(o, contract=replace(o.contract, code="DEMO-ROLLED")) if o.value == "70400" else o
        for o in records()
    ]
    assert "contract roll" in report_for(data, hypothesis)["evidence"][0]["reason"]


def test_curve_definition_change(hypothesis):
    data = [replace(o, definition="new definition") if o.value == "70400" else o for o in records()]
    assert "definition changed" in report_for(data, hypothesis)["evidence"][0]["reason"]


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "magic"},
        {"expected": "MAYBE"},
        {"expected": "NONE"},
        {"threshold": "-1"},
        {"max_age_days": 0},
        {"material": "yes"},
    ],
)
def test_invalid_rules(change, hypothesis):
    with pytest.raises(ValueError):
        Rule(**(asdict(hypothesis.rules[0]) | change))


def test_invalid_hypotheses(hypothesis):
    data = asdict(hypothesis)
    for rules in ([], [asdict(hypothesis.rules[3])], [data["rules"][0]] * 2):
        with pytest.raises(ValueError):
            Hypothesis.from_dict(data | {"rules": rules})


def test_markdown_and_machine_report(archive, hypothesis):
    report = evaluate(archive, hypothesis, DEFAULT_CUTOFF)
    rendered = markdown(report)
    assert "INCONCLUSIVE" in rendered
    assert "SYNTHETIC" in rendered
    assert report["report_hash"] in rendered
    assert '"material_conflict":true' in canonical(report)


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError, match="unknown scenario"):
        scenario("unknown")


def test_comparison_gap_does_not_round_away_hours(hypothesis):
    rule = replace(hypothesis.rules[1], max_gap_days=3)
    hypothesis = replace(hypothesis, rules=(rule,))
    data = [
        replace(
            o,
            event_time="2025-09-18T08:00:00Z",
            published_time="2025-09-18T08:00:00Z",
            ingested_time="2025-09-18T08:00:00Z",
        )
        if o.value == "120000"
        else o
        for o in records()
        if o.revision == 0
    ]
    assert "gap exceeds" in report_for(data, hypothesis)["evidence"][0]["reason"]
