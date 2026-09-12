# EasyDesign v3 consequential Agent contract ownership

Phase 2.2d implementation audit, baseline `4df3b2bd19f72a39f67ad40c3874b30323f0aafb`.
This is an ownership specification, not a declaration that real scientific acceptance passed.

Phase 2 final closure update (20260913, under validation): the authoritative scope is
`PHASE2_FINAL_ASSIGNMENT_20260912.md`. Stop after Phase 2 freeze; do not enter Phase 3.
Research remains agentic. Runtime assembles an immutable Dossier with stable candidate IDs,
exact authoritative membership/mapping and decision-scoped original evidence. A fresh LangChain
structured inference returns only `SiteDecision`: ID selection/comparison, recommendation,
scientific rationale, approach, risks and uncertainty. It cannot submit chains, residue arrays,
number conversions, SASA or regenerated evidence identities. Runtime hydrates the existing
SiteIntent from exact candidate definitions and validated research relations, then the separate
Evidence Judge critiques it. Source/fact checks remain mandatory. The saved original Dossier
retains the full candidate facts needed for hydration; the final inference receives a semantic
scientific projection, with no Research/tool history or duplicated metadata forms.

Decision-bound official passages and already-read primary publication passages are retained,
including uncited opposing experiments; remaining database pages/full acquisition bodies stay in
the existing durable store. The Judge receives the scoped passages independently of final
citation repetition. Research preferences, conclusions and stopping claims remain fallible
opinions; source verification never certifies scientific entailment. No new scheduler, store,
planner, sufficiency agent or repair subsystem is introduced. The small decision shares the
existing bounded schema-correction and global model-call accounting.

DeepAgents handles research summarization and original-history offloading. Auxiliary summary
calls share the persisted model-call budget. The former Site whole-history fitting and
history-value pointer mechanism have been removed. The historical implementation details below
are retained for earlier reports, not current Site behavior. `max_input_chars=60000` is now a
soft working-set target; `hard_input_chars=100000` is separately configurable, with an additional
approximate token guard when the selected model exposes a context profile. Tool schemas and
call arguments count in the hard character guard. Scientific oracle fixtures and accepted
milestones are unchanged; the Golden spec records the user-authorized engineering amendment.

Explicit DeepSeek Pro/reasoning settings are local debugging configuration, not a product
model-policy decision. Product selection requires controlled same-evidence/prompt/tools/runtime
comparison if a model-policy change is proposed. See the checkpoint for required metrics.

**Trusted runtime owns scientific facts. Specialists own scientific interpretation.
Evidence Judge owns independent critique. Scientists own consequential decisions.**

| Contract | Runtime-owned hard facts | LLM-owned interpretation | Human-owned decision |
| --- | --- | --- | --- |
| Target Assessment / Gate 1 | Verified accession and sequence identity, canonical/construct/observed counts, source chain, existing mapping and coordinate presence, source/request binding and eligible options | Construct significance, uncertainty, alternatives, suggested eligible option and action | Approve, revise, reject or explicitly override a discouraged eligible option through the existing decision service |
| Site / Hotspot / Gate 2 | Approved Target, residue identity and label/auth/canonical mapping, coordinates, surface measurements, supplied topology/biological facts, candidate validity and immutable evidence refs | Mechanism, accessibility hypothesis, useful site/alternatives, risks and strength of retrieved evidence | Gate 2 selection and scientific steering; no model-written approval |
| Binder / Design / Gate 3 | Approved hotspot/exclusions, supported modality and backend schema, official scaffolds, compiler output, exact imported native bytes | Supported design intent, crop/CDR rationale, arm allocation and uncertainty | Gate 3 approval or revision of a validated specification |
| Evidence Judge | Exact delegated snapshot and all canonical refs, request identity, source role and assessment identity; facts are not regenerated | Independent critique: entailment, conflicting evidence, known hard-fact contradictions, unsupported claims and uncertainty | Does not own approval; its opinion precedes the human Gate |

The existing scientific kernel, Stage 02–07, backend implementations and compute recovery remain
the authority. None is replaced by an Agent DTO, session event, model response or test approval.

## Submission mechanism and audit findings

Installed at this baseline: DeepAgents 0.7.13, LangChain 1.4.0, LangGraph 1.2.11 and
langchain-openai 1.6.1. The Model API uses the existing ChatOpenAI-compatible DeepSeek function
calling adapter, `deepseek-flash`, with thinking disabled. No provider/model or 60k input limit
change is needed. The current adapter already performed real scientific tool calls in Phase 2.2c.

[LangChain ToolStrategy](https://docs.langchain.com/oss/python/langchain/structured-output)
is the selected existing mechanism. DeepAgents passes `response_format` to its isolated
specialists; LangChain validates Pydantic tool arguments and returns `structured_response`.
Installed `langchain/agents/factory.py` was inspected, including its output parsing and
`handle_errors` paths. No new generic structured-output framework or provider beta endpoint
is introduced.

| Path before Phase 2.2d | Weakness | Current submission |
| --- | --- | --- |
| TargetAssessment, both slices | Full response text parsed as JSON; model copied facts, options and evidence refs | ToolStrategy(TargetInterpretation), then runtime-owned TargetAssessment envelope |
| Phase 1 Judge | Full response text parsed as JSON | ToolStrategy(JudgeVerdict), existing callback binds snapshot |
| Phase 2 Judge | ToolStrategy existed; generic retry policy | Same scientific DTO, bounded persisted schema correction |
| SiteIntent and BinderIntent | ToolStrategy existed; generic retry policy | Same intent DTOs and trusted validators; bounded persisted correction |

Pure JSON text and fenced JSON do not submit proposals. Incidental prose accompanying a valid
typed tool call is not authoritative and is replaced by the callback's runtime result. Invalid
schema submissions get exact schema diagnostics through the framework; malformed tool JSON or
missing typed submission gets a narrowly bounded correction. Two output-contract corrections
are allowed per runtime-selected typed contract in one persisted execution (the global call
budget remains shared across roles), separately from four shared source/projection correction rounds (20260912 bounded recovery update;
historical Phase 2.2d used two). Every attempt also consumes the unchanged model-call budget.
Errors within one native parallel tool batch share its runtime-derived round; every diagnostic
remains recorded and explicit source selection is still mandatory. Replaying that exact batch
retains its attempt; a new model message consumes a new round. Legacy events without a batch
identity each count once. Restart or redelegation cannot reset either allowance. No scheduler or schema migration is added.

Site first-delivery admission reserves32k for complete receptor analysis, the exact allowlisted
Skill text plus line/wrapper margin for Skill reads, and6k per bounded evidence page. Multi-call batches above32k are rejected before scientific
handlers with TOOL_BATCH_TOO_LARGE, sharing the same repair-round ledger. The model chooses
smaller batches; runtime neither schedules a continuation nor drops unconsumed answers. The
final60k input guard remains independent and authority/integrity failures remain fatal.

Complete receptor display uses explicit local value_same_as JSON pointers only for exact repeated
values. Every unique scientific value remains in that same tool view and expands to the exact
ordinary overview. Raw analysis and scoped candidate aliases stay unchanged/expanded; reserved
source-field collisions use the ordinary representation. No scientific selection or summary.

If Site reasoning history still exceeds the input cap after whole-view archival, exact repeated
historical values may use history_value_same_as pointers within that one working-history message.
Every unique value remains present and mechanically expands to the original working view. User
turns, checkpoint records, latest answers and scientific archival choices do not change. Existing
encoded receptor views retain their own local scope. Incomplete exchanges and native/non-reasoning
input behavior are unchanged; telemetry identifies this encoding and the60k guard still applies.

## Target facts and scientific consistency

`TargetInterpretation` contains no hard-fact, evidence-ID or source-reference fields.
`TargetAssessment` is a runtime envelope: `hard_facts`, interpretation, verified source identity,
refs and eligible options. `TargetFacts` is a small display/review projection; complete sequences,
residue mappings and source bytes remain in the existing verified records and TargetBundle.

The old inventory field named `canonical_residue_count` meant observed standard amino-acid
residues, not canonical protein length. The Agent projection now calls it
`observed_amino_acid_count`; the protected inventory/kernel is unchanged. Canonical length is
read from the verified reference/identity report. Construct length and observed positions come
from their respective existing identity objects, never one another.

Explicit contradictory canonical-count and chain-specific construct/observed-count statements
in Target, Site and Binder intent, or an approving Judge opinion, produce `HARD_FACT_CONTRADICTION`. The rejected opinion is retained as a finding, cannot create
a Target assessment, and may be corrected within the output-contract allowance. Each callback
rechecks current facts after its delegation checks and before persistence. A rejecting Judge
can quote a bad claim to critique it; that does not make the claim authoritative. Gate payloads and Judge snapshots contain runtime
facts and a separately labeled, source-bound interpretation. A changed interpretation changes
the Judge binding; an old Judge opinion cannot approve a replacement interpretation.

The narrow numerical checks are not a general natural-language verifier. Other claims require
independent Judge review, Golden factual oracles and scientific content acceptance. Site/Design Judge snapshots include the runtime Target fact projection. Structured
fields in Site/Binder already pass trusted residue/coordinate/hotspot/schema checks; any
remaining unsupported prose still fails scientific acceptance. Human approval never repairs it.

## Stable evidence and current scientific binding

The existing project evidence artifacts and corpus remain the only source store. A stable
source is identified by provider/accession and exact verified source refs within the project.
Corpus existence is independent of current target/config revision. Current-state relevance is
separate: a selected source is not automatically supporting evidence or proof of target identity.

Only the exact UniProt source verified by an existing canonical-reference-proposal event can
carry its original selection across that event's precise prior/current binding. Other historical
sources remain readable as project inventory but cannot enter focused retrieval without a
current explicit thread/need selection. No transitive relevance graph or inferred cross-project
binding is created. A changed view invalidates its old cursor.

Focused cards carry stable source/project evidence identity, verification status, acquisition
and current binding context, unresolved relevance, and selection provenance. Full-source reuse
for a new selected need reads the same verified corpus, not another network download; previous
scientific conclusions are not automatically carried forward. Separate threads select their
own current needs. Artifact integrity and project confinement remain mandatory before reuse.

The five pre-frozen Golden specifications and machine-readable truth are unchanged. Offline
tests prove mechanics; real before/after retrieval, independent hard-fact checks, evidence
critique and all required Gates must pass before Phase 2 can freeze.

Ordinary completed replies carry a runtime-rendered Target facts object and separate interpretation.
Coordinator sentences that restate Target identity/sequence facts are omitted from ordinary output;
its original message remains in the event log for diagnostics. These checks do not validate arbitrary
scientific prose or replace independent review. Existing sessions retain their fingerprint guard:
a new contract requires a new Agent thread, while project evidence and scientific jobs remain intact.
Discovery leads are labeled separately from verified acquired sources and verified derivations.
