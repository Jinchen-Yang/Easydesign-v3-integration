# Phase 2 Judge / Gate 2 consolidation

Audit baseline: `1477c796fa9ae00dfce9148ad93efb7a15719458`. The preserved final exam
failed locally before final Judge inference (101,131 input characters; existing hard
guard 100,000). Phase 2 is not frozen. This work is confined to SiteDecision → hydration
→ independent Judge → Gate 2. Historical evidence, scientific kernels and Golden oracles
are not rewritten. The existing user-authorized migration worktree remains authoritative;
the development context's pre-existing extra-worktree warnings do not authorize cleanup.

## Audit before implementation

| Active boundary | Finding | Required disposition |
| --- | --- | --- |
| `contracts.JudgeVerdict` | Description rejects every categorical mechanism/access claim, including correctable downstream overstatement. | Distinguish invalid factual premises from non-blocking qualifications at Gate 2; retain hard rejection. |
| Evidence Judge Skill | General reject rule and whole-VHH impossibility rule override its own allowance for unresolved questions. | Stage-proportionate scientific floor, explicit corrections and downstream uncertainty. |
| `Phase2Bridge.site_snapshot` → `judge_evidence` | Dossier facts, selected/alternative evaluations, hydrated interpretation and prepared-target context repeat mapping, surface facts and rationale. | One authoritative Judge packet for the current dossier path; original artifacts and non-Judge snapshot consumers remain intact. |
| Site hydration | Runtime chooses exact memberships; explicit avoid overlaps already fail. | Preserve these checks and verify candidate/mapping/topology consistency before Judge admission. |
| Judge registration / Gate 2 | `ready-to-ask` is required for eligible sites; `reject` cannot become readiness just because the proposal is discouraged. | Keep rejection blocking. Teach Judge to return ready-to-ask with explicit qualifications when only downstream uncertainty/overstatement remains. |
| Gate 2 display | Proposal science is copied to the card; independent corrections need visible ownership. | Carry Judge qualifications and limitations to the card without rewriting the original proposal or silently endorsing its overstatement. |
| Shared context policy | The 100k guard worked; no extra Judge-local guard is necessary. | Reduce semantic duplication, preserve all scoped source passages and exact facts, measure full input including schemas. |

No change is intended to Target/Design factual standards, five-Gate architecture, model
configuration, research execution, scientific kernels, source store or bounded recovery.

## Scientific contract

- **Blocking:** wrong identity, scope, mapping, authoritative topology, fabricated evidence,
  explicit exclusions, deterministic contradictions or another premise invalidating the site.
- **Non-blocking correction:** an unsupported absolute access/causal statement whose correction
  leaves a reasonable hotspot. Judge records the claim and its qualified interpretation;
  warnings cannot waive a hard constraint or repair an invalid candidate.
- **Downstream unresolved:** whole-binder clearance, final orientation/mode, affinity, generated
  binder function and actual activation/trafficking outcome. Honest uncertainty is expected
  before design; lack of these later results alone is not grounds for reject/insufficient.

An eligible, reasonable question may be `ready-to-ask` with `SUPPORTED` or `DISCOURAGED`.
DISCOURAGED still requires explicit human OVERRIDE. Runtime BLOCKED is never overridable.
Judge does not approve a site. Corrections are independent review opinions, not new kernel
facts or edits to the preserved SiteDecision. The human card must display them alongside the
unapproved proposal, and downstream consumers retain the review qualifications.

## Validation sequence

First verify packet construction and hard-error rejection using the preserved final-exam
artifacts and synthetic mutations. Retain all decision-critical source passages, contradictory
evidence, query failures and unresolved items. Compare full production Judge input with the
shared guard. Replay only Judge on a copy of the saved evidence/checkpoint; do not repeat
Research or mutate original checkpoints. Test readiness, warnings and restart behavior, and
read back accepted Cases 1/3/4/5 with their original integrity checks.

Only after targeted checks and saved Judge replay are stable may all changes be committed
with a clean tree and one additional fresh frozen GPCR exam run. If that exam fails, stop
and report the blocker. If it passes, revalidate Cases 1/3/4/5, run final full regression,
verify parity/protected integrity, create the formal Phase 2 frozen milestone, then stop.
Do not enter Phase 3. Results belong in a subsequent validation section after execution.

## Saved-evidence validation (before any additional fresh exam)

- The deterministic packet/authority/Gate fixtures pass all 14 checks, including mapping,
  topology, membership, explicit avoid constraints, identity, hydration and competing metrics.
  Registration, restart, non-blocking corrections, explicit human override and downstream
  Design propagation are exercised. `reject` / `insufficient` cannot become Site readiness.
- The preserved exam packet retains all 9 source passages/provenance, all 24 residue fact rows,
  3 candidates, the unchanged SiteDecision, questions, retrieval failures, original selection
  scope and all shared/individual candidate limitations. Static prompt/Skill/DTO names align.
- Saved Judge replay 01 produced a reviewable card but **failed the content requirement**:
  its reasons repeated an alternative's unvalidated absolute access claim. That result is kept.
  The Skill now requires equal claim review of selected and alternative candidates and forbids
  reasserting an unsupported impossibility in the Judge's own reasoning.
- Saved Judge replay 02 completed using only the original checkpoint and verified evidence.
  It explicitly qualified the core-pocket absolute whole-VHH access claim as unresolved
  clearance, and the cysteine/trafficking causal claim as structural risk rather than proven
  artifact. It returned `ready-to-ask`; production Gate logic generated `DISCOURAGED`, with
  both corrections visible in warnings and independent review. No human approval was issued.
- Replay 02 used two model calls and one built-in typed-output repair (initial empty tool
  arguments). Complete inputs including schemas were **81,057** and **81,995** characters,
  approximately 18% below the unchanged 100,000 hard guard. This is measured headroom, not a
  promise that any future evidence packet has the same size. There is no new local limit.
- All 317 original exam files and model configuration remained byte-identical. No Research
  was rerun for either Judge replay. Runtime records, tool-output retention and existing
  bounded recovery remain the production mechanisms.
- Cases 1/3/4/5 pass current read-only compatibility checks and retain their original accepted
  receipts. Case 1's original receipt references attempt-0001, whereas its current project
  already referenced attempt-0002 at baseline `1477c796`; this pre-existing distinction is
  recorded rather than rewriting either identity. Its complete current Site snapshot equals
  the baseline snapshot. Cases 4/5 retain exact proposal/request/evidence/evaluation bindings;
  Case 3 still passes the fixed identity oracle. The source database/WAL were not modified.

Evidence root: `runtime/tmp/phase2-judge-gate2-20260913/`. Key records are
`packet-preservation-and-static-audit.json`, `packet-tests-04.log`,
`saved-judge-01/content-review.json`, `saved-judge-02/content-review.json`, and
`accepted-cases-reproducible-03.json`. The first full integration run was deliberately stopped
for the required Skill correction (28 passed, 11 skipped); it is not a completed validation.
The final-source integration command (`scripts/dev.py verify --mode integration`) then
passed: `make check` (Ruff, compilation, vendored asset verification and mypy over 190 source
files) plus **944 passed / 11 skipped** in `make test` (1,493.07 seconds). The skips are the
three opt-in live API/backend smokes and eight unavailable standalone PyMOL integrations;
these are not claimed as executed. Two existing Anthropic tool-choice/thinking warnings
remain. Log: `full-integration-02.log`. No product, Skill or test bytes changed after the
successful saved replay; only this outcome documentation was added.

Protected integrity also passed for 385 files, 25 existing tags, original accepted receipts,
30 live187 artifacts, the unchanged model configuration and unchanged Golden oracles
(`integrity-final.json`). The code is eligible for a clean commit and one additional frozen
fresh GPCR exam; neither a GPCR PASS nor a formal Phase 2 freeze is claimed here.

Scope of the Skill change: Gate 2 stage proportionality and the shared Judge submission
boundary; no new biological generalization or accepted epitope is asserted. Evidence is the
saved replay and deterministic counterexamples above. Confidence is bounded to those checks;
this is not fresh GPCR acceptance. Reviewer: development scientific-content review,
2026-09-13, under the user's explicit Judge/Gate 2 consolidation instructions.
