# Data contract

The ingestion format is UTF-8 JSONL containing one canonical envelope per line.
`metals-evidence fixtures` prints a complete example without a network dependency.

## Observation envelope

| Field | Contract |
| --- | --- |
| source, series | Nonempty provider and series identifiers; never silently merge providers. |
| metal | COPPER or ALUMINUM; copper only is exercised in the research demo. |
| geography | Explicit coverage identifier; IN-BD denotes the synthetic India–Bangladesh research scope, not a measured regional aggregate. |
| event_time | Realized observation/period-end time, with timezone. |
| published_time | When that version became available from its source. |
| ingested_time | When this system actually received the version. |
| revision | Nonnegative, monotonic ordinal assigned by the adapter per source/series/event. |
| value | Nonnegative finite decimal string; null only when quality is MISSING. |
| unit | tonne, CNY/tonne, USD/tonne, or USD/lb; no implicit conversion. |
| definition | Stable semantic definition identifier; changes block direct comparisons. |
| quality | OK, PRELIMINARY, REVISED, SUSPECT, or MISSING. |
| raw_payload | Original source text retained verbatim inside the JSON string. |
| contract | Optional code, exchange, delivery month, and timezone-aware last-trade time. |

Unknown fields are rejected by typed constructors. Times are normalized to UTC;
naive timestamps, nonfinite numbers, binary float inputs, invalid units, negative
levels, and publication-before-event/receipt-before-publication are rejected.
This v1 models realized observations, not forecasts or advance estimates dated
after their publication.

Monthly flow `event_time` is the period end. Compare only like-defined periods;
this prototype does not annualize, seasonally adjust, or align monthly flows with
daily stocks into a mass balance.

## Identity and revision behavior

The record ID hashes the canonical envelope, including receipt time and embedded
contract metadata. The raw-payload hash independently covers the retained UTF-8
source text, not the normalized observation.

JSON reports expose a separate `provenance` list with these identifiers, source,
series, geography, revision and all three timestamps. Raw payloads remain in the
archive. `observation_confidence` is distinct from each evidence row's `quality`
flags and from the hypothesis conclusion; `observation_quality` is retained as a
compatibility alias for the same confidence rubric.

An identical envelope is a no-op. A different envelope with the same
`(source, series, event_time, revision)` raises an error instead of silently
overwriting anything. Re-downloads with a new receipt timestamp must reuse the
original archived envelope when the provider version is unchanged; a future
adapter should deduplicate before assigning receipt events.

The whole input file is parsed and validated before ingestion starts. Appends are
individually transactional: a conflicting duplicate discovered during insertion
can leave an earlier valid prefix committed. This is safe to retry with identical
envelopes, but ingestion is not an all-or-nothing batch operation.

## Source integration gate

A real provider adapter must document rights to store and redistribute data,
endpoint/version semantics, publication timezone, missing-release behavior,
revision ordering, contract metadata, units, and series definitions. Preserve
raw responses before normalization and never label backfilled downloads as
historical local observations.

No API keys or provider account data belong in this repository. The current
fixtures are invented and contain no personal, employer, or proprietary market data.
