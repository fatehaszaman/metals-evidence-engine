# Live-source integration: API first

This is the source-access and implementation guide for the private Metals Evidence
Engine. Its research scope is India and Bangladesh, copper first and aluminum second,
for cable, conductor, power and industrial supply chains.

**Status: no live economic-data source is connected, no source adapter is implemented,
and no continuous collection service is deployed.** Public documentation, interface
HTML and an API field dictionary were inspected on 2026-09-20. That is source-access
verification, not proof of complete data extraction or a working live feed.
The existing `capture` command watches local files; it does not make API requests.

## Access order

Use an official API where available, then an official downloadable file, then
permitted HTML extraction. Use OCR or LLM-assisted extraction only as an explicitly
unverified candidate path. Browser automation is a fallback for permitted interactive
downloads, not a way around logins, CAPTCHAs, bot protection or subscription rights.

“Live source” here means actual external observations collected as the source
publishes them. It does not mean every series is real-time: preserve annual,
monthly, end-of-day, delayed and real-time cadences separately. A running collector
cannot make an old observation current.

## Engineering stack and link-quality requirements

Use each language for an explicit responsibility, not as a claim that a larger
stack makes observations more accurate. The current repository implements Python,
SQLite-backed SQL storage and shell-invoked commands; it has no Java collector or
deployed Bash scheduler.

- **Python:** implemented envelope validation, requirement scoring, evidence
  evaluation and local delivery intake. Source-specific API clients, HTML/PDF
  parsers and link-validation adapters remain to be implemented.
- **SQL / SQLite:** implemented append-only observations, raw deliveries, decisions,
  requirement scorecards and advisory reviews. A source-discovery/link registry
  would be a separate future schema, not an existing table.
- **Bash:** documented repeatable CLI commands for intake, scoring, tests and replay.
  Deployment scripts would manage exit codes, supervision and redacted logs;
  no shell loop should conceal rate limits or repeated fetch failures.
- **Java:** an optional future typed API/streaming collector if a provider or
  operational requirement calls for it. It would emit the same canonical delivery
  contract and must pass the same fixtures as Python. No Java implementation or
  Java-derived data is claimed in this repository.

“Valid, accurate, unique links” means three separate controls:

- **Valid access:** an allowed official host, successful authorized retrieval,
  acceptable redirects and expected content type/signature. A working link alone
  does not establish a permitted use or a valid data table.
- **Accurate identity and extraction:** verify publisher, report title, country,
  product, period, units and document structure against the actual content.
  A link checker cannot certify economic truth.
- **Unique discovery, preserved versions:** deduplicate discovery URLs and identical
  payloads while retaining every distinct release, revision and retrieval event
  needed for audit. A changed document at the same URL is not a duplicate release.

See the [link-validation and deduplication contract](SCRAPING.md#link-validation-and-deduplication-contract)
for the proposed adapter rules. These do not override quarantine or the
`INCONCLUSIVE` boundary when economic evidence conflicts.

## Recommended first API: UN Comtrade

UN Comtrade documents anonymous preview APIs and subscription-key APIs, including
data availability and publication-update routes; access depends on the API product
and subscription ([official API guide](https://uncomtrade.org/docs/un-comtrade-api/)).
It is a candidate trade-flow input, not a contract-price or inventory feed.
Country/product coverage must be checked before claiming India or Bangladesh coverage.

### Request shape

The following is a documentation-derived template, **not a tested data request**.
Resolve parameters against current official code lists and the developer portal;
do not guess country codes, product mappings or available months
([API guide](https://uncomtrade.org/docs/un-comtrade-api/),
[developer portal](https://comtradedeveloper.un.org/)).

```text
GET https://comtradeapi.un.org/public/v1/preview/C/M/HS
    ?reporterCode=<verified India OR Bangladesh reporter code>
    &partnerCode=<explicit partner selection>
    &flowCode=<verified import OR export code>
    &cmdCode=<verified copper product code; aluminum follows separately>
    &period=<YYYYMM with confirmed availability>
```

The route uses the documented commodity, monthly and classification dimensions;
the parameters must be validated for the chosen endpoint before execution
([API guide](https://uncomtrade.org/docs/un-comtrade-api/)).
Do not copy a global metals chapter into a refined-copper hypothesis without checking
product definitions. Reporter imports and partner exports are distinct observations,
not interchangeable measurements or automatic duplicates.

The public preview does not require a subscription key, but preview output is
limited to a snapshot of up to 500 records and may omit part of a query result
([API guide](https://uncomtrade.org/docs/un-comtrade-api/),
[preview limitations](https://uncomtrade.org/docs/what-is-data-preview/)).
Therefore `HTTP 200`, a nonempty response, or fewer than the requested maximum
records is not alone a completeness proof. Establish an explicit coverage check
using the provider's supported metadata/count/download mechanisms before accepting
a query as complete. Do not invent offset pagination or enumerate around access limits.

### Fields and point-in-time mapping

The official dictionary includes `reporterCode`, `partnerCode`, `classificationCode`,
`cmdCode`, `period`, `qty`, `qtyUnitCode`, `netWgt`, `primaryValue`, `isReported` and
`isAggregate`; it also defines quantity and weight-estimation flags
([field dictionary](https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json)).
These are source fields to preserve, not permission to equate value, quantity and weight.

- **Series identity:** include reporter, partner, direction, product code,
  classification edition, measure and any customs/transport coverage dimensions.
- **Country identity:** preserve the actual reporter and partner; do not rewrite
  real rows as the synthetic fixture's `IN-BD` region.
- **Units:** confirm the actual measure's unit from provider metadata before
  conversion. Keep the original unit, exact decimal and scaling factor.
  The current canonical model does not support every currency or quantity unit.
- **Estimated values:** retain the exact source flags; do not quietly promote
  estimated quantities to verified observations.
- **Publication time:** the inspected field dictionary does not supply a
  publication/release timestamp. Obtain it from release metadata rather than
  interpreting `period` as a publication date
  ([field dictionary](https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json)).
- **Release monitoring:** the API guide documents `data/v1/getLiveUpdate`,
  `data/v1/getDa` and metadata access, but those routes were not called in this
  documentation check ([API guide](https://uncomtrade.org/docs/un-comtrade-api/)).
- **Revisions:** content changes are retrieval versions until a validated
  source-revision convention exists. A payload hash is not a source revision number.
  The engine's current integer revision contract must not be populated with
  invented publication history.

If publication time, units, coverage or revision semantics cannot be established,
retain the raw response and quarantine the candidate. A freshly downloaded current
release cannot prove what was available at an earlier historical cutoff.

### API client requirements before activation

Implement a bounded client with explicit timeouts, response-size limits, an
allowlisted HTTPS host, documented authentication and schema checks. Capture the
exact response bytes before parsing, the UTC local receipt time, redacted request
parameters, response status, relevant cache/revision headers and parser version.
Neither a provider's HTTP `Date` header nor local receipt proves publication time.

Honor provider limits and `Retry-After`; cap retries for transient failures.
Stop for missing permissions and unrecognized schema rather than retrying blindly.
Treat rate limits, empty results, partial results and unavailable periods as distinct
states. Store checkpoints only after the raw response is durable.

Use the approved credential vault or deployment secret manager for subscription
keys. Never commit keys or log credential-bearing URLs; redact authentication query
parameters before storing request metadata. No key is configured by this guide.
Confirm licensing and redistribution permissions before sharing raw data or sending
it to an external LLM.

## Official-page and downloadable-file alternatives

### India TradeStat

The inspected TradeStat country-wise export interface exposes a POST form with
month, year, country, commodity-level and report controls, plus a hidden `_token`;
its page also distinguishes final/revised releases
([inspected interface](https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export)).
This is a verified form, **not a verified public JSON API**. No form was submitted,
no export file was downloaded and no economic rows were ingested.

Use the API route above where its definitions and coverage fit. If TradeStat is
needed, follow its permitted official export workflow and preserve query selections.
Do not treat an export-only page as an import source or automatically equate Indian
exports to Bangladesh with Bangladesh-reported imports.
See [actual interface inspection and scraping steps](SCRAPING.md).

### Bangladesh National Board of Revenue

The customs publications page lists separate `IM-4-Commecial` and `IM-7-Bond`
statements with month labels and publication dates
([NBR publications](https://nbr.gov.bd/publications/customs/eng)).
The inspected HTML exposed direct statement PDF links; a selected PDF fetch failed,
so PDF columns, completeness and parsing are not claimed as verified.
Do not combine the two statement types without an explicit coverage and overlap
assessment. The spelling `Commecial` is retained from the source.

Prefer official downloadable files over scraping rendered numeric cells. Keep the
listing, PDF, statement type, report period and publication-date evidence together;
preserve pagination and exact row/column locations during extraction.
See [NBR collection runbook](SCRAPING.md#bangladesh-nbr-document-discovery).

### MCX contracts and spreads

MCX documents real-time, delayed and end-of-day data products and requires an
appropriate subscription/agreement for its feeds
([MCX datafeed documentation](https://www.mcxindia.com/technology/datafeed)).
This is an authorized-feed integration, **not a public-page scraping task**.
No feed entitlement, connection or contract-data request was verified.

Before implementation, confirm permitted analytical/non-display use, storage,
model-processing and redistribution rights for the chosen product. Preserve actual
contract identifiers, exchange timestamps, delivery metadata, quote units and
latency. Do not relabel unsupported local-currency prices as USD to fit the model.
No real-time claim is allowed without a verified real-time subscription and measured
end-to-end delivery latency.

## Handoff to the existing engine

```text
approved source and permissions
    -> API response or original downloadable file
    -> durable raw archive + redacted request/release metadata
    -> source-specific parser with fixture tests
    -> canonical candidate with source, country, units and time lineage
    -> requirement scorecard
    -> mandatory failure or missing mandatory check? QUARANTINE
    -> otherwise emit a complete deterministic delivery via atomic *.ready rename
    -> capture re-checks and records its own local receipt time
    -> as_of() hypothesis evaluation; material conflict stays INCONCLUSIVE
```

These source-adapter steps are a specification, not existing automated code.
The runnable pieces are documented in [guarded intake and review](../data-intake.md).
Do not add arbitrary metadata keys to the strict canonical envelope. Keep the full
source manifest separately and preserve source text/structured provenance inside
`raw_payload` according to an explicitly versioned adapter convention.

The current capture clock records engine receipt, which can be later than network
fetch time. Keep both timestamps in provenance, but do not backdate canonical
ingestion to make historical coverage appear better. Unknown precise release times
require an explicit conservative time policy or quarantine, not fabricated precision.

## Text-first storage and bounded memory

Use UTF-8 `.txt` for extracted source passages and `.jsonl` for structured,
line-delimited staging records and collection logs. Keep README documentation in
plain-text Markdown; do not create PDF or Word copies just to describe the pipeline.
These are proposed collector storage conventions, not new accepted intake formats.

- **Preserve originals:** retain original API response bytes, HTML and downloadable
  documents in a controlled raw archive. A TXT extraction is a derived view, not
  a replacement for the evidence it came from.
- **Stream derived records:** design adapters to iterate through JSONL records or
  document pages with explicit size limits instead of loading an entire history
  into one in-memory list. Do not put all extracted documents into one LLM prompt.
- **Keep batches small:** emit bounded canonical JSON deliveries using the existing
  `extraction_method` / `observations` envelope and atomic `*.ready` rename.
  The watcher does not currently accept arbitrary TXT or JSONL files as deliveries.
- **Keep provenance attached:** each extracted passage or row needs a source-file
  hash and precise record/page/row location. Keep exact decimal strings, units,
  missing markers and character encoding; do not flatten away meaningful columns.
- **Separate storage and memory claims:** choose a format based on actual measured
  disk size, parse cost and peak memory for the target workload. Do not treat a
  `.txt` filename extension as a guarantee of lower RAM use.

The current `capture` implementation reads a complete ready file and parses its
JSON in memory. Its 10 MiB processing limit is checked after bytes are read and
preserved; it is **not** a streaming parser or a pre-read memory cap.
Bound delivery size in the trusted producer today. A streaming/bounded-read
collector and retention policy must be implemented and benchmarked before making
low-memory or production-scale claims.

## Activation checklist

- [ ] Source permissions and API tier confirmed; no secrets in Git or logs.
- [ ] One actual authorized response/file archived unchanged with receipt metadata.
- [ ] India or Bangladesh reporter, direction, product and period verified.
- [ ] Complete coverage established; preview truncation and missing rows detected.
- [ ] Units, estimation flags, definitions and statement boundaries preserved.
- [ ] Source publication time and revision convention validated.
- [ ] Schema drift, HTML-instead-of-JSON, empty results, partial files, duplicates,
      conflicting revisions, rate limits and timeouts covered by tests.
- [ ] Correct source-specific policy enabled; the example policy remains deny-all.
- [ ] Source-specific hypothesis configured; do not relabel real rows to fit fixtures.
- [ ] `as_of()` replay verified; model proposals cannot rewrite historical evidence.
- [ ] Supervision, alerts, checkpoint recovery and retention configured.
- [ ] Small-batch or streaming behavior tested with measured peak memory;
      text extracts remain traceable to unchanged original payloads.

Until these checks are complete, call the integration **planned** or **experimental**,
not live, production-ready or historically complete. Requirement scores measure
implemented checks; they do not certify economic truth or erase conflicting evidence.
