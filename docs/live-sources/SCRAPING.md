# Actual source inspection and scraping runbook

APIs and official downloads take precedence over HTML scraping. This document
records what was actually inspected on 2026-09-20 and separates those observations
from parser work that remains to be implemented.

## What actually ran

Public pages were retrieved using `pplx_sdk.content.fetch`; returned HTML was
inspected with Python's standard-library `HTMLParser` for form methods/actions,
input names and PDF hyperlinks. No form was submitted, no user credentials were
used, and no numeric economic observations were accepted into the engine.
The probe was run in the development environment, not installed as a repository
collector. SDK-extracted content is not an archive of original HTTP response bytes.

- **TradeStat interface:** page and HTML retrieval succeeded for the
  [country-wise all-commodities export form](https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export).
- **TradeStat older route:** the request to the
  [older EIDB landing page](https://tradestat.commerce.gov.in/eidb/Default.asp)
  returned `http_code_client_error` in this check. That is a failed retrieval,
  not proof the provider is permanently unavailable.
- **NBR listing:** page and HTML retrieval succeeded and exposed import-statement
  PDF hyperlinks on the [customs publications page](https://nbr.gov.bd/publications/customs/eng).
- **NBR document:** fetching the linked
  [May 2026 IM-4 statement](https://nbr.gov.bd/uploads/publications/Import_Statement-IM-4-Commecial(May,2026).pdf)
  returned `fetcher_error`. No PDF table or commodity row was extracted from it.
- **API metadata:** the
  [UN Comtrade field dictionary](https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json)
  was read successfully. A dictionary response is not a trade-data response.
- **Feed documentation:** [MCX datafeed information](https://www.mcxindia.com/technology/datafeed)
  was read successfully. No licensed feed was accessed.

## India TradeStat form

The inspected HTML uses a POST action pointing to the same country-wise export
route and includes the following exact control names
([TradeStat interface](https://tradestat.commerce.gov.in/meidb/country_wise_all_commodities_export)):

```text
_token
cwcexddMonth
cwcexddYear
cwcexallcount
cwcexddCommodityLevel
cwcexddReportVal
cwcexddReportYear
```

These are observed control names, not a guaranteed stable API contract. Option
values and returned report schemas were not validated. Never guess the meaning
of numeric option values or turn the hidden token into a committed configuration.

### Implementation procedure

1. Confirm current access terms and whether an official export/API is available.
2. If permitted, open the form in an authorized session and obtain current form
   controls/tokens through the normal workflow. Stop at access challenges.
3. Select one explicit country/partner, period, commodity level and measure.
   Store both the selected labels and their transmitted values.
4. Request the official report/download using the normal form. Do not infer
   an undocumented JSON endpoint merely from a form action.
5. Archive the response/file and the source's final/revised labels before parsing.
6. Validate the full headers, row counts, unit labels, pagination and report totals
   where applicable. A changed heading or empty table is an extraction failure,
   not a zero trade flow.
7. Parse exact decimals, preserving product codes as strings and keeping all
   grouping dimensions in the series identity.
8. Leave the candidate quarantined until units, publication evidence, coverage
   and a source-revision convention satisfy the engine's mandatory checks.

No POST payload, downloaded table or stable CSS selector is supplied as tested
here because none was exercised. An export-form scrape would not by itself
establish import coverage, bilateral symmetry or historical vintage completeness.

## Bangladesh NBR document discovery

The inspected listing contained these exact links
([customs publications](https://nbr.gov.bd/publications/customs/eng)):

- [IM-4-Commecial, May 2026](https://nbr.gov.bd/uploads/publications/Import_Statement-IM-4-Commecial(May,2026).pdf)
- [IM-7-Bond, May 2026](https://nbr.gov.bd/uploads/publications/Import_Statement-IM-7-Bond(May,2026).pdf)

The listing also contains unrelated PDFs and unrelated survey forms, so collecting
every PDF or submitting the first form would be incorrect
([inspected listing](https://nbr.gov.bd/publications/customs/eng)).
Scope discovery to the customs publication entries and allowlisted import-statement
types. Keep the document's actual URL and visible title rather than constructing
future filenames.

### Proposed document parser

```text
fetch permitted publication listing
preserve listing bytes and local receipt
identify the target statement entries, their visible titles and publication dates
resolve each observed PDF link against the source page
reject off-host links and unrelated statement types

for each new or changed document:
    retrieve with bounded size/timeout; archive original bytes before parsing
    on access error or unavailable file: record failure, not an empty dataset
    verify file signature and content type; reject HTML error pages
    preserve file hash, listing publication evidence and report-period evidence
    extract table cells with page/table/row/column locations
    validate headers, repeated page headings, column alignment and page completeness
    retain wrapped descriptions, blank cells, footnotes and explicit missing markers
    preserve statement type and commodity-code hierarchy
    normalize only explicitly supported units using exact, logged conversions
    if OCR/LLM was involved: mark candidate unverified and require human review
    send supported canonical candidates through the mandatory intake gates
```

This is implementation pseudocode, not an installed PDF scraper. Because the
selected PDF fetch failed, this guide deliberately does not claim verified PDF
column headers, row counts, copper coverage or a successful parsing result.
Filename dates are hints, not substitutes for verified publication metadata.

## API and scraping failures use the same controls

Keep an append-only collection log with source URL/endpoint, non-secret request
parameters, attempt/receipt time, parser version, payload hash when obtained,
result state and reason. Distinguish `FETCH_FAILED`, `ACCESS_BLOCKED`, `RATE_LIMITED`,
`SCHEMA_CHANGED`, `PARTIAL_RESPONSE`, `NO_DATA_REPORTED` and `CANDIDATE_READY`.
These names specify proposed adapter states; they are not new engine enums.

Never turn an empty response into zero, treat a capped preview as complete, retry
around access restrictions, or use an LLM to invent missing rows. When a source
changes a published document, preserve both payloads and investigate the version
change before assigning any canonical revision.

Retain source-local dates and timezones alongside normalized timestamps. If only
a publication date is known, do not invent an exact intraday release time.
Document a conservative policy or quarantine; never substitute the reporting
period for publication or local receipt.

## Link validation and deduplication contract

This is a proposed source-adapter contract, not an implemented link checker.
Python or a future Java collector should use the same test cases and produce the
same discovery records; SQL should enforce identities and preserve version history.
Bash should invoke the tested collector and expose its exit status rather than
perform fragile HTML parsing with shell regular expressions.

```text
discover only links relevant to the configured official source
resolve relative links against the observed page URL
retain the original URL for retrieval; never rewrite signed request URLs
construct a separate conservative discovery key
validate scheme, official-host allowlist, redirect targets and content type
record the discovered source page, anchor/title context and retrieval outcome

if discovery key already exists:
    avoid redundant discovery work, but preserve the new discovery/receipt event

if retrieval is permitted and succeeds:
    archive bytes and compute SHA-256
    if identical content already exists:
        reuse content storage, retaining source URL and receipt lineage
    else:
        preserve a new content version, even if the URL is unchanged
        verify title, country, commodity, period, units and expected structure
        parse into candidates; validate and score; quarantine failures
```

Conservative normalization may lowercase the host and remove a URL fragment in
the comparison key. Preserve path case, report identifiers, country/product/period
query selections and any parameters that can alter the response. Do not strip all
query strings, assume reordered signed parameters are safe, or drop “duplicate”
country reports merely because their titles match.

Reject off-allowlist redirects, non-HTTPS targets, embedded user credentials,
private-network destinations and unexpected file signatures before parsing.
Allowlisting is a source-selection control, not proof a server or payload is authentic.
Respect access controls and stop rather than trying alternate encodings to bypass them.
Do not store secret-bearing signed URLs in ordinary logs; retain safe identifiers
and keep any necessary protected retrieval details in access-controlled storage.

Useful proposed SQL identities are a source plus discovery key for link discovery,
SHA-256 for immutable content storage, and a separate receipt-event ID for each
authorized fetch. Do not put a unique constraint on URL alone for all releases.
The current intake archive deduplicates identical delivery bytes and does **not**
yet maintain this separate receipt-event registry.

Minimum adapter tests should cover relative links, duplicate links, redirects,
query parameters that change report identity, unchanged bytes at multiple URLs,
revised bytes at the same URL, signed URLs, HTML error pages returned as PDFs,
empty downloads, truncated responses and schema changes. Verified link identity
is a prerequisite for parsing, never a substitute for row-level data checks.

Store discovered-link records and parser audit logs as bounded JSONL records and
human-readable extracted passages as TXT where useful. Keep the original HTML/PDF
and its hash separately; extraction must not discard tables, footnotes, units or
source locations. Follow the [text-first storage policy](README.md#text-first-storage-and-bounded-memory);
do not label the existing whole-delivery intake as a streaming implementation.

## Next executable integration

Start with one narrow, authorized UN Comtrade API query and its release metadata,
not a broad scrape across every source. Then implement and test its source-specific
adapter before enabling local delivery intake. The existing
[API-first guide](README.md) and [intake controls](../data-intake.md) define that
handoff; neither claims a connected or continuously running collector.
