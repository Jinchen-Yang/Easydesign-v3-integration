# Phase 2 Site Judge fact integrity — validation in progress

Current amendment: [Structured fact consistency](PHASE2_STRUCTURED_FACTS_20260914.md)
replaces the Site Judge lexical output grammar; historical validation records below remain unchanged.

Baseline: `8c4625dadeb447108ea5068ae7916cdfee774f50`.

The preserved GPCR Judge changed AINCYANETCCD to approximately 184–196 in a reason.
The original Research interpretation contained 181–192, but its answer was not in the
Judge projection. The selected source passage contained the sequence without that explicit
range. Binding the input artifacts did not validate newly generated factual prose.
The original independent scientific FAIL remains unchanged.

## Boundary and authority

The existing dossier, approved Target mapping, verified UniProt record and original kernel
remain authoritative. A Site Judge packet now includes content/revision-bound fact references
into those same packet objects, plus runtime-derived exact sequence occurrences and overlaps.
A shared revision and indexed collections avoid repeating a hash/path record for every fact.
Identical source metadata is stored once; expanding each passage with its source group
reproduces the exact original record, including every qualifier and passage byte.
It does not introduce a database, scheduler, scientific kernel, provider, alignment method,
status enum or model-authored fact registry.

| Fact | Runtime authority / scope |
| --- | --- |
| Canonical/design/construct/source-author labels and chain | Existing verified mapping rows; conditional status, nulls and substitutions retained |
| Candidate and avoid membership | Exact hydrated SiteDecision candidate, explicit exclusions and existing deterministic validation |
| Peptide occurrence | Literal sequence candidates in verified passages searched exactly against the approved canonical sequence; reference source hash is checked before use |
| Overlap | Each canonical occurrence joined to exact candidate mapping rows, retaining unmapped and substituted members |
| Topology | Official canonical annotation, GPCRdb segment and kernel point region retain different scopes; no whole-binder clearance claim |
| Motif coordinates | Existing sequence-motif facts; not occupancy or functional proof |
| Source identity | Bound original passage and provider identifier, existing dossier/evidence references |

Sequence candidate discovery is a narrow uppercase amino-acid token recognizer on already
verified source passages. A token can also be an uppercase word; detection alone certifies
neither a peptide in an assay nor an epitope. No match stays unresolved, all repeated exact
occurrences are retained, and variants are never approximately aligned. Research's proposed
numbering is not promoted to truth. No new retrieval is required for this derivation.

## Judge output and human presentation

Dossier-backed Site Judge text uses `[fact:REVISION:kind:index]` references for protected factual values.
Unknown or stale IDs, numeric literals, supplied sequence literals and reserved location/chain
classification literals in reasons, limitations, warnings, alternatives or correction
qualifications fail the existing bounded output-contract repair. This is a lexical output
grammar, not an NLP system that infers the truth of arbitrary sentences. It intentionally
requires even correct numeric restatements to use references, including source identifiers.
Scientific interpretation, risk, evidence strength and uncertainty remain model opinions.
The grammar does not certify arbitrary prose, entailment, word-spelled facts or functional
conclusions; independent scientific review remains required.

Runtime renders references from the current verified packet before building the card and
includes a runtime-fact view with the bound independent review. Expanded fields must fit the
existing text limits. The same rendered review and warnings flow through the existing approved
Site outcome into Design. The original Judge assessment retains tokens for audit. The old
wrong submission is preserved, rejected at registration, and rejected again if an old
assessment is used to request a new card. Previously issued historical cards and receipts are
not rewritten. Exact Site claim excerpts remain explicitly quoted unaccepted claims next to
the Judge qualification; original SiteDecision bytes are unchanged.

Target/Design and historical pre-dossier Site DTOs keep their existing contracts. The shared
preflight now applies fact-reference validation to negative as well as positive Site opinions.
No negative opinion is upgraded and no human approval is inferred. The five Gates, hard
constraint behavior and early Site scientific floor are unchanged.

## Required verification and stop condition

Use deterministic tests and the preserved real GPCR boundary before any live model call.
Replay writes a memory-copy ledger and separate fixture outputs; it cannot turn the original
scientific FAIL into PASS. Cover real prior rationale rejection, exact range and overlap,
nonidentity mapping, topology, exclusions, source binding, card rendering, downstream warning
compatibility, and existing bounded repair/exhaustion.

Commit only after targeted checks, saved replay, accepted Cases 1/3/4/5 current readback and
protected/Golden/config parity pass. Then one frozen fresh GPCR is authorized. On FAIL stop and
preserve/package the blocker. On PASS run current accepted-case readback, the actual final full
regression and parity, then create the formal Phase 2 milestone and stop before Phase 3.
Model/configuration, the 64-call budget, 100k hard input guard and bounded repairs stay fixed.
