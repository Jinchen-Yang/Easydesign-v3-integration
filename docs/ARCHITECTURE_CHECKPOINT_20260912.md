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
all retrieved exact passages, deterministic candidate evaluations, search/access outcomes,
limitations and alternatives. Model notes are labeled opinions. Missing or contradictory
evidence cannot disappear merely because it was omitted by the researcher. The dossier is a
derived artifact in the existing project store, not a second corpus or hard-fact producer.

Fresh synthesis receives the original goal, current trusted revision and dossier, with the
typed SiteIntent submission surface. It does not inherit research/tool/thinking history.
Existing source, citation, mapping and hard-fact checks still validate its output. Verified GPCR
kernel cards remain citable as non-primary computational context, preserving the original Site
contract; source acquisition receipts are not passage citations. Independent
Judge continues to receive its own verified scientific snapshot, not a research summary.

## Verification required before acceptance

Test actual compiled isolation, retained raw history, ordinary and summary call accounting,
soft-target overrun versus hard rejection, source/project/target binding, exact passages,
counterevidence/access failures, unchanged Judge authority and interrupted-resume behavior.
Run GPCR Case 2 with real sources/model and independently review its scientific content.
Then full regression; freeze Phase 2 only when all five accepted cases and parity checks pass.
Continue original Phase 3/4 micro-compute assignment without resetting valid earlier work.

This engineering checkpoint does not claim a new Golden PASS or Phase closure.


## Dossier v2 engineering follow-up

The first live handoff exposed a large dossier, despite correctly isolated research history.
Normalize shared residue facts using existing design labels and omit repeated cache/selection/
reference-control metadata from the model-facing passage view. Preserve exact source text,
evidence levels, access/scientific limitations and runtime source relation/relevance. Full
original artifacts and their verification remain in the existing store. Candidate hypotheses
and deterministic evaluations remain separate from evidence and each appears once.

Native summarization starts between the soft working target and independent hard guard;
60k alone does not require summarization. Research progress is read from existing evidence
snapshots, explicitly separating named-record acquisition, literature discovery and unresolved
material topics. No added scheduler, source store, history alias/pointer or scientific kernel.
Read-only replay reduced live172's dossier from 108,782 to 74,448 characters without changing
passage bytes or candidate evaluations. This does not fix its inadequate scientific research
or establish Case 2 acceptance. Fresh real validation and full regression remain required.


## Stable reads and dossier v3

Native summary eviction must not change a tool's advertised or executed argument contract.
Site exact-label reads now return one bounded complete patch of up to40labels, with no offset;
legacy internal bridge pagination is retained. Full facts are still persisted before projection.
Receptor candidate source identifiers explicitly use the source namespace; their numeric values
are not approved design labels. Remove repeated-value display pointers and use ordinary JSON.

The derived dossier reuses the existing fact table and keeps source-control refs in verified
durable artifacts rather than repeating them in every inventory/card. Exact focused passages,
adverse findings, scientific qualifiers, search outcomes and deterministic evaluations remain.
Runtime Gate1 resolution is explicitly separate from conditional scientific mapping and fallible
research notes. Read-only same-evidence replay of live173 reduces102,949→70,395characters while
preserving all44fact rows and all17passages exactly; expected first synthesis is89,123characters.
This neither repairs its flawed biological hypotheses nor supplies a Golden PASS. The native
framework summary prompt requests bounded working memory; no custom history compression is added.


## Standard Research stopping policy (175)

The next user-authorized step shifts research from taxonomy coverage to decision sufficiency.
See STANDARD_RESEARCH_POLICY.md. Use the existing Site Handoff to record a few decisive questions,
actual contradiction-search query IDs and a stopping rationale; no extra planner/agent/subsystem.
Relevant source queries can inform more than one indexed topic. The dossier remains a verified
scientific projection with original focused passages and hard facts; full source bodies remain
durable. Its research assessments and saturation claim are fallible opinions for the independent
Judge, which receives critical opposing citations even when final SiteIntent omits them.60ksoft/
100khard, framework memory/isolation, current local debug model and all frozen science remain.


###176: runtime candidate correspondence after live175

Live175 discovered relevant counterevidence but failed typed Handoff mapping before Dossier;
peak68296characters stayed within the existing100kguard. A candidate-specific exact approved
Target lookup now accompanies GPCR hypotheses, preserving source labels, canonical positions,
prepared design labels and every ambiguity/missingness qualification. It reuses the existing
Site fact-table view and original ArtifactRefs; the scientific kernel is unchanged. Blocked
Handoff diagnostics identify the offending candidate. Standard source pagination stops after
answering that candidate's question. No model/config change, new agent or message compression.
All previous accepted milestones remain. Full scientific Case2 acceptance is still required.
