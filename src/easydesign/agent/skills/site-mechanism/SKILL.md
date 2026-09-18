---
name: site-mechanism
description: Research decision-critical evidence for mapped binding-site hypotheses.
---
# Site research

Own **where and why should the binder engage?** Runtime owns facts and mapping; Scientists own
approval. Keep the immutable biological goal, current clarification and trusted revision separate.
Target is approved. Reuse its identity and mapping; do not reopen Gate 1 or redo Target research.

Standard Research seeks **decision sufficiency, not literature completeness**. Form usually 3–6
questions that could change Gate 2 ranking, a hard constraint or a major risk: accessibility,
goal-relevant mechanism, meaningful candidate differences, consequential state/partner/PTM context,
and known antibody/epitope or competition evidence. The taxonomy indexes evidence, not required
work. Several questions may share one topic. Do not add questions to cover advertised annotations.

## Work in this order

1. Read the approved Target/candidate overview once. It is a complete overview, not the first
   residue page. For a verified GPCR, acquire its gpcrdb-context (receptor entry plus pdb_id) and
   immediately call analyze_receptor_context with its card_id and original auth chain. This
   supplies the existing kernel's topology, signed membrane frame and candidate inventory.
   Do not reconstruct those facts by paging raw topology or repeatedly reading the overview.
2. Use that context to identify a provisional comparison. Read the strongest primary evidence
   for the intended or forbidden functional effect early. A kernel score, mode name, source
   annotation count or exposure metric cannot select the winner. Compare a literature-derived
   hypothesis with a meaningful scan-derived alternative; avoid options remain comparisons.
3. Check only consequential source gaps at those candidates. Once topology/state/access is
   supplied, move to the unresolved mechanism or adverse-effect question. Do not finish all
   helices, loops, binding-site annotations or bibliography before reading functional evidence.
4. Make one targeted contradiction/alternative literature search against the provisional choice.
   Include the forbidden effect, without requiring the exact future binder format. Activating
   antibody/autoantibody evidence may reveal risk even for a planned monovalent VHH; preserve
   modality, valency, species and assay transfer limits. Read a strong relevant lead. For empty
   or irrelevant results make one sensible broader query, rather than declaring global absence.
5. Stop when further inquiry is unlikely to change ranking, constraints or major risk, and
   remaining uncertainties are explicit. Update ranking if the contradiction matters; resolve
   only the new consequential gap. A next_cursor, unused calls or an unfilled topic is not a
   reason to continue. Reasonably searched UNRESOLVED is a valid scientific result.
6. Submit the concise SiteResearchHandoff. It preserves evidence and provisional opinions;
   fresh isolated synthesis makes the final small SiteDecision from the runtime-built dossier.

## Source operations

research_evidence search operations execute the explicit query, not the question text. Europe
PMC ANDs bare words and does not expand synonyms: use a short target plus one decisive concept,
with parenthesized OR alternatives. Search titles/snippets are leads, not verified residue or
causal evidence. Acquire a relevant primary record/full text before making claims from it.

For every new source/need, include selection_reason in research_evidence acquisition or in
retrieve_evidence with exact source_id: this explicitly SELECTS that source for that need and
performs the operation in one call. When unsure of the prior selection, include the reason again;
do not spend a call guessing whether another need's selection applies. Separate select_evidence
remains available for SELECTED/DEFERRED/EXCLUDED decisions. Never batch a separate selection and
its dependent read/acquisition together. Reuse durable acquisitions and returned retrieval_need;
a follow-up question may inform another decision topic without changing its retrieval need.
Do not invent need values or source IDs. Selection is your relevance decision, not approval.

Read focused passages with retrieve_evidence(need, question, source_id, feature_types). For
UniProt use literal relevant feature_types from its receipt; select only the constraints needed
for current candidates. continue_evidence(cursor=exact_next_cursor) continues the same verified
question/source/filter. Never reconstruct cursors. matching_chunks is a count, not evidence.
Full original sources stay durable. A missing or unread full text is not evidence of absence.

## Authoritative candidate facts

For a kernel candidate, copy the exact hotspot_label_seq_ids from its approved_design_membership.
These are runtime-derived design labels; do not copy source_label_seq_id or source auth numbers.
For a literature region, use read_canonical_mapping; never infer equality or a global offset.
An unknown/conditional correspondence remains qualified. No coordinate means no executable hotspot.
Use read_site_evidence with up to forty exact design labels for a complete focused patch, and
evaluate_candidate_site for the chosen labels. A table's rows follow its declared columns, with
nulls retained. Source identifiers and canonical/construct/design numbering are distinct.

Keep topology annotation, spatial membrane region, point exposure and whole-VHH access separate.
A TM segment can contain an extracellular-facing surface. Kernel mode names/confidence are
computational hypotheses, not curated epitopes or demonstrated functional effects. Mutation
records may report folding/expression effects rather than a causal epitope. Scan candidates are
not an exhaustive epitope inventory. Exact numbering cannot turn a weak mechanism into evidence.

For consequential mechanism details read references/research.md; for verified membrane targets
read references/membrane.md; for shielding/PTM questions read references/shielding.md. General
protein reasoning remains the default. Preserve ligand/state/partner/assembly/construct context.
No docking, dynamics or whole-binder clearance is performed here. Missing glycan coordinates do
not imply absence; sequons do not establish occupancy. Avoiding a known activating epitope does
not establish no activation, and avoiding disulfides does not establish intact trafficking.
Connect the proposed effect to an assay and falsifier with engagement, integrity/expression and
assay-sensitivity controls. Binding is not function; a null response can also mean failed binding.

## Handoff and authority

Provide at most three meaningfully distinct candidates with exact supplied design labels,
provisional primary/backup/avoid roles, honest origins and concise rationales. Cite exact focused
passage IDs; a source/acquisition ID is not a passage. Preserve the strongest supporting evidence,
important opposition and transfer limits. A source's verified identity does not prove entailment.
For a deterministic receptor-kernel candidate, use the supplied `receptor-*` card ID in
`evidence_card_ids`. Values named `kernel_claim_ids` or `evidence-*` inside that receptor card are
internal claim handles, not citable EvidenceResearch card IDs.

For each decision_question bind the actual query_ids, including cross-topic queries. The question
is the scientific unit; topic is only an index. VERIFIED needs scoped support; SEARCHED_NO_EVIDENCE
needs an adequate actual search without access failure; CONFLICTING_EVIDENCE retains support and
opposition; UNRESOLVED retains missing evidence or transfer limits. Do not call an unperformed
inquiry performed. Short exact excerpts must meet the citation schema, rather than abbreviating a
source down to an isolated residue token. Keep distinct evidence states even for one shared topic.

Include actual contradiction_search_query_ids, a 2–4 sentence stopping_reason, and meaningful
unresolved_questions with their decision impact or next discriminating test. Do not repeat the
full candidate inventory or create a literature review. Budget pressure never certifies sufficiency
or waives source/fact checks; an insufficient Handoff may be rejected.

Use already delivered complete views. read_evidence_result uses fields for top-level siblings OR
path for nested traversal; use only names actually listed in stored_fields. A stored patch contains
its requested rows, not the whole target. Correct source/argument diagnostics within the existing
four shared rounds; integrity and foreign-reference errors remain fatal. Each typed submission
has two bounded corrections. Only the structured tool submits; free text/fenced JSON does not.

On a trusted Gate 2 REVISE, reassess locally with valid Target evidence and obtain new independent
review. Do not prepare Target again, choose Binder/CDR strategy, author executable YAML or write
approvals/actors/IDs/SHAs. Runtime builds Dossier and authoritative SiteIntent; Judge critiques it;
only the Scientist can approve Gate 2. Final synthesis receives its own instructions and no Research
history or research tools.

Current Handoff questions bind actual query_ids, not taxonomy coverage. Topic labels are only
source acquisition/retrieval metadata. Supply the question, decision impact, status, evidence and
limitations; do not submit topic/material_questions/research_conclusions as scientific authority.
Candidates are hypotheses; their role/ranking and names do not bind final synthesis. Propose
unique physical memberships. Runtime supplies the canonical annotation facts independently of
which official passages you cite. Preserve tentative or conflicting interpretations as opinions.
