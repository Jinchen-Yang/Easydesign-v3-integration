# GPCR Family Playbooks

## 使用边界

只有在受体身份、GPCRdb 顶层家族和真实结构域组成均已核对后，才使用本手册生成机制假设。
家族规则属于条件性启发，不是实验事实，也不能替代同一受体的结构、药理、突变或功能证据。
若家族先验与当前受体证据冲突，应保留冲突、降低结论强度并停止自动选出主候选。

## 目录

- [跨家族问题](#cross-family-questions)
- [Class A/B/C/F 及稀有家族](#001-class-a-rhodopsin)
- [二聚体与寡聚体](#dimer-and-oligomer-playbook)
- [大型 ECD 与自抑制](#large-ecd-and-autoinhibition-playbook)
- [规则使用记录](#family-rule-reporting)

Use these playbooks only after resolving the receptor's GPCRdb top-family slug and verifying its actual domain architecture. Treat every item as a conditional hypothesis generator, never as an automatic residue selector. Prefer same-receptor structures and functional data over family priors.

## Cross-Family Questions

Answer these before choosing a family branch:

1. What is the endogenous input: small molecule, lipid, ion, peptide, protein, mechanical force, light, metabolite or unknown?
2. Where is the causal recognition module: transmembrane bundle, extracellular vestibule, N-terminal domain, ECD, VFT, CRD, GAIN/tethered peptide or an inter-protomer interface?
3. Does signalling require a monomer, constitutive dimer, ligand-induced oligomer, co-receptor or accessory protein?
4. Is the extracellular region intact, cleaved, shed, truncated, antibody-bound or artificially replaced in the structure?
5. Does an endogenous segment occupy or mask the activation site, and is the intended mechanism to stabilize or release that autoinhibition?
6. Is the desired binder expected to enter a cavity with a CDR tip, cap a rim, bridge domains or stabilize a state-selective surface?

Generate separate candidates when the answers support genuinely different mechanisms. Do not blend them into one score.

## `001`: Class A (Rhodopsin)

Typical architecture: compact seven-transmembrane bundle with short-to-moderate N terminus and extracellular loops. Orthosteric sites range from deeply buried small-molecule pockets to broad peptide/protein-facing extracellular surfaces.

For small-molecule or lipid receptors:

- For inhibition, test extracellular pocket rim/vestibule occlusion, direct orthosteric competition, and receptor-specific negative-allosteric cavities.
- For activation, test the active-state pocket core or trigger network only where a protein binder can reach it without crossing the membrane or colliding with the pocket wall. Otherwise test an extracellular state-selective surface that allosterically stabilizes activation.
- Distinguish pocket-facing TM residues from lipid-facing residues using membrane orientation and side-chain direction. A TM label alone neither accepts nor rejects a residue.

For peptide, chemokine, glycoprotein-hormone or protease-activated receptors:

- Include N terminus and ECL contacts when they form the primary recognition site.
- Separate a distal peptide-capture region from the TMD activation core; they may support different inhibition or activation hypotheses.
- For protease-activated receptors, treat cleavage and the newly exposed tethered ligand explicitly; intact and cleaved constructs are not interchangeable.

Check receptor-specific dimer/oligomer evidence, but do not assume a functional dimer from a crystal contact. Exclude intracellular G-protein/arrestin surfaces for a default extracellular binder.

## `002`: Class B1 (Secretin)

Typical architecture: a structured N-terminal ECD coupled to a seven-transmembrane bundle. Many peptide agonists use a two-domain mechanism: the peptide C terminus is captured by the ECD, while its N terminus engages the TMD core to trigger activation.

- For competitive inhibition, test the peptide-capture face on the ECD, the ECD-TMD entry path and the extracellular TMD vestibule. Keep them as separate hypotheses when their approach directions differ.
- For activation, test the peptide N-terminal insertion/trigger region and active-state extracellular TMD network, but require feasible cavity access. Consider an agonist-mimetic ECD/TMD bridge when supported by a same-receptor complex.
- Do not select every peptide-contact residue. Use a small subset that constrains the ligand-like pose or blocks a causal entry path.
- Inspect ECD orientation, linker flexibility, disulfides and glycans. A stand-alone ECD structure does not establish its orientation relative to the membrane.
- Treat reported extracellular-domain antibody epitopes as receptor- and mechanism-specific evidence, not a transferable class rule.

## `003`: Class B2 (Adhesion)

Typical architecture: very large, modular extracellular regions, often including a GAIN domain and GPS autoproteolysis site, coupled to a seven-transmembrane bundle. Some receptors signal through an exposed tethered agonist (Stachel sequence) after displacement or cleavage of an N-terminal fragment.

- First establish the full domain composition, autoproteolysis status, N-terminal-fragment/C-terminal-fragment association and whether the deposited construct retains the native ECD.
- For inhibition, test stabilization of an autoinhibited ECD/GAIN arrangement, blockade of tethered-agonist exposure or insertion, and receptor-specific extracellular TMD entry sites.
- For activation, test release of autoinhibition, exposure or agonist-like engagement of the tethered peptide, or stabilization of an active extracellular TMD state.
- Keep mechanical-force, ligand-binding and tethered-agonist mechanisms separate unless direct evidence connects them.
- Treat ECD interfaces, cleavage surfaces and putative dimers as conditional. Require biological-assembly, crosslinking, mutational or functional support before nominating an inter-protomer hotspot.
- Reject conclusions drawn from a TMD-only construct when the intended mechanism depends on the missing ECD/GAIN region.

## `004`: Class C (Glutamate)

Typical architecture: large Venus-flytrap (VFT) extracellular domains, often cysteine-rich domains, a seven-transmembrane bundle and functionally important homo- or heterodimer organization.

- Define protomer identity, stoichiometry and whether the functional unit is a homodimer or heterodimer before mapping sites.
- For orthosteric inhibition, test the ligand-binding VFT cleft, closure-preventing domain surfaces or validated negative-allosteric TMD pockets.
- For activation, test a closed/active VFT conformation, the VFT-to-CRD/TMD coupling path, an active dimer arrangement or a validated positive-allosteric TMD pocket.
- Model both protomers in approach checks. A binder that fits one isolated protomer may clash with its partner or lock the wrong dimer geometry.
- Do not transfer a hotspot between heterodimer partners solely by generic-number equivalence.
- Distinguish ECD orthosteric ligands from TMD allosteric modulators; their state logic and access geometry are different.

## `005`: Class D1 (Ste2-like Fungal Pheromone)

Architecture and activation mechanisms are less uniformly represented than mammalian Class A receptors.

- Start from receptor-specific sequence, topology, oligomeric evidence and ligand class.
- Test extracellular loops/N terminus and TMD pocket only when same-receptor or close-fungal-homolog evidence supports them.
- Evaluate receptor-specific oligomerization without treating an assembly contact as functional by default.
- Do not import Class A generic motifs, pocket depth or state rules without a validated cross-family mapping.
- Keep low-confidence regions and absent experimental structures explicitly unresolved.

## `006`: Class F (Frizzled)

Typical architecture: an N-terminal cysteine-rich domain (CRD), extracellular linker and seven-transmembrane bundle. Frizzled receptors, Smoothened and related members have distinct ligand and sterol/lipid mechanisms.

- Identify whether the receptor is Frizzled-like, Smoothened-like or another Class F branch before applying a mechanism.
- For ligand blockade, test the receptor-specific CRD ligand surface, extracellular linker, validated co-receptor interface or extracellular TMD cavity.
- For activation, test ligand/sterol-supported active arrangements, CRD/linker-to-TMD coupling or an active-state extracellular TMD site only when supported by receptor-specific evidence.
- Treat lipids and sterols as part of the structural context. Do not ask an extracellular protein binder to occupy a lipid-facing intramembrane site.
- Inspect CRD disulfides, glycosylation, flexible linkers and possible dimer geometry. A detached CRD pose is not a membrane-referenced approach model.

## `007`: Class O1

Use a receptor-specific workflow because broad transferable structural rules may be sparse.

- Verify that the parent hierarchy and receptor annotation are current.
- Build hypotheses from the endogenous ligand, measured topology, same-receptor structures and functional mutagenesis.
- Preserve multiple domain-architecture hypotheses when the ECD or oligomeric state is unresolved.
- Do not borrow a better-characterized family playbook without an explicit, sequence- and structure-supported analogy.

## `008`: Class O2

Use the same conservative policy as Class O1:

- Require receptor-specific identity, topology, ligand and state evidence.
- Mark absent generic numbering, uncertain membrane orientation or incomplete constructs as unresolved.
- Generate only candidates whose access geometry can be inspected directly in the supplied structure.
- Avoid mechanistic labels that cannot be linked to an assay falsifier.

## `009`: Class T2

Typical members include taste-family receptors with limited structural and pharmacological coverage compared with canonical Class A targets.

- Resolve the exact receptor, species and ligand modality before using family priors.
- Test extracellular vestibule/TMD sites only when mapping and membrane-facing status are defensible.
- Treat oligomerization, accessory proteins and large extracellular contributions as receptor-specific questions.
- Prefer conservative, surface-accessible state hypotheses over deep-pocket claims unsupported by structures.

## `010`: Other GPCRs

This branch is a routing signal, not a biological mechanism.

- Derive architecture from sequence annotations, curated domains and the actual structure.
- Require receptor-specific evidence for ligand site, state, dimerization, autoinhibition and transducer coupling.
- Do not force a Class A, B, C or F template merely to complete the workflow.
- Stop primary selection if the domain architecture or membrane orientation cannot support a feasible approach model.

## Dimer and Oligomer Playbook

Classify an interface as `biological_supported`, `possible`, `crystal_contact` or `unresolved` using biological assembly, repeated structures, buried area, conserved contacts, crosslinking, mutagenesis and functional data.

Only propose an interface hotspot when:

- the oligomer is required for the intended signalling mechanism;
- the relevant protomers and membrane planes are represented;
- binding can plausibly stabilize or disrupt the intended geometry;
- the candidate does not depend only on a packing artifact; and
- the assay can distinguish interface modulation from nonspecific receptor loss.

Keep “bind one protomer near the interface,” “bridge protomers,” and “sterically disrupt the interface” as separate hypotheses.

## Large ECD and Autoinhibition Playbook

For receptors with a large ECD, VFT, CRD, GAIN region or endogenous blocking segment:

1. Map domains, cleavage sites, disulfides, glycans, unresolved linkers and construct deletions.
2. Determine whether the ECD blocks, presents or transmits the endogenous input.
3. Compare intact and activated/cleaved structures when available.
4. For inhibition, consider stabilizing the closed/autoinhibited state or blocking exposure of the trigger.
5. For activation, consider releasing the block, mimicking the exposed trigger or stabilizing the coupled active arrangement.
6. Reject a hotspot if the proposed binder occupies space already filled by an intact native domain unless displacement is the explicit, supported mechanism.

## Family-Rule Reporting

For every rule used, record:

- GPCRdb top-family slug and resolved family name.
- The architecture condition that made the rule applicable.
- Same-receptor evidence that supports or contradicts it.
- The candidate it generated or removed.
- A falsifier and the assay/structure needed to test it.

If no rule applies, report that outcome without manufacturing a family-specific candidate.
