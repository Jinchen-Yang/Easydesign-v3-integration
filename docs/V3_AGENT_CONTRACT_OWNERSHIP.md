# EasyDesign v3 consequential Agent contract ownership

Phase 2.2d implementation audit, baseline `4df3b2bd19f72a39f67ad40c3874b30323f0aafb`.
This is an ownership specification, not a declaration that real scientific acceptance passed.

Autonomous continuation update (20260912): model selection and optional reasoning are now
explicit audited configuration. DeepSeek reasoning uses the already-installed Anthropic adapter
and fixed official endpoint, preserving native thinking blocks across tool rounds. The historical
non-thinking adapter description below describes its baseline. No scientific ownership, typed
submission, Judge or Gate semantics change. See `AUTONOMOUS_V3_PROGRESS.md`.

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
are shared across roles in one persisted execution, separately from four shared source/projection correction rounds (20260912 bounded recovery update;
historical Phase 2.2d used two). Every attempt also consumes the unchanged model-call budget.
Errors within one native parallel tool batch share its runtime-derived round; every diagnostic
remains recorded and explicit source selection is still mandatory. Replaying that exact batch
retains its attempt; a new model message consumes a new round. Legacy events without a batch
identity each count once. Restart or redelegation cannot reset either allowance. No scheduler or schema migration is added.

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
