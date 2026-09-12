---
name: site-mechanism
description: Interpret approved structural and biological evidence to propose mapped sites and hotspots.
---

# Site & Mechanism

Own **where and why should the binder engage?** Propose science; runtime owns hard facts and
Scientists own decisions. Target is already approved. Keep the immutable goal, current message
and trusted revision separate. Reuse the approved identity/mapping; do not repeat Target work.

## Research and evidence

Standard Research seeks **decision sufficiency, not literature completeness**. From the
biological objective, approved Target and Gate 2, form usually 3-6 decision-critical questions.
The topic taxonomy indexes evidence; it is not a checklist to complete. Ask only what could
change site ranking, a hard constraint or the major risk assessment. Typical questions concern
whole-binder access, goal-relevant mechanism/function, consequential state/ligand/partner or
membrane/glycan/disulfide constraints, known antibody/epitope/competition evidence, and a real
scientific distinction between candidate A/B/C. Combine related issues; do not expand the list
just because a database advertises more annotation types.

Start from the approved Target and supplied candidate facts. Once the relevant candidate's
access/topology question is answered, stop that source's pagination; unrelated loop/helix or
bibliography coverage is not required. Spend the next inquiry on a remaining decision gap.

Use research_evidence for those missing facts. Query keywords execute the search; question
states the decision it informs. Acquire requested and relevant primary records plus the few
necessary official structure/database records. Search titles are leads, not residue or causal
evidence. If matches are empty or irrelevant, make one sensible broader query; do not keep
adding desired terms. Search the target and decisive effect first. Do not require all synonyms
or the eventual binder format together: antibody, autoantibody and nanobody evidence may inform
the same mechanistic risk, with explicit modality/valency/species transfer limits.
Supply selection_reason to acquire a selected source atomically. Selection is relevance, not
entailment; reuse existing acquisitions. A relevant query can inform several topics using its
returned query_id; do not repeat the same inquiry merely to fill another taxonomy category.
For another retrieval need, select_evidence with the exact provider/identifier/need.

Read focused passages with retrieve_evidence(need, question, source_id, feature_types). For UniProt
annotations, select literal feature_types shown in its receipt rather than paging bibliography.
Continue only a needed page with continue_evidence(cursor=exact_next_cursor); it restores the
original verified question/need/source/filter. For a different question start a new retrieval.
Never edit/decode/rebuild cursors. matching_chunks is an integer count, not passage text or a
list. Read cards for the returned page or continue_evidence for its next_cursor; changing a
count's offset/limit does not reveal evidence. Do not repeatedly request the same stored value.
Cite exact returned passage card IDs and short excerpts.
Source IDs, source acquisition card IDs and focused passage card IDs are different identifiers.

Stop policy:

1. Obtain initial candidate facts and a provisional ranking from enough relevant primary and
   official evidence. Reuse approved identity and supplied kernel facts.
2. Then perform one targeted contradiction or meaningful-alternative literature search: what
   evidence would reverse the ranking, invalidate an access assumption or reveal the forbidden
   functional effect? Include the user's forbidden effect, rather than only the preferred
   epitope's geometry. Use a short target-plus-effect query without requiring the exact binder
   format. Unrelated hits do not establish saturation until a sensible broader check. Read a
   strong relevant lead, including adverse findings. If it changes the
   recommendation, update the comparison and resolve only the new consequential issue.
3. Ask: is more searching reasonably likely to change Gate 2 ranking, a hard constraint or a
   major risk? If no, STOP RESEARCH and submit SiteResearchHandoff now. Remaining call budget,
   a next_cursor, an unread source section or an unfilled taxonomy topic is not a reason to
   continue. A negative/unchanged check can establish bounded saturation, never global absence.
4. If an important issue remains unresolved after reasonable inquiry, state its effect on the
   decision, the missing evidence and the next discriminating experiment. UNRESOLVED is a legal
   stopping state; it may warrant DISCOURAGED or insufficient evidence, not endless retrieval.

Record decision_questions with their actual query_ids, statuses, strongest relevant supporting
and important opposing/scoping passage citations, and decision_impact. Cite exact excerpts.
Record contradiction_search_query_ids and stopping_reason, including whether ranking changed.
VERIFIED is scoped source support, never certified efficacy. SEARCHED_NO_EVIDENCE needs an
actual adequate search without access failure; it does not mean no literature exists.
CONFLICTING_EVIDENCE preserves support and contradiction. UNRESOLVED preserves inquiry/access/
transfer limits. An unperformed inquiry cannot be relabeled as performed; peripheral unsearched
issues belong in remaining uncertainty, not an expanding material-topic task list.

In synthesis, use scope=mechanistic for biological goals and address the decision-critical
questions in SiteIntent. Merge conclusions sharing a topic; reuse relevant query_ids even when
that query was indexed under another topic. Do not add a conclusion for every available topic.
The existing source/quote/primary-eligibility checks and independent Judge remain mandatory.
Read /skills/site-mechanism/references/research.md only for consequential mechanism reasoning.

## Mapped candidate comparison

Use the supplied scan overview and literature hypotheses to choose focused residue reads.
read_site_evidence accepts up to forty exact approved design labels and returns the complete
requested patch, with no offset. Omit labels for the overview. facts_table
rows follow mapping_columns then metric_columns, with every null retained. A canonical null is
unknown; a non-null conditional row remains a correspondence with its mapping qualification.
Design labels, construct positions, canonical positions and source author IDs are distinct.
For canonical annotation positions use the supplied approved_design_mapping or call
read_canonical_mapping; these return all matching
rows, observed design labels and unmapped/missing-coordinate cases. Preserve every qualification.
Map literature positions through those supplied rows; never infer equality or a global offset.
compare_reference_identity is only for an additional retrieved reference; it requires the exact
uniprot-record source card_id. It does not approve or replace the existing Target mapping.

Compare literature-derived and scan-derived candidates, marking origin and primary/backup/
avoid/unresolved role. Literature-derived sites cite focused source cards. A backup should test
a different plausible mechanism or approach, not a cosmetic residue shift. Never invent options.
Evaluate selected hotspot labels with evaluate_candidate_site before submission. Check components,
exposure and local geometry; SASA/heuristic scores do not establish epitope usefulness or affinity.
A residue may be exposed while a whole VHH cannot approach. No docking, dynamics or affinity
calculation is available here: state approach/clearance as hypotheses and identify missing tests.
Kernel candidates are a limited hypothesis set, not an exhaustive list of accessible epitopes.
Mutation-record counts alone do not rank functional relevance or whole-binder accessibility.

For each biological proposal connect desired/forbidden effects, observation, interpretation,
alternative, discriminating assay and falsifier. Enzyme inhibition needs integrity/interference
controls; a passive sensor needs sensing/stabilization/competition/format alternatives and
independent perturbation controls. State specificity needs relevant state/counterstate evidence,
never exposure or one structure alone. User-supplied biology remains labeled as user-supplied.

For a verified GPCR, acquire gpcrdb-context with identifier=exact_receptor_entry and pdb_id when
known. The PDB code alone is not the receptor identifier. After a complete context card arrives,
call analyze_receptor_context alone, with that card_id and original auth chain, before paging
topology. Split TOOL_BATCH_TOO_LARGE diagnostics into smaller reads; no tool in that batch ran. Read /skills/site-mechanism/references/membrane.md for this branch. Distinguish original
source auth/label numbering from approved design labels. Preserve membrane orientation, state,
ligand, fusion/partner, full assembly and extracellular-delivery limitations. Intracellular
binding is not an extracellular epitope. Unresolved membrane geometry stays unresolved.
For PTM/glycan questions read /skills/site-mechanism/references/shielding.md. A motif is not
occupancy; absent coordinates/annotations are not absence of glycans, partners or shielding.

## Working context and submission

Earlier full_result outputs are historical snapshots, not proof that later research was absent.
Use complete supplied scientific content directly. Archived/partial views are not the whole
source; explicitly read a consequential missing field, never infer omitted values. Full results
remain durable. read_evidence_result uses fields=['a','b'] for top-level siblings OR
path=['a','b'] for one nested traversal, never both. Offset/limit index that stored list/text,
not residue labels. stored_fields lists the actual root keys of each original full_result.
Different tools have different keys: mapping lookups use matches, source passages use cards,
and a residue page uses facts. Never assume all results have facts. A stored residue page
contains only its requested rows, not the whole target.
Correct supplied INVALID_FIELD_PROJECTION/source-selection diagnostics within four shared
model correction rounds; parallel errors in one tool batch share one round. Foreign references, corruption and authority errors are not recoverable argument errors.

Follow the current runtime stage and shared budget, which includes framework summaries.
In Evidence Research, finish with SiteResearchHandoff: mapped candidates with focused citations,
decision_questions, actual contradiction-search IDs, stopping_reason and unresolved questions. Runtime builds the dossier
from original evidence; this handoff creates no Site proposal. In isolated synthesis, research
is complete: the runtime supplies references/synthesis.md and the dossier, then accepts only
SiteIntent. The research workflow above is not part of that fresh stage's instructions.
Give positive evidence, mechanism, access, approach, meaningful alternatives, risks and
uncertainties. SUPPORTED is limited to actual evidence; poor access/shielding/unknown membrane
orientation may be DISCOURAGED but testable. Illegal mapping/coordinates or explicit hard
exclusions are runtime BLOCKED; favorable prose or override cannot make them executable.
Free text/fenced JSON cannot submit. Each typed contract permits two persisted output corrections
within the same shared model-call budget; budget pressure never resolves uncertainty or waives
factual/source checks.

On Gate2 REVISE, reassess locally with valid Target evidence and trusted instructions, then obtain
new independent review and Gate2. State any upstream assumption needing correction. Do not
prepare the target again, choose Binder/CDR strategy, write approvals/actors/IDs/SHAs/bindings or
YAML. Runtime attaches identities and compiles the proposal; only a Scientist can approve it.

The receptor-candidate-overview is complete for its declared fields: every existing candidate's
scientific metadata and listed source-residue columns are supplied together, with topology/state/
membrane context. Candidate/member values are ordinary JSON values; no pointer expansion is
required. Use that view directly. For a consequential missing source field, use
fields=['state','membrane','topology_summary'] for context and
path=['candidate_overview', MODE, INDEX] for one candidate. Do not page topology.residues
from zero to reconstruct an already supplied overview. Other source fields are focused reads. Source auth/label IDs are not design IDs; verify chosen canonical correspondences with
read_canonical_mapping and retain ambiguity. Candidate scores and confidence are kernel heuristics,
not proof of extracellular VHH access or the desired functional effect.
