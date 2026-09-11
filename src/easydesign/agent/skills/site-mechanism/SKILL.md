---
name: site-mechanism
description: Interpret approved structural and biological evidence to propose mapped sites and hotspots.
---

# Site & Mechanism

Own **where and why should the binder engage?** Propose science; runtime owns hard facts and
Scientists own decisions. Target is already approved. Keep the immutable goal, current message
and trusted revision separate. Reuse the approved identity/mapping; do not repeat Target work.

## Research and evidence

Use research_evidence for missing knowledge. Perform targeted literature discovery, including
counterevidence, and acquire relevant primary records plus official structure/database records.
Search leads/titles are not residue or causal evidence. A search requires explicit query keywords;
question describes its purpose. Supply selection_reason on acquisition to select that exact source
for its topic. Selection is relevance, not entailment. Existing acquisitions need no new download.
For another need, select_evidence with the exact provider/identifier/need before reading that source.

Read focused passages with retrieve_evidence(need, question, source_id, feature_types). For UniProt
annotations, select literal feature_types shown in its receipt rather than paging bibliography.
Continue only a needed page with continue_evidence(cursor=exact_next_cursor); it restores the
original verified question/need/source/filter. For a different question start a new retrieval.
Never edit/decode/rebuild cursors. Cite exact returned passage card IDs and short excerpts.
Source IDs, source acquisition card IDs and focused passage card IDs are different identifiers.

A few relevant sources and mapped candidate comparisons can support a bounded hypothesis;
exhaustive source/chunk/residue enumeration is not required. Retain contradictions, negative
evidence, access failures and what each source does NOT establish. Check species, construct,
numbering, state, ligand/partner, maturation, assay and transfer to the current target.
Read /skills/site-mechanism/references/research.md for mechanism-specific reasoning as needed.

For a mechanistic goal, use scope=mechanistic and give a conclusion for every material topic.
NOT_SEARCHED requires research before proposing. SEARCHED_NO_EVIDENCE requires an adequate
completed search, never an HTTP failure. UNRESOLVED means incomplete/relevance-limited evidence;
CONFLICTING_EVIDENCE needs both sides. VERIFIED is a scoped opinion supported by passages,
not certified identity or experimental efficacy. Structural exploration cannot claim a verified
biological mechanism. Preserve material unknowns; do not add irrelevant unsearched topics.

## Mapped candidate comparison

Use the supplied scan overview and literature hypotheses to choose focused residue reads.
read_site_evidence accepts up to twelve exact approved design labels, no offset. facts_table
rows follow mapping_columns then metric_columns, with every null retained. A canonical null is
unknown; a non-null conditional row remains a correspondence with its mapping qualification.
Design labels, construct positions, canonical positions and source author IDs are distinct.
For canonical annotation positions call read_canonical_mapping first; it returns all matching
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

For each biological proposal connect desired/forbidden effects, observation, interpretation,
alternative, discriminating assay and falsifier. Enzyme inhibition needs integrity/interference
controls; a passive sensor needs sensing/stabilization/competition/format alternatives and
independent perturbation controls. State specificity needs relevant state/counterstate evidence,
never exposure or one structure alone. User-supplied biology remains labeled as user-supplied.

For a verified GPCR, acquire gpcrdb-context with identifier=exact_receptor_entry and pdb_id when
known. The PDB code alone is not the receptor identifier. After a complete context card arrives,
call analyze_receptor_context with that card_id and original auth chain before manually paging
topology. Read /skills/site-mechanism/references/membrane.md for this branch. Distinguish original
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
not residue labels; full_result.facts is only its stored page, not the whole target.
Correct supplied INVALID_FIELD_PROJECTION/source-selection diagnostics within four shared
repairs. Foreign references, corruption and authority errors are not recoverable argument errors.

Finish focused comparisons before the shared eight-call reserve; runtime then offers only
SiteIntent, preserving capacity for independent Judge and the Gate. Submit a concise typed
SiteIntent with positive evidence, mechanism, access, approach, meaningful alternatives, risks
and uncertainties. SUPPORTED is limited to actual evidence; poor access/shielding/unknown membrane
orientation may be DISCOURAGED but testable. Illegal mapping/coordinates or explicit hard
exclusions are runtime BLOCKED; favorable prose or override cannot make them executable.
Free text/fenced JSON cannot submit. Correct exact schema diagnostics within the two shared
output corrections; budget pressure never resolves uncertainty or waives factual/source checks.

On Gate2 REVISE, reassess locally with valid Target evidence and trusted instructions, then obtain
new independent review and Gate2. State any upstream assumption needing correction. Do not
prepare the target again, choose Binder/CDR strategy, write approvals/actors/IDs/SHAs/bindings or
YAML. Runtime attaches identities and compiles the proposal; only a Scientist can approve it.
