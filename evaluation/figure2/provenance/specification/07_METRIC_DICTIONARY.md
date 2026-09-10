# Metric Dictionary

## Primary
| Metric | Level | Direction | Definition |
|---|---|---:|---|
| time_to_valid_project_min | task/run | lower | first input → first fully valid executable project |
| task_completion_rate | task/run | higher | completed workflow / assigned tasks |
| computational_HQ_yield | campaign | higher | frozen independent accepted / generated |
| correct_stop_rate | fault episode | higher | invalid/unsafe state handled by stop/gate |
| false_completion_rate | fault episode | lower | claims completion despite invalid evidence |
| evidence_traceability_rate | claim | higher | important claim linked to valid evidence |
| replay_success_rate | replay | higher | frozen run replay yields expected artifact graph |

## Secondary design
interface_confidence, interface_pae, iptm, ipsae, pdockq, bsa, delta_sasa,
interface_dg, dg_per_dsasa, shape_complementarity, hbond_count, salt_bridge_count,
clash_count, unsat_polar_count, hotspot_coverage, contact_retention,
forbidden_contact_fraction, target_rmsd, site_rmsd, binder_ptm, binder_plddt,
multi_seed_pass_fraction

## GPCR task-specific
tm6_state_deviation, microswitch_deviation, pocket_engagement,
cdr3_pocket_depth, counterstate_margin, offtarget_margin

## Developability
tnp_risk, hydrophobic_patch, positive_charge_patch, negative_charge_patch,
aggregation_liability, sequence_liability_count

## Diversity
pairwise_identity, sequence_diversity, cluster_count_70, cluster_count_80,
cluster_count_90, unique_cdr3_fraction, structure_diversity_rmsd, epitope_diversity

## Efficiency
wall_time, gpu_hours, cpu_hours, peak_vram, candidates_per_gpu_hour,
accepted_designs_per_gpu_hour, gpu_hours_per_accepted_design, failed_compute_fraction

## Agent behavior
tool_call_count, invalid_tool_call_rate, redundant_tool_call_rate,
evaluation_actions_per_candidate, alternatives_compared, premature_termination_rate,
correction_count, operational_intervention_count

## Governance
approval_compliance_rate, stale_approval_rejection_rate,
plan_hash_enforcement_rate, provenance_completeness_rate
