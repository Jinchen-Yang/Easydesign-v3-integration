# Site context boundary checkpoint — 2026-09-12

Status: architecture review and initial implementation complete; targeted boundary tests pass.
Broader regression and new GPCR live acceptance remain pending.
Resume baseline: `522a519037b5a332b6946899b37210292dc2351e`.
The user explicitly resumed autonomous work with this checkpoint. Preserve accepted Cases
1/3/4/5 and all milestone tags. Case 2 remains unaccepted; Phase 2 is not frozen.

## Updated authority and scope

The user's 2026-09-12 instruction supersedes the historical 60,000-character hard limit.
`max_input_chars=60000` becomes a soft working-set target. Evaluate a separately configurable
100,000-character hard guard with an additional model-profile-aware token check. Report both
metrics and any target overruns honestly. This changes an engineering acceptance condition,
not a protein-science oracle, source input, deterministic algorithm or Scientific Gate.

Stop adding local compression, alias and pointer mechanisms to fit the old limit. The desired
boundary is Evidence Research → durable evidence → compact trusted Site Evidence Dossier →
fresh isolated Site synthesis → SiteIntent → independent Judge → existing Gate 2.

Pro and its current reasoning configuration remain a recorded local debugging choice. They
are not a product-default decision. After the boundary, prompt, evidence, tools and runtime are
fixed, any model-selection experiment must compare Flash and Pro on the same Golden Case.
Record scientific pass/fail, tool/recovery errors, no-progress loops, calls, context, latency
and usage/cost (unavailable pricing must remain unavailable). A Pro pass alone establishes
neither Flash acceptance nor a product policy. No provider escalation as a context repair.

## Source review

Read-only reference checkouts under the user-specified `agent-framework-study` directory:

| Reference | Inspected revision | Relevant implementation |
| --- | --- | --- |
| DeepAgents | `481773caed336c86034e1c72b4988e7e93968610` | `libs/deepagents/deepagents/middleware/summarization.py`, `middleware/subagents.py`, `graph.py` |
| LangGraph | `e539ac122f4126f6dd850581c1494948cf620e31` | `libs/langgraph/langgraph/graph/message.py`; existing compiled graph/checkpoint composition |
| LangChain | `60357692c76651a7cd6153496a24658fa355bdcc` | `libs/langchain_v1/langchain/agents/middleware/summarization.py`; existing ToolStrategy |
| CatMaster | `5246749f8d20cce144faa12f4535a5c9a4de4427` | `catmaster/specialists/runtime.py`, `runtime/literature/corpus.py`, `runtime/tool_output_adapter.py` |

Installed public APIs were checked separately: DeepAgents 0.7.13, LangGraph 1.2.11,
LangChain 1.4.0 and langchain-core 1.6.2. No dependency upgrade is required for this design.

DeepAgents summarization keeps original message state and records a private summarization
event, offloads evicted history through the configured backend, preserves recent tool
transactions, and supports model-aware thresholds and overflow recovery. Its public middleware
can replace the default slot. LangChain's base summarizer instead replaces message state with
RemoveMessage; prefer DeepAgents here because raw trace preservation matters. Summaries remain
fallible working memory, never source evidence or hard-fact authority. Summary model calls
must participate in the same budget and telemetry as ordinary calls.

DeepAgents isolated subagents receive a fresh task message and return a final result, not the
parent's full transcript. CompiledSubAgent supports composition using the existing LangGraph
checkpoint runtime. LangGraph message reducers do not themselves create a scientific boundary:
the synthesis input must be explicitly constructed from the dossier, without research messages
or a research summarization event. Do not introduce another scheduler or checkpoint store.

CatMaster separates literature coordination from bounded workers and durable corpus/results.
Its corpus returns partial locators, explicit scope and continuation cursors; source acquisition,
passage reading and citation finalization remain distinct. Its tool adapter separates concise
observations from large retained artifacts. Adopt these boundaries, not its unrelated research
graph, execution infrastructure or additional storage systems.

## Responsibility and simplification

| Current surface | Keep in EasyDesign | Delegate or simplify |
| --- | --- | --- |
| `harness.py` | Role permissions, trusted task/revision binding, shared budgets, source/contract preflight, independent Judge, human Gates | Research transcript summarization and tool-history handling belong to DeepAgents. Remove Site's dependency on whole-history fitting and exact-value history pointers. Compose research and fresh synthesis within the existing graph. |
| `evidence_output.py` | Verified artifact access, project confinement, source-specific scientific projections and explicit partial reads | Do not grow generic message compression, alias navigation or repeated-value encodings. Synthesis consumes the dossier directly, not result navigation history. |
| `evidence_research.py` | Explicit source selection, immutable source/corpus refs, primary eligibility, access failures, exact passage citations, protein context analyses | Keep research out of final synthesis. Acquisition receipt history and current retrieval need must be distinct; they are not scientific conclusions. |

Research submits a bounded selection of source cards and candidate patches plus explicitly
non-authoritative notes. Runtime revalidates current Target binding and exact sources, then
assembles the dossier from existing evidence artifacts: trusted target/mapping/state facts,
selected exact passages, deterministic candidate evaluations, search/access outcomes,
limitations and alternatives. Model notes are labeled opinions. Missing or contradictory
evidence cannot disappear merely because it was omitted by the researcher. The dossier is a
derived artifact in the existing project store, not a second corpus or hard-fact producer.

Fresh synthesis receives the original goal, current trusted revision and dossier, with the
typed SiteIntent submission surface. It does not inherit research/tool/thinking history.
Existing source, citation, mapping and hard-fact checks still validate its output. Independent
Judge continues to receive its own verified scientific snapshot, not a research summary.

## Verification required before acceptance

Test actual compiled isolation, retained raw history, ordinary and summary call accounting,
soft-target overrun versus hard rejection, source/project/target binding, exact passages,
counterevidence/access failures, unchanged Judge authority and interrupted-resume behavior.
Run GPCR Case 2 with real sources/model and independently review its scientific content.
Then full regression; freeze Phase 2 only when all five accepted cases and parity checks pass.
Continue original Phase 3/4 micro-compute assignment without resetting valid earlier work.

This checkpoint does not claim an implementation, new Golden PASS or Phase closure.
