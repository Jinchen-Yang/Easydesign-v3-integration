# GPCR VHH template prior and experimental arms

For a GPCR target, prefer this Skill's `assets/gpcr-vhh7-v1` template set.
`read_design_evidence` exposes `default_scaffold_template` and the exact constraints of each
available template. Set an arm's `scaffold_template` to `gpcr-vhh7-v1`, or omit it to use that
default. Runtime resolves the choice before preflight, saving the proposal, Judge and Gate 3.
Non-GPCR defaults stay `official-vhh7-v1`. Expert-native imported YAML remains unchanged.

These are the scientist-supplied seven complete YAML/CIF templates from
`generic_nanobody_scaffolds_7_cdr3-15-50_complete.tar.gz`. Their manifest pins every source file.
Preserve their CDR1/CDR2 configuration and CDR3 design/exclusion/insertion-position semantics;
they differ from the original official YAMLs. Do not reconstruct them using a uniform range.
The supplied CIFs match the official registry after newline normalization; the compiler reuses
those verified registry coordinates and copies the selected YAML configuration into each arm.

| Scaffold | CDR3 insertion count |
| --- | --- |
| 7eow | 1..37 |
| 7xl0 | 1..46 |
| 8coh | 1..37 |
| 8z8v | 1..42 |
| gontivimab | 1..36 |
| isecarosmab | 1..43 |
| sonelokimab | 1..38 |

These are inserted-residue counts, not final CDR3 lengths. The archive filename and comments
are not a verified guarantee of total CDR3 length 15–50. CDR1/CDR2 continue to be designed
according to these templates; keeping their settings does not freeze their sequences.
The widened search is a design prior, not evidence that longer loops bind better or penetrate
the approved pocket. Actual geometry and binding remain questions for downstream experiments.

The prior is overridable. Explain a concrete target/site reason in the existing arm rationale
when choosing `official-vhh7-v1` or adjusting CDR parameters. For an insertion-only adjustment,
set `cdr_overrides=[{"cdr":3,"insertion_num_residues":"3..20"}]`; omit `design_res_index` to
preserve each scaffold's own design region. This is an example, not another preferred range.

Use one to three meaningful arms. Every arm uses all seven scaffolds and 40 planned candidates
per scaffold. Different scaffold backgrounds expand within an arm; they are not separate arms.
Possible comparisons include the supplied template versus a different insertion range, or
different conditioning subsets within the approved hotspot. Integrated changes are allowed;
record all changed and held-constant factors and interpret them as a combined hypothesis.
Do not force three arms or present identical executable settings as independent experiments.

Generate target `binding` from the selected Gate 2 hotspot or an explicit nonempty subset.
For an explicitly extracellular GPCR VHH objective, every arm defaults to the union of
runtime `gpcr_exclusions.label_seq_ids`, approved Site exclusions and its own verified avoid
residues. This union reaches actual YAML `not_binding`; it does not depend on the model
remembering the default. The runtime uses the approved Site's saved official cytoplasmic
annotations, declared intracellular topology and observed receptor contacts with identified
G-protein/arrestin partners. Exact target, source-chain, model and numbering correspondences
are retained. Deposited mmCIF partner entity names supplement already typed kernel interfaces;
unknown partners are not guessed from chain letters. Only coordinate-present receptor labels
are emitted. Missing coordinates/source evidence remain visible as limitations.
This policy is independent of scaffold choice. Non-GPCR and explicitly intracellular designs
keep their existing defaults. Expert-native input is not rewritten: omissions require revision
of that imported specification. No arbitrary TM/pore residues are excluded merely for being
buried, and missing independent evidence does not prove a region safe to contact.
Unselected portfolio candidates are not automatically forbidden contacts. Binding and avoid
must not overlap; any crop must retain both. A different Site requires Scientist steering at
Gate 2 and cannot be introduced as a new arm. An avoid list is not a membrane simulation.

Run `evaluate_design_constraints`, inspect effective template/arm settings, then submit concise
`BinderIntent`. The existing compiler and actual backend validate the resulting YAML before
Gate 3. Neither this Skill nor an arm proposal authorizes candidate generation.
