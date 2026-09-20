# Synthetic requirement-score example

These examples exercise the India–Bangladesh evaluator's intake requirements,
not actual copper-market data. Copper remains the first research case and
aluminum the second planned case.

## First valid synthetic inventory observation

| Requirement | Score | Outcome |
| --- | ---: | --- |
| Canonical schema | 100 | PASS |
| Provenance fields present | 100 | PASS |
| Source/series allowlisted | 100 | PASS |
| Metal matches policy | 100 | PASS |
| Geography matches policy | 100 | PASS |
| Unit matches policy | 100 | PASS |
| Definition matches policy | 100 | PASS |
| Reported quality usable | 100 | PASS |
| Freshness within policy | 100 | PASS |
| Revision integrity | 100 | PASS |
| Relative-change guard | null | NOT_ASSESSED: no earlier baseline |
| Independent source authentication | null | NOT_ASSESSED: not provided by file intake |

Requirements score: **83.33 / 100**. Assessed pass rate: **100%**.
Assessment coverage: **83.33%**. Disposition: `ELIGIBLE_FOR_INTAKE`.
This does not assert that the quantity is true or the upstream provider authenticated.

## A high score can still mean quarantine

For a later observation, suppose the relative-change guard passes but geography
fails. Ten requirements still pass out of twelve, so the score remains **83.33**.
Eleven requirements were assessed, yielding **90.91%** assessed pass rate and
**91.67%** coverage.

Disposition: **QUARANTINE**. Mandatory failure: `geography`.
No high total, LLM verdict, or improvement in another requirement can waive this
failure. The archive is not updated with the rejected observation.

The examples are covered by `tests/test_quality.py`. Requirement scoring has no
authority to rewrite supporting or weakening economic evidence; material conflict
still yields `INCONCLUSIVE`.
