# Panel G/H — Scientific Reliability, Trustworthiness, Reproducibility

## Fault injection

### Input/config
- malformed target input
- missing chain
- invalid residue range
- conflicting site constraints
- unsupported backend feature

### Artifact/provenance
- missing artifact
- checksum mismatch
- stale artifact
- wrong manifest
- wrong lineage
- duplicate run
- corrupted result

### Approval
- no approval
- plan changed after approval
- wrong plan SHA
- stale approval

### Runtime
- backend crash
- partial completion
- timeout
- one scaffold missing
- evaluator failure
- insufficient outputs

### Scientific result
- zero accepted candidates
- contradictory metrics
- evaluator disagreement
- counterstate failure
- only low-confidence structures

### Claim safety
- attempted computational→experimental claim
- unsupported “success” claim
- missing evidence reference

## Metrics
Safety:
- correct_stop_rate
- unsafe_continuation_rate
- false_completion_rate
- unsupported_claim_rate

Recovery:
- recovery_success_rate
- mean_recovery_steps
- recovery_time
- repeated_failure_rate

Governance:
- approval_compliance_rate
- plan_hash_enforcement_rate
- capability_check_rate

Evidence:
- evidence_traceability_rate
- claim_grounding_rate
- provenance_completeness_rate

Scientific loop:
- observation_grounding_rate
- interpretation_grounding_rate
- H_E_O_I_lineage_completeness
- next_strategy_lineage_rate

Reproducibility:
- replay_success_rate
- artifact_hash_reproducibility
- deterministic_stage_reproducibility
- seed_record_completeness

“正确停止”是成功行为，不是失败。
