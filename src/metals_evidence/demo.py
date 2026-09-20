"""Small invented records for adversarial tests. These are NOT historical market observations."""

from __future__ import annotations

from dataclasses import replace

from metals_evidence.archive import Archive
from metals_evidence.evidence import Hypothesis, evaluate
from metals_evidence.model import Contract, Observation, canonical, utc

DEFAULT_CUTOFF = "2025-09-19T09:00:00Z"


def observation(
    series: str,
    event: str,
    value: str,
    published: str | None = None,
    ingested: str | None = None,
    **kwargs: object,
) -> Observation:
    publication = published or event
    return Observation(
        source="synthetic-cn-metals",
        series=series,
        metal="COPPER",
        geography="CN",
        event_time=event,
        published_time=publication,
        ingested_time=ingested or publication,
        revision=kwargs.pop("revision", 0),
        value=value,
        unit=kwargs.pop("unit", "tonne"),
        definition=kwargs.pop("definition", series + ":synthetic-v1"),
        quality=kwargs.pop("quality", "OK"),
        raw_payload=canonical(
            {"dataset": "SYNTHETIC", "series": series, "event": event, "value": value}
        ),
        **kwargs,
    )


def records() -> list[Observation]:
    result = []
    for day, values in (("15", ("70000", "70100")), ("18", ("70400", "70200"))):
        for month, value in zip(("10", "11"), values, strict=True):
            result.append(
                observation(
                    f"settlement:CU-{month}",
                    f"2025-09-{day}T07:00:00Z",
                    value,
                    published=f"2025-09-{day}T08:00:00Z",
                    ingested=f"2025-09-{day}T08:05:00Z",
                    unit="CNY/tonne",
                    definition="synthetic-settlement-v1",
                    contract=Contract(
                        code=f"DEMO-CU-2025{month}",
                        exchange="SYNTHETIC",
                        delivery_month=f"2025-{month}",
                        last_trade_time=f"2025-{month}-15T07:00:00Z",
                    ),
                )
            )
    result.extend(
        [
            observation("inventory", "2025-09-15T07:00:00Z", "100000"),
            observation("inventory", "2025-09-18T07:00:00Z", "120000", quality="PRELIMINARY"),
            observation(
                "refined_production",
                "2025-07-31T23:00:00Z",
                "1000000",
                published="2025-08-20T01:00:00Z",
            ),
            observation(
                "refined_production",
                "2025-08-31T23:00:00Z",
                "1050000",
                published="2025-09-15T01:00:00Z",
                quality="PRELIMINARY",
            ),
            observation(
                "refined_imports",
                "2025-07-31T23:00:00Z",
                "300000",
                published="2025-08-20T01:00:00Z",
            ),
            observation(
                "refined_imports",
                "2025-08-31T23:00:00Z",
                "280000",
                published="2025-09-15T01:00:00Z",
                quality="PRELIMINARY",
            ),
            # Published after the first cutoff; must never rewrite its earlier state.
            observation(
                "inventory",
                "2025-09-18T07:00:00Z",
                "90000",
                published="2025-09-20T08:00:00Z",
                ingested="2025-09-20T08:05:00Z",
                revision=1,
                quality="REVISED",
            ),
            # Event and publication precede first cutoff, but local receipt does not.
            observation(
                "shipments",
                "2025-09-17T07:00:00Z",
                "15000",
                published="2025-09-18T08:00:00Z",
                ingested="2025-09-21T08:00:00Z",
            ),
            observation("inventory", "2025-09-22T07:00:00Z", "85000"),
        ]
    )
    return result


def parity_audit(hypothesis: Hypothesis) -> dict:
    """Compare a growing ingestion prefix with a full archive queried at each same cutoff."""
    observations = sorted(records(), key=lambda o: (o.ingested_time, o.id))
    cutoffs = sorted({o.ingested_time for o in observations})
    checkpoints = []
    with Archive() as complete, Archive() as incremental:
        for item in observations:
            complete.append(item)
        for cutoff in cutoffs:
            for item in observations:
                if item.ingested_time == cutoff:
                    incremental.append(item)
            live = evaluate(incremental, hypothesis, cutoff)
            replay = evaluate(complete, hypothesis, cutoff)
            checkpoints.append(
                {
                    "as_of": cutoff,
                    "incremental_hash": live["report_hash"],
                    "replay_hash": replay["report_hash"],
                    "matches": live == replay,
                }
            )
    return {
        "dataset": "SYNTHETIC",
        "audit": "incremental_ingestion_vs_full_archive_replay",
        "passed": all(c["matches"] for c in checkpoints),
        "checkpoints": checkpoints,
        "boundary": "Proves parity on these fixture envelopes, not a deployed live feed.",
    }


def scenario(name: str) -> tuple[list[Observation], str]:
    """Counterfactual scenarios retain clearly synthetic provenance."""
    if name == "conflict":
        return records(), DEFAULT_CUTOFF
    if name == "stale":
        return records(), "2026-01-01T09:00:00Z"
    if name == "definition-break":
        return [
            replace(o, definition="inventory:synthetic-v2-expanded-coverage")
            if o.series == "inventory" and o.event_time == utc("2025-09-18T07:00:00Z")
            else o
            for o in records()
        ], DEFAULT_CUTOFF
    raise ValueError(f"unknown scenario {name}")
