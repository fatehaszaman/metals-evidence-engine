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

**Status: working synthetic-data vertical slice, not a live market-data service.**
All included market values and contract identifiers are invented fixtures.
The repository is employer-neutral and makes no investment-performance claims.
Keep this repository private. Development remains **copper first, aluminum second**:
the working synthetic case is copper; an aluminum case is not yet implemented.

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
- **Verification:** adversarial tests and a Python 3.11/3.12/3.13 GitHub Actions matrix.

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

No live provider adapter, proprietary data, verified India or Bangladesh market
coverage, calibrated economic thresholds, shipment reconciliation, full physical balance, aluminum
case study, continuous futures series, or deployed monitoring is claimed.
The metal enum permits aluminum but the implemented research case is copper only.

V1 does not discover structural breaks statistically or reconcile competing
vendors automatically. It guards explicit definition changes and keeps sources
separate; `SUSPECT` flags must currently be supplied by an adapter or researcher.
Outlier detection, release calendars, and licensed data integration remain future work.

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
- [Data contract](docs/data-contract.md): units, revisions, provenance, and ingestion.
- [Research method](docs/research-method.md): rules, ambiguous evidence, and conclusion gates.
- [Case studies](examples/README.md): conflict, later revision, stale data, and definition breaks.
- [Release checklist](docs/release-checklist.md): conditions before considering public release.

The next scope is one documented public-data adapter with honest historical-vintage
coverage, not a dashboard or a trading strategy. Keep the repository private until
its owner explicitly decides to publish it.
