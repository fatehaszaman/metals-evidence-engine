# Engineering skills in service of research

The project connects software engineering and infrastructure to a specific research
need: evaluate explicit hypotheses using only evidence available at a cutoff,
without hiding contradictions or overstating data quality. The scope remains
India and Bangladesh, copper first and aluminum second, relevant to cable,
conductor, power and industrial supply chains.

## One coherent responsibility for each skill

| Skill | Implemented responsibility | Research benefit | Boundary |
| --- | --- | --- | --- |
| Python / software engineering | Typed observations, deterministic validation, exact-decimal spreads, adversarial tests and CLI | Traceable transformations and explicit failures | Tests do not validate an economic hypothesis |
| SQL / SQLite | Append-only observations, delivery/review/score history and separate collector receipts | Reconstruct what was locally known and retain revisions | Database triggers are not a tamper-proof external audit service |
| Infrastructure engineering | Fixed-host API requests, bounded reads, socket timeout, failure receipts, content-addressed storage and reproducible CI | Make collection failures and provenance inspectable | No deployed scheduler, alerting system or production reliability claim |
| Bash / terminal workflows | Repeatable commands for collection, testing, build and replay | Reproduce the same work without manual dashboard steps | No installed Bash scheduler or hidden retry loop |
| LLM integration | Advisory structured reviews with exact source quotes and retained proposals | Assist investigation of messy extraction | Cannot auto-correct, approve data or resolve economic conflict |
| Research design | Explicit hypothesis rules, cutoff reconstruction, separate confidence and quality | Preserve limits of the available evidence | Material conflict remains `INCONCLUSIVE` |

Java is an optional future collector choice if a provider or operational constraint
justifies it. This repository contains no Java collector, and language breadth is
not presented as a substitute for working, reproducible code.

## Preserved original milestone

The original working synthetic-data version was committed at
[`9bbd4bcf60a9c346f9723e1b5475915adf2b89d6`](https://github.com/fatehaszaman/metals-evidence-engine/commit/9bbd4bcf60a9c346f9723e1b5475915adf2b89d6).
Its recorded local verification was **86 passing tests with 99.28% coverage**.
These are historical milestone numbers, not the current test count.
The original [GitHub Actions run](https://github.com/fatehaszaman/metals-evidence-engine/actions/runs/35519611213)
passed the Python 3.11, 3.12 and 3.13 matrix, lint, formatting, replay audit and builds.

The baseline implemented:

- **Point-in-time archive:** original payloads, revisions, publication times and
  receipt times.
- **`as_of()` reconstruction:** future observations and later revisions excluded
  from an earlier cutoff.
- **Contract spreads:** exact-decimal calculations with traceable inputs.
- **Evidence evaluation:** material contradictions produce `INCONCLUSIVE`.
- **Reproducible cases:** conflicts, revisions, staleness and definition changes.

That milestone was a synthetic first version, not a live market-data system.
Subsequent regional documentation, guarded intake, quality scoring and advisory
review did not remove those boundaries. The repository remains private and
development commits use the owner's configured Git identity; no public release
has been authorized.

## Current extension and its evidence

The experimental Comtrade collector adds actual network collection, not a new
market-state score. Its [technical smoke-test record](../examples/comtrade-collection-smoke.json)
documents the successful transport checks and unresolved metadata without
committing raw trade values. CI uses synthetic transport fixtures, separate from
this dated network check.

On the local Python 3.11 validation run for this extension, **241 tests passed with
99.28% coverage**. Coverage measures code exercised, not source correctness,
economic accuracy, full provider coverage or production readiness.
Use the latest [repository CI runs](https://github.com/fatehaszaman/metals-evidence-engine/actions)
to verify subsequent commit results rather than treating a historical count as current.

The new collector never imports observations into the canonical archive. Publication
time, complete coverage and revision semantics remain unresolved; API rows cannot
silently enter a historical hypothesis report. The original point-in-time,
exact-decimal, replay and contradiction tests remain part of the full test suite.

## Accurate project description

> I use software and infrastructure engineering to make research evidence
> reproducible and auditable. This project preserves source bytes and receipt
> history, validates explicit data requirements, reconstructs point-in-time
> evidence, and keeps conflicting observations visible instead of forcing a
> directional conclusion. Its evaluator currently uses synthetic case studies;
> the first real API collector stages data in quarantine pending source validation.

This is research infrastructure, not a trading strategy, a price-prediction model
or a live market-data platform. No employer branding or claim about an employer's
internal methodology is needed to explain the engineering contribution.
