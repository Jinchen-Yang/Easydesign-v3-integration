# Gate 2 ranked site portfolio implementation

Gate 2 now presents every supplied hard-valid candidate as a selectable relative recommendation.
SiteDecision owns the order. Runtime binds exact membership and explicit constraints. Judge adds
an independent second opinion; Scientist chooses a candidate or requests revision/rejection.

## Runtime behavior

- Live synthesis submits `RankedSiteDecision`, with a separate rationale, mechanism, approach,
  supporting evidence, risks, uncertainty and confidence for every supplied candidate. Exact
  residues, chain, mapping and evidence-card IDs are hydrated from the immutable Dossier.
- All supplied candidates must occur exactly once. Hard-invalid candidates remain visible but
  disabled; they do not consume selectable A/B/C positions. If all candidates are invalid, no
  rank or executable Site run is fabricated. Current Research/kernel contracts supply 1–3
  candidates; missing alternatives are never invented to fill three slots.
- Poor exposure, uncertain whole-binder access, weak evidence and scientific risk do not disable
  a valid candidate. An explicit tie requires the missing discriminator; `preference_group`
  records equal priority while A/B/C remain unique selection keys.
- Explicit BiologyContext exclusions remain hard constraints. The optional trusted
  `required_site_compartment` field checks supplied, unambiguous ECL/ECD versus ICL topology.
  TM/pore labels and low exposure alone do not establish a compartment contradiction. This
  field is imported through the existing user BiologyContext entry, not inferred by scanning
  Judge prose. Existing identity/mapping/source-revision checks remain mandatory.
- Judge retains its bounded normal/recovery contracts, structured-fact validation and classified
  failure records. Its scientific `reject`/`insufficient` opinion remains visible but does not
  make a hard-valid portfolio ineligible. Unavailable review is explicit and never replaces an
  already completed negative opinion. Judge cannot silently change the SiteDecision order.
- Human `APPROVE` selects the displayed default A; `--candidate <stable-candidate-id>` selects
  another entry. The interactive prompt accepts A/B/C/revise/reject. Merely displaying A has
  no effect. The persisted `DecisionOutcome.selected_option_id` binds the actual selection.
  No override, mandatory rationale or additional acknowledgement is required for a valid entry.
- A single existing Stage 2 proposal contains all selectable regions. Approval selects exactly
  one corresponding kernel region. The approved projection carries that candidate's residues,
  evidence, rationale, risks and uncertainty downstream, preserving the original portfolio.
  Gate 3 and generation remain separate human-authorized boundaries.
- Historic single-Site decisions/cards retain their original behavior. Optional new fields are
  omitted from legacy serialization so existing evidence bindings remain unchanged.

## Verification record

Python regression coverage is **1,111 unique tests: 1,100 passed, 11 skipped**, with no
unresolved failures. The skips are eight opt-in independent PyMOL checks and three opt-in
live API/backend smoke tests; the actual saved-GPCR validation below is separate evidence.

The complete suite ran in four file partitions. Four assertions still simulated the former
live synthesis contract; only those current-interface fixtures were corrected, keeping legacy
replay tests. Seven setup errors from explicit-file fixture discovery were rechecked using full
suite discovery. All 11 previously unsuccessful items then passed. `regression-acceptance.json`
reconciles every test ID against the original 1,111-item collection and records the report for
each final result. This is a complete coverage aggregate, not a claimed monolithic `make test`.
Runtime source remained identical across these regression checks, and source hashes were
unchanged during each run. Core data model tests also passed independently (67 tests).

All 17 new portfolio cases passed, covering real A/B/C kernel approvals in synthetic projects,
selected evidence/risks/uncertainty, duplicate/stale/reordered cards, recovery, explicit ties,
all-invalid and partially-invalid portfolios, normal/repair/unavailable Judge paths, and
B/C propagation into all seven scaffold design inputs. Those fixture approvals do not authorize
the actual GPCR case. `make check` passed after fixture corrections: repository/asset checks,
compilation, Ruff, and strict mypy for 195 source files.

The saved GPCR case is the original successful 20260913T204010742154Z exam. Validation uses new
isolated copies; the original experiment, approval state, source artifacts and frozen tag are
not modified. It reuses Gate 1, Research and the exact saved Dossier rather than repeating source
searches to debug the final decision path.

The final saved-case run (`live-final-03`) used the actual `deepseek-v4-pro` Site and Judge
profiles, with no model configuration change:

| Role | Input tokens | Output tokens | Total | Repairs |
| --- | ---: | ---: | ---: | ---: |
| Site synthesis | 17,407 | 9,031 | 26,438 | 0 |
| Judge | 18,579 | 3,106 | 21,685 | 0 |

Both submitted on their first call: 48,123 tokens in total, zero fallback. Maximum input was
66,333 characters, below the unchanged 100,000-character hard limit. Runtime produced an actual
three-region Stage 2 proposal and Gate 2 card. Site ordered ECL2, outer-pore, core-pore as A/B/C;
all three remained selectable despite the Judge's retained `DISCOURAGED` scientific opinion.
Judge qualifications and risks remained visible. Exact `canonical W286 -> design W414` mapping
was rendered from Runtime. The old AINCYANETCCD passage was absent from this saved Dossier;
the replay does not invent or claim to verify a peptide passage it did not contain.

Card: `ec2011cee533d32656db3cb4d2e431395667ee9057e67791c9a2f0c0e6e6f737`.
Isolated Site run: `foundation-20260914-040414-2b9f0a77`.
The validation copy is experimental evidence; it does not migrate or authorize a production
Scientist session. No actual candidate was approved and no generation was started.

Earlier setup runs used two additional model calls (one Site and one Judge). The first cloned
workspace retained the original runtime profile path, so clone confinement correctly rejected
Stage 2 execution. A new isolated profile revision corrected that replay setup without changing
the original workspace. Those earlier results remain separate from the final run above.

After the final live run, strict mypy required a local list type annotation in
`compile_ranked_decision`. Its executable bytecode was verified unchanged, and subsequent
regression/static checks use the annotated source. This proof is retained as
`typing-only-proof.json`; later corrections affect test fixtures and documentation only.

All logs, source manifests, actual model-response usage, original-case integrity results, card,
proposal and fixture results are preserved under
`runtime/tmp/phase2-ranked-site-implementation-20260914/` in the authoritative repository.

## Historical freeze

Original accepted code: `0859a5e583b7f44bf417e77741a8914831ca9e25`.
Original tag: `easydesign-v3-phase2-frozen-20260914`.
This change does not relabel that historical run or claim a new full-fresh GPCR exam.
