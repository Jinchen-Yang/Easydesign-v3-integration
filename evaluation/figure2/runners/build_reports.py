"""Build analysis tables exclusively from append-only measured receipts."""
import csv
import hashlib
import json
import random
import statistics
from pathlib import Path
from datetime import datetime, timezone

EVAL = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csvout(name, fields, records):
    path = EVAL / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def jsonout(name, value):
    path = EVAL / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def md(name, text):
    path = EVAL / "reports" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n")


def readcsv(name):
    with (EVAL / name).open() as handle:
        return list(csv.DictReader(handle))


def receipts(tier):
    return [json.loads(p.read_text()) | {"receipt_path": str(p.relative_to(EVAL)), "receipt_sha256": sha(p)} for p in sorted((EVAL / "results/raw" / tier).glob("*/episode.json"))]


def main():
    frozen = json.loads((EVAL / "provenance/freeze.json").read_text())
    hardware = json.loads((EVAL / "provenance/hardware.json").read_text())
    protocol = json.loads((EVAL / "configs/protocol.json").read_text())
    targets = readcsv("configs/target_selection.csv")
    t0, t1, agents = receipts("tier0"), receipts("tier1"), receipts("agent-decision")
    for item in t1:
        classified_file = EVAL / "provenance/setup-evidence-v2" / f"{item['run_id']}.json"
        if classified_file.exists():
            classified = json.loads(classified_file.read_text())
            item["original_prepare_status"] = item["status"]
            item["status"] = classified["final_observed_status"]
            item["failure_reason"] = classified["cause"]
    profile_sha = sha(EVAL / "configs/evaluator_profile.json")
    fields = ["benchmark_version", "repository_commit", "source_tree_sha256", "method", "model_id", "reasoning_mode", "target_id", "target_family", "task_id", "benchmark_mode", "campaign_id", "replicate_id", "condition_id", "x_conditions", "scaffold_count", "candidates_per_scaffold", "candidates_expected", "candidates_generated", "evaluator_profile", "evaluator_profile_sha256", "metric_name", "metric_value", "metric_unit", "numerator", "denominator", "status", "failure_reason", "start_time", "end_time", "wall_time_s", "gpu_hours", "cpu_hours", "hardware", "target_input_sha256", "plan_sha256", "artifact_manifest_sha256", "provenance_complete", "data_origin", "main_figure_eligible", "analysis_scope", "receipt_path"]
    fields += ["repository_dirty", "prompt_sha256", "backend_versions_receipt_sha256", "gpu_receipt_sha256", "seed_policy", "site_manifest_sha256", "condition_manifest_sha256", "candidate_budget", "failure_retry_history_ref", "runner_sha256"]
    long = []
    provenance = []
    failure = []
    runs = []

    def common(item):
        base = dict(benchmark_version="0.1.0", repository_commit=frozen["repository_commit"], source_tree_sha256=frozen["source_tree_sha256"], method=item["method"], model_id=item.get("model_id", "not-applicable-deterministic-probe"), reasoning_mode=item.get("reasoning_effort", "not-applicable"), target_id=item.get("target_id", "fixture"), target_family=item.get("target_family", "fixture"), task_id=item.get("case_id", item["run_id"]), benchmark_mode=item.get("benchmark_mode", "fixture-contract"), campaign_id=item["run_id"], replicate_id=item["replicate_id"], condition_id="", x_conditions=1, scaffold_count=7, candidates_per_scaffold=40, candidates_expected=0, candidates_generated=0, evaluator_profile="independent-computational-hq-v1", evaluator_profile_sha256=profile_sha, start_time=item.get("start_time", item.get("started_at")), end_time=item.get("end_time", item.get("ended_at")), wall_time_s=item["wall_time_s"], gpu_hours=0, cpu_hours="", hardware=hardware["platform"] if not item["method"].endswith("decision_probe") else "local-Mac-Codex-CLI", target_input_sha256=item.get("target_input_sha256", ""), plan_sha256=item.get("plan_sha256", ""), artifact_manifest_sha256=item.get("output_manifest_sha256", ""), provenance_complete=False, data_origin=item["data_origin"], main_figure_eligible=False, analysis_scope="Supplementary-engineering-characterization", receipt_path=item["receipt_path"])
        base.update(repository_dirty=True, prompt_sha256=item.get("prompt_sha256", ""))
        if "tier" in item:
            base.update(backend_versions_receipt_sha256=sha(EVAL / "provenance/runtime-registry-snapshot.json"),
                        gpu_receipt_sha256=sha(EVAL / "provenance/hardware.json"),
                        seed_policy="no-generated-candidates; fixed technical schedule")
        else:
            base.update(seed_policy="model seed not controllable; independent session blocks")
        base.update(candidate_budget=0, site_manifest_sha256="not-applicable-diagnostic", condition_manifest_sha256="not-applicable-diagnostic", failure_retry_history_ref=item["receipt_path"], runner_sha256=item.get("runner_sha256", frozen["harness_files"].get("runners/run_cpu.py", "")))
        return base

    for item in t0 + t1:
        base = common(item)
        # Actual artifact verification; a complete diagnostic receipt is not a complete scientific run.
        dest = EVAL / item["receipt_path"]
        manifest_path = dest.parent / "artifact-manifest.json"
        checks = json.loads(manifest_path.read_text())
        valid = sha(manifest_path) == item["output_manifest_sha256"] and all((dest.parent / p).is_file() and sha(dest.parent / p) == expected for p, expected in checks.items())
        base["provenance_complete"] = valid
        if item["tier"] == 0:
            long.append(base | dict(metric_name="contract_check_pass", metric_value=int(item["status"] == "passed"), metric_unit="fraction", numerator=int(item["status"] == "passed"), denominator=1, status=item["status"]))
        else:
            classification = EVAL / "provenance/setup-evidence-v2" / f"{item['run_id']}.json"
            classified = json.loads(classification.read_text()) if classification.exists() else {}
            reason = classified.get("cause", item.get("failure_reason", ""))
            long.append(base | dict(metric_name="setup_probe_wall_time_s", metric_value=item["wall_time_s"], metric_unit="second", status=item["status"]))
            long.append(base | dict(metric_name="executable_project_reached", metric_value=int(item["executable_project"]), metric_unit="binary", numerator=int(item["executable_project"]), denominator=1, status=item["status"]))
            long.append(base | dict(metric_name="time_to_valid_project_min", metric_value="", metric_unit="minute", status="endpoint-not-reached", failure_reason=item.get("failure_reason")))
            if not item["executable_project"]:
                failure.append({"run_id": item["run_id"], "target_id": item["target_id"], "method": item["method"], "event_type": item["status"], "message": reason, "evidence": str(classification.relative_to(EVAL)) if classification.exists() else item["receipt_path"], "data_origin": "real_run"})
        if not valid or (item["tier"] == 0 and item["status"] != "passed"):
            failure.append({"run_id": item["run_id"], "method": item["method"], "event_type": "integrity-or-contract-failure", "message": item["status"], "evidence": item["receipt_path"], "data_origin": item["data_origin"]})
        runs.append(base | dict(run_id=item["run_id"], tier=item["tier"], status=item["status"], failure_reason=item.get("failure_reason", "")))
        provenance.append({"run_id": item["run_id"], "receipt_path": item["receipt_path"], "receipt_sha256": item["receipt_sha256"], "source_tree_sha256": frozen["source_tree_sha256"], "prompt_sha256": item["prompt_sha256"], "plan_sha256": item["plan_sha256"], "output_manifest_sha256": item["output_manifest_sha256"], "hash_verification": valid, "scientific_main_provenance_complete": False, "reason": "diagnostic probe; no complete scientific method campaign"})

    for item in agents:
        base = common(item)
        base.update(benchmark_mode="fixture-decision-only", plan_sha256=item["casefile_sha256"], provenance_complete=False)
        dest = EVAL / item["receipt_path"]
        valid = sha(dest.parent / "prompt.txt") == item["prompt_sha256"] and sha(EVAL / "configs/decision_cases.json") == item["casefile_sha256"]
        for scored in item["scored"]:
            long.append(base | dict(task_id=scored["case_id"], metric_name="fixture_decision_correct", metric_value="" if scored["correct"] is None else int(scored["correct"]), metric_unit="binary", numerator="" if scored["correct"] is None else int(scored["correct"]), denominator=1, status="not-scorable" if scored["correct"] is None else "measured"))
        runs.append(base | dict(run_id=item["run_id"], tier=0, status="completed" if item["returncode"] == 0 else "runner-failed"))
        provenance.append({"run_id": item["run_id"], "receipt_path": item["receipt_path"], "receipt_sha256": item["receipt_sha256"], "prompt_sha256": item["prompt_sha256"], "plan_sha256": item["casefile_sha256"], "hash_verification": valid, "scientific_main_provenance_complete": False, "reason": "Prompt/case hashes checked; output files sealed at package closure. " + item["isolation_limit"]})
        if item["returncode"]:
            failure.append({"run_id": item["run_id"], "method": item["method"], "event_type": "agent-runner-failure", "message": "See captured CLI stderr; no outcome imputation", "evidence": item["receipt_path"], "data_origin": item["data_origin"]})

    queue = []
    target_rows = []
    for target in targets:
        source = EVAL / "fixtures/targets" / target["target_id"] / "target-receipt.json"
        record = json.loads(source.read_text()) if source.exists() else {"status": "not-retrieved"}
        target_rows.append(target | dict(benchmark_mode="controlled", structure_source=f"https://files.rcsb.org/download/{target['pdb_id']}.cif", structure_sha256=record.get("structure_sha256", ""), chain=record.get("selected_chain", ""), status=record["status"], source_receipt=str(source.relative_to(EVAL)), site_definition="UNRESOLVED; mandatory before GPU", counterstate="unresolved-if-required", offtargets="unresolved-if-required"))
        for rep in range(1, 4):
            for method in protocol["methods"]:
                rid = f"gpu-v010-{target['target_id']}-{method}-r{rep}"
                item = dict(run_id=rid, benchmark_version="0.1.0", tier=2 if target["target_family"].startswith("GPCR") else 3, target_id=target["target_id"], target_family=target["target_family"], method=method, benchmark_mode="controlled", replicate_id=rep, model_id=protocol["model_id"] if method != "fixed_pipeline" else "not-applicable", reasoning_effort=protocol["reasoning_effort"] if method != "fixed_pipeline" else "not-applicable", x_conditions=1, candidate_budget=280, candidates_expected=280, candidates_generated="", generation_backend="boltzgen-0.3.2@a3149cf18eeb58648d1abbb27539bd73f746cdda", evaluator_profile_sha256=profile_sha, seed_policy="uncontrolled-generation; evaluator=11,29,47; target-blocked pairing", target_sha256=record.get("structure_sha256", ""), site_sha256="", condition_sha256="", plan_sha256="", prompt_sha256="", backend_receipt_sha256="", site_approved=False, runtime_validated=False, baseline_isolation_verified=False, independent_evaluator_smoke_passed=False, resource_cost_measured=False, explicit_gpu_authorization=False, status="not-run-gated")
                queue.append(item)
                runs.append(item | dict(reasoning_mode=item["reasoning_effort"], repository_commit=frozen["repository_commit"], source_tree_sha256=frozen["source_tree_sha256"], data_origin="", main_figure_eligible=False, failure_reason="Missing approved site, exact plans, baseline isolation and evaluator/cost smoke; GPU not authorized"))
    random.Random(protocol["generation"]["schedule_seed"]).shuffle(queue)
    jsonout("manifests/GPU_TASK_QUEUE.json", queue)
    csvout("TARGET_MANIFEST.csv", list(target_rows[0]), target_rows)
    csvout("RUN_MANIFEST.csv", list(dict.fromkeys(["run_id", "tier", "status", "failure_reason"] + fields)), runs)
    csvout("FIGURE2_DATA_LONG.csv", fields, long)
    csvout("PROVENANCE_MANIFEST.csv", ["run_id", "receipt_path", "receipt_sha256", "source_tree_sha256", "prompt_sha256", "plan_sha256", "output_manifest_sha256", "hash_verification", "scientific_main_provenance_complete", "reason"], provenance)
    csvout("FAILURE_EVENTS.csv", ["run_id", "target_id", "method", "event_type", "message", "evidence", "data_origin"], failure)
    csvout("CLAIM_EVENTS.csv", ["run_id", "claim_id", "assertion_domain", "evidence_ref", "supported", "main_figure_eligible"], [])
    summary = []
    case_ids = sorted({i["case_id"] for i in t0})
    for key in case_ids:
        items = [i for i in t0 if i["case_id"] == key]
        summary.append(dict(panel=items[0]["panel"], method="easydesign_contract_probe", metric_name="contract_check_pass", target_id=key, estimate=sum(i["status"] == "passed" for i in items)/len(items), n_runs=len(items), n_targets=0, raw_candidate_count=0, ci_low="", ci_high="", status="descriptive-technical-replays", main_figure_eligible=False))
    agent_sessions = []
    for item in agents:
        scored = [s for s in item["scored"] if s["correct"] is not None]
        agent_sessions.append(dict(run_id=item["run_id"], method=item["method"], replicate_id=item["replicate_id"], correct=sum(s["correct"] for s in scored), scorable=len(scored), accuracy=sum(s["correct"] for s in scored)/len(scored) if scored else "", status="measured" if scored else "infrastructure-failure-unscorable"))
    csvout("results/derived/AGENT_DECISION_SESSION_SUMMARY.csv", ["run_id", "method", "replicate_id", "correct", "scorable", "accuracy", "status"], agent_sessions)
    agent_summary_text = []
    for method in sorted({i["method"] for i in agent_sessions}):
        scored = [i for i in agent_sessions if i["method"] == method and i["scorable"]]
        total = sum(i["scorable"] for i in scored)
        correct = sum(i["correct"] for i in scored)
        agent_summary_text.append(f"- {method}: {correct}/{total} decisions in {len(scored)} independent model sessions (12 clustered questions/session).")
        summary.append(dict(panel="ED", method=method, metric_name="fixture_decision_correct", estimate=statistics.mean(i["accuracy"] for i in scored) if scored else "", n_runs=len(scored), n_targets=0, raw_candidate_count=0, status="supplementary-session-clustered; no population inference", main_figure_eligible=False))
    for letter, metric in zip("abcdefgh", ["time_to_valid_project_min", "task_completion_rate", "computational_HQ_yield", "independent_interface_quality", "non_gpcr_HQ_yield", "paired_generalization_effect", "correct_stop_rate", "evidence_traceability_rate"]):
        summary.append(dict(panel=letter, method="primary-comparison", metric_name=metric, estimate="", ci_low="", ci_high="", n_targets=0, n_runs=0, raw_candidate_count=0, status="NOT AVAILABLE", main_figure_eligible=False))
    csvout("FIGURE2_SUMMARY.csv", ["panel", "method", "target_id", "metric_name", "estimate", "ci_low", "ci_high", "n_targets", "n_runs", "raw_candidate_count", "status", "main_figure_eligible"], summary)

    dictionary = [
        ("time_to_valid_project_min", "a", "target-campaign", "minute", "lower", "First input to first fully valid target/site/backend/artifact executable project; missing if endpoint not reached"),
        ("task_completion_rate", "b", "target-campaign", "fraction", "higher", "Complete defined workflow / all assigned method episodes; scientific stop reported separately"),
        ("first_pass_validity_rate", "b", "target-campaign", "fraction", "higher", "First submitted project valid without operational correction / all assigned episodes"),
        ("operational_intervention_count", "b", "target-campaign", "count", "lower", "Human repairs to config/tool/path; excludes necessary scientific approval"),
        ("computational_HQ_yield", "c/e", "target-campaign", "fraction", "higher", "All generated designs passing frozen independent profile / all generated designs; incomplete evaluation is missing"),
        ("independent_iptm", "d", "candidate-to-campaign", "fraction", "higher", "Protenix complex interface confidence; campaign median; no affinity interpretation"),
        ("interface_pae_angstrom", "d", "candidate-to-campaign", "angstrom", "lower", "Both directed PAE entries averaged over inter-chain residue pairs in <=5 A heavy-atom contact"),
        ("hotspot_coverage", "d", "candidate-to-campaign", "fraction", "higher", "Frozen hotspot residues contacting binder <=5 A / all hotspot residues"),
        ("severe_clash_count", "d", "candidate-to-campaign", "count", "lower", "Inter-chain heavy-atom pairs <1.5 A"),
        ("target_site_ca_rmsd_angstrom", "d", "candidate-to-campaign", "angstrom", "lower", "Site plus 8 A reference neighborhood CA RMSD after global mapped target CA Kabsch alignment"),
        ("multi_seed_pass_fraction", "d", "candidate-to-campaign", "fraction", "higher", "Passing independent evaluation seeds / all 3 required seeds"),
        ("paired_generalization_effect", "f", "target", "absolute-yield-difference", "higher", "Mean matched campaign HQ yield EasyDesign minus Plain Codex within target"),
        ("correct_stop_rate", "g", "independent-fault-episode", "fraction", "higher", "Unsafe/invalid state stopped or gated / applicable episodes; not a unit-test pass rate"),
        ("unsafe_continuation_rate", "g", "independent-fault-episode", "fraction", "lower", "Invalid state actually continued / applicable episodes"),
        ("recovery_success_rate", "g", "independent-fault-episode", "fraction", "higher", "Valid state actually restored / recoverable episodes"),
        ("false_completion_rate", "g", "independent-fault-episode", "fraction", "lower", "Completion asserted with invalid evidence / episodes"),
        ("unsupported_claim_rate", "g", "claim", "fraction", "lower", "Unsupported important claims / reviewed important claims"),
        ("approval_compliance_rate", "h", "decision", "fraction", "higher", "Actions with exact valid required approval / actions requiring approval"),
        ("evidence_traceability_rate", "h", "claim", "fraction", "higher", "Claims with verified artifact references / important claims"),
        ("replay_success_rate", "h", "scientific-replay", "fraction", "higher", "Frozen scientific run reproduced with expected artifact graph; byte identity separately reported"),
        ("lineage_completeness", "h", "campaign", "fraction", "higher", "Connected hypothesis-experiment-observation-interpretation chain / eligible runs"),
        ("provenance_completeness_rate", "h", "campaign", "fraction", "higher", "All mandatory provenance fields genuinely recorded / campaigns"),
        ("contract_check_pass", "ED", "contract-case", "binary", "higher", "Existing deterministic production contract test assertions passed; repeats technical"),
        ("setup_probe_wall_time_s", "ED", "technical-setup-replay", "second", "none", "Observed init/status/prepare/optional-scan/validate elapsed time; not usability turnaround"),
        ("executable_project_reached", "ED", "technical-setup-replay", "binary", "higher", "Actual validated executable project endpoint reached by deterministic setup probe"),
        ("fixture_decision_correct", "ED", "model-episode-block", "binary", "higher", "Decision disposition matches preregistered fixture and no experimental overclaim; no executed-workflow claim")]
    optional = ["ipsae", "bsa", "delta_sasa", "interface_dg", "dg_per_dsasa", "shape_complementarity", "tnp_risk", "sequence_diversity", "cluster_count_70", "cluster_count_80", "cluster_count_90", "unique_cdr3_fraction", "tm6_state_deviation", "counterstate_margin", "offtarget_margin", "forbidden_contact_fraction", "gpu_hours", "cpu_hours", "peak_vram", "accepted_designs_per_gpu_hour", "tool_call_count", "correction_count"]
    dictionary += [(metric, "ED", "campaign", "provider-defined", "not-frozen", "Optional secondary; exact computation and applicability must be frozen before analysis; currently unavailable") for metric in optional]
    csvout("METRIC_DICTIONARY.csv", ["metric_name", "panel", "analysis_unit", "unit", "direction", "definition"], [dict(zip(["metric_name", "panel", "analysis_unit", "unit", "direction", "definition"], row)) for row in dictionary])

    manifest = {"benchmark_version": "0.1.0", "created_at": datetime.now(timezone.utc).isoformat(), "frozen_source": frozen["source_tree_sha256"], "repository_commit": frozen["repository_commit"], "dirty": True, "protocol_sha256": sha(EVAL / "configs/protocol.json"), "evaluator_profile_sha256": profile_sha, "thresholds_frozen_before_generation": True, "evaluator_runtime_validated": False, "methods": protocol["methods"], "probe_methods_not_main_comparison": sorted({i["method"] for i in t0+t1+agents}), "tier0_contract_episodes": len(t0), "tier1_setup_episodes": len(t1), "agent_decision_episodes": len(agents), "planned_gpu_campaigns": len(queue), "planned_candidates": sum(r["candidate_budget"] for r in queue), "actual_generated_candidates": 0, "real_gpu_runs": 0, "main_figure_admissible_rows": 0, "manual_expert": "NOT AVAILABLE", "wet_lab": "NOT AVAILABLE", "pending_blockers": ["Exact approved target/site/condition manifests", "Main Full/Plain agent execution isolation", "Independent-evaluator end-to-end smoke and cost calibration", "Shared GPU capacity and explicit authorization"], "data_files": {name: sha(EVAL/name) for name in ["TARGET_MANIFEST.csv", "RUN_MANIFEST.csv", "FIGURE2_DATA_LONG.csv", "FIGURE2_SUMMARY.csv", "FAILURE_EVENTS.csv", "PROVENANCE_MANIFEST.csv", "METRIC_DICTIONARY.csv"]}}
    jsonout("EVAL_MANIFEST.json", manifest)
    n_pass = sum(i["status"] == "passed" for i in t0)
    n_valid = sum(i["executable_project"] for i in t1)
    t1states = {status: sum(i["status"] == status for i in t1) for status in sorted({i["status"] for i in t1})}
    valid_targets = sum(t["status"] == "acquired-identity-bound" for t in target_rows)
    md("EVAL_PREFLIGHT.md", f"""# Figure 2 evaluation preflight

Frozen v2.1 source: `{frozen['repository_commit']}` with dirty source tree `{frozen['source_tree_sha256']}`.
Core science and 7 × 40 × X remain unchanged. Evaluation instrumentation is separate.

## Target and budget queue

6 GPCR: ADRB2, CXCR4, MC4R, GLP1R, ADORA2A, DRD2.
7 non-GPCR: PD-L1, EGFR, IL7Ralpha, BHRF1, SpCas9, BBF-14, MBP.
All three primary methods have X=1, 280 candidates/campaign, 3 campaigns/target.
GPCR: 54 campaigns / 15,120 candidates. Non-GPCR: 63 / 17,640.
Total: 117 campaigns / 32,760 generated candidates, plus 98,280 independent Protenix seed predictions.
No 50k scale jobs are included. Every target remains in the manifest, including acquisition failures.
Methods: EasyDesign Full, Plain Codex (gpt-6-astra/high for both), deterministic fixed pipeline.
Controlled site and condition manifests are not yet approved or hash-bound; these queue entries are planning records.

## Hardware and cost

Host observation: 8 × A100 PCIe 40GB, all about 97–100% utilized by existing work; 96 logical CPU cores;
data filesystem 4.46 TB (4.05 TiB) available at initial inspection. Hardware receipt records exact bytes and time.
Runtime doctor passed: BoltzGen 0.3.2, Protenix 2.0.0, AFO/OpenFold3 3.1.4, PyMOL, CPU ScanNet and TNP.
Registry snapshots contain package locks/checkpoint identities. This is not an independent-evaluator smoke test.

Measured benchmark GPU-hours: **0**. Reliable projected GPU-hours: **UNMEASURED**.
Planning sensitivity only: if generation costs 30–120 GPU-seconds/design and independent evaluation
20–90 GPU-seconds/design/seed, the 32,760-candidate queue costs approximately 819–3,549 GPU-hours,
before additional AFO internal screening, MSA, warm-up, retries and TNP. These are assumptions, not measured throughput.
Full SpCas9 and receptor constructs may exceed these assumptions or 40GB capacity.
Storage sensitivity: assuming 1–10 MB per generated/evaluated structure set and four sets/design,
about 131–1,310 GB, excluding trajectories and intermediate caches. Measure a bounded pilot before reserving space.
Do not translate GPU-hours to USD without an explicit dated hardware pricing source.

## Evaluator and seed policy

Independent profile SHA: `{profile_sha}`.
Predict with independent Protenix seeds 11/29/47 and apply common interface confidence, contact-pair PAE,
hotspot engagement, severe-clash, target-deformation and 2-of-3 consistency gates.
Profile is prospectively specified, not experimentally calibrated. Its runtime and geometry mapping still require smoke validation.
BoltzGen 0.3.2 does not expose reproducible generation seed control; pairing is by target/replicate block,
not identical random samples. Never claim exact stochastic coordinate replay.

## Commands

```sh
.venv/bin/python evaluation/figure2/runners/run_cpu.py verify
.venv/bin/python evaluation/figure2/runners/run_cpu.py tier0
.venv/bin/python evaluation/figure2/runners/run_cpu.py acquire
.venv/bin/python evaluation/figure2/runners/run_cpu.py tier1
.venv/bin/python evaluation/figure2/runners/gpu_gate.py --queue evaluation/figure2/manifests/GPU_TASK_QUEUE.json
```

The last command deliberately exits blocked and never launches GPU. Production Full method, once an actual
project and strategy are frozen: `easydesign pilot plan PROJECT --strategy REVISION --prediction-backend afo --json`;
then use the returned exact plan-bound run intent after explicit GPU authorization.
Plain/fixed native backend commands cannot be called executable before their target/site/native YAML and equal-budget
manifests are bound and validated. No fake ready-to-run command is supplied for these unresolved inputs.

## Gate disposition

GPU **NOT AUTHORIZED / NOT STARTED**. Needed: exact sites and scope reviews, baseline isolation,
independent evaluator smoke, measured cost and available capacity. Tier 0/1 diagnostic work is authorized and recorded.
""")
    md("FIGURE2_RESULTS_REPORT.md", f"""# Figure 2 measured results

{n_pass}/{len(t0)} deterministic contract executions passed, covering {len(case_ids)} distinct cases with three technical replays each.
This tests frozen code behavior, not full autonomous agent success. Fixture values are not candidate design results.

{valid_targets}/13 target structures were acquired and bound to the selected RCSB polymer entity.
{len(t1)} assigned setup checks across {len({i['target_id'] for i in t1})} targets were recorded:
36 real CLI setup sequences and 3 BHRF1 input-identity blocks before CLI launch.
Executable-project endpoint reached: {n_valid}/{len(t1)}. Observed dispositions: `{json.dumps(t1states)}`.
These final dispositions use the latest captured stage response. The raw CPU episode's `status` field
records target preparation only; all three BBF-14 preparations succeeded but their later SASA site
proposals require approval. This distinction is preserved in `provenance/setup-evidence-v2/`.
Elapsed setup time is diagnostic timing, not time-to-valid-project. The success endpoint was not reached.
Scientific review requests are retained as review requests, not scored as unnecessary operational interventions.

Separate model fixture-decision probes: {len(agents)} attempted sessions. They use identical gpt-6-astra/high settings.
They measure Skill-guided decision policy, not the full EasyDesign harness. See raw transcripts, including errors.
They are Supplementary-only and do not establish main-method superiority.

{chr(10).join(agent_summary_text)}

Two initial sessions failed at CLI configuration before model inference and are unscorable, not model failures.
Later successful sessions are all retained; the identical ceiling result supplies no evidence of superiority.
Questions share a session context and must not be analysed as independent campaigns.

Computational generation: 0 candidates, 0 GPU campaigns. HQ yield, diversity, GPCR quality advantage,
non-GPCR paired effect and experimental affinity/hit rate are NOT AVAILABLE.
The four research questions remain open until fair complete campaigns exist.

The initial non-GPCR BHRF1 accession was not the strain accession of 2WH6; the strict retrieval check retained this
as an explicit identity mismatch instead of silently choosing the nearest protein. Its correction requires a recorded
target-manifest amendment before any main benchmark launch. Historical benchmark wet-lab values are not imported.
""")
    md("FIGURE2_STATISTICAL_REPORT.md", """# Statistical analysis and current limits

Independent primary unit: target × independent campaign. Candidate values only form a campaign HQ numerator,
denominator and descriptive quality/diversity summaries. Targets receive equal weight.
The paired effect is EasyDesign minus Plain Codex within matched target, site, condition, budget and replicate block.
Resample targets first and matched campaign pairs within sampled targets, 10,000 draws, seed 20260906,
percentile 95% CI. `metrics/independent_hq.py` implements this analysis and returns missing for absent data.
Absolute effect, relative effect where the baseline is nonzero, N targets, N runs and raw candidates must accompany results.
With only one target report descriptive effect and no population CI. With 3 campaigns/target, per-target intervals
are exploratory and unstable; prefer the raw paired run effects. Zero baseline relative effect is undefined.

No p-values or superiority claims are presently computed. If used later: state a two-sided paired/permutation
hypothesis before analysis; apply BH FDR within the full declared secondary endpoint family, retaining null results.
Time endpoint failures remain censored/missing plus observed stop time, never zero or the stopping time labelled as success.
All assigned failures enter operational analyses; scientific negative results remain completed scientific results.
Zero generated designs give undefined HQ yield. Partial independent evaluation prevents a primary HQ estimate;
accepted/generated lower bound may be shown separately and cannot replace the endpoint.

The contract suite's three repetitions are technical replays, so 60 passes do not constitute 60 independent
reliability observations and no Wilson interval is attached to those repetitions. Contract cases were selected from
existing production tests: ascertainment bias and lack of independent adversarial discovery must be disclosed.
Model fixture questions share one session per block; questions are clustered, not independent trials.
Only the model-session block is a replicate for the supplementary decision probe, and it has limited read isolation.

Present data support engineering characterization only. No main-method paired sample, target-level effect size,
bootstrap CI or causal comparison exists yet. Main plot empty states are intentional, not zero estimates.
""")
    md("FIGURE2_MISSING_DATA.md", """# Missing data register

| Component | State | What is needed |
|---|---|---|
| Main Full vs Plain vs fixed comparison | NOT RUN | Isolated equal-tool method execution and receipts |
| Tier 1 executable plan | Endpoint not reached in diagnostic sweep | Construct/identity resolution, reviewed sites, real strategies |
| 2a true turnaround / 2b usability | NOT AVAILABLE | Independent end-to-end agent episodes and scientific approval timing |
| 2c/d GPCR HQ yield and depth | NOT AVAILABLE | Equal-budget generation + independent evaluation for all candidates |
| 2e/f generalization | NOT AVAILABLE | Same evaluation on seven non-GPCR targets |
| 2g full-method reliability | NOT AVAILABLE | Actual isolated action execution fault episodes; contract results are supplementary |
| 2h scientific replay | NOT AVAILABLE | Real frozen science run + replay, not just graph/unit test replays |
| Mandatory exact sites / X condition artifacts | Unresolved | Source-bound biological/context review before GPU |
| BHRF1 strain accession | Initial identity mismatch | Recorded target-manifest correction to deposited strain |
| GPU throughput/storage estimates | Uncalibrated | Bounded approved cost/evaluator smoke |
| Optional physics/developability | NOT AVAILABLE | Validated common provider outputs |
| Expert / wet lab | NOT AVAILABLE | Real expert logs or experimental records only |

Blank CSV values mean unmeasured; status explains why. No mock numeric row is used as a result.
""")
    md("FIGURE2_FINAL_AUDIT.md", f"""# Figure 2 final audit

## Actual evidence

Frozen production source `{frozen['source_tree_sha256']}`; {len(t0)} real deterministic fixture executions,
{len(t1)} actual target setup attempts, {len(agents)} separately labelled model fixture-decision sessions.
Run logs, input files, HTTP retrieval receipts, project/run manifests and hashes are retained.
No old design results were selected or re-labelled. No expert or wet-lab data were invented.

## Infrastructure versus scientific completion

Protocol, target panel, evaluator cutoff definition, metric schemas, equal-budget inert queue,
acceptance math, hierarchical paired bootstrap, report generation and a–h plotting entrypoints are present.
End-to-end independent evaluator integration and isolated primary method runners remain incomplete.
No generated candidate or independent prediction exists. A parsed config, passing unit test or prepared input
does not constitute scientific benchmark completion.

## Figure eligibility

Current main-figure comparative evidence: **none**. 2a–f are empty publication-schema panels.
2g/h show explicitly labelled contract-only diagnostics and are suitable only for Supplementary engineering validation.
Main 2g/h require actual Full-versus-Plain executed-action episodes and real scientific replay.
Model decision probes and setup wall times are supplementary with scope labels and raw transcripts.

## Fairness, leakage and tuning

Main methods share gpt-6-astra/high for both agents and identical BoltzGen/evaluator/budget policy.
No generation or threshold tuning occurred. Cutoffs are operational, not empirically calibrated.
Controlled and end-to-end effects are kept separate. Existing tested targets may already have informed Skill development;
there is no assertion of training-data exclusion. Frozen test selection is not an independently held-out adversarial set.
Model probes use clean cwd and disabled host Skill discovery/plugins, but read-only sandbox is not a proven
read-isolation boundary. They cannot substitute for isolated primary baselines.
Generation seeds are unsupported by the pinned CLI; exact random-number matching cannot be claimed.
Every excluded/unscorable record remains in run/failure tables; no candidate-level pseudoreplication or zero imputation.

## Production issue observed

The local mmCIF + canonical identity path evaluates every inventory chain, including non-protein chains with
empty sequence, before applying an explicit selected chain. Real IL7Ralpha 3DI3 failed with
`construct sequence must be nonempty` in the retained Stage 01 manifest.
Relevant source: `src/easydesign/orchestration/stage01_sources.py` identity_by_chain comprehension (around line 1738).
This is a frozen-version finding, not a reason to patch the system mid-comparison. Any repair requires a new
source/benchmark version and reruns of every affected method. Do not count initial empty strategy drafts as validated strategies.

## Next high-value work

1. Resolve construct/chain/identity failures and BHRF1 strain in a versioned target manifest; preserve this sweep.
2. Produce mechanism/context-bound shared sites for one GPCR and one non-GPCR, then review exact plans.
3. Validate isolated Full/Plain/fixed CPU agents on those same two targets with three independent episodes each.
4. Run an explicitly approved bounded backend/evaluator/cost smoke when GPU capacity becomes available.
5. Only then release the 117-campaign queue, preferably the 6-target GPCR arm followed by the 7 non-GPCR arm.

No GPU benchmark was launched, and no blanket approval is inferred from availability.
""")
    md("SOURCE_NOTES.md", """# Sources and retrieval scope

BenchBB target names and PDB suggestions were checked against the original organizer page:
https://www.adaptyvbio.com/blog/benchbb . The older start URL now redirects to services.
Target acquisition uses RCSB mmCIF + polymer entity API and UniProt canonical records, with raw per-request receipts.
BenchBB serves as a standardized target panel for VHH; historical miniprotein wet-lab performance is not a comparator.

BioDesignBench methodology source identity was verified as a preprint:
https://pubmed.ncbi.nlm.nih.gov/42146566/ (Kim and Romero, 2026; DOI 10.64898/2026.05.06.723381).
No quantitative outcome from this paper is imported into Figure 2.
The supplied binder-scoring preprint https://www.biorxiv.org/content/10.1101/2025.08.14.670059v2
could not be retrieved by the browser; no numerical threshold is attributed to it.

Codex noninteractive execution was checked against local CLI help and official documentation:
https://learn.chatgpt.com/docs/non-interactive-mode . Raw local CLI events record actual model sessions.
""")
    print(json.dumps({"tier0": len(t0), "tier1": len(t1), "agents": len(agents), "planned_campaigns": len(queue), "actual_generated": 0, "main_rows": 0}))


if __name__ == "__main__":
    main()
