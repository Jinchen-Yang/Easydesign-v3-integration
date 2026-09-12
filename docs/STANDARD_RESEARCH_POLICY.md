# Standard Research: evidence sufficient for the decision

User-authorized policy update, 2026-09-12. Preserve all accepted milestones and the current
Architecture Checkpoint. Phase2 remains not frozen; Cases1/3/4/5 are accepted and GPCR Case2
requires a fresh scientific PASS before full regression and Phase2 closure.

## Scientific stopping rule

Start from the biological objective, approved Target and current Gate. Form usually3–6questions
that could change site ranking, a hard constraint or the major risk assessment. Access, mechanism,
state/ligand/partner, consequential membrane/glycan/disulfide constraints and known epitopes are
conditional examples, not a taxonomy checklist. A few well-chosen primary/official sources can
support a defensible next step; Standard Research is not a comprehensive literature review.

After initial candidate ranking, make a targeted contradiction/alternative literature search and
read consequential leads. If it changes the recommendation, update the comparison and investigate
only the new decision-critical gap. Otherwise ask whether more searching is reasonably likely to
change ranking, constraints or major risk. When not, stop immediately and hand off. Remaining
budget, a continuation cursor or an unfilled annotation category is not a reason to continue.

VERIFIED, SEARCHED_NO_EVIDENCE, CONFLICTING_EVIDENCE and UNRESOLVED are legitimate assessed states.
They do not certify efficacy or approve the candidate. An adequately investigated unresolved
question can support a qualified next step or an insufficient-evidence recommendation. Preserve
its decision consequence, missing evidence and discriminating test. A source failure is not an
empty search, and an unperformed inquiry cannot be relabeled as performed.

## Implementation boundary

Use the existing Site specialist, research tools, Evidence Store, typed Handoff and graph nodes.
No new Research Planner, Sufficiency Agent, workflow subsystem or Fast/Deep modes are introduced.

- Site Skill and existing system/native-memory prompts carry the stopping policy.
- Runtime activity reports actual inquiry counts and literature searches; it does not display
  all unsearched taxonomy categories as tasks.
- Existing query receipts expose their original query_id. ResearchConclusion can bind those
  actual queries across topic labels; runtime verifies ownership/existence and exact source
  citations. Topic-indexed legacy conclusions remain supported. Cross-topic reuse is a relevance
  judgment for the scientific owner/Judge, not automatic proof of entailment.
- SiteResearchHandoff carries at most6decision_questions, candidate comparisons, actual
  contradiction_search_query_ids, a stopping_reason and meaningful uncertainties. Structural
  exploration without external research may omit research questions; an external research
  snapshot requires them and an actual literature-search receipt. The runtime proves the search
  occurred; its scientific adequacy, timing relative to the provisional ranking and saturation
  claim remain reviewable opinions, not deterministic certificates.
- Dossier v4 places decision questions beside approved Target/candidate hard facts and exact
  focused passages. All already-read focused passages, including uncited opposition, remain;
  full acquisition bodies/bibliographies stay in the durable corpus. Bounded purposeful reading
  provides the compact scope; no sentiment filter drops disagreeing evidence.
- Fresh synthesis gets the original goal/current trusted revision plus the dossier, without
  research/tool/thinking history. It must address the decision-critical questions and can reuse
  their actual query IDs; it does not expand to unrelated taxonomy coverage.
- The independent Judge receives the research stopping basis and its cited contrary evidence
  even when final SiteIntent omits that citation. Source artifacts and the derived dossier ref
  are verified through existing immutable evidence refs. No automatic approval follows.

The public DeepAgents summary machinery still owns research working memory/offload.60k remains
soft;100k is the current independent guard, with the existing model-profile token guard. The
local Pro/high configuration and32shared calls are unchanged. Product Flash defaults and all
scientific kernel/Gate/oracle invariants are unchanged. No controlled model A/B claim is made.

## Verification and acceptance

Targeted tests exercise query identity/reuse, unperformed versus failed/empty search, explicit
unresolved stopping, missing/fabricated contradiction query rejection, retained opposing source
bytes and Judge visibility, source tampering, unchanged mapping and isolated restart/correction.
These scripted/synthetic tests do not establish scientific Case2 acceptance. Real GPCR validation
must independently pass exact identity/numbering, relevant primary evidence, contradiction check,
credible candidate comparison, honest uncertainty and Judge review without known science errors.
Full regression and Phase2 freeze follow only after that PASS, then the original Phase3→4 task.


### Approved candidate correspondence

GPCR candidate canonical/source positions are not approved design labels. The existing
receptor-analysis evidence now includes approved_design_mapping, an exact lookup against the
current approved Target, after matching canonical accession and original chain. It preserves
all corresponding rows and scientific qualifications; it never infers an offset or silently
selects one of several correspondences. This is EasyDesign-specific hard-fact ownership.
DeepAgents still owns research history summarization; no new generic context subsystem is added.
A bounded candidate inventory or mutation-record count is not exhaustive epitope knowledge.
Stop source pagination once the candidate-specific question is answered, preserving meaningful
uncertainty and contradictory evidence. The original records remain durable and traceable.

### Synthesis instructions and bounded submission recovery

Live176 demonstrated the real boundary with a62318character dossier and83826character first
isolated synthesis input, preserving13focused passages and22approved candidate mapping rows.
It then failed on an empty SiteIntent after two Handoff corrections; it did not pass Case2.
The fresh stage now receives only references/synthesis.md's scientific interpretation and
submission criteria, rather than the whole Research Skill with acquisition/pagination steps.
The graph, durable dossier, source checks and independent Judge remain the same.

Queries begin with the target and decisive effect. Empty or irrelevant hits warrant one
sensible broadening; requiring antibody AND nanobody AND a precise mechanism can exclude
consequential evidence. The contradiction check includes the user's forbidden functional
effect, with antibody/autoantibody/modality/species transfer limits. No specific Golden paper,
residue set or preferred answer is inserted. Handoff remains concise and its array must contain
actual mapped design labels, not canonical values explained correctly only in prose.

The existing persisted correction counter is scoped to the runtime-selected typed contract:
two corrections each for Handoff and SiteIntent, across delegations/restarts, under the same
unchanged32model-call total. Legacy unscoped corrections count conservatively against every
contract. No model-supplied scope, new retry engine or fresh overall execution budget is created.
Schema-error metadata is recorded before a correction-budget exception, without reasoning text;
its usage duplicates model-response when recovery returns and must not be summed twice.
