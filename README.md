# Metals Evidence Engine

Given only information actually available at a point in time, what evidence supports,
weakens, contradicts, or leaves unresolved a hypothesis about copper and aluminum
conditions relevant to Bangladesh–India cable, conductor, power, and industrial
supply chains?

This project is a point-in-time hypothesis evidence evaluator, with original payloads,
provenance, revisions, contract-level lineage, explicit evidence rules, and deterministic
`as_of()` reconstruction. Its regional research scope is India and Bangladesh.
It evaluates evidence for a defined hypothesis; it does not declare the physical
market "tightening" or "loosening."

**Status: synthetic research evaluator, guarded intake, advisory LLM review, and
an experimental real API preview collector that writes only to quarantine.**
All checked-in market values and contract identifiers are invented fixtures.
The collector has made actual public API requests; no real observations have been
promoted into the research archive. No continuous service is deployed.
The repository is employer-neutral and makes no investment-performance claims.
Development remains **copper first, aluminum second**:
the working synthetic case is copper; an aluminum case is not yet implemented.

Software engineering and infrastructure are the means of making the research
auditable: explicit data contracts, bounded collection, immutable provenance,
testable quality gates and reproducible historical queries. They do not substitute
for economic reasoning or turn uncertain observations into facts.
See [engineering evidence and preserved milestones](docs/engineering-evidence.md)
for the implemented responsibilities and the original 86-test baseline.

## Regional scope

The intended use is research on metal availability inputs relevant to cable,
conductor, power, and industrial supply chains in Bangladesh and India. Inventory,
production, imports, shipments, and contract evidence must retain their actual
source, country, product, coverage, units, and observation vintage.

The demo's `IN-BD` identifier denotes an explicitly synthetic India–Bangladesh
research scope, not a measured national total, bilateral flow, or pooled regional
balance. Its USD-denominated contract fixtures are invented reference quotations,
not prices from an Indian or Bangladeshi exchange. No FX conversion or empirical
rescaling is implied by the toy values. Real integration must preserve country-specific
definitions and justify cross-country comparisons rather than relabeling observations.

## Run the complete slice

Python 3.11+ and `uv` are required for the commands below. Runtime code uses only
the Python standard library; `uv.lock` pins development dependencies.

```bash
uv sync --locked --extra dev
uv run metals-evidence demo
uv run metals-evidence audit
uv run pytest --cov
uv run ruff check .
uv run ruff format --check .
```

Alternatively, use `python -m pip install -e ".[dev]"`, then run
`metals-evidence demo` and `pytest`. Run commands from the repository root so the
default hypothesis path resolves, or supply an explicit `--hypothesis` path.

## What the demonstration does

```text
Versioned hypothesis and expected mechanism
                    |
Canonical envelopes + original payloads
                    |
Append-only point-in-time archive
                    |
as_of(event <= t, publication <= t, local receipt <= t)
                    |
Semantic checks + same-contract-pair spread construction
                    |
Supporting / weakening / unavailable / insufficient evidence
                    |
Bounded conclusion, or an explicit refusal to conclude
```

The default fixture produces the following deliberately contradictory evidence.
These labels concern the stated hypothesis, not a claim about actual markets.

| Input | Evidence | Interpretation boundary |
| --- | --- | --- |
| Nearby spread | SUPPORTS | Same-pair spread strengthens in the fixture. |
| Visible inventory | WEAKENS | Covered stocks rise; coverage is not total inventory. |
| Refined production | WEAKENS | Output rises; demand is not observed. |
| Refined imports | INSUFFICIENT | Context only; direction is economically ambiguous. |
| Shipments | UNAVAILABLE | Published, but not yet received at the cutoff. |

Overall: **INCONCLUSIVE**. Material conflicts remain visible rather than being
averaged into a directional market-state label. Observation confidence is reported
separately from the conclusion and per-input data quality; it is an operational
usability rubric, not a probability that the hypothesis is true.
Reports also retain provenance, revisions, and the explicit `as_of` cutoff.

## Implemented

- **Archive:** immutable records, raw-payload SHA-256, exact duplicate handling,
  source-specific revision selection, explicit local-knowledge cutoffs.
- **Contracts:** delivery metadata embedded in each versioned observation,
  same-time and same-unit comparisons, nearest two covered delivery months,
  exact-decimal spreads and parent IDs.
- **Evidence:** a versioned hypothesis file, per-series freshness and gap limits,
  definition and unit checks, explicit alternatives, conservative aggregation.
- **Replay:** incremental ingestion and full-archive historical queries call the
  same evaluator; the audit compares complete reports at every fixture checkpoint.
- **Interface:** canonical JSONL ingestion, persistent SQLite storage, JSON and
  Markdown reports, generated conflict/revision/staleness case studies.
- **Guarded intake:** continuous local-file polling, immutable delivery bytes,
  original receipt/policy snapshots, per-row quarantine, freshness and change guards.
- **Advisory LLM judge:** provider-neutral callback, fixed verdict schema, literal
  evidence-quote checks, immutable review history; no automatic data correction.
- **Requirement scores:** per-check 100/0/unassessed, overall score and assessment
  coverage, immutable scorecards and non-overridable mandatory quarantine gates.
- **Real-source collection:** anonymous UN Comtrade copper preview requests,
  bounded response reads, original bytes, append-only receipt events and JSONL
  staging. All rows remain unverified; no automatic handoff to the evaluator.
- **Verification:** adversarial tests and a Python 3.11/3.12/3.13 GitHub Actions matrix.

## Collect a real API response without pretending it is approved evidence

```bash
uv run metals-evidence collect-comtrade \
  --reporter IN --partner WORLD --period 202501 --commodity 740311 \
  --output outputs/comtrade
# Use --reporter BD for Bangladesh. No subscription key is used by this preview.
```

This command was exercised on 2026-09-20: the India request returned six rows,
all quarantined; the Bangladesh request returned no rows, not a measured zero.
Both are current retrievals for a historical reporting period, not historical
publication vintages. The [technical collection record](examples/comtrade-collection-smoke.json)
contains receipt metadata and hashes, not trade values.

Publication time, source revision semantics and complete query coverage remain
unverified. Missing content-type metadata is also recorded as a blocker rather
than fabricated. Exit code 0 means the collection operation completed, not that
the data passed research-quality gates. See the [runnable source guide](docs/live-sources/README.md)
for exact boundaries, request codes, failure states and next release gates.

## Messy data and the LLM judge

The intake process can continuously watch a directory populated by an authorized
provider adapter. This is a running local process, not a deployed service or a
claim that an exchange feed is connected. Source publication frequency determines
freshness; polling a monthly release frequently does not make its observations real-time.

```bash
mkdir -p inbox outputs
uv run metals-evidence capture --db outputs/capture.db --inbox inbox \
  --policy config/intake-policy.example.json --interval 30 --once
# Remove --once to keep watching while this process runs.
```

The checked-in policy deliberately accepts **no series**. An operator must define
source-specific units, geography, coverage/definition, freshness limits and optional
relative-change limits before accepting any records. Producers atomically rename
complete JSON deliveries to `*.ready`; raw bytes are preserved before parsing.
Bad rows remain quarantined, not silently repaired or discarded.

An LLM can compare a candidate extraction against raw text and propose a correction,
abstain, or escalate. Its output must cite exact source text and pass structural
checks; even a valid verdict remains `REQUIRES_HUMAN_REVIEW`. The judge cannot
promote records, replace observations, invent missing values, or resolve economic
contradictions. Observation confidence remains separate from the model's opinion.

Every intake decision now includes a `quality_scorecard` across schema, provenance,
source/series, metal, geography, units, definitions, quality flags, freshness,
revision integrity, change guards and source authenticity. Scores are deterministic,
not an LLM's self-rating. Unassessed requirements earn no overall credit, and any
failed or unassessed mandatory requirement blocks acceptance regardless of score.
An 83.33 score can therefore accompany a quarantined record; no score certifies truth.

See [Guarded intake and advisory review](docs/data-intake.md) for the delivery
contract, runnable review command, adapter interface and operational limits.

### Pipeline pseudocode and live-source boundary

This pseudocode summarizes the controls, not an end-to-end live integration.
**The API preview collector stops at quarantine; no continuous service is deployed.**
Release metadata, canonical mapping, permissions for broader use and supervised
operation remain integration work. Optional LLM review is a separate explicit call,
not an automatically running job.

```text
# Research scope: India and Bangladesh; copper first, aluminum second.
# AVAILABLE: local file watcher, guarded intake, advisory judge, as_of evaluator.
# AVAILABLE: real Comtrade preview -> immutable raw archive + quarantined JSONL.
# NOT CONNECTED: verified source release -> canonical adapter -> delivery files.
# A polling interval is not proof of real-time source publication.

when the researcher explicitly runs the API preview collector:
    request one validated country / product / period scope on an allowed HTTPS host
    preserve bounded original bytes and a distinct receipt event
    reject redirects, access failures, invalid JSON and wrong query scope
    retain absent metadata, preview completeness and revision questions as blockers
    write only unverified staging rows; NEVER promote into canonical evidence

when a completed local delivery arrives:
    preserve original bytes, first local receipt time, and policy snapshot
    if delivery is malformed or extraction is unverified / LLM-generated:
        quarantine delivery; never silently repair or accept it
    otherwise, for each candidate:
        check schema, provenance presence, source/series, metal, geography,
              units, definitions, quality flags, freshness, revisions,
              and relative change where a threshold and baseline exist
        leave independent source authenticity NOT_ASSESSED

        requirement score = 100 for PASS, 0 for FAIL, null for NOT_ASSESSED
        overall score = 100 * passed requirements / all requirements
        coverage = 100 * assessed requirements / all requirements
        preserve scorecard, reasons, policy hash, and assessment cutoff

        if ANY mandatory requirement is failed or unassessed:
            QUARANTINE, regardless of the overall score
        else:
            append validated observation, or retain the original duplicate
            # Passing implemented checks does not certify economic truth.

when a researcher explicitly requests optional LLM review:
    compare the raw source with the candidate; propose, keep, abstain, or escalate
    require literal evidence quotes, allowed fields, and canonical proposed values
    record REJECTED_REVIEW or REQUIRES_HUMAN_REVIEW; never auto-apply
    # Human investigation and an auditable new delivery are separate steps.
    # Re-score any corrected candidate; never overwrite prior observations.

when evaluating a versioned hypothesis at cutoff t:
    reconstruct only evidence with event, publication, and local receipt <= t
    preserve supporting, weakening, missing, and conflicting evidence
    if material evidence conflicts: return INCONCLUSIVE
    report observation confidence, data quality, provenance, and revisions separately
    # Cleanliness scores do not vote on or override the hypothesis conclusion.
```

## Inspect the archive yourself

```bash
mkdir -p outputs
uv run metals-evidence fixtures > outputs/synthetic.jsonl
uv run metals-evidence ingest --db outputs/demo.db --input outputs/synthetic.jsonl
uv run metals-evidence evaluate --db outputs/demo.db \
  --as-of 2025-09-19T09:00:00Z --format json
uv run metals-evidence evaluate --db outputs/demo.db \
  --as-of 2025-09-20T09:00:00Z
uv run metals-evidence demo --scenario definition-break
uv run metals-evidence demo --scenario stale
```

The inventory revision becomes visible only after its publication and receipt.
The earlier report remains unchanged even when the full archive contains that
revision and later observations.

## Boundaries

No approved real-data adapter into the evaluator, proprietary data, verified
complete India or Bangladesh market coverage, calibrated economic thresholds,
shipment reconciliation, full physical balance, aluminum
case study, continuous futures series, or deployed monitoring is claimed.
The metal enum permits aluminum but the implemented research case is copper only.

V1 does not discover structural breaks statistically or reconcile competing
vendors automatically. It guards explicit definition changes and keeps sources
separate; `SUSPECT` flags must currently be supplied by an adapter or researcher.
An optional deterministic relative-change guard quarantines suspicious jumps without
asserting they are errors. Statistical anomaly models, release calendars, and licensed
data integration remain future work. No trained ML model or scheduled LLM service is included.

A missing nearby contract in the supplied universe cannot be discovered without
a complete contract master. Therefore “M1/M2” always means the nearest two valid
contracts **within supplied coverage**, not a guarantee of complete exchange coverage.
Contract rolls are withheld rather than back-adjusted.

The evaluator accepts a caller-supplied hypothesis version and checks its declared
effective time. That does not prove a rule was historically authored or prevent
researcher hindsight in rule selection. Historical replay is as rigorous as the
archived envelopes, declared versions, and ingestion-time integrity.

No buy/sell signals, price predictions, portfolio construction, causal-identification
claims, employer branding, or claims about an employer's internal methodology.
This is neither a trading strategy nor a live market-data platform.

## Documentation

- [Architecture and algorithms](docs/architecture.md): time semantics, algorithms,
  complexity, lineage, and limits.
- [Engineering evidence and milestones](docs/engineering-evidence.md): how software
  and infrastructure support research, with the original implementation preserved.
- [Data contract](docs/data-contract.md): units, revisions, provenance, and ingestion.
- [Guarded intake and advisory review](docs/data-intake.md): messy deliveries,
  quarantine, LLM proposals, audit history and live-feed boundaries.
- [Live sources: API-first integration](docs/live-sources/README.md): UN Comtrade
  API access, source-specific mapping, permissions and activation requirements.
- [Actual source inspection and scraping runbook](docs/live-sources/SCRAPING.md):
  verified TradeStat controls and NBR document links, observed retrieval failures,
  and the distinction between inspected interfaces and implemented collectors.
- [Research method](docs/research-method.md): rules, ambiguous evidence, and conclusion gates.
- [Case studies](examples/README.md): conflict, later revision, stale data, and definition breaks.
- [Release checklist](docs/release-checklist.md): conditions before considering public release.

The next scope is verified release metadata, coverage and a canonical mapping for
the first source, not a dashboard or a trading strategy.
