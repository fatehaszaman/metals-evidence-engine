"""Versioned hypothesis evaluation. Contradictions never collapse into a directional score."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

from metals_evidence import __version__
from metals_evidence.archive import Archive
from metals_evidence.model import canonical, decimal_text, digest, number, timestamp, utc
from metals_evidence.transforms import nearby_spread


@dataclass(frozen=True)
class Rule:
    name: str
    kind: str
    source: str
    series: str
    unit: str
    expected: str
    threshold: str
    max_age_days: int
    max_gap_days: int
    material: bool
    rationale: str

    def __post_init__(self) -> None:
        if self.kind not in {"level_change", "spread_change", "context"}:
            raise ValueError("unsupported rule kind")
        if self.expected not in {"UP", "DOWN", "NONE"}:
            raise ValueError("unsupported expected direction")
        if self.kind != "context" and self.expected == "NONE":
            raise ValueError("directional rules require an expectation")
        if number(self.threshold) < 0:
            raise ValueError("threshold cannot be negative")
        if (
            type(self.max_age_days) is not int
            or type(self.max_gap_days) is not int
            or self.max_age_days < 1
            or self.max_gap_days < 1
            or type(self.material) is not bool
        ):
            raise ValueError("age/gap must be positive integers; material must be boolean")


@dataclass(frozen=True)
class Hypothesis:
    id: str
    version: str
    question: str
    mechanism: str
    metal: str
    geography: str
    effective_time: str
    alternative_explanations: tuple[str, ...]
    boundary: str
    rules: tuple[Rule, ...]

    @classmethod
    def from_dict(cls, data: dict) -> Hypothesis:
        data = dict(data)
        data["rules"] = tuple(Rule(**r) for r in data["rules"])
        data["alternative_explanations"] = tuple(data["alternative_explanations"])
        data["effective_time"] = utc(data["effective_time"])
        if not data["rules"] or not any(r.material for r in data["rules"]):
            raise ValueError("at least one material rule is required")
        names = [r.name for r in data["rules"]]
        if len(names) != len(set(names)):
            raise ValueError("rule names must be unique")
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> Hypothesis:
        return cls.from_dict(json.loads(Path(path).read_text()))


def classify(delta: Decimal, expected: str, threshold: Decimal) -> str:
    if abs(delta) <= threshold:
        return "INSUFFICIENT"
    supports = (delta > 0 and expected == "UP") or (delta < 0 and expected == "DOWN")
    return "SUPPORTS" if supports else "WEAKENS"


def evaluate(archive: Archive, hypothesis: Hypothesis, cutoff: str) -> dict:
    cutoff = utc(cutoff)
    if hypothesis.effective_time > cutoff:
        raise ValueError("hypothesis version was not effective at this cutoff")
    snapshot = archive.as_of(cutoff)
    scoped = [
        o for o in snapshot if o.metal == hypothesis.metal and o.geography == hypothesis.geography
    ]
    rows = []
    for rule in hypothesis.rules:
        observations = [
            o
            for o in scoped
            if o.source == rule.source
            and (
                o.series.startswith(rule.series)
                if rule.kind == "spread_change"
                else o.series == rule.series
            )
        ]
        row = {
            "name": rule.name,
            "material": rule.material,
            "status": "UNAVAILABLE",
            "quality": [],
            "parent_ids": [],
            "reason": "No observations available at the cutoff.",
            "rationale": rule.rationale,
        }
        if observations:
            times = sorted({o.event_time for o in observations})
            latest = times[-1]
            row["latest_event_time"] = latest
            row["age_days"] = (timestamp(cutoff) - timestamp(latest)).total_seconds() / 86400
            relevant = [o for o in observations if o.event_time in times[-2:]]
            row["parent_ids"] = sorted(o.id for o in relevant)
            row["quality"] = sorted({o.quality for o in relevant})
            if row["age_days"] > rule.max_age_days:
                row.update(status="INSUFFICIENT", reason="Latest observation is stale.")
                row["quality"].append("STALE")
            elif any(o.unit != rule.unit for o in relevant):
                row.update(status="INSUFFICIENT", reason="Input unit does not match rule unit.")
                row["quality"].append("SEMANTIC_REVIEW")
            elif any(o.value is None or o.quality == "SUSPECT" for o in relevant):
                row.update(status="INSUFFICIENT", reason="Missing or suspect comparison inputs.")
            elif rule.kind == "context":
                row.update(
                    status="INSUFFICIENT",
                    reason="Context only: this series has no unambiguous directional mapping.",
                    latest_value=observations[-1].value,
                    unit=observations[-1].unit,
                )
            elif len(times) < 2:
                row.update(status="INSUFFICIENT", reason="Two comparison periods are required.")
            elif (
                timestamp(latest) - timestamp(times[-2])
            ).total_seconds() > rule.max_gap_days * 86400:
                row.update(status="INSUFFICIENT", reason="Comparison gap exceeds rule limit.")
            else:
                try:
                    if rule.kind == "spread_change":
                        previous, current = [
                            nearby_spread(observations, time) for time in times[-2:]
                        ]
                        row["constructs"] = [previous.to_dict(), current.to_dict()]
                        row["parent_ids"] = sorted(previous.parents + current.parents)
                        if previous.contracts != current.contracts:
                            raise ValueError(
                                "contract roll: unlike pairs are not directly comparable"
                            )
                        if previous.definitions != current.definitions:
                            raise ValueError("contract definition changed between periods")
                        if previous.unit != current.unit:
                            raise ValueError("spread units changed between periods")
                        delta = number(current.value) - number(previous.value)
                        row["unit"] = current.unit
                    else:
                        previous, current = sorted(observations, key=lambda o: o.event_time)[-2:]
                        if (
                            previous.unit != current.unit
                            or previous.definition != current.definition
                        ):
                            raise ValueError("unit or source definition changed between periods")
                        delta = number(current.value) - number(previous.value)
                        row["unit"] = current.unit
                    row.update(
                        status=classify(delta, rule.expected, number(rule.threshold)),
                        change=decimal_text(delta),
                        reason=f"Observed change evaluated against {rule.expected} expectation; "
                        f"absolute threshold {rule.threshold} {row['unit']}.",
                    )
                except ValueError as exc:
                    row.update(status="INSUFFICIENT", reason=str(exc))
                    row["quality"].append("SEMANTIC_REVIEW")
        rows.append(row)
    material = [r for r in rows if r["material"]]
    directions = {r["status"] for r in material}
    conflict = "SUPPORTS" in directions and "WEAKENS" in directions
    if conflict:
        overall = "INCONCLUSIVE"
        why = (
            "Material observations support opposing interpretations; no unified claim is justified."
        )
    elif directions == {"SUPPORTS"}:
        overall = "BOUNDED_SUPPORT"
        why = "All required material comparisons support the scoped hypothesis, not causality."
    elif directions == {"WEAKENS"}:
        overall = "BOUNDED_WEAKENING"
        why = "All required material comparisons weaken the scoped hypothesis, not causality."
    else:
        overall = "INSUFFICIENT_EVIDENCE"
        why = (
            "At least one required comparison is missing, stale, neutral, or semantically invalid."
        )
    observation_quality = (
        "LOW"
        if any(r["status"] in {"UNAVAILABLE", "INSUFFICIENT"} for r in material)
        else "MODERATE"
        if any(q != "OK" for r in material for q in r["quality"])
        else "HIGH"
    )
    report = {
        "engine_version": __version__,
        "as_of": cutoff,
        "hypothesis": asdict(hypothesis),
        "hypothesis_hash": digest(asdict(hypothesis)),
        "snapshot_ids": sorted(o.id for o in scoped),
        "evidence": rows,
        "material_conflict": conflict,
        "overall_evidence_state": overall,
        "observation_quality": observation_quality,
        "quality_boundary": (
            "Operational quality of required observations, not hypothesis probability."
        ),
        "why": why,
        "boundary": hypothesis.boundary,
    }
    report["report_hash"] = digest(report)
    return report


def markdown(report: dict) -> str:
    lines = [
        "# Copper evidence evaluation",
        "",
        f"As of `{report['as_of']}`. Engine version `{report['engine_version']}`.",
        "",
        report["hypothesis"]["question"],
        "",
        "## Evidence",
        "",
        "| Input | Evidence | Data quality | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["evidence"]:
        cells = [
            row["name"],
            row["status"],
            ", ".join(row["quality"]) or "UNAVAILABLE",
            row["reason"],
        ]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    lines.extend(
        [
            "",
            "## Conclusion boundary",
            "",
            f"Overall evidence state: **{report['overall_evidence_state']}**. {report['why']}",
            "",
            f"Observation quality: {report['observation_quality']}. {report['quality_boundary']}",
            "",
            report["boundary"],
            "",
            "## Alternative explanations",
            "",
            *[f"- {a}" for a in report["hypothesis"]["alternative_explanations"]],
            "",
            "## Audit",
            "",
            f"Report hash: `{report['report_hash']}`",
            "",
            f"Hypothesis hash: `{report['hypothesis_hash']}`",
            "",
            "Parent observation IDs and exact construct lineage are in the JSON report.",
            "",
        ]
    )
    return "\n".join(lines)


def json_report(report: dict) -> str:
    return canonical(report) + "\n"
