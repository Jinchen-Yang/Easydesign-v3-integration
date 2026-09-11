# Evidence and mechanism questions

Migrated reasoning contract from the legacy target/site, numbering, special-target and GPCR
playbooks. These are conditional questions, not approved empirical claims or parameters.

General protein reasoning is the default: exact identity/mapping, biological goal, desired and
forbidden effects, assay/readout, structure context, accessible geometry and credible alternatives.
Current messages clarify the immutable goal. A literature source is not the user's approval.

Research sequence:

1. Reuse approved accession/species/construct/mapping. Compare an additional reference only
   when it changes the scientific question; do not restart Target identity work.
2. Search same-target structures/complexes and their primary publications. Retrieve the records.
3. Search independent epitope/mutation, competition/function, state and shielding evidence.
4. Compare source construct, state, ligand, partner, maturation and assay to this project.
5. Separate direct current-context E1, scoped-transfer E2, computational E3 and hypothesis E4.
6. Retain counterevidence, negative results and retrieval failures. Unknown is not not-searched.
7. Map any literature residues through the approved coordinate mapping. Author integer alone is
   insufficient: chain, insertion code, precursor/mature offsets and missing positions matter.
8. Compare literature-derived and scan-derived sites, with different primary/backup hypotheses
   and explicit avoid/unresolved regions. A full binder must have a plausible access route.

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

- Class A: distinguish extracellular pocket rim/vestibule from inaccessible lipid-facing TM
  surface; peptide receptors may require N-terminus/ECL context. Ligand binding is not function.
- Class B1: large ECD capture and TMD activation can be different mechanisms; preserve both domains.
- Class B2: cleavage, GAIN/GPS and Stachel exposure may control state and access.
- Class C: VFT/linker/dimer context may be causal; a crystal dimer is not automatically physiological.
- Class F: CRD/lipid and TMD context can differ; do not apply Class A pocket heuristics blindly.
- Rare/unresolved families: retain receptor-specific evidence and uncertainty, not a guessed class.

Default extracellular delivery excludes an intracellular transducer mechanism unless the goal
explicitly authorizes intrabody access. A signed membrane frame must come from validated geometry.
Compare target/counterstate, ligand/transducer, construct fusions/mutations and full framework
access. Family rules may generate hypotheses, not assign a fused score or choose a winner.

Hard mapping/coordinate/exclusion failures block executable hotspots. Scientific access or
mechanism uncertainty remains visible for Judge and scientist; an override does not create
missing evidence or validate an impossible representation. If the existing backend cannot
represent necessary ensemble, multichain, glycan or ligand semantics, explicitly report the
capability gap instead of silently deleting that context.
