# Synthetic case studies

These generated reports are engineering demonstrations, not reconstructions of
actual copper-market conditions. Every observation, contract ID, and declared
historical rule-effective date is synthetic.

## Reproduce

```bash
uv run metals-evidence demo > examples/conflict.md
uv run metals-evidence demo --format json > examples/conflict.json
uv run metals-evidence demo --as-of 2025-09-20T09:00:00Z > examples/revision.md
uv run metals-evidence demo --scenario definition-break > examples/definition-break.md
uv run metals-evidence demo --scenario stale > examples/stale.md
uv run metals-evidence audit > examples/replay-audit.json
```

## What to inspect

- **Conflict:** the nearby spread changes from -100 to +200 CNY/tonne while
  visible inventory rises from 100,000 to 120,000 tonnes. Output is INCONCLUSIVE.
- **Revision:** a later inventory revision changes the latest stock to 90,000
  tonnes. Inventory evidence flips, but production still weakens the hypothesis,
  so the aggregate remains INCONCLUSIVE; the earlier report is unchanged.
- **Definition break:** the latest stock coverage definition changes. Inventory
  direction is withheld instead of comparing unlike definitions.
- **Staleness:** a cutoff months after the final release produces
  INSUFFICIENT_EVIDENCE, not a recycled directional result.
- **Replay:** full-archive reconstruction equals incremental ingestion at every
  receipt-time checkpoint, including late data and the revision.

The JSON report exposes all parent IDs, observed values for curve constructs,
rule content, snapshot IDs, and hashes. Raw envelopes can be regenerated with
`metals-evidence fixtures` and matched by their deterministic content IDs.
