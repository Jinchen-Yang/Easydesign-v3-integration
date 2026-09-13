# Gate 2 Judge availability and normal-path repair

Current amendment: [Structured fact consistency](PHASE2_STRUCTURED_FACTS_20260914.md)
replaces the Site Judge lexical output grammar; historical validation records below remain unchanged.

This user-authorized amendment separates independent review availability from scientific
recommendation. It does not declare Phase 2 frozen. It supersedes earlier requirements that
a completed Judge opinion must exist before every dossier-backed Gate 2 card can be displayed.
Gate 1, pre-dossier Site and Gate 3 keep their existing review contracts.

## Two independent acceptance requirements

1. The ordinary Judge must submit a real, scientifically usable structured review and produce
   its bound Gate 2 card in saved-state real-model validation. An unavailable-review card does
   not satisfy this requirement. Valid negative opinions remain negative outcomes, not an
   engineering formatting failure or a forced positive assessment.
2. Classified operational failures must leave a safe path to Scientist review when the exact
   proposal and deterministic checks remain valid. This is separately tested through fault
   injection. Passing this path does not demonstrate that the ordinary Judge has been repaired.

Validation proceeds from the existing immutable Dossier / SiteDecision / hydrated intent /
Judge packet, to Judge and Gate 2, then the joined downstream flow. Research and Gate 1 do not
need to be repeated for this debugging work. Any later full fresh exam and final regression
must be reported separately. Saved-state success is not full fresh biological acceptance.

## Ordinary review

The dossier-backed Site Judge uses one native LangChain structured inference with no research
or filesystem tools. The working input retains target facts, exact candidate membership and
mapping, topology, exclusions, source passages and qualifiers, counterevidence, the original
SiteDecision and unresolved downstream work. Only transport/navigation and duplicated contract
instructions are omitted. Runtime binds short fact references to the current evidence revision
and renders facts; it does not rewrite scientific conclusions or manufacture a verdict.

`SiteJudgeVerdict` contains current-stage verdict, recommendation, short reasons, uncertainties,
warnings, alternative, exact-quote qualifications and short fact references. Runtime normalizes
it into the existing `JudgeVerdict` and uses the same registration and fact/correction checks.
The normal schema permits at most two reasons, three uncertainties, three warnings, three
qualifications and four fact references; prose is bounded to three hundred characters per item.
The recovery schema permits one reason, two uncertainties and one fact reference. All model
calls and both repairs use the existing execution ledger and `JudgeVerdict` repair budget.

A truncated or invalid response receives the compact recovery contract, specific validation
diagnostics and the prior typed opinion when available. Recovery corrects the previous review
rather than restarting a long review. Original failed submissions remain in the audit ledger.
The original model configuration, output allowance, global model-call budget and hard input
character guard are unchanged. No provider retry loop, scheduler or persistence service is added.

## Explicitly unavailable review

Only exhausted, classified technical failures qualify: output truncation, missing/invalid typed
submission, provider timeout or temporary provider unavailability. Unexpected programming errors,
stale bindings, source corruption and unresolved substantive findings propagate as errors.
A valid existing Judge assessment, including `reject` or `insufficient`, cannot be replaced by
an unavailable-review record. Invalid submissions carrying negative findings cannot silently
become an operational fallback either.

The runtime writes `site-judge-unavailable`, bound to the current evidence, execution and exact
failure event receipts. It writes no `EvidenceAssessment`, `ready-to-ask`, SUPPORTED or DISCOURAGED
opinion on the Judge's behalf. The Gate 2 card uses `assessment_id=null`, `judge_status=null` and
`scientific_summary.independent_review.availability=unavailable`, with the failure record ID.
The existing proposal, runtime facts, source scopes, risks and uncertainties remain visible.

Ordinary APPROVE is unavailable for this card. The Scientist can REVISE, REJECT, or explicitly
acknowledge the missing independent review and provide a rationale via the existing OVERRIDE
human outcome. This is a human decision despite missing review, not an override of a fabricated
Judge opinion. Target / chain / revision, exact residue mapping, candidate membership, topology,
explicit avoid constraints and verified source references remain mandatory. Runtime BLOCKED
cannot be bypassed. Approval rechecks current bindings and rejects a stale absence record if
an actual independent assessment or substantive finding has since appeared.

Restart reuses the same receipt/card and does not reset the exhausted budget. Downstream Design
retains the unavailable-review status, warning and real human acknowledgement. Models have no
human approval fields or authority. Synthetic approval tests do not approve any saved GPCR case.

## Evidence and limitations

Per-run records are written to distinct local validation directories. Real normal-path outcomes,
fault-injected availability outcomes, compatibility tests and source-preservation checks must be
reported individually. A small number of successful real samples cannot guarantee every future
provider response. The previous literal fact guard is a restricted output grammar, not a general
semantic fact checker; a valid structured opinion still requires scientific content review.
