# Evidence and mechanism questions

Migrated reasoning contract from the legacy target/site, numbering, special-target and GPCR
playbooks. These are conditional questions, not approved empirical claims or parameters.

General protein reasoning is the default: exact identity/mapping, biological goal, desired and
forbidden effects, assay/readout, structure context, accessible geometry and credible alternatives.
Current messages clarify the immutable goal. A literature source is not the user's approval.

Standard Research sequence (decision sufficiency, not a literature review):

1. Reuse approved identity/mapping; form usually 3-6 questions that can change this Gate's
   ranking, hard constraints or major risk. The table below is a conditional reasoning aid,
   not a set of required searches. Do not mechanically traverse every evidence topic.
2. Read the few necessary primary/official records and candidate facts, with exact source,
   construct/state/assay transfer limits. Prefer strongest relevant evidence over page count.
3. Map literature positions through the approved mapping. Compare initial literature/scan
   candidates and meaningful alternatives, including full-binder access and hard constraints.
4. If a focused contradiction/alternative literature search can change the initial ranking,
   run it and read important opposing evidence. Otherwise retain the gap explicitly and stop.
5. Stop when additional inquiry is unlikely to change ranking, a hard constraint or major
   risk. Explicit unresolved issues after reasonable inquiry are valid; say what experiment
   could discriminate them. Do not fill unused calls or unread annotation pages.
6. Handoff decision_questions, exact query/passage citations, any actual contradiction-search IDs,
   stopping reason and consequential uncertainty. Full sources stay durable; fresh synthesis
   receives the trusted dossier, without research/tool history. No stopping claim is approval.

For each mechanism state observation, interpretation, alternative, predicted assay result and
falsifier. Do not turn exposure, contact, curated state or a high model score into efficacy.

| Goal/context | Required questions and alternative | Discriminating evidence |
| --- | --- | --- |
| PPI blocking | Direct footprint occlusion vs adjacent steric interference vs allostery; full partner/assembly access | Competition, function, target integrity, partner/context controls |
| Enzyme/cleft | Penetration vs rim/entry blockade vs allosteric patch; substrate path and full-VHH mouth clearance | Kinetics, fold/activity controls; penetration must be observed, not inferred from CDR length |
| State sensor | Passive sensing vs stabilization vs competition vs expression/format artifact | State-selective binding plus dose-dependent function/ensemble and partner controls; low perturbation is co-primary |
| Imaging | Stable accessible nonfunctional site vs state-sensitive perturbing site; label/linker/valency/delivery | Localization and function/turnover/dose controls; fluorescence is not low perturbation |
| Structural chaperone | Desired-state stabilization vs wrong-state enrichment; rigidity/assembly and native partner mimicry | Independent state markers, structure quality and biochemical function |
| Membrane/glycan | Topology/side, membrane orientation, mature full assembly, glycoform occupancy and framework collision | Full/cell-surface context and glycoform/side controls; a missing glycan model is not absence |
| IDR/flexible loop | Motif, ensemble or partner/PTM-dependent folding; induced structure vs pre-existing state | Ensemble/conditional folding evidence; a low-confidence single pose cannot support precise geometry |
| Amyloid/repeated surface | Monomer/oligomer/fibril, polymorph, end polarity vs side binding, avidity/crosslink | Assembly-specific and elongation/side controls; different fibril ends are not equivalent |
| Multimer/composite epitope | Native assembly vs crystal contact, stoichiometry, cross-subunit access and concentration | Native assembly evidence and matching assay material; monomer crop cannot validate composite epitope |

Conditional GPCR branch only after verified receptor identity and family hierarchy:

- For both activating and inhibitory extracellular GPCR binder goals, when the candidate set
  contains a verified extracellular site covering the orthosteric ligand entrance or outer
  vestibule and extending sufficiently far along the orthosteric pocket to support a direct
  ligand-occupancy or receptor-conformation mechanism, treat it as the default provisional
  first-ranked hypothesis if coordinate mapping is valid, surface exposure is reasonable and
  there is no clear whole-VHH approach conflict. Peripheral ECL-only patches and other surfaces
  without an orthosteric mechanistic connection default later. Pocket-lining ECL residues are part
  of the orthosteric candidate, not evidence that it is merely peripheral.
- Pocket depth alone is insufficient. Distinguish a CDR-reachable entrance/outer vestibule from
  a narrow inner cavity that only a small molecule can enter while the VHH framework cannot
  approach. Mapping/access conflicts, functional mismatch or stronger receptor-specific contrary
  evidence can overturn the default, but state the reason explicitly. Orthosteric engagement alone
  does not prove whether the binder activates or inhibits.
- Class A: distinguish extracellular pocket rim/vestibule from inaccessible lipid-facing TM
  surface; peptide receptors may require N-terminus/ECL context. Ligand binding is not function.
- Class B1: large ECD capture and TMD activation can be different mechanisms; preserve both domains.
- Class B2: cleavage, GAIN/GPS and Stachel exposure may control state and access.
- Class C: VFT/linker/dimer context may be causal; a crystal dimer is not automatically physiological.
- Class F: CRD/lipid and TMD context can differ; do not apply Class A pocket heuristics blindly.
- Rare/unresolved families: retain receptor-specific evidence and uncertainty, not a guessed class.

Default extracellular delivery excludes an intracellular transducer mechanism unless the goal
explicitly authorizes intrabody access. That verified compartment conflict is hard-invalid rather
than a lower-ranked A/B/C alternative. A signed membrane frame must come from validated geometry.
Compare target/counterstate, ligand/transducer, construct fusions/mutations and full framework
access. Family rules may generate hypotheses, not assign a fused score or choose a winner.

Hard mapping/coordinate/exclusion failures block executable hotspots. Scientific access or
mechanism uncertainty remains visible for the Scientist and optional Judge; an override does not create
missing evidence or validate an impossible representation. If the existing backend cannot
represent necessary ensemble, multichain, glycan or ligand semantics, explicitly report the
capability gap instead of silently deleting that context.
