# v2 → v3 scientific capability parity

Acceptance audit, Phase 2.2: **FAIL — Phase 2 is not frozen; Phase 3/4 not started.**
The selected-source corpus, canonical-reference/old Gate 1 adapter and trusted native-expert
import are implemented. The first real soluble Agent case failed before acquisition/Gate 1:
an omitted SELECTED prerequisite raised a terminal AgentBoundaryError. The remaining real
cases were not run after the required critical-failure stop. Four short model calls cannot
establish end-to-end context improvement or completed scientific capability parity.
Detailed implementation/test evidence and stop decision: `PHASE22_UNBLOCK_CLOSURE.md`.

COMPLETE requires current implementation and acceptance evidence;
PARTIAL includes unvalidated real-source/model coverage. MISSING is explicit, not retired.
No legacy capability is intentionally retired in this migration. Phase 3/4 work may begin
only after the preceding phase's architecture, science and parity gates pass.

Legacy owner abbreviations: RS = external research agent using `easydesign-research`;
DS = deterministic scientific services; H = scientist. Reference paths below are relative to
`.agents/skills/easydesign-research/references/`; source code paths are repository-relative.
All 16 reference files were read, including JSON family rules and the draft claim index.
The claim index is not approved project knowledge; its sources require fresh verification.

| Legacy capability | Legacy owner | Legacy source/path | v3 owner | Status | Required phase | Evidence/test | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Biological goal, desired and forbidden effect | RS/H | target-and-site.md; special-target-playbooks.md | Target/Site + immutable research goal | PARTIAL | 2.2 | multiturn contract; real sources PASS; Agent goldens FAIL | Do not replace original goal with follow-up |
| Assay/readout, success/falsifier, controls | RS/H | target-and-site.md | Site/Binder | PARTIAL | 2.2 | Site skill; golden pending | Binding is not function; low perturbation is independent |
| Canonical target/species/isoform identity | DS/RS/H | evidence-and-numbering.md; core/target_identity.py | Target proposal + old identity/decision service | PARTIAL | 2.2 | Six fixture identity/proposal/species/replay cases; real path failed before acquisition | Configured reference is now accepted; real authoritative-bundle completion still unvalidated |
| Construct/canonical/coordinate/design-scope separation | DS/RS | target-and-site.md; evidence-and-numbering.md | Target + unchanged mapping kernel | PARTIAL | 2.2 | Clean/subsequence/ambiguous-chain/sequence-difference old-service regressions | No replacement mapping; inherited old multi-decision edge cases are not claimed repaired |
| Author/label/insertion/missing mapping | DS | evidence-and-numbering.md; stages/s01_target_preparation | Existing kernel via Target/Site | COMPLETE | 2.2 | test_source_author_numbering_is_not_invented | No invented canonical offset |
| Structure/state comparison and counterstate | RS | gpcr-mechanism-and-state.md | Target/Site + Research | PARTIAL | 2.2 | real source/kernel PASS; Agent golden FAIL | Bound ligand alone cannot establish active state |
| Ligand, partner, assembly and construct context | RS/DS | target-and-site.md; special-target-playbooks.md | Research + Target/Site | PARTIAL | 2.2 | PDB polymer/deposition retrieval | Source identity differs from context transfer |
| Target ambiguity handling | DS/H/RS | evidence-and-numbering.md | Target/Judge/Gate 1 | PARTIAL | 2.2 | Old Gate 1 jobs pass offline; actual first live failed before Gate 1 | No first/largest chain heuristic; missing real identity-trap completion |
| Active literature search | RS | target-and-site.md; scientific-claims.md | Shared EvidenceResearch + selected corpus | PARTIAL | 2.2 | Source/status/corpus tests; real selection-prerequisite recovery FAIL | Bounded EuropePMC discovery; do not auto-select to evade the failure |
| Primary-source retrieval | RS | evidence-and-numbering.md | EvidenceResearch + focused passages | PARTIAL | 2.2 | Full XML retention, source identity, passage and cursor regressions | Acquisition receipt is not a scientific citation; real workflow not completed |
| Database search and UniProt evidence | DS/RS | target-and-site.md; gpcrdb-contract.md | EvidenceResearch reusing ScientificHttpClient | PARTIAL | 2.2 | Cached source and first-class proposal regression; live acquisition not reached | Scientist species cannot be silently replaced |
| Structure and known complex search | RS/DS | target-and-site.md | EvidenceResearch + RCSB | PARTIAL | 2.2 | bounded PDB search/entry/polymer retrieval | Assembly and physiological context require interpretation |
| Mutagenesis evidence | RS | target-and-site.md; gpcrdb-contract.md | EvidenceResearch + Site | PARTIAL | 2.2 | literature topics + existing GPCRdb adapter | Mutation can affect expression/fold rather than epitope |
| Competition and known epitope evidence | RS | target-and-site.md | EvidenceResearch + Site | PARTIAL | 2.2 | source-bound conclusions; golden pending | Direct overlap and allostery are distinct |
| Functional evidence | RS | target-and-site.md; scientific-claims.md | EvidenceResearch + Site/Judge | PARTIAL | 2.2 | synthetic primary passage test | Preserve assay and target-context limits |
| State-dependent evidence | RS | gpcr-mechanism-and-state.md | EvidenceResearch + Target/Site | PARTIAL | 2.2 | real source/kernel PASS; Agent golden FAIL | Sensor/stabilizer/competitor/artifact hypotheses separate |
| PTM/glycan evidence | RS/DS | special-target-playbooks.md | Research + Site existing features/motifs | PARTIAL | 2.2 | glycan runtime regression | Motif is not occupancy; absent model is not absence |
| Source verification, strength and scope | DS/RS | evidence-and-numbering.md; scientific-claims.md | Runtime source binding + owner/Judge | PARTIAL | 2.2 | tamper/PMID/passage tests | Source verified does not imply biological entailment |
| Conflicting and negative evidence | RS | target-and-site.md | EvidenceResearch + owner/Judge | PARTIAL | 2.2 | All bound counterevidence preserved; exact Judge delegation/oversize regressions | Full real Judge path still missing; no silent contradiction truncation |
| Literature-derived site candidates | RS | target-and-site.md | Site + focused source cards | PARTIAL | 2.2 | Focused-card binding and source-tamper regression | Must independently map residues; real Gate 2 not completed |
| Scan-derived candidate alternatives | DS/RS | target-and-site.md | Site + old SASA/geometry | COMPLETE | 2.2 | test_site_runtime | No new fused winner score |
| Surface accessibility / SASA / burial | DS/RS | target-and-site.md | Existing Stage 02 kernel via Site | COMPLETE | 2.2 | real deterministic tool regression | SASA is not full-VHH access |
| Secondary structure and interface geometry | DS/RS | target-and-site.md; vhh-geometry-priors.md | Site + existing structure tools | PARTIAL | 2.2 | SASA/region geometry; broader context pending | Do not infer axes from sequence labels |
| Membrane access, topology and orientation | DS/RS | gpcr-review-schema.md; gpcrdb-contract.md | Site + existing GPCR tools | PARTIAL | 2.2 | synthetic seven-helix; real source/kernel PASS; Agent golden FAIL | No GPCR leakage into soluble reasoning |
| Glycan shielding and full-context approach | RS/DS | special-target-playbooks.md | Site | PARTIAL | 2.2 | warnings and override regression | Full body clearance cannot be claimed from residue centroid |
| Mechanistic relevance / functional regions | RS | target-and-site.md | Site + Research/Judge | PARTIAL | 2.2 | mechanistic evidence contract | General protein reasoning first |
| Conservation/variants when available | DS/RS | target-and-site.md | Site + UniProt/primary evidence | PARTIAL | 2.2 | CONSERVATION EvidenceNeed and existing source/claim contract | No invented conservation percentage or completeness claim |
| Primary/backup/avoid and alternative mechanisms | RS/H | target-and-site.md; gpcr-family-playbooks.md | Site/Judge/Gate 2 | PARTIAL | 2.2 | typed origin/role; live golden pending | Backup must differ scientifically, not cosmetically |
| Hotspot selection and exact review | DS/RS/H | strategy-yaml.md; orchestration/research.py | Site/Judge/Gate 2 + old site service | COMPLETE | 2.2 | Site approval/revision/override/replay | Final scientific authority stays human |
| GPCR conditional family heuristics | RS | gpcr-family-rules.json; gpcr-family-playbooks.md | Site after verified relevance | PARTIAL | 2.2 | real GPCR/family audit pending | Priors generate hypotheses; cannot pick winner |
| Special targets: enzyme/IDR/amyloid/multimer/imaging/chaperone | RS | special-target-playbooks.md | Target/Site/Binder | PARTIAL | 2.2 | skill parity audit | Conditional context and representation limits must remain visible |
| Binder modality / VHH strategy | RS/H | strategy-yaml.md; vhh-geometry-priors.md | Binder | COMPLETE | 2.2 | design runtime/harness | Current supported modality remains VHH |
| Hotspot conditioning, explicit avoid and neutral residues | DS/RS | strategy-yaml.md | Binder + old compiler | COMPLETE | 2.2 | design constraint tests | Non-hotspot is neutral, not implicitly forbidden |
| Crop reasoning and full-target confirmation | RS/DS | vhh-geometry-priors.md | Binder / later Pilot | PARTIAL | 2.2 / 3 | compiler tests; scientific loop pending | Crop cannot delete genuine shielding to fabricate accessibility |
| CDR/scaffold identity and actual asset ranges | RS/DS | boltzgen-contract.md; vhh-geometry-priors.md | Binder + old compiler/validator | COMPLETE | 2.2 | Phase 2 real BoltzGen check | Insertion count differs from final CDR length |
| Design arms, comparator and changed/held factors | RS/H | strategy-yaml.md | Binder | PARTIAL | 2.2 | typed arm metadata; parity review pending | Integrated arm cannot identify a single causal factor |
| First Pilot protocol, seven scaffolds × 40 per condition | DS/RS | boltzgen-contract.md; strategy-yaml.md | Binder + existing protocol validator | COMPLETE | 2.2 | Standard coverage plus native-condition before/after and invalid-coverage tests | Narrow legacy facade bug fixed; exact seven-by-40 scientific invariant preserved |
| Native BoltzGen YAML compilation and checks | DS | boltzgen-contract.md | Trusted callback + existing compiler/validator | COMPLETE | 2.2 | Phase 2 real check and YAML regression | No LLM-authored runnable YAML |
| Native expert path when standard cannot express science | DS/RS/H | strategy-yaml.md; boltzgen-contract.md | Trusted scientist import + Binder + old compiler/Judge/Gate 3 | PARTIAL | 2.2 | Native bytes/constraints/Gate 3/shared-approval offline regressions | First-class import exists; required live model/backend Gate 3 rerun NOT RUN |
| Thread-local proposals / project-global approved science | DS/RS | orchestration/research.py | Runtime explicit ownership adapters | COMPLETE | 2.2 | Ownership regressions plus corpus cross-thread and native approval inheritance | Thread evidence views remain separate; approved scientific state remains shared |
| Full evidence retention, scoped consumption and pagination | RS/DS | CatMaster review; existing ArtifactRef | EvidenceCorpus + tool-owned views | PARTIAL | 2.2 | Large-source retention, independent thread views and exact cursor tests PASS | Real full scientific path unvalidated; short failed trace is not a context benchmark |
| First-class Target/Site/Design through Gate 1/2/3 | RS/DS/H | existing decision and research services | Coordinator + owners + independent Judge | PARTIAL | 2.2 | Offline multi-turn harness PASS; live stopped before Gate 1 | No complete real golden; cannot freeze Phase 2 |
| Pilot generation and explicit execution approval | DS/H | pilot-diagnosis.md; orchestration/research_plans.py | Gate 3 + existing job runtime | MISSING | 3 | Phase 3 pending | Old freeze-only approval cannot authorize launch |
| Prediction and filtering | DS | metric-guide.md; stages/s05_pilot_screen | Existing backend/filter + Agent bridge | MISSING | 3 | real micro pending | No deterministic metric rewrite |
| Metric provenance, hard gates and missingness | RS/DS | metric-guide.md | Pilot owner/Judge + trusted artifact reader | MISSING | 3 | synthetic meaningful fixture pending | Missing is not zero; preserve fallback values/source |
| Denominators and group comparability | RS | pilot-diagnosis.md | Pilot diagnosis | MISSING | 3 | synthetic contrasts pending | Candidate nesting and operational bias remain explicit |
| Target/site/hotspot failure attribution | RS | failure-atlas.md; pilot-diagnosis.md | Pilot diagnosis/Judge | MISSING | 3 | synthetic evidence pending | Observation vs interpretation vs alternative |
| CDR/scaffold/crop/interface/membrane diagnosis | RS | failure-atlas.md | Pilot diagnosis/Judge | MISSING | 3 | synthetic evidence pending | Avoid post-hoc single-factor causal stories |
| Generation/prediction/filter failure vs scientific negative | DS/RS | failure-atlas.md | Old job runtime + diagnosis | MISSING | 3 | real micro/recovery pending | Zero micro passes must be INCONCLUSIVE |
| Next discriminating experiment | RS/H | pilot-diagnosis.md | Binder/Pilot + Gate 4 | MISSING | 3 | all five Gate 4 outcomes pending | Do not just tune around top-1 |
| Revision of Site/Design with local invalidation | DS/RS/H | pilot-diagnosis.md | Gate 4 routing | MISSING | 3 | revision cases pending | Valid upstream Target is preserved |
| Promotion/another pilot/revise/stop | RS/H/DS | scale-and-selection.md | Judge/Gate 4 + old promotion service | MISSING | 3 | meaningful synthetic promotion pending | Micro evidence cannot justify scientific promotion |
| Optional prediction triage | H/RS | pilot-diagnosis.md | Runtime compute interrupt | MISSING | 3 | Phase 3 pending | Optional checkpoint, not a sixth scientific gate |
| Typed Observation/Interpretation/hypothesis lineage | RS/DS | pilot-diagnosis.md; orchestration/research.py | Existing research events + Agent | MISSING | 3 | Phase 3 pending | No second evidence or hypothesis engine |
| Scale approval, allocation, exact budget | DS/H | scale-and-selection.md | Gate 4 / old ScaleExecutionPlan | MISSING | 4 | Phase 4 pending | Equal policy preserved; intent distinct from micro execution |
| Real scale batch execution/recovery | DS | scale-and-selection.md | Existing job runtime | MISSING | 4 | tiny real scale pending | No production-scale compute |
| Aggregation/global competition/indexing | DS | scale-and-selection.md | Existing aggregation + selection adapter | MISSING | 4 | 50k synthetic rows pending | Stress demonstrates functionality, not throughput |
| Diversity, quality/risk tradeoffs, redundancy | RS/DS | scale-and-selection.md | Selection owner/Judge | MISSING | 4 | realistic synthetic panel pending | No single-score top-N substitute |
| Developability when supported | RS/DS | scale-and-selection.md | Selection owner | MISSING | 4 | Phase 4 pending | Do not fabricate absent predictors/experimental values |
| Panel arithmetic, controls and coverage | RS/H | scale-and-selection.md | Selection/Gate 5 | MISSING | 4 | panel feasibility tests pending | Explicit total/controls/cluster caps |
| Final candidate approval/revision/rejection/override | H/DS | scale-and-selection.md | Gate 5 + existing authority | MISSING | 4 | Phase 4 pending | Hard-invalid candidates remain blocked |
| Wet-lab recommendation and handoff | RS/H/DS | scale-and-selection.md | Selection/Gate 5 | MISSING | 4 | Phase 4 pending | Package only, no ordering or real experiment |
| Existing Stage 05/07 read-only dashboards | DS/RS | pilot-diagnosis.md; scale-and-selection.md | Existing reports | COMPLETE | retained legacy | prior reporting regressions; source manifests | No Workbench migration; display actions are not approvals |

Full audit source inventory: `target-and-site.md`, `evidence-and-numbering.md`,
`strategy-yaml.md`, `boltzgen-contract.md`, `gpcr-mechanism-and-state.md`,
`gpcrdb-contract.md`, `gpcr-family-playbooks.md`, `gpcr-family-rules.json`,
`gpcr-review-schema.md`, `metric-guide.md`, `pilot-diagnosis.md`,
`scale-and-selection.md`, `scientific-claims.md`, `special-target-playbooks.md`,
`failure-atlas.md`, `vhh-geometry-priors.md`.

Phase 3/4 MISSING rows do not block Phase 2 solely because they belong to later approved phases.
Any unclosed Prepare/Strategize PARTIAL row is assessed explicitly at Phase 2.2 acceptance;
it cannot be silently deferred to Pilot or presented as scientific parity.
