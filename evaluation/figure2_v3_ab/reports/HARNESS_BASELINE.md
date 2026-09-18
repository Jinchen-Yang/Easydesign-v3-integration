# Harness baseline before Figure 2A/B freeze

The immutable NK2R Attempt005 Gate 2 event range (after sequence 204 through 570) is the
pre-patch efficiency baseline. The collected trace is bound to SHA-256 digest
`ba5ecd1ea723108d36d97de7e89d79801349fac3ea301c55b029bb7f104a781d`.

| Measure | Observed | Pre-freeze target | Result |
|---|---:|---:|---|
| Model calls | 52 | <= 30 | FAIL |
| Site-role model calls | 50 | <= 24 | FAIL |
| Framework summaries | 13 | <= 2 | FAIL |
| Framework summary output tokens | 94,457 | <= 2,048 | FAIL |
| Tool calls | 96 | <= 60 | FAIL |
| `read_file` calls | 16 | <= 8 | FAIL |
| `read_evidence_result` calls | 36 | <= 18 | FAIL |
| Maximum input characters including schemas | 86,016 | <= 90,000 | PASS |
| Hard context guard events | 0 | 0 | PASS |

This baseline shows repeated, expensive memory summaries rather than a hard-context overflow.
It does not establish any Figure 2 scientific comparison and is not a post-patch result.
Scientific correctness is evaluated separately from efficiency.
