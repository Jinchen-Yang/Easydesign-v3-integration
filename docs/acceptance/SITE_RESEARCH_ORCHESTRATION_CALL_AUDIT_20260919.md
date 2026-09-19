# Site Research orchestration call audit — R11–R16

## Scope and authority

This audit was reconstructed read-only from each fresh NK2R project's
`metadata/agent.sqlite` plus the accepted repair ledger. It covers the Site execution after
Gate 1. Provider usage is taken from persisted response metadata; an interrupted request has no
response usage. Framework summaries are auxiliary context-maintenance calls: they cost provider
tokens and wall time but do not learn scientific evidence.

Authoritative implementation baseline:

- worktree: `/data/easydesign-worktrees/figure2-ab-20260918`
- branch: `codex/site-intelligence-latency-20260919`
- start commit: `753af0f6e9089fadc469b5ca59ee8ad0fdc57eaa`

## Aggregate finding

| Attempt | Scientific calls | Auxiliary summaries | Provider calls | Scientific input/output tokens | Summary input/output tokens | Max admitted request | Site provider wall time | Outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| R11 | 12 | 1 | 13 | 131,440 / 29,568 | 9,105 / 1,024 | 73,899 chars | 305.68 s | synthesis exhausted output; superseded |
| R12 | 4 | 1 | 5 | 50,343 / 4,713 | 16,665 / 1,024 | 82,868 chars | 69.35 s | reading budget ended after discovery |
| R13 | 9 | 2 | 11 | 121,305 / 21,030 | 28,324 / 2,048 | 94,537 chars | 258.83 s | Gate 2 completed |
| R14 | 5 | 1 | 6 | 47,605 / 7,160 | 16,188 / 1,024 | 82,482 chars | 89.57 s | summary forgot kernel delivery |
| R15 | 9 | 1 | 10 | 105,280 / 12,786 | 15,186 / 1,024 | 87,474 chars | 143.57 s | finalization replayed old actions |
| R16 | 5 | 1 | 6 | 67,876 / 8,964 | 15,971 / 1,024 | 82,081 chars admitted | 119.11 s | next summary input reached 101,965 chars |

The table separates model calls that can change scientific state from summaries. Before this
consolidation both categories consumed the same persisted `model-call` budget. R13 therefore
reached eight counted Research calls after six scientific calls and two summaries, even though
the summaries acquired no evidence.

## Call-by-call classification

The persisted traces support six recurring call classes:

| Class | Scientific? | New evidence? | Runtime substitute? | Finding |
|---|---|---|---|---|
| Initial Site context + GPCRdb acquisition | yes | yes | acquisition remains a tool; target/site facts are Runtime-owned | Necessary bounded start |
| `analyze_receptor_context` after GPCRdb | no new interpretation | no; kernel already exists | yes, deterministic Runtime projection | One avoidable provider round trip per successful navigation, repeated in R14 |
| Literature discovery/acquisition/retrieval | yes | often | no for interpretation; Runtime can normalize transport/results | Necessary, but search leads must be read before ordinary sufficiency |
| Site fact/candidate evaluation | mixed | deterministic facts only | Runtime can project exact facts; LLM still compares implications | Repeated full projections inflated context |
| Framework summary | auxiliary | no | framework machinery | Must count cost but not consume the scientific-call allowance |
| Typed handoff finalization | serialization | no new evidence | fresh Runtime-built packet can replace transcript transformation | R11 needed three attempts; R15 copied withdrawn actions |

### R11

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1–7 | context, GPCRdb/source navigation and reading | 38,118–73,899 chars | 7 calls | 75.09 s | evidence and deterministic facts accumulated, with repeated navigation |
| 8 | framework summary | 9,105 tokens | 1,024 tokens | 9.80 s | none; context maintenance |
| 9–11 | typed handoff + two schema/citation repairs | 32,630–54,790 chars | 5,725 tokens | 52.98 s | only call 11 committed a valid handoff |
| 12 | Site synthesis | 31,909 chars | 16,384 tokens | 167.82 s | no submission; output exhausted |
| 13 | synthesis recovery | 32,700 chars | interrupted | — | no state change |

R11 proved that compact synthesis and kernel existence were separate concerns. Calls 9–10 existed
only for serialization repair. Call 12 motivated non-thinking forced Site synthesis.

### R12

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1 | Site context + GPCRdb | 38,203 chars | 392 tokens | 6.21 s | structured receptor source and kernel created |
| 2 | model-selected kernel read | 52,005 chars | 237 tokens | 3.76 s | no new fact; delivered existing kernel |
| 3 | three literature searches | 82,868 chars | 2,386 tokens | 27.80 s | discovery leads only |
| 4 | framework summary | 16,665 tokens | 1,024 tokens | 13.40 s | none |
| 5 | forced handoff | 34,023 chars | 1,698 tokens | 18.18 s | bounded handoff; strongest leads had not been read |

R12 shows that an operation limit is a guard, not evidence sufficiency.

### R13

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1–5 | initial context, result navigation, Site facts and focused reading | 38,203–94,537 chars | 11,011 tokens | 117.82 s | evidence accumulated; generic navigation preceded kernel delivery |
| 6 | framework summary | 12,660 tokens | 1,024 tokens | 12.91 s | none |
| 7 | model-selected kernel read | 43,452 chars | 1,200 tokens | 14.35 s | no new fact; delivered existing kernel |
| 8 | focused reads/searches | 77,921 chars | 6,146 tokens | 68.36 s | decision-relevant evidence acquired/read |
| 9 | framework summary | 15,664 tokens | 1,024 tokens | 11.06 s | none |
| 10 | typed handoff | 33,356 chars | 1,544 tokens | 18.13 s | valid first submission |
| 11 | compact Site synthesis | 29,945 chars | 1,129 tokens | 16.20 s | valid ranked A/B/C decision |

R13 is the positive scientific baseline. Its synthesis path should remain unchanged.

### R14

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1 | Site context + GPCRdb | 38,203 chars | 395 tokens | 4.46 s | source and kernel created |
| 2 | kernel read | 41,673 chars | 130 tokens | 2.71 s | delivered existing kernel |
| 3 | focused searches | 82,482 chars | 5,146 tokens | 55.82 s | discovery/evidence work |
| 4 | framework summary | 16,188 tokens | 1,024 tokens | 11.57 s | none; live delivery message removed |
| 5 | repeated kernel read | 33,677 chars | 1,489 tokens | 15.02 s | no new fact; duplicate projection |
| 6 | next research call | 80,628 chars | interrupted | — | no state change |

R14 proves that transcript presence cannot be the authority for kernel delivery.

### R15

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1–5 | context, GPCRdb, kernel and four-source batch | 38,203–87,474 chars | 9,377 tokens | 98.49 s | evidence accumulated; kernel read remained a navigation call |
| 6 | framework summary | 15,186 tokens | 1,024 tokens | 11.37 s | none |
| 7 | selection and additional searches | 44,355 chars | 2,516 tokens | 21.93 s | evidence working set changed |
| 8–10 | forced finalization | 49,296–50,723 chars | 893 tokens | 11.78 s | none; copied withdrawn retrieval/acquisition actions |

R15 shows that hiding action tools is insufficient while their call structures remain in the
model-visible finalization context.

### R16

| # | Purpose | Input | Output | Wall | Scientific-state effect |
|---:|---|---:|---:|---:|---|
| 1 | Site context + GPCRdb | 38,203 chars | 268 tokens | 3.88 s | source and kernel created |
| 2 | kernel read | 41,264 chars | 149 tokens | 2.77 s | delivered existing kernel |
| 3 | focused searches | 82,081 chars | 3,225 tokens | 39.26 s | discovery/evidence work |
| 4 | framework summary | 15,971 tokens | 1,024 tokens | 14.18 s | none |
| 5 | acquisition, Site facts and candidate evaluation | 43,661 chars | 2,517 tokens | 27.45 s | evidence and deterministic evaluation added |
| 6 | retrieval, three evaluations/searches | 72,905 chars | 2,805 tokens | 31.57 s | a complete large tool batch followed |
| 7 | attempted framework summary | 101,965 chars | blocked before provider | — | hard guard prevented transmission |

R16 proves that reactive summarization cannot provide admission control for the batch that causes
the overflow.

## Architectural conclusion

The science-producing calls are not the common failure. Failures cluster around delivery,
bookkeeping, context maintenance and serialization:

1. a deterministic kernel required a model-selected read;
2. delivery authority was inferred from transient messages;
3. summaries consumed the scientific call allowance;
4. finalization inherited action-call structures;
5. tool results were admitted before projected next-request capacity was checked.

The repair therefore keeps GPCRdb, literature reading, exact mapping, candidate evaluation,
SiteResearchHandoff validation and R13 Site synthesis intact. It moves kernel projection,
lifecycle milestones, finalization packet construction, capacity admission and call-category
accounting into deterministic Runtime code.
