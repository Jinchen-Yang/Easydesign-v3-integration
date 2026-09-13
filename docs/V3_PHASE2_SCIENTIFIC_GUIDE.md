# Phase 2 scientific interaction

Current Gate 2 review availability policy (2026-09-14, under validation):
[Judge resilience](PHASE2_JUDGE_RESILIENCE_20260914.md). A runtime-validated proposal may reach
a clearly marked Scientist review card after independent review is technically unavailable.
Continuation requires acknowledgement and a human rationale. Hard contradictions and valid
negative reviews remain blocking; an unavailable review is never reported as a successful Judge.

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

## Binder strategy and Gate 3

The default scope is `--through design`; use it explicitly when starting a new research thread:

```bash
easydesign-agent start PROJECT --target /absolute/path/target.cif \
  --models config/llm.yaml --through design \
  --goal "Select a defensible site and freeze a reviewed VHH design specification; do not generate."
```

After Gate 2 approval, Binder Strategy decides HOW to design against that approved site.
It reads the actual seven official VHH template constraints, approved hotspot/context and
upstream warnings. Its typed intent describes conditioning, excluded positions, target crop,
CDR settings, approach hypothesis and meaningful experimental arms. It cannot write arbitrary
backend YAML. The existing compiler produces executable YAML and the existing BoltzGen
validation service checks it before the independent Judge and Gate 3 review.

A project runtime profile must already contain a working `boltzgen_validation` installation.
Follow the existing runtime/deployment instructions; a model API key alone does not provide a
scientific backend. A missing validator is an operational setup error, never a successful
scientific validation. This phase only needs YAML validation assets, not a generation run.

The existing first-pilot protocol remains all seven official scaffolds × 40 candidates per
condition. A request to reduce that number is reported as incompatible with the current
protocol; the Agent cannot silently relax it. CDR overrides must remain within the declared
CDR loop of every selected official scaffold. These settings are hypotheses for a later pilot,
not evidence that a binder will bind or adopt the intended geometry.

At Gate 3, the common card displays the design objective, approach, conditioning, exclusions,
crop/CDR constraints, experimental arms, planned pilot scope, validation result and uncertainty.
For a local HOW revision, for example:

```bash
easydesign-agent resume PROJECT --thread THREAD --through design --models config/llm.yaml \
  --card CARD --decision revise --instruction "Keep the approved target and hotspot; shorten CDR3 exploration within the verified template constraints."
```

This preserves Target and Hotspot approval and returns to Binder Strategy, compilation and a
fresh Judge/card. If the instruction changes WHERE to bind, the Coordinator must explicitly
reopen Site selection. That invalidates the dependent design and requires a new Site proposal,
Judge and Gate 2 approval; it preserves the approved Target. Changing upstream target identity
also invalidates Site and Design. Existing configuration/identity guards fail closed if an
upstream change requires a new preparation context; the model cannot rewrite that identity.

Gate 3 approval calls the existing human plan-approval and strategy-freeze services. It freezes
an executable scientific specification and stops. It does not start pilot generation, predict
candidate structures or run filtering. A rejected proposal leaves the project usable. A
DISCOURAGED design needs explicit warning acknowledgement and rationale; BLOCKED is never
eligible for override. Upstream override warnings remain visible downstream.

Each ordinary user turn or validated Phase 2 human acceptance/revision has a bounded 32-call
execution. Empty resume, crash recovery and duplicate responses reuse the persisted execution.
Thread lifetime usage remains telemetry. The immutable research goal, current user message,
trusted revision instruction and LangGraph conversation history remain separate.

The runtime explicitly reports whether CDR ranges lie within the declared loop bounds of all
seven verified official VHH assets. This is a verified compiler-numbering fact, while equivalent
loop geometry across scaffolds remains unproven. No Design Viewer is added in Phase 2; a report
must not invent a link or suggest the existing Target Viewer displays the frozen design.

## Phase 2.2 evidence and canonical identity

Evidence owners first discover candidates, then select, defer or exclude a source for a named
protein-design evidence need. Only selected sources are acquired deeply. Complete response
bytes and derived section/chunk indexes remain in the existing project evidence artifacts.
`retrieve_evidence` supplies a few source-bound passages for the current question, with a
query-bound continuation cursor. `read_evidence_result` opens a named field or short page from
an offloaded tool result. A preview is partial; omitted values are not negative evidence.
Selections and current views belong to the thread. Another thread may select and retrieve
project evidence independently without inheriting the first thread's pending conclusions.

For a local construct with a known UniProt reference, state the accession and identity question
in the original goal before preparation. Target Intelligence can retrieve the official record
and propose the verified reference; runtime copies accession/species into the existing config
revision service. The unchanged Stage 01 mapping and decision services determine chain/scope
ambiguity and whether Gate 1 is required. The model cannot supply a residue map or silently
retarget an already prepared project. Canonical reference approval does not verify native state,
physiological mechanism or efficacy.

Full source records do not enter conversation as tool text. The input guard remains 60,000
characters, with per-call telemetry and separate tool-schema character counts. Judge views
preserve every item in the delegated scientific projection, including cited contradictions;
a projection over 32,000 characters is rejected for narrowing rather than silently dropping
support or counterevidence. The Judge cannot read another delegation's archived result.

## Scientist-provided native strategy

Standard structured DesignArm remains available. Once Gate 2 is approved, an expert can instead
supply a project-local legacy ResearchStrategy whose variants cite native BoltzGen YAML:

```bash
easydesign-agent start PROJECT --through design --models config/llm.yaml \
  --native-strategy /absolute/path/PROJECT/inputs/expert/strategy.yaml \
  --goal "Review the supplied native VHH strategy against the approved hotspot; preserve the YAML and request Gate 3."
```

The imported strategy must cite the current approved foundation. Each native variant declares
one official scaffold and the source checksum using the existing strategy schema. For the
first pilot, seven variants share one explicit hypothesis/condition, one per official scaffold,
with 40 candidates each and coherent changed/held experimental factors. Missing or duplicate
coverage is rejected. The Agent receives scientific summaries and returns its opinion; it does
not rewrite the source YAML. Replacement requires a scientist REVISE.

Supported native inputs contain one frozen prepared target and one VHH scaffold. Target chain,
explicit numeric crop and binding/avoid labels must fit the approved mapping and hotspot.
Compiler asset paths are accepted; other inputs must be stable absolute project-local paths.
An expert scaffold YAML must retain the declared official structure, chain and framework, with
bounded loop design/exclusion/insertion settings. The original compiler and real backend schema
validator still run. Unknown or incompatible target/scaffold directives cannot bypass these
checks. Runtime keeps and verifies all source bytes through Judge review and Gate 3. Approval
freezes the specification only; it does not authorize generation or prediction.
