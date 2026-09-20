# Architecture and algorithms

The project separates observation availability from economic interpretation.
Every transformation receives a point-in-time snapshot instead of consulting a
mutable “latest data” table.

## Data path

`model.py` validates canonical observation envelopes; `archive.py` stores them
append-only; `transforms.py` builds exact-decimal contract spreads;
`evidence.py` evaluates the supplied hypothesis. The CLI and parity audit share
those functions rather than maintaining separate historical and live logic.

SQLite triggers reject row updates and deletes through ordinary SQL. This is an
application-level integrity control, not tamper-proof storage against a database
administrator who can drop triggers or replace the file.

## Point-in-time selection

Purpose: reconstruct the observations the local system could have used at cutoff `t`.
Inputs: archive and timezone-aware cutoff. Output: highest available revision of
each `(source, series, event_time)`.

```text
# Normalize every timestamp to a fixed-width UTC representation.
# First exclude future events, unpublished releases, and not-yet-received records.
eligible = records where event_time <= t
                     and published_time <= t
                     and ingested_time <= t

# Rank only the eligible subset, never rank before applying the cutoff.
# Revisions are provider-adapter assigned monotonic ordinals, not ingestion order.
for each source / series / event_time partition:
    choose the greatest revision ordinal

# Preserve source identity and return deterministic ordering.
return selected records ordered by source, series, event_time, content_id
```

Conservative upper-bound cost: O(n log n) time and O(n) working storage for ranking
eligible rows; actual plans depend on SQLite and the availability-time index.
Source revisions arriving out of order cannot roll a series backward.

Operational knowledge uses `max(published_time, ingested_time)` as a necessary
availability bound, with the event cutoff applied too. Downloading a revised
history today does not make its original vintage available yesterday; unknown
publication time must not be guessed by a future provider adapter.

## Contract spread

Purpose: calculate earlier-delivery minus later-delivery settlement at one event time.
Inputs: selected contract envelopes. Output: spread, quotation unit, contract IDs,
quality flags, and two parent observation hashes.

```text
# Work within one source, exchange, metal, geography, and quotation unit.
# Require observations at the same event timestamp.
# Exclude contracts already expired at that observation timestamp.
# Sort covered contracts by delivery month.
# Reject duplicate delivery months and missing/suspect nearby values.
# Select first two deliveries and compute their exact-decimal difference.
# Preserve the two original record IDs.
```

For k covered contracts: O(k log k) time and O(k) working storage. Positive spread
means the earlier quoted contract exceeds the later one under this project's
explicit sign convention; this alone does not establish a physical shortage.

Comparisons across observation times require identical contract codes and
definitions. The engine refuses to interpret a roll transition as a market move.
It does not interpolate, convert currencies, fill missing tenors, or back-adjust.

## Evidence aggregation

Purpose: evaluate whether material, comparable evidence agrees with a hypothesis.
Inputs: selected observations and one versioned rule set. Output: a complete
report with evidence rows, quality, explicit limits, and deterministic hash.

```text
# For each rule, use its exact source and series (or settlement prefix).
# Expose unavailable, stale, missing, suspect, and semantically changed data.
# Only compare eligible periods within the declared gap limit.
# Context-only series never receive a directional interpretation.
# Classify directional changes using the rule's expected sign and deadband.

if material SUPPORTS and material WEAKENS coexist:
    INCONCLUSIVE
elif every material rule SUPPORTS:
    BOUNDED_SUPPORT
elif every material rule WEAKENS:
    BOUNDED_WEAKENING
else:
    INSUFFICIENT_EVIDENCE
```

The simple implementation rescans the snapshot per rule: O(r n log n) conservative
time including period sorts, with O(r n) report lineage in the worst case.
This is intentionally small-scale research code, not a throughput claim.

Contradiction takes precedence over missingness: an absent required series does
not erase a contradiction already present. Data quality is distinct from evidence
direction and never becomes a weighted “tightness score.”

## Replay parity

The fixture audit appends original envelopes in receipt-time order. At each
checkpoint it compares an incremental archive's report with a fully populated
archive queried at the same cutoff, hypothesis version, and engine version.
Both complete reports and hashes must match.

This proves parity for the tested envelopes and cutoffs. It does not demonstrate
a deployed live connector, validated source timestamps, global data completeness,
or point-in-time discovery of the economic hypothesis itself.
