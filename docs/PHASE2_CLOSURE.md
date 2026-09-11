# Phase 2 acceptance — Phase 2.2d review, 2026-09-12

**FAIL / NOT FROZEN. Phase 3 and Phase 4 have not started.**

Trusted runtime owns scientific facts; Specialists own scientific interpretation; Evidence Judge
owns independent critique; Scientists own consequential decisions. The current implementation
uses native typed submissions for all consequential specialists, runtime Target fact envelopes,
bounded output corrections and stable project evidence with explicit current binding.
See `V3_AGENT_CONTRACT_OWNERSHIP.md` for mechanism and ownership details.

The real deepseek-flash run did not reach those acceptance boundaries. It made 32 model calls
(Coordinator 2/Target 30); Target repeatedly polled no-bound-job, read its Skill and not-prepared
Target evidence, but never acquired sources, proposed canonical identity or called prepare.
The next model call was correctly blocked at the unchanged per-execution limit32. This is an
Agent no-progress failure, not evidence of a budget accounting defect. No scientific job,
Judge, typed final assessment, Gate card, approval or authoritative Target Bundle was produced.

Identity Trap FAIL; the other four required Golden paths NOT RUN after critical stop.
Canonical binding continuity, typed submission recovery and scientific consistency have offline
regression coverage but were NOT EXERCISED by this real run. Context end-to-end remains unaccepted:
0 acquired raw characters/corpus/cards; peak15011 system+message chars,23925 including schemas.
The partial top-level progress showed only2calls; persistent SQLite proves32 and is authoritative.

The full suite also exposes a focused-card delivery regression: the recovered source yields two
cards, but new binding metadata makes their page6,091 characters; the unchanged6,000-character
adapter limit sends only a narrower-field instruction and delivers zero cards. Full source/page
bytes remain intact. This separate blocker is retained without post-STOP implementation.

Final integration007: **774 passed, 1 failed, 11 skipped**;786 collected,1152.498 s in JUnit.
Agent unit159PASS/1FAIL; new Phase 2.2d contract/binding22PASS; fixed Golden oracles6PASS;
multi-turn/resume/ownership9PASS; source/projection recovery16PASS/1FAIL. Repository structure,
vendored assets, compileall, Ruff and mypy185 source files PASS. The failure is
`test_harness_repairs_selection_then_acquires_and_reads_durable_source` at line 185: no post-adapter
`focused_cards_in_model_result > 0`. Eleven skips are3 opt-in live integration tests and8 PyMOL
integration tests lacking the separate environment. The separate real Golden attempt failed;
a skipped live test does not count as a live PASS.

See `PHASE22D_AGENT_CONTRACT_CLOSURE.md` for all13 closure areas, actual metrics and remaining
blocker. The pre-frozen Golden spec/oracle remain unchanged. Consequential real acceptance rows
remain PARTIAL. Previous PHASE22C/22B/22/21 reports are historical evidence.

All 187 non-Agent source files match baseline4df3b2b; v2 stays at c93da74660639c095d3de252cddb88a00fd3671d.
No new frozen tag, Phase 3/4, storage/workflow engine, Workbench or compute expansion. Only final
reporting, completion of the already running offline suite and full repository packaging follow
this stop. Further implementation/live validation requires explicit user resumption.
