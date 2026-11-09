# Lessons

Mistakes found in this project, kept visible with their fixes.

## Series identity did not include the metal

**What happened.** The archive identified a series only by its source and series
name. Copper and aluminum both used a series named `inventory`, so adding the
aluminum case exposed two failure modes. An append with the same event time and
revision failed with a uniqueness error. Worse, `as_of()` ranked revisions within
`(source, series, event_time)` across both metals, so an aluminum revision could
silently replace a copper observation in a point-in-time snapshot.

**Fix.** Aluminum series now use their own names (`aluminum_inventory`,
`aluminum_primary_production` and so on), and the archive rejects any append that
would put two metals or two geographies in one `(source, series)`. A test covers
both checks. Copper series names and fixture records are unchanged.

**Why it matters.** The defect was found while building the second case, on
synthetic data only; no real observations were affected. A test suite with one
metal could not have caught it. Extending the system to a second case was what
made it possible to trust the series-identity design, rather than assuming it.
