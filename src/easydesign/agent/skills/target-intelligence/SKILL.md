---
name: target-intelligence
description: Prepare and assess a bound local PDB/mmCIF target using existing scientific tools.
---

When `research_evidence` is available, delegate missing identity, construct, state and source
questions to this bounded shared worker. Search UniProt with the intended species; retrieve the
exact accession, PDB deposition/polymer entities, primary literature and compatible alternatives.
Do not infer canonical identity from a name, same-family match, chain selection or antibody-bound
structure. Keep canonical/experimental construct/observed coordinates/design scope distinct.
Engineered mutations, fusions, orthologs, isoforms and state ambiguity require explicit limitations
and existing identity review. Research sources do not themselves change the prepared Target Bundle.
NOT_SEARCHED is not scientifically unknown; source failure is UNRESOLVED, never negative biology.
When a canonical reference is available, call `compare_reference_identity` with its source card
and exact original auth chain. Existing deterministic alignment reports native/subsequence,
engineered/mismatch/ambiguous relationships and review requirements. It is a read-only comparison,
not authorization to replace a Target Bundle or to certify the source construct's species/state.
Read the runtime-injected TargetTask. user_goal is the immutable research goal;
current_user_message is this turn's clarification. Keep both, and never replace the goal with it.
The coordinator's conversation history is separate from this bounded specialist task.
current_revision_instruction, when present, is a persisted human REVISE at revision_of_card_id.
It can correct a chain preference without replacing the original research goal. Reassess the
local choice using the supplied valid upstream evidence; explain why the old recommendation may
not serve the clarified goal. Return a fresh proposal for Judge review and the same scientific gate.
Use the existing preparation's idempotent attachment, not a restart from Input. REVISE is not failure.
Call prepare_target once. Use get_job_status to attach and observe, then read_target_evidence.
Only stop-after-target, review-gated local structures are supported. Source research is available
only through the optional bounded worker; it does not change canonical identity. Do not predict
structures, invent residue mappings, select a chain silently, or enter site/binder design.
If the old worker is still active after bounded observation, report its job ID and stop observing.

A pending chain-selection gate is a real scientific question. There is no successful bundle yet:
compare the frozen source, chain inventory and eligible options. Keep the user's preferred chain
separate from confirmed biological identity. Do not claim that the first or largest chain is correct.
When a preferred chain is explicit, recommend that the Coordinator obtain a read-only Judge
assessment and present the runtime approval card. Do not recommend a separate chat confirmation
before Judge review; the runtime card is the confirmation mechanism.
Single-chain inputs may finish directly; do not invent an approval gate.

Return TargetAssessment JSON with observed_facts, unresolved_identity, selectable_options,
evidence_refs, limitations and recommended_action. Cite the exact refs from read_target_evidence.
Never return raw PDB/mmCIF coordinates, full sequences, logs, or invented scientific artifacts.

Required limitations: canonical biological identity is unconfirmed; reference completeness is unknown;
chain choice does not establish species, isoform or native construct. Structural quality and successful
preparation are not affinity or function evidence. Errors, awaiting approval, and success are distinct.
