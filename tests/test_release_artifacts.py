"""Release examples must remain byte-for-byte reproducible."""

import json
from pathlib import Path

from metals_evidence.archive import Archive
from metals_evidence.demo import parity_audit, scenario
from metals_evidence.evidence import evaluate, json_report, markdown

ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_cases_are_reproducible(hypothesis):
    for name, cutoff, filename in [
        ("conflict", None, "conflict"),
        ("conflict", "2025-09-20T09:00:00Z", "revision"),
        ("definition-break", None, "definition-break"),
        ("stale", None, "stale"),
    ]:
        records, default = scenario(name)
        with Archive() as archive:
            for record in records:
                archive.append(record)
            report = evaluate(archive, hypothesis, cutoff or default)
        assert (ROOT / f"examples/{filename}.md").read_text() == markdown(report)
        if filename == "conflict":
            assert (ROOT / "examples/conflict.json").read_text() == json_report(report)


def test_checked_in_audit_is_reproducible(hypothesis):
    expected = json.loads((ROOT / "examples/replay-audit.json").read_text())
    assert expected == parity_audit(hypothesis)
