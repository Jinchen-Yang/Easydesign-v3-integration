# Final Phase 2 exam preflight

Starting commit: `0bba70a4026d4629c5bfe0779733521cbee3ee34`.
The user's latest instruction resumes from the collaborator review pause: perform a small
deterministic preflight, commit and freeze source, then run exactly one fresh GPCR Case 2 E2E.
No broad refactor, new agents, changed limits or configuration, source patch during the run,
automatic second fresh run, or Phase 3/4 is authorized. Failure preserves evidence and stops
for human review. Only independent scientific PASS permits compatibility revalidation of the
four preserved cases, final-commit full regression, parity/closure and a formal Phase 2 tag.

The active-path wording check found:

- Judge Skill still named removed `decision_basis`, Research question statuses/stopping opinions,
  and the former model-facing singular `field` selector. Replace those instructions with the
  actual `research_evidence.decision_questions`, `retrieval_status`, `source_cards`, runtime facts,
  hydrated SiteIntent and model-facing `fields`/`path` interface.
- Synthesis Skill and the working-set authority text still described preliminary Research
  opinions as material to assess. Name the actual question scope, runtime facts, scoped evidence
  and access failures. Preliminary opinions stay in the durable Dossier for audit.

No DTO, validator, routing, scientific kernel, budget or model configuration is changed.
The existing `ResearchConclusionMismatch` boundary error remains active for real Handoff and
selection errors; its class name does not duplicate scientific authority. Historical terms in
negative instructions, tests and immutable records are not new model output requirements.
The remaining 32k detailed-history/view limits apply to Target/Binder, not the removed Site/Judge
batch guard. They remain outside this wording correction. The internal singular `field` reader
remains available to trusted code; the model schema continues to expose only `fields` and `path`.

Verification uses existing deterministic authority, Dossier, SiteDecision, projection and model
schema tests. No preflight live model or source acquisition is permitted. Exact test outcomes,
final commit, configuration hashes and the single-run marker are recorded under
`runtime/tmp/phase2-final-exam-20260913/`. Phase 2 remains unfrozen until all conditional acceptance
and closure steps actually succeed. The earlier 922-pass run is not final-commit regression.
