# GPCR Mechanism, State, and Selection Logic

## 使用原则

本文件用于把“希望受体被激活或抑制”拆成可以反证的机制、状态与接近路径假设。
必须先明确功能测定、目标状态、反状态、递送侧和 binder 形态，再讨论残基；结合膜方向检查完整
scaffold，而不只检查 CDR 尖端。结合位点、状态偏好和功能效应是三类不同证据，不得相互替代。

## 目录

- [设计意图与残基角色](#define-the-design-intent)
- [抑制、激活与状态选择机制](#mechanism-branches)
- [状态与膜方向](#assign-receptor-state)
- [hard gate 与风险](#apply-hard-gates)
- [候选比较与 assay](#compare-without-a-fused-score)

Select a hotspot to test a causal pharmacology hypothesis, not merely to occupy an attractive surface. Define the desired function, target state, counterstate, access route and assay before ranking geometry.

## Define the Design Intent

Record all fields explicitly:

- `mode`: `inhibit`, `activate`, or `both`.
- `pharmacology`: competitive antagonist, inverse agonist, negative allosteric modulator, positive allosteric modulator, agonist mimic, state-selective binder, structural chaperone, sensor/imaging binder, dimer modulator, autoinhibition stabilizer or autoinhibition releaser.
- `endogenous_input`: ligand class and known recognition domains.
- `target_state`: active, inactive, intermediate, ligand-specific state or unresolved.
- `counterstate`: the state the binder should avoid or discriminate against.
- `binder_format`: VHH, antibody, peptide binder or other scaffold; include approximate size and reach.
- `delivery_side`: extracellular by default, intracellular only when explicitly authorized and biologically feasible.
- `assay`: the primary functional readout plus expression/trafficking and nonspecific-loss controls.
- `falsifier`: an observation that would reject the mechanism.

Do not convert “binds receptor” into “activates” or “inhibits.” Binding, state preference and functional effect require separate evidence.

## Separate Three Residue Roles

### Functional site

Define the complete receptor region causally involved in ligand recognition, conformational coupling, autoinhibition or oligomerization. It may be larger than a designable interface.

### Conditioning hotspot

Select a small, spatially coherent subset that forces the designed binder toward the intended functional geometry. Choose residues because they constrain pose and mechanism, not because a model accepts a long list.

### Validation residue

Track residues used to test the hypothesis, including mutational controls, state markers and residues expected to remain untouched. Do not feed validation-only residues into the hotspot list.

## Mechanism Branches

### Inhibition

Evaluate these hypotheses independently:

| Hypothesis | Preferred region | Required causal claim | Common failure |
| --- | --- | --- | --- |
| Competitive cap | ECD, pocket rim or extracellular vestibule | Blocks ligand entry or docking | Binder sits near the site but leaves the ligand path open |
| Orthosteric occupancy | Reachable pocket/recognition cleft | Directly competes with endogenous input | Protein framework cannot reach the buried volume |
| Negative allostery | Validated extracellular allosteric surface | Stabilizes a signalling-incompetent state | Surface binding has no coupling to function |
| Inactive-state lock | State-differential extracellular epitope | Raises the barrier to activation | Epitope is equally exposed in active state |
| Autoinhibition stabilization | ECD/GAIN/VFT or endogenous blocking interface | Preserves a native closed/inhibited arrangement | Construct lacks the native blocking element |
| Trigger blockade | Tethered agonist exposure/insertion path | Prevents release or engagement of the trigger | Cleavage state is unknown |
| Dimer modulation | Supported inter-protomer interface | Disrupts or locks a required arrangement | Interface is only a crystal contact |

The default inhibition prior is “extracellular recognition region plus pocket entrance/vestibule,” not an unconditional outer ring. Include deeper pocket residues only when an accessible CDR tip can reach them and their occupancy is mechanistically causal.

### Activation

Evaluate these hypotheses independently:

| Hypothesis | Preferred region | Required causal claim | Common failure |
| --- | --- | --- | --- |
| Agonist mimic | Ligand trigger/core site | Reproduces essential agonist contacts and direction | Binder occupies the site without applying the needed coupling geometry |
| Active-state stabilization | State-specific extracellular epitope | Preferentially binds and stabilizes the active ensemble | State label is inferred from ligand name only |
| Positive allostery | Validated extracellular allosteric site | Enhances endogenous agonist efficacy/potency | Binding merely increases apparent surface retention |
| Autoinhibition release | Endogenous blocking interface | Displaces or unlocks the inhibitory element | Binder instead stabilizes the closed state |
| Tethered-agonist engagement | GAIN/GPS/TMD entry path | Exposes, mimics or stabilizes the tethered trigger | Native cleavage and fragment association are absent |
| Productive dimer lock | Supported active oligomer geometry | Stabilizes a signalling-competent arrangement | Crosslinking prevents rather than promotes motion |

The default activation prior is “target-state pocket core or causal trigger center,” but apply family exceptions. Class B1 peptide receptors, Class C VFT/dimers, Adhesion GPCR tethered agonists and Class F ECD/lipid coupling may require a domain or interface site rather than a deeply buried TMD center.

### State-Selective Chaperone or Sensor

When the goal is structural capture, imaging or conformational sensing, optimize state discrimination and assay compatibility rather than functional direction. Keep any predicted agonism/inhibition as an unverified secondary hypothesis.

## Assign Receptor State

Require at least two compatible state signals when possible:

- Curated GPCRdb structure state.
- Bound agonist, antagonist, inverse agonist or modulator with known pharmacology.
- G-protein, arrestin or mimetic transducer engagement.
- Receptor-specific activation markers or global TM rearrangement.
- Same-receptor active/inactive structural comparison.
- Functional construct metadata and stabilizing mutations.

Do not infer state from a ligand label alone. Record `active`, `inactive`, `intermediate`, `mixed`, `predicted` or `unresolved`, along with evidence and contradictions. Keep target state and counterstate structures separate and hash each input.

Use state comparisons to ask:

1. Is the candidate present, exposed and geometrically coherent in the target state?
2. Is it absent, occluded or differently arranged in the counterstate?
3. Does the difference remain after accounting for construct changes, missing loops and different partners?
4. Would binding stabilize the intended state or merely recognize it after the causal event?

## Establish Membrane and Approach Geometry

Represent membrane context with an extracellular-to-intracellular normal, bilayer midplane, approximate headgroup boundaries, source and confidence. Do not derive a normal from TM residue numbers alone.

Classify each candidate residue:

- `extracellular_exposed`
- `vestibule_facing`
- `pocket_facing`
- `lipid_facing`
- `intracellular_exposed`
- `buried`
- `unresolved`

Record a candidate-level approach vector or cone. Check the entire binder, not only the contacting CDR tip:

- Can the CDR tip enter the cavity without threading through an impossible aperture?
- Does the framework remain outside the membrane and avoid the ECD, glycans, neighbouring protomer and bound ligand/partner unless displacement is intended?
- Is there enough room for pose diversity without rotating the scaffold into the bilayer?
- Does the path approach from the authorized biological side?

Treat a deep, narrow cavity as unavailable when only a small molecule can occupy it. A pocket-facing TM residue may remain a strong hotspot if it is reachable from the extracellular vestibule; a lipid-facing residue remains avoid even if its solvent-accessible area is high in a membrane-free model.

## Apply Hard Gates

For a default extracellular protein binder, classify a candidate as `avoid` when any condition holds:

- It lies on the intracellular G-protein/arrestin/transducer interface.
- It is lipid-facing or requires the framework to enter the bilayer.
- It belongs only to a fusion protein, crystallization/stabilization partner, affinity tag or artificial linker.
- It is absent from the intended native receptor/isoform or created by an unexplained construct mutation.
- It requires passage through an inaccessible buried pore or an intact native domain.
- Its receptor chain or residue mapping is ambiguous.
- The membrane orientation is unresolved and extracellular accessibility cannot otherwise be established.
- It is a crystal-contact/oligomer interface without biological support.

When intracellular delivery is explicitly authorized, replace the first gate with a delivery- and specificity-aware analysis; do not silently reuse extracellular assumptions.

## Track Soft Risks

Retain but flag candidates affected by:

- Flexible or missing loop coordinates.
- Nearby glycosylation, disulfides, cleavage sites or heterogeneous post-translational modification.
- Conserved-family evidence without same-receptor support.
- Moderate state differences, low-resolution side chains or predicted structures.
- Narrow approach cones, framework collision risk or strong dependence on CDR length.
- Potential interference with receptor expression, folding or trafficking.
- Species/isoform differences or polymorphic residues.
- Interface hydrophobicity that may cause nonspecific membrane association.

Describe the exact risk and a way to test it. Do not hide soft risks inside a confidence label.

## Construct Candidates

Build each candidate as a mechanism-level object:

- Unique `id` and `classification`: `primary`, `backup`, `avoid`, or `unresolved`.
- Mechanism-specific `role` and one-sentence `hypothesis`.
- A small list of conditioning residues with dual structure numbering and GPCRdb annotations.
- Functional-site context not included as hotspots.
- Target state, counterstate and expected state preference.
- Approach direction, accessible opening and scaffold collision checks.
- Evidence tier and source identifiers.
- Hard-gate results, soft risks, confidence and falsifier.
- Primary functional assay and orthogonal controls.

Prefer a spatially connected set containing one or more causal/chemical anchors plus enough geometric separation to orient the binder. Avoid redundant adjacent hydrophobes, an entire ligand shell or residues chosen only for high SASA.

## Compare Without a Fused Score

Use a decision table, preserving each dimension:

| Dimension | Question |
| --- | --- |
| Mechanistic causality | Would occupying/stabilizing this site plausibly cause the intended effect? |
| Evidence strength | Is support same-receptor and state/assay matched? |
| State discrimination | Does target vs counterstate exposure support the claim? |
| Extracellular accessibility | Can the authorized binder reach it in the membrane context? |
| Approach feasibility | Can CDR and framework occupy a plausible pose? |
| Construct robustness | Is the site native and present across relevant isoforms/constructs? |
| Family coherence | Does the receptor architecture support the hypothesis? |
| Experimental testability | Is there a direct falsifier and appropriate assay? |
| Risk | Are glycans, flexibility, oligomer ambiguity or trafficking effects manageable? |

Apply hard gates first. Then nominate at most three distinguishable A/B/C hypotheses. Do not sum dimensions into one number, choose a winner automatically or present a precision unsupported by the evidence.

## Assay Logic

Pair function with controls:

- Measure pathway-proximal signalling appropriate to the receptor; include concentration-response and time dependence when relevant.
- Measure surface expression/trafficking so receptor loss is not mistaken for inhibition.
- Test ligand competition for a competitive hypothesis.
- Compare basal activity for inverse agonism.
- Compare target and counterstate binding for state selectivity.
- Use interface-disrupting mutations or protomer controls for a dimer hypothesis.
- Compare intact, cleaved and trigger-mutant constructs for tethered-agonist/autoinhibition hypotheses.
- Check orthogonal pathways when biased signalling is possible.

Write the result that would falsify each candidate before marking it primary.
