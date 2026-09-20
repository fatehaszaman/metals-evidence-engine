"""Deterministic requirement scores, not probabilities of truth or model confidence."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

from metals_evidence.archive import Archive
from metals_evidence.model import Observation, digest, number, timestamp, utc

SCORE_VERSION = "requirements-v1"
REQUIREMENTS = (
    "schema",
    "provenance",
    "source_series",
    "metal",
    "geography",
    "unit",
    "definition",
    "quality",
    "freshness",
    "revision",
    "change_guard",
    "source_authenticity",
)


def summarize(checks: list[dict], as_of: str | None = None, policy_hash: str | None = None) -> dict:
    passed = sum(c["status"] == "PASS" for c in checks)
    assessed = sum(c["status"] != "NOT_ASSESSED" for c in checks)
    failures = [c["requirement"] for c in checks if c["mandatory"] and c["status"] != "PASS"]
    report = {
        "score_version": SCORE_VERSION,
        "assessed_as_of": as_of,
        "policy_hash": policy_hash,
        "requirements_score": round(100 * passed / len(checks), 2),
        "assessed_pass_rate": round(100 * passed / assessed, 2) if assessed else None,
        "assessment_coverage": round(100 * assessed / len(checks), 2),
        "mandatory_failures": failures,
        "disposition": "QUARANTINE" if failures else "ELIGIBLE_FOR_INTAKE",
        "requirements": checks,
        "boundary": (
            "Equal-weight deterministic requirement checks, not truth, economic confidence, "
            "or provider authentication. Unassessed requirements earn no overall credit. "
            "No aggregate threshold overrides a mandatory failure."
        ),
    }
    report["scorecard_hash"] = digest(report)
    return report


def assess(archive: Archive, candidate: dict, policies: list, received: str) -> tuple:
    """Use only records locally known by receipt time; return observation and scorecard."""
    received = utc(received)
    policy_hash = digest([asdict(p) for p in policies])
    checks = {
        name: {
            "requirement": name,
            "status": "NOT_ASSESSED",
            "score": None,
            "mandatory": name not in {"change_guard", "source_authenticity"},
            "reason": "Prerequisite validation unavailable.",
        }
        for name in REQUIREMENTS
    }

    def check(name, passed, reason, mandatory=None):
        checks[name].update(
            status="PASS" if passed else "FAIL", score=100 if passed else 0, reason=reason
        )
        if mandatory is not None:
            checks[name]["mandatory"] = mandatory

    checks["source_authenticity"]["reason"] = (
        "Local file intake does not independently authenticate the upstream provider."
    )
    try:
        if not isinstance(candidate, dict):
            raise ValueError("observation must be an object")
        observation = Observation.from_dict(candidate | {"ingested_time": received})
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        check("schema", False, str(exc))
        return None, summarize(list(checks.values()), received, policy_hash)
    o = observation
    check("schema", True, "Canonical types, finite nonnegative values and time order passed.")
    check("provenance", True, "Source, raw payload, definition and version timestamps present.")
    rule = next((p for p in policies if p.source == o.source and p.series == o.series), None)
    check(
        "source_series",
        rule is not None,
        "Allowlisted source/series." if rule else "source/series is not allowlisted",
    )
    if rule:
        for field in ("metal", "geography", "unit", "definition"):
            matches = getattr(o, field) == getattr(rule, field)
            check(
                field,
                matches,
                f"{field} matches policy." if matches else f"{field} mismatch or definition change",
            )
        fresh = (
            timestamp(received) - timestamp(o.event_time)
        ).total_seconds() <= rule.max_age_seconds
        check(
            "freshness",
            fresh,
            "Within source-specific event-age limit."
            if fresh
            else "stale observation; preserve raw and review, do not call it live",
        )
    usable = o.value is not None and o.quality not in {"MISSING", "SUSPECT"}
    check(
        "quality",
        usable,
        f"Reported quality: {o.quality}."
        if usable
        else "missing or suspect value; no imputation permitted",
    )
    versions = archive.connection.execute(
        "SELECT envelope FROM observations WHERE source=? AND series=? AND event_time=? "
        "AND ingested_time<=?",
        (o.source, o.series, o.event_time, received),
    ).fetchall()
    revision_error = None
    for row in versions:
        existing = Observation.from_dict(json.loads(row[0]))
        if existing.revision == o.revision:
            if replace(o, ingested_time=existing.ingested_time) != existing:
                revision_error = "conflicting duplicate revision; preserve and investigate"
                break
        elif (existing.revision < o.revision and existing.published_time > o.published_time) or (
            existing.revision > o.revision and existing.published_time < o.published_time
        ):
            revision_error = "revision and publication order disagree"
            break
    check(
        "revision",
        revision_error is None,
        revision_error or "No conflicting duplicate or revision/publication ordering found.",
    )
    previous = [
        item
        for item in archive.as_of(received)
        if item.source == o.source
        and item.series == o.series
        and item.event_time < o.event_time
        and item.value is not None
    ]
    if rule and rule.max_relative_change is not None and previous and usable:
        baseline = number(max(previous, key=lambda item: item.event_time).value)
        if baseline == 0:
            acceptable = number(o.value) == 0
            reason = (
                "Zero baseline unchanged."
                if acceptable
                else ("zero baseline: relative-change check requires review")
            )
        else:
            acceptable = abs(number(o.value) - baseline) / abs(baseline) <= number(
                rule.max_relative_change
            )
            reason = (
                "Within configured relative-change limit."
                if acceptable
                else ("large change requires review; may be economic, not a data error")
            )
        check("change_guard", acceptable, reason, mandatory=True)
    else:
        checks["change_guard"]["reason"] = (
            "No configured threshold, prior baseline, or usable value; no anomaly assurance."
        )
    return observation, summarize(list(checks.values()), received, policy_hash)


def rejected_delivery(reason: str) -> dict:
    """Malformed or unverified deliveries cannot earn observation-level scores."""
    checks = [
        {
            "requirement": name,
            "status": "FAIL" if name == "schema" else "NOT_ASSESSED",
            "score": 0 if name == "schema" else None,
            "mandatory": name not in {"change_guard", "source_authenticity"},
            "reason": reason if name == "schema" else "Delivery validation failed.",
        }
        for name in REQUIREMENTS
    ]
    return summarize(checks)
