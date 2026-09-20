# Release checklist

Private development does not imply production readiness. Public visibility is a
separate owner decision, and no build command changes repository visibility.

## Engineering gates

- Run lint, formatting, tests with coverage, and replay audit.
- Verify hosted GitHub Actions on every supported Python version.
- Review generated reports and their explicit synthetic-data labels.
- Confirm package build and clean-checkout instructions work.
- Check for credentials, personal information, proprietary data, and generated databases.
- Preserve the owner's Git author and committer identity.

## Real-data gates still open

- Select one public source with documented access and redistribution rights.
- Implement and test its adapter rather than calling fixtures “live.”
- Document actual vintage coverage and local collection start.
- Validate timezone, units, definition, contract-universe completeness, and revisions.
- Write a bounded, source-cited real-data case study.
- Stress-test economic assumptions and threshold sensitivity separately from code.
- Decide whether and how to add a license before public release.
- Obtain the owner's explicit decision to make the repository public.

## Intentionally out of scope

No strategy, alpha, portfolio, performance, employer-methodology, or production-feed
claim belongs in this release. Aluminum expansion and additional feature categories
remain deferred until the copper data path is credible end to end.
