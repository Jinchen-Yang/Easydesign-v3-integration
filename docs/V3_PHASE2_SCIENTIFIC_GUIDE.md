# Phase 2 scientific interaction

The v3 `easydesign-agent` entry point owns model calls, isolated specialists and human interrupts.
The v2 `easydesign` CLI and scientific services remain available as the compatibility path.
Use an explicitly configured model (`config/llm.template.yaml`); never put credentials in a goal,
biology file or scientific project. The CLI does not automatically source private environment files.

## Site and mechanism

For a local structure, choose the scientific scope explicitly:

```bash
easydesign-agent start PROJECT --target /absolute/path/target.cif \
  --models config/llm.yaml --through site \
  --goal "Identify an experimentally testable extracellular VHH epitope; distinguish evidence from hypotheses."
```

Gate 1 resolves the target/structure question when required by the original target service.
After that, Site & Mechanism reads the approved mapping and actual structure calculations.
It proposes a site; the independent Evidence Judge challenges the bound proposal, and Gate 2
asks which region the scientist wants to target. SASA and geometric scores are not affinity,
functional validation, docking clearance or biological identity.

Optional biology context is an explicit scientist-supplied YAML file, passed with
`--biology-context /absolute/path/biology.yaml`. The runtime verifies chain and residue mapping.
It labels the biological statements as supplied evidence, not independently verified annotation.
A minimal example is:

```yaml
target_auth_chain: A
target_kind: gpcr
structural_state: unresolved
state_source: No active/inactive assignment supplied
topology_source: Scientist-reviewed topology for this construct
# All residue IDs below use the approved label_seq_id mapping, not canonical numbering.
topology:
  - {label_seq_id: 120, segment: ECL2}
features:
  - kind: glycan
    label_seq_ids: [120]
    description: Potential shielding; occupancy not measured in this construct
    source: Scientist-supplied annotation
limitations:
  - The construct lacks a membrane environment and explicit glycans
```

The example residue must be replaced with a verified mapped position. A sparse loop annotation
is insufficient to calculate a reliable signed membrane frame; the existing GPCR kernel needs
adequate TM geometry and orientation evidence. Missing biology stays unknown. Sequence motifs
indicate possible glycosylation; they do not establish occupancy.

The common decision card offers approve, revise, reject and override. For example:

```bash
easydesign-agent resume PROJECT --thread THREAD --through site --models config/llm.yaml \
  --card CARD --decision revise --instruction "Keep the target; avoid this glycan region and reassess the extracellular alternative."
```

Use the exact thread/card values displayed by the CLI. `--interactive` offers the same actions
without manually entering a card value. A revision preserves the immutable research goal and
is delivered separately to the owning specialist. It produces a fresh proposal, Judge opinion
and card. Rejection leaves the scientific project available for another proposal.

SUPPORTED means support within the stated evidence scope. DISCOURAGED means executable but
scientifically risky: ordinary approval is refused; explicit override requires acknowledgement
and rationale. BLOCKED is established by runtime facts such as absent mapped residues or a hard
exclusion, and cannot be bypassed with override. The original scientific approval service remains
the authority for published hotspot state.

A changed target invalidates dependent Site/Design evidence. Re-importing different biology
context also invalidates the old Site proposal; it does not silently edit the target or reinterpret
an old approval. `status` never imports context. Models cannot write biology context.

An interrupted CLI can resume with the same thread. Agent checkpoints do not replace scientific
job status or compute recovery. A thread cannot report completion while its requested scientific
gate remains unresolved. A completed `--through site` scope has approved hotspots and launches
no binder generation.
