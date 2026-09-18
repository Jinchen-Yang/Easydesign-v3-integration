# Figure 2A/B control execution contract

The benchmark starts from the same frozen, approved Target state. Figure 2A follows each method
to a pilot-ready project. Figure 2B uses each method's own selected Site and Design strategy in an
equal-budget candidate campaign.

## Main comparison

1. `expert_curated_reference`: a named human expert authors the plan and a second named human
   records review. Missing human data remain `UNAVAILABLE`; an LLM may never role-play this arm.
2. `base_llm_tools`: a prospective deterministic script executes the declared standard atomic
   tool manifest against the frozen source snapshot. At Site and Binder, the same foundation
   model receives the corresponding frozen packet and gets one structured submission per stage.
   It has no autonomous tool loop, protein-design Skill, model-facing scientific memory,
   specialist decomposition, scientific Judge or automatic recovery.
3. `generic_agent`: the same foundation model uses the same scientific tools and hard ceilings in
   standard autonomous Site and Binder tool-calling loops. It has no EasyDesign domain Skill,
   specialist decomposition, evidence-dossier synthesis, scientific Judge or automatic recovery.
   Runtime retains approved artifacts only so the method can reach the same compiler-validated
   Gate 3 endpoint. It is a competitive generic agent, not an intentionally weakened prompt.
4. `easydesign_v3_full`: the production Harness with domain Skills, persistent scientific state,
   isolated research/synthesis, runtime dossier, deterministic validators, independent Judge and
   recovery.

`native_interface_oracle` is a deterministic hidden-interface upper bound for the retrospective
complex. It is neither an expert nor an autonomous method and is not drawn as a fifth main method.

## Ablation comparison

Panel A4 separately evaluates `minus_scientific_state`, `minus_domain_skills`,
`minus_evidence_judge` and `minus_recovery` against the full Harness. These ablations cannot be
substituted for Base LLM + Tools or Generic Agent in the main comparison.

The Skill loader is method-defining infrastructure rather than an atomic scientific evidence
source. All computational methods use the same source snapshot, target input, model version and
settings, and the same implementation of each scientific tool. The Base packet records every tool
name, argument hash, result hash and source snapshot ID. Autonomous methods choose their calls
within the same source/query ceiling. Source acquisition is frozen before randomized method order,
so later network or database changes cannot favor a method.

## Fair execution

Each computational method gets one primary attempt per replicate and no method-specific control
retry. First-pass output is frozen before repair. By investigator instruction, Codex occupies the
human-repair slot and may perform at most two uniformly logged correction rounds after first-pass
scoring. A code or Harness change invalidates that run and requires a fresh project from raw input.
Base LLM + Tools has one structured submission per stage; Generic Agent and EasyDesign share the
same maximum model/tool/query ceilings. Failures remain results. Runtime hard-fact validation and
the independent evaluator are shared. Machine-readable records retain the Codex operator identity.

Figure 2B uses 7 VHH scaffolds x 40 candidates per scaffold per method/case. Candidate filters,
metric definitions, BoltzGen/sequence/refold settings, compute precision and selection rules are
frozen before the first campaign. Every generated candidate remains in the denominator. Candidate
rows are not reported as independent target replicates.
