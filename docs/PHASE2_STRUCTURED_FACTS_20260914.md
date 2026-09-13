# Site Judge: structured fact consistency and scientific expression

This amendment replaces the lexical fact-output grammar in
`PHASE2_FACT_INTEGRITY_20260913.md`. It preserves the runtime fact packet and the
availability / Scientist authority contract in `PHASE2_JUDGE_RESILIENCE_20260914.md`.
It is a local Judge repair, not a new control-flow audit or Phase 2 scientific freeze.

## Authority and output

Runtime owns target/chain/revision, exact peptide occurrences, canonical/design mapping,
candidate membership, scoped topology, exclusions and verified sources. Judge interprets
that evidence. Scientist still makes the consequential Gate decision.

Judge may use normal scientific vocabulary and numbers in reasons, uncertainties, warnings,
alternatives and correction qualifications. There is no number, peptide or topology word
blacklist and no NLP truth checker. Existing concise output bounds and scientific standards
remain: point exposure is not whole-binder clearance; contact with a disulfide-forming
cysteine is not demonstrated folding or trafficking damage.

`fact_refs` cites supplied facts. Compact Site outputs use short IDs, such as `peptide:0`;
Runtime binds them to the current evidence revision before persistence. Optional `fact_claims`
assert exact values when necessary, without copying the full fact table:

```json
{
  "fact_ref": "peptide:0",
  "field": "canonical_occurrences",
  "value": [[181, 192]]
}
```

The field is a direct key of the referenced object; null addresses that whole value.
Judge does not write JSON paths or nested array indices. The working input lists the exact
available IDs, so Judge need not count a collection to invent a reference. Mapping rows
use existing named columns, source records use expanded provenance, and other facts use
their existing packet shape. No second fact registry or inferred alignment is added.
References alone are sufficient for interpretation; Judge need not restate exact values.

The validator checks packet integrity, current references, existing fields and exact JSON
value equality. Types, nulls, order and complete ranges are preserved. A wrong range,
mapping, topology or membership is a substantive conflict, including in a negative review.
Unknown/stale IDs and missing fields are rejected. Existing source binding and hard constraint
checks still run independently. Legacy inline fact citations remain supported and checked.
Target/Design retain their prior stage semantics; Site fact fields are rejected when no
runtime fact collection is supplied. The old Target prose count checker no longer applies
to dossier-backed Site Judge output, including its registration/preflight entry points.

## Scientist card and limits

The card's `runtime_facts` are always read and rendered from the validated runtime packet.
`cited_fact_ids` identifies the Judge's structured citations and claims. Claim values are
checked but are never copied over runtime facts. Judge reasons, limitations and exact-quote
qualifications remain separate scientific interpretation. Raw submissions stay in the audit.

This boundary does **not** certify the truth of every sentence in free prose. A legacy or new
sentence containing an incorrect number is not recognized by a lexical/NLP scan, and citing
a fact does not certify the entailment of the sentence. Such prose remains visibly scoped
interpretation and cannot update the precise-fact channel. The historical wrong `184–196`
prose is preserved, not silently corrected or retrospectively declared scientific PASS.
A structured assertion of that wrong range deterministically fails; the runtime peptide
fact and card fact entry continue to read `181–192` with overlaps `183, 192`.

## Availability and validation

The existing compact recovery budget, operational-failure classification and explicit
unavailable-review handoff are unchanged. An unresolved structured fact conflict cannot be
relabeled a technical outage. Runtime hard failure / BLOCKED and existing negative Judge
findings still cannot be bypassed. No new approval or routing policy is introduced.

Tests cover scientific prose in every field, changed ranges/mapping/topology/membership/
exclusions/provenance, strict types and field names, stale references, registration and saved-card
revalidation, native repair, technical fallback, hard-error and negative-review protection.
Readable structured assertions are checked even when another field fails schema validation;
malformed prose or another malformed assertion cannot hide a conflicting exact fact. All
readable reference, field and value issues are reported together with available fields. This
feeds the existing substantive-error path without changing the availability policy.
Saved evidence replay separately checks the original peptide case and real native Judge to
Gate 2 on the latest saved proposal. Source ledgers remain immutable; new events/cards use
isolated ledgers and output directories. No Gate 1, Research, full fresh GPCR or real Scientist
approval is part of this validation. Real-model completion is reported separately from
synthetic boundary tests and does not constitute biological acceptance or a success-rate study.
