# v2 → v3 scientific capability parity

Acceptance audit, Phase 2.1: **FAIL — Phase 2 is not newly frozen; Phase 3/4 not started.**
The real soluble and GPCR Agent goldens both hit the 60,000-character context bound before Gate 2.
The formal canonical-reference and native-expert first-class paths remain critical parity gaps.
Source-only and deterministic checks cannot substitute for a completed scientific Agent/Judge case.
Detailed test evidence and stop decision: `PHASE2_CLOSURE.md`.

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
| Biological goal, desired and forbidden effect | RS/H | target-and-site.md; special-target-playbooks.md | Target/Site + immutable research goal | PARTIAL | 2.1 | multiturn contract; real sources PASS; Agent goldens FAIL | Do not replace original goal with follow-up |
| Assay/readout, success/falsifier, controls | RS/H | target-and-site.md | Site/Binder | PARTIAL | 2.1 | Site skill; golden pending | Binding is not function; low perturbation is independent |
| Canonical target/species/isoform identity | DS/RS/H | evidence-and-numbering.md; core/target_identity.py | Target + old identity service | PARTIAL | 2.1 | Phase 1 chain tests; deterministic identity PASS; formal reference config FAIL | Formal reference config is still rejected; read-only comparison cannot replace old identity approval |
| Construct/canonical/coordinate/design-scope separation | DS/RS | target-and-site.md; evidence-and-numbering.md | Target + mapping kernel | PARTIAL | 2.1 | source-author numbering regression | Engineered construct cannot be silently treated as canonical |
| Author/label/insertion/missing mapping | DS | evidence-and-numbering.md; stages/s01_target_preparation | Existing kernel via Target/Site | COMPLETE | 2.1 | test_source_author_numbering_is_not_invented | No invented canonical offset |
| Structure/state comparison and counterstate | RS | gpcr-mechanism-and-state.md | Target/Site + Research | PARTIAL | 2.1 | real source/kernel PASS; Agent golden FAIL | Bound ligand alone cannot establish active state |
| Ligand, partner, assembly and construct context | RS/DS | target-and-site.md; special-target-playbooks.md | Research + Target/Site | PARTIAL | 2.1 | PDB polymer/deposition retrieval | Source identity differs from context transfer |
| Target ambiguity handling | DS/H/RS | evidence-and-numbering.md | Target/Judge/Gate 1 | PARTIAL | 2.1 | Phase 1 steering; deterministic real-construct trap PASS; live completion absent | No first/largest chain heuristic |
| Active literature search | RS | target-and-site.md; scientific-claims.md | Shared EvidenceResearch worker | PARTIAL | 2.1 | test_evidence_research; real source retrieval PASS; Agent golden FAIL | Bounded EuropePMC queries |
| Primary-source retrieval | RS | evidence-and-numbering.md | EvidenceResearch | PARTIAL | 2.1 | PMID/PMCID identity and passage tests | Search leads/reviews cannot become direct primary evidence |
| Database search and UniProt evidence | DS/RS | target-and-site.md; gpcrdb-contract.md | EvidenceResearch reusing ScientificHttpClient | PARTIAL | 2.1 | existing UniProt helpers; real sources PASS; Agent goldens FAIL | Species required for UniProt search |
| Structure and known complex search | RS/DS | target-and-site.md | EvidenceResearch + RCSB | PARTIAL | 2.1 | bounded PDB search/entry/polymer retrieval | Assembly and physiological context require interpretation |
| Mutagenesis evidence | RS | target-and-site.md; gpcrdb-contract.md | EvidenceResearch + Site | PARTIAL | 2.1 | literature topics + existing GPCRdb adapter | Mutation can affect expression/fold rather than epitope |
| Competition and known epitope evidence | RS | target-and-site.md | EvidenceResearch + Site | PARTIAL | 2.1 | source-bound conclusions; golden pending | Direct overlap and allostery are distinct |
| Functional evidence | RS | target-and-site.md; scientific-claims.md | EvidenceResearch + Site/Judge | PARTIAL | 2.1 | synthetic primary passage test | Preserve assay and target-context limits |
| State-dependent evidence | RS | gpcr-mechanism-and-state.md | EvidenceResearch + Target/Site | PARTIAL | 2.1 | real source/kernel PASS; Agent golden FAIL | Sensor/stabilizer/competitor/artifact hypotheses separate |
| PTM/glycan evidence | RS/DS | special-target-playbooks.md | Research + Site existing features/motifs | PARTIAL | 2.1 | glycan runtime regression | Motif is not occupancy; absent model is not absence |
| Source verification, strength and scope | DS/RS | evidence-and-numbering.md; scientific-claims.md | Runtime source binding + owner/Judge | PARTIAL | 2.1 | tamper/PMID/passage tests | Source verified does not imply biological entailment |
| Conflicting and negative evidence | RS | target-and-site.md | EvidenceResearch + owner/Judge | PARTIAL | 2.1 | conflict and failure-status tests | NOT_SEARCHED differs from scientific unknown |
| Literature-derived site candidates | RS | target-and-site.md | Site | PARTIAL | 2.1 | SiteIntent origin/source card contract | Must independently map residues |
| Scan-derived candidate alternatives | DS/RS | target-and-site.md | Site + old SASA/geometry | COMPLETE | 2.1 | test_site_runtime | No new fused winner score |
| Surface accessibility / SASA / burial | DS/RS | target-and-site.md | Existing Stage 02 kernel via Site | COMPLETE | 2.1 | real deterministic tool regression | SASA is not full-VHH access |
| Secondary structure and interface geometry | DS/RS | target-and-site.md; vhh-geometry-priors.md | Site + existing structure tools | PARTIAL | 2.1 | SASA/region geometry; broader context pending | Do not infer axes from sequence labels |
| Membrane access, topology and orientation | DS/RS | gpcr-review-schema.md; gpcrdb-contract.md | Site + existing GPCR tools | PARTIAL | 2.1 | synthetic seven-helix; real source/kernel PASS; Agent golden FAIL | No GPCR leakage into soluble reasoning |
| Glycan shielding and full-context approach | RS/DS | special-target-playbooks.md | Site | PARTIAL | 2.1 | warnings and override regression | Full body clearance cannot be claimed from residue centroid |
| Mechanistic relevance / functional regions | RS | target-and-site.md | Site + Research/Judge | PARTIAL | 2.1 | mechanistic evidence contract | General protein reasoning first |
| Conservation/variants when available | DS/RS | target-and-site.md | Site + UniProt/primary evidence | PARTIAL | 2.1 | typed biology + Research | No invented conservation percentage |
| Primary/backup/avoid and alternative mechanisms | RS/H | target-and-site.md; gpcr-family-playbooks.md | Site/Judge/Gate 2 | PARTIAL | 2.1 | typed origin/role; live golden pending | Backup must differ scientifically, not cosmetically |
| Hotspot selection and exact review | DS/RS/H | strategy-yaml.md; orchestration/research.py | Site/Judge/Gate 2 + old site service | COMPLETE | 2.1 | Site approval/revision/override/replay | Final scientific authority stays human |
| GPCR conditional family heuristics | RS | gpcr-family-rules.json; gpcr-family-playbooks.md | Site after verified relevance | PARTIAL | 2.1 | real GPCR/family audit pending | Priors generate hypotheses; cannot pick winner |
| Special targets: enzyme/IDR/amyloid/multimer/imaging/chaperone | RS | special-target-playbooks.md | Target/Site/Binder | PARTIAL | 2.1 | skill parity audit | Conditional context and representation limits must remain visible |
| Binder modality / VHH strategy | RS/H | strategy-yaml.md; vhh-geometry-priors.md | Binder | COMPLETE | 2.1 | design runtime/harness | Current supported modality remains VHH |
| Hotspot conditioning, explicit avoid and neutral residues | DS/RS | strategy-yaml.md | Binder + old compiler | COMPLETE | 2.1 | design constraint tests | Non-hotspot is neutral, not implicitly forbidden |
| Crop reasoning and full-target confirmation | RS/DS | vhh-geometry-priors.md | Binder / later Pilot | PARTIAL | 2.1 / 3 | compiler tests; scientific loop pending | Crop cannot delete genuine shielding to fabricate accessibility |
| CDR/scaffold identity and actual asset ranges | RS/DS | boltzgen-contract.md; vhh-geometry-priors.md | Binder + old compiler/validator | COMPLETE | 2.1 | Phase 2 real BoltzGen check | Insertion count differs from final CDR length |
| Design arms, comparator and changed/held factors | RS/H | strategy-yaml.md | Binder | PARTIAL | 2.1 | typed arm metadata; parity review pending | Integrated arm cannot identify a single causal factor |
| First Pilot protocol, seven scaffolds × 40 per condition | DS/RS | boltzgen-contract.md; strategy-yaml.md | Binder + existing protocol validator | COMPLETE | 2.1 | frozen design validation | validation_micro will be a separate execution guard, not a protocol edit |
| Native BoltzGen YAML compilation and checks | DS | boltzgen-contract.md | Trusted callback + existing compiler/validator | COMPLETE | 2.1 | Phase 2 real check and YAML regression | No LLM-authored runnable YAML |
| Native expert path when standard cannot express science | DS/RS/H | strategy-yaml.md; boltzgen-contract.md | Binder + legacy compatibility | PARTIAL | 2.1 | legacy path retained; first-class capability probe FAIL | Critical missing first-class native import; not deferrable to Phase 3 or a coverage bypass |
| Thread-local proposals / project-global approved science | DS/RS | orchestration/research.py | Runtime explicit ownership adapters | COMPLETE | 2.1 | full-suite ownership tests + 13-case focused rerun PASS | Overall phase remains FAIL for other critical conditions |
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
Any unclosed Prepare/Strategize PARTIAL row is assessed explicitly at Phase 2.1 acceptance;
it cannot be silently deferred to Pilot or presented as scientific parity.
