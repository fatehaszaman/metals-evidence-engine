# Guarded intake and advisory LLM review

The research scope remains India and Bangladesh, copper first and aluminum second.
This layer handles potentially messy deliveries without turning the evaluator into
a trading strategy, a live market-data platform, or a market-state classifier.
A separate experimental [API preview collector](live-sources/README.md) fetches
real responses into quarantine only. No real feed into this intake layer or
continuously deployed service is included.

## Trust boundaries

```text
Authorized source / trusted adapter
                |
Immutable raw delivery + local receipt + policy snapshot
                |
Deterministic envelope and source-specific policy checks
        /                                       \
Accepted observations                      Quarantine
        |                                       |
Point-in-time archive             Optional advisory LLM review
        |                                       |
as_of() and hypothesis evaluation       Deterministic verdict checks
        |                                       |
Conflict -> INCONCLUSIVE                 Human investigation
                                                |
                                   Explicit, auditable new delivery
                                   (never overwrite old evidence)
```

The file boundary is local and must be access-controlled. A source allowlist,
content hash or self-declared `extraction_method` is not source authentication.
The Python callback is trusted application code, not a security sandbox. Do not
give a model database credentials, filesystem tools or write access.
Prompt separation reduces risk but does not prove prompt-injection immunity.

## Delivery contract and polling

Run `metals-evidence capture --help` for the CLI. `--once` scans once; without it,
the command polls until stopped. It does not install a scheduler or background
service. An operator must supervise it, monitor failures, manage retention, and
implement authorized source retrieval with backoff and release-aware scheduling.
It does not connect to any network provider on its own.

Each `*.ready` file contains:

```json
{
  "extraction_method": "deterministic",
  "observations": ["replace this illustrative string with canonical observation objects"]
}
```

The placeholder above is intentionally not an ingestible observation. The object
schema is defined in [Data contract](data-contract.md); `metals-evidence fixtures`
prints synthetic canonical objects for local tests. A trusted adapter must keep
the original source text in each observation's `raw_payload` rather than
substituting an LLM summary. Binary documents need separately controlled archival
storage; the built-in review interface accepts UTF-8 source text, not PDF/OCR.

Write a temporary file, close it, and atomically rename it to `*.ready`.
The scanner ignores symlinks and defers files whose size or modification time
changes during reading. This is a cooperative delivery protocol, not a hostile
filesystem defense. Readable raw bytes are archived before JSON validation.
Deliveries above 10 MiB are preserved but quarantined rather than parsed.

`config/intake-policy.example.json` is deny-all. Populate its `series` list with
explicit `source`, `series`, `metal`, `geography`, `unit`, `definition`,
`max_age_seconds` and optional decimal-string `max_relative_change` values.
The latter is a ratio, so `"0.25"` means a 25% change threshold.
Freshness must fit the series cadence; a monthly quantity should not inherit a
contract quote's freshness limit. Actual Indian and Bangladeshi observations need
their real geography and coverage, not the fixture's synthetic `IN-BD` label.
The current model's allowed units must be extended and tested before introducing
unsupported local-currency prices; never relabel them as USD.

Intake checks:

- **Schema and time:** canonical types, finite decimal values and
  event <= publication <= local receipt. Producer-supplied receipt time is ignored.
- **Coverage:** allowlisted source/series and exact metal, geography, unit and
  definition. Definition changes require investigation and explicit policy changes.
- **Quality and age:** missing or suspect values and stale events are quarantined.
  Preliminary and revised values retain their quality labels.
- **Duplicates and revisions:** identical versions reuse the original receipt.
  Conflicting versions with the same source key and revision are quarantined.
  Revision order must agree with publication order.
- **Change guard:** optional relative-change thresholds compare to the latest
  earlier accepted event for that series. A zero baseline with a nonzero new value
  requires review. A large jump may be economic, not an error.
- **Unverified extraction:** deliveries labeled LLM/ML or otherwise nondeterministic
  are quarantined. A model must never self-label its extraction as deterministic.

The archive commits per row, not atomically for an entire batch. Valid rows can
be accepted while neighboring rows are quarantined. Identical delivery retries
use the first receipt and policy snapshot; changing a policy does not retroactively
reprocess an old receipt. A crash after observation storage but before recording
its decision can recover as `DUPLICATE` on retry without duplicating observations.
Raw-file hashes deduplicate content, so repeated identical receipts do not create
a separate receipt-event log.

Keep source deliveries, databases and model inputs out of Git. `inbox/` and
`outputs/` are ignored, but arbitrary alternative paths are not automatically
protected. SQLite append-only triggers protect the normal application path;
they do not protect against an administrator modifying the database.

## Advisory judge

`metals_evidence.judge.review(raw_source, candidate, reviewer, reviewer_id,
reviewed_at)` calls a provider-neutral adapter with:

- **Instruction:** raw text and candidate are untrusted data, never instructions.
- **Fixed schema:** `KEEP`, `PROPOSE_CORRECTION`, `ABSTAIN` or `ESCALATE`, with
  reasons, literal evidence quotes and proposed changes.
- **Bounded input:** at most 256,000 UTF-8 bytes of source text per request.
- **Provenance:** versioned prompt and hashes of source, candidate and full input.

The caller's adapter returns a JSON-compatible verdict dictionary. It can use an
authorized LLM provider; runtime code does not require a vendor SDK. Do not send
private or licensed material to a model without permission. The adapter is responsible
for credentials, request timeouts, token limits, model/version identifiers and
provider error handling. Adapter exceptions stop the call without accepting data.
No model provider, paid subscription or trained ML pipeline is configured by default.

Proposals may only address `value`, `unit` or `quality`. They must match the
candidate's current value and quote exact source text. Source, geography,
publication time, event time and revisions cannot be silently rewritten.
Proposed values must be finite, nonnegative decimal strings; units and quality
labels must belong to the canonical model's allowed sets.
Literal matching is not semantic verification: a model can quote a real sentence
and still propose the wrong number. Therefore every structurally valid verdict,
including `KEEP`, remains `REQUIRES_HUMAN_REVIEW`; invalid verdicts become
`REJECTED_REVIEW`. Neither is approval.

`save_review(archive, record)` writes the source text, candidate, response, validation
status, reviewer identity, review time and hashes to an append-only review table.
It verifies the record hash and recomputes its status/provenance before writing.
Original observations and quarantine decisions are never changed. `reviewer_id`
is caller-supplied audit metadata, not attested model identity. Review records remain
separate from hypothesis report inputs and cannot influence `as_of()` results.

To audit an externally generated verdict without connecting a model:

```bash
uv run metals-evidence review --db outputs/capture.db \
  --raw outputs/source.txt \
  --candidate outputs/candidate.json \
  --verdict outputs/model-verdict.json \
  --reviewer 'provider/model-version; extraction-prompt-version' \
  --reviewed-at 2026-09-20T15:00:00Z
```

Those input files must exist. Use the actual review timestamp, not the example.
Exit code 0 means valid advisory review, not accepted data; 1 means a rejected
verdict was archived; 2 means invalid command/input.

After investigation, an operator can supply a new, explicitly documented canonical
delivery through a trusted adapter. There is deliberately no automatic
`approve`/`apply` endpoint. Correcting an already accepted extraction requires a
documented correction-version convention before integration; do not invent a
source revision, forge its publication time or overwrite an existing record.
The existing `ingest` CLI is a trusted offline import path for canonical envelopes,
not a substitute for guarded intake of untrusted deliveries.

## Requirement scores, not a "clean data" certificate

Intake scores and acceptance share one deterministic requirement checker. Every
decision includes a versioned, hashed, append-only `quality_scorecard`. It records
the receipt-time cutoff, policy hash, requirement outcomes and explicit reasons.
Retries retain their first scorecard; old decisions created before this feature
show a null scorecard rather than a fabricated retrospective assessment.
Delivery-level failures score zero before observation checks can be performed.

Each requirement scores 100 for `PASS`, 0 for `FAIL`, or null for `NOT_ASSESSED`.
The twelve requirements are schema, provenance presence, source/series allowlisting,
metal, geography, unit, definition, quality flag, freshness, revision integrity,
relative-change guard and source authenticity.

- **Requirements score:** 100 × passed requirements / all requirements.
  Unassessed items earn no credit but remain distinguishable from failed items.
- **Assessed pass rate:** 100 × passed requirements / assessed requirements.
  This is reported alongside coverage, never by itself.
- **Assessment coverage:** 100 × assessed requirements / all requirements.
  No assessment means a null pass rate, not a perfect score.
- **Mandatory failures:** any mandatory requirement that is not `PASS`
  forces `QUARANTINE`, regardless of the overall score.

The change guard is mandatory when a threshold, usable value and prior baseline
make it assessable. Without these it remains visibly unassessed, not an automatic
pass. Source authenticity is always unassessed by this local file interface;
provenance presence and source allowlisting cannot prove the provider is authentic.
These two checks are not mandatory when unassessable in this prototype. Accordingly,
`ELIGIBLE_FOR_INTAKE` means the implemented mandatory checks passed, not all
requirements were verified. Statistical outlier detection, vendor agreement,
economic truth and licensing compliance are not scored.

For example, a first valid synthetic observation passes ten checks while anomaly
baseline and authenticity remain unassessed: score 83.33, assessed pass rate 100,
coverage 83.33. A later observation with a valid baseline but wrong geography can
also score 83.33, yet must be quarantined. The requirement details matter more
than the headline number.

Preview scores for a canonical candidate without accepting it:

```bash
uv run metals-evidence score --input outputs/candidate.json \
  --policy outputs/source-policy.json --as-of 2026-09-20T15:00:00Z
# Add --db outputs/capture.db to check against an existing archive's known versions.
```

Use the actual intended cutoff, not the illustrative time. Without an archive there
is no historical baseline. This is a preview against the supplied policy and declared
cutoff, not proof the policy was historically in use. Exit 0 means eligible under
mandatory checks, 1 means quarantine, and 2 means invalid command/input.
The live file-intake path instead supplies its local receipt clock.

LLM proposals never increase these scores automatically. A researcher can evaluate
a proposed corrected candidate separately, but it still requires human approval,
full provenance and guarded re-ingestion. Clean formatting or a high score does
not resolve economic disagreement: material evidence conflict still yields
`INCONCLUSIVE`, with observation confidence kept separate.

## What is not solved

No actual India or Bangladesh data coverage, live exchange connection, statistical
drift model, automatic human approval workflow, or semantic truth guarantee is
claimed. Continuous file polling is not continuous source publication.
The scanner rereads ready files and retains raw bytes; it is a bounded local
prototype, not a throughput benchmark or production-scale ingestion service.
Licensed data access, country-specific definitions, source adapters and operation
remain explicit integration work.

Regardless of model advice, material supporting and weakening evidence remains
visible and produces `INCONCLUSIVE`. Observation confidence, per-input data quality,
provenance, source revisions and historical `as_of()` reconstruction stay separate.
