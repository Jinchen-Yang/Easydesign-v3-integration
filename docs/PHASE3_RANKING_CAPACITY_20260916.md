# Phase 3 Ranking Capacity Hardening

Scope: a capacity patch on the Phase 3 product closure `2a8fa2e7`. No new Agent,
ranking formula, eligibility rule, scientific workflow, naming migration or backend run.
`pilot-diagnosis`, `PilotDiagnosisOpinion` and historical artifacts remain compatible.

## Decision view and authority

The native Specialist receives `pilot-ranking-decision-view-v1`. The original
measurement, Design intents, source packet and evidence artifacts stay in Runtime.
Their identities bind the view and the existing stale-evidence check remains in force.

- Shared Design/scaffold settings and target context are sent once; Arms carry exact
  recursive deltas. Lists are atomic, null is distinct from absence.
- The matrix names each candidate's Arm directly and groups metrics into short vectors
  with at most six named values each, avoiding a single unbroken 41-column vector. They retain every native-PASS candidate, all 29 existing ranking dimensions
  and 12 chemistry/contact context dimensions. Numeric values are not rounded/rescaled.
  Repeated categorical strings are shared through exact indexed tables.
- Exact sequence-equality groups replace long sequences in the model view; they are
  not similarity scores. Full sequences, raw metrics (including non-projected columns),
  ranks, masks and structures remain in the measurement and complete Scientist dossier.
- Long provenance and per-source exclusion expansions stay behind source references.
  Actual hotspot/not_binding membership, missing residues, limitations, profile rules,
  thresholds and distinct attempt identity remain represented.
- Short candidate references resolve deterministically against sorted canonical PASS
  IDs under the immutable measurement. Runtime expands references before binding and
  publishing; canonical IDs still identify every candidate on the Scientist card.

This is an explicit decision projection, not a claim that every raw column is repeated
inside the model prompt. It does not discard the authoritative raw record.

## Compact output and delta repair

`candidate_order` lists every PASS exactly once. `candidate_rankings` supplies detailed
notes on the top three, all promotion-support candidates and selected important tradeoffs
(at most 12 notes). Other rows are explicitly rank-only with Runtime facts; no model
rationale or risk text is fabricated for them. Arm ranking, completeness, Recovery,
Scale allocation, scientific support and Scientist authorization validators are unchanged.

New native decision-view calls require this compact format. Historical saved opinions
without candidate_order continue to bind through the original detailed-list format.

After a readable failed submission, the same structured tool offers optional replacement
fields. Runtime retains omitted fields, replaces supplied top-level fields, then runs
the complete original schema and scientific validators. Arrays are replaced in full.
The ledger records the patch and merged submission. Unknown top-level shapes use bounded
full recovery instead. Malformed oversized prose stays in the ledger, not unboundedly in
the next prompt. The existing initial call plus two repairs, shared call ledger, restart
behavior, 100,000-character guard and configured 8192 output-token limit are not increased.
Phase 4 and Judge do not opt into this repair protocol.

The real 60-PASS exam exposed a further output bottleneck: the configured DeepSeek thinking
transport exhausted 8192 tokens before a valid opinion, despite a 54k input. Native ranking
now uses the same DeepSeek model with non-thinking, forced submission of the one existing
opinion tool through the native DeepSeek tools endpoint. The compatibility endpoint had
returned empty tool input despite billing thousands of output tokens. The transient native
client reuses the SDK-held credential without restoring it to environment or audit data. Provider/model, evidence, criteria and token
limit stay fixed; Phase 2, Phase 4 and other roles retain their clients. The explicit
`native-ranking-tool-first-v4` protocol participates in cache binding and audit telemetry.
The wire schema requires every proposal field explicitly and exactly the current PASS count;
it does not change the persisted opinion schema. Repair groups errors without dropping later
malformed rows and reports correlated detail coverage before the full binder can run. It also
identifies selected Arms missing support with their allowed references, and missing/foreign
ranking references. These are validation hints, never an automatic scientific selection.
The failed exams and interrupted earlier regression remain in the audit records.

## Acceptance scope

Fixtures use realistic seven-scaffold NK2R Design context and varied synthetic measurements;
expanded candidate populations are capacity tests, not new biological results.

- 3 Arms × 20 PASS: first input below 60k characters including Skill/reference/tool schema;
  malformed submission followed by repair below 70k; all 60 candidates and three Arms retained;
  exact Scale proposal; original/merged evidence validation and durable restart.
- 5 Arms × 40 PASS: deterministic packet construction below the unchanged 100k guard;
  test growth and retain all 200 candidates. This does not promise arbitrary population sizes.
- Duplicate, omitted or foreign candidates, missing required notes, unknown metric references,
  oversized malformed prose and exhausted repair budgets remain rejected.
- Legacy opinions and real saved NK2R evidence must replay without modifying old records.

Measured results and exact tested commits are recorded in the completion section when
the frozen implementation finishes its live-model and regression checks.
