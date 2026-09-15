"""Scientific Arm populations, native-PASS working sets and bounded opinion binding."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any, TypeGuard

from easydesign.core import canonical_model_sha256

from .contracts import AgentBoundaryError
from .phase34_contracts import PilotMeasurement
from .phase34_plan import PilotArmIntent

NATIVE_RANKING_POLICY = "native-ranking-first-v2"

# Direction organizes observations; it is neither a cutoff nor a fitness equation.
METRIC_DIRECTIONS = {
    "bb_rmsd": "lower",
    "bb_rmsd_design": "lower",
    "bb_rmsd_target": "lower",
    "bb_rmsd_design_target": "lower",
    "bb_target_aligned_rmsd_design": "lower",
    "design_ptm": "higher",
    "design_to_target_iptm": "higher",
    "design_iptm": "higher",
    "design_iiptm": "higher",
    "design_ipsae_min": "higher",
    "interaction_pae": "lower",
    "min_design_to_target_pae": "lower",
    "complex_plddt": "higher",
    "complex_iplddt": "higher",
    "delta_sasa_refolded": "higher",
    "plip_hbonds_refolded": "higher",
    "plip_saltbridge_refolded": "higher",
    "refold_hotspot_to_binder_contact_count": "higher",
    "refold_hotspot_to_binder_contact_fraction": "higher",
    "refold_hotspot_to_design_contact_count": "higher",
    "refold_hotspot_to_design_contact_fraction": "higher",
    "refold_avoid_to_binder_contact_count": "lower",
    "refold_avoid_to_design_contact_count": "lower",
    "refold_interface_atom_contacts": "higher",
    "refold_interface_residue_pairs": "higher",
    "refold_severe_clash_count": "lower",
    "refold_minimum_heavy_atom_distance": "context",
    "refold_design_contact_fraction": "higher",
    "refold_design_interface_fraction": "higher",
}


def _numeric(value: Any) -> TypeGuard[float | int]:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _distribution(values: list[Any]) -> dict[str, Any]:
    present = [float(v) for v in values if _numeric(v)]
    quartiles = statistics.quantiles(present, n=4, method="inclusive") if len(present) > 1 else []
    return {
        "available": len(present),
        "missing": len(values) - len(present),
        "minimum": min(present) if present else None,
        "q25": quartiles[0] if quartiles else (present[0] if present else None),
        "median": statistics.median(present) if present else None,
        "q75": quartiles[2] if quartiles else (present[0] if present else None),
        "maximum": max(present) if present else None,
    }


def native_working_set(
    measurement: PilotMeasurement, arms: tuple[PilotArmIntent, ...]
) -> dict[str, Any]:
    from .phase34_science import compact_arm_intent

    native = measurement.native_evidence
    if native is None:
        raise AgentBoundaryError("Native ranking requires verified native evidence")
    owner = {s: a.arm_id for a in arms for s in a.strategy_ids}
    if len(owner) != sum(len(a.strategy_ids) for a in arms) or (
        {d.strategy_id for d in measurement.arms} - set(owner)
    ):
        raise AgentBoundaryError("Scientific Arm ownership is ambiguous or incomplete")
    rows = {c.candidate_id: c for c in native.candidates}
    lineage = {c.lineage.candidate_id: c.lineage for c in measurement.candidates}
    passes = {i: c for i, c in rows.items() if c.native_pass is True}
    vectors = {i: {**c.metrics, **c.additional_metrics} for i, c in rows.items()}
    candidate_facts = {}
    for candidate_id in sorted(passes):
        vector = vectors[candidate_id]
        ranks = {}
        for metric, direction in METRIC_DIRECTIONS.items():
            value = vector.get(metric)
            population = [vectors[i].get(metric) for i in passes]
            present = [v for v in population if _numeric(v)]
            if not _numeric(value) or direction == "context":
                continue
            better = sum(v < value if direction == "lower" else v > value for v in present)
            ranks[metric] = {
                "rank": better + 1,
                "population": len(present),
                "fraction_strictly_worse": sum(
                    v > value if direction == "lower" else v < value for v in present
                )
                / len(present),
            }
        c = lineage[candidate_id]
        candidate_facts[candidate_id] = {
            "arm_id": owner[c.strategy_id],
            "strategy_id": c.strategy_id,
            "backend_candidate_id": c.backend_candidate_id,
            "sequence": vector.get("designed_chain_sequence"),
            "designed_sequence": vector.get("designed_sequence"),
            "sequence_sha256": c.sequence_sha256,
            "design_mask_residue_ids": c.designed_binder_residue_ids,
            "native_pass": True,
            "profile_sha256": passes[candidate_id].profile_sha256,
            "metrics": {k: vector.get(k) for k in METRIC_DIRECTIONS},
            "available_additional_metrics": passes[candidate_id].additional_metrics,
            "within_pilot_pass_ranks": ranks,
            "full_metric_vector_ref": f"native_evidence.candidates:{candidate_id}",
            "missing_metrics": [k for k in METRIC_DIRECTIONS if vector.get(k) is None],
            "original_structure": c.original_structure.model_dump(mode="json"),
            "refolded_structure": c.refolded_structure.model_dump(mode="json"),
        }
    arm_facts = {}
    for arm in arms:
        group = [i for i, c in lineage.items() if c.strategy_id in arm.strategy_ids]
        denominators = [d for d in measurement.arms if d.strategy_id in arm.strategy_ids]
        planned = sum(d.planned_candidates for d in denominators)
        generated = sum(d.generated_candidates for d in denominators)
        evaluable = sum(rows[i].native_pass is not None for i in group)
        passed = [i for i in group if i in passes]
        complete = planned > 0 and planned == generated == evaluable
        mode = ("PROMOTION" if passed else "RECOVERY") if complete else "OPERATIONAL_INCOMPLETE"
        if complete and measurement.execution.mode == "validation-micro":
            mode = "VALIDATION_ONLY"
        all_distributions = {
            k: _distribution([vectors[i].get(k) for i in group]) for k in METRIC_DIRECTIONS
        }
        pass_distributions = {
            k: _distribution([vectors[i].get(k) for i in passed]) for k in METRIC_DIRECTIONS
        }
        failures: Counter[str] = Counter()
        combinations: Counter[str] = Counter()
        scaffold_failures: dict[str, Counter[str]] = {}
        for i in group:
            failed = [d.feature for d in rows[i].decisions if d.passed is False]
            failures.update(failed)
            if failed:
                combinations[" + ".join(sorted(failed))] += 1
                scaffold_failures.setdefault(lineage[i].strategy_id, Counter()).update(failed)
        arm_facts[arm.arm_id] = {
            "design_intent": compact_arm_intent(arm),
            "mode": mode,
            "validation_only": measurement.execution.mode == "validation-micro",
            "complete": complete,
            "planned": planned,
            "generated": generated,
            "evaluable": evaluable,
            "native_pass_count": len(passed),
            "native_pass_rate": len(passed) / planned if complete else None,
            "observed_pass_fraction": len(passed) / evaluable if evaluable else None,
            "pass_scaffold_count": len({lineage[i].strategy_id for i in passed}),
            "executed_scaffold_count": len(denominators),
            "strategy_denominators": [d.model_dump(mode="json") for d in denominators],
            "pass_candidate_ids": passed,
            "all_candidate_distributions": all_distributions,
            "pass_candidate_distributions": pass_distributions,
            "unique_pass_sequences": len({lineage[i].sequence_sha256 for i in passed}),
            "operational_failure_count": sum(d.operational_failure_count for d in denominators),
            "failure_dossier": {
                "native_filter_failure_histogram": dict(failures),
                "failure_cooccurrence": dict(combinations),
                "per_scaffold_failures": {s: dict(v) for s, v in scaffold_failures.items()},
            }
            if mode == "RECOVERY"
            else None,
        }
    return {
        "version": "ranked-pilot-v1",
        "measurement_sha256": canonical_model_sha256(measurement),
        "execution": measurement.execution.model_dump(mode="json"),
        "facts": {**arm_facts, **candidate_facts},
        "scientific_arms": arm_facts,
        "pass_candidates": candidate_facts,
        "metric_directions": METRIC_DIRECTIONS,
        "filter_profiles": {
            k: {
                "rules": [r.model_dump() for r in p.rules],
                "source_commit": p.source_commit,
                "configuration_ref": p.configuration_ref.model_dump(mode="json"),
            }
            for k, p in native.profiles.items()
        },
        "interpretation_limits": [
            "Only complete Arms with native passes are eligible for Scale recommendation.",
            "Only complete/evaluable zero-pass Arms receive scientific recovery analysis.",
            "Individual candidate or scaffold failure is not scientific Arm failure.",
            "Incomplete Arms can have provisional candidate rankings, never final yield claims.",
            "Use all available metric dimensions, not a universal fitness equation or cutoff.",
            "Ranks are within this Pilot PASS population; "
            "compare unequal samples with uncertainty.",
            "AFO and Judge are optional; "
            "scientific uncertainty does not remove native PASS candidates.",
            "Hypothesis comparisons do not establish binding, inhibition "
            "or negative-control truth.",
        ],
    }


def bind_native_ranking(
    measurement: PilotMeasurement, arms: tuple[PilotArmIntent, ...], opinion: Any
) -> dict[str, Any]:
    packet = native_working_set(measurement, arms)
    assert measurement.native_evidence is not None
    candidates, arm_facts = packet["pass_candidates"], packet["scientific_arms"]
    candidate_order = [r.candidate_id for r in opinion.candidate_rankings]
    if len(candidate_order) != len(set(candidate_order)) or set(candidate_order) != set(candidates):
        raise AgentBoundaryError("Candidate leaderboard must cover every native PASS exactly once")
    eligible = {a for a, fact in arm_facts.items() if fact["mode"] == "PROMOTION"}
    if eligible and opinion.recommended_action != "PROMOTE_TO_SCALE":
        raise AgentBoundaryError(
            "Complete native-PASS Arms require a ranked Scale proposal for Scientist review. "
            "Scientific weaknesses affect selection, allocation and risks; the Scientist "
            "can choose revision or STOP. Recovery is reserved for complete zero-pass Arms."
        )
    if len(opinion.ranked_arm_ids) != len(set(opinion.ranked_arm_ids)) or (
        set(opinion.ranked_arm_ids) != eligible
    ):
        raise AgentBoundaryError("Arm leaderboard must rank every complete native-PASS Arm")
    recovery = {r.arm_id: r for r in opinion.arm_recovery}
    expected_recovery = {a for a, fact in arm_facts.items() if fact["mode"] == "RECOVERY"}
    if len(recovery) != len(opinion.arm_recovery) or set(recovery) != expected_recovery:
        raise AgentBoundaryError("Recovery is allowed only for each complete zero-native-pass Arm")
    for r in recovery.values():
        if r.changes_approved_site and r.action != "REVISE_SITE":
            raise AgentBoundaryError("Material Site changes must return through Gate 2")
    selected_arms = {
        a.arm_id for a in arms if set(a.strategy_ids) & set(opinion.selected_strategy_ids)
    }
    if selected_arms - eligible:
        raise AgentBoundaryError(
            "Scale selection includes a zero-pass or incomplete scientific Arm"
        )
    for arm in arms:
        allocations = {
            opinion.scale_allocations[s] for s in arm.strategy_ids if s in opinion.scale_allocations
        }
        if len(allocations) > 1:
            raise AgentBoundaryError(
                "The current executor requires equal selected-scaffold allocations within an Arm"
            )
    if set(opinion.supporting_candidate_ids) - set(candidates):
        raise AgentBoundaryError(
            "Scientific promotion support must reference native PASS candidates"
        )
    if opinion.recommended_action == "PROMOTE_TO_SCALE" and any(
        not set(arm_facts[a]["pass_candidate_ids"]) & set(opinion.supporting_candidate_ids)
        for a in selected_arms
    ):
        raise AgentBoundaryError("Each selected scientific Arm needs native-PASS support")
    if (
        not eligible
        and not expected_recovery
        and opinion.recommended_action not in {"RUN_ANOTHER_PILOT", "STOP"}
    ):
        raise AgentBoundaryError(
            "Operationally incomplete evidence cannot diagnose a Site/Design failure"
        )
    findings = {f.arm_id: f for f in opinion.arm_findings}
    candidate_board = []
    for rank, entry in enumerate(opinion.candidate_rankings, 1):
        fact = candidates[entry.candidate_id]
        native = next(
            c
            for c in measurement.native_evidence.candidates
            if c.candidate_id == entry.candidate_id
        )
        known_metrics = set(fact["metrics"]) | set(native.metrics) | set(native.additional_metrics)
        if any(ref not in known_metrics for ref in entry.metric_refs):
            raise AgentBoundaryError("Ranking explanation cites an unknown metric")
        candidate_board.append({"rank": rank, **fact, **entry.model_dump(mode="json")})
    arm_board = []
    for arm_id in [*opinion.ranked_arm_ids, *sorted(set(arm_facts) - eligible)]:
        fact = arm_facts[arm_id]
        top = [r for r in candidate_board if r["arm_id"] == arm_id][:5]
        arm_board.append(
            {
                "arm_id": arm_id,
                "rank": opinion.ranked_arm_ids.index(arm_id) + 1 if arm_id in eligible else None,
                **fact,
                "finding": findings[arm_id].model_dump(mode="json"),
                "top_candidate_ids": [r["candidate_id"] for r in top],
                "top_k_distributions": {
                    k: _distribution([r["metrics"].get(k) for r in top]) for k in METRIC_DIRECTIONS
                },
                "recovery": recovery[arm_id].model_dump(mode="json")
                if arm_id in recovery
                else None,
            }
        )
    return {
        "version": "ranked-pilot-v1",
        "policy": NATIVE_RANKING_POLICY,
        "candidate_leaderboard": candidate_board,
        "arm_leaderboard": arm_board,
        "metric_directions": METRIC_DIRECTIONS,
        "filter_profiles": packet["filter_profiles"],
        "measurement_sha256": packet["measurement_sha256"],
    }


def compact_native_packet(
    measurement: PilotMeasurement, arms: tuple[PilotArmIntent, ...]
) -> dict[str, Any]:
    """Columnar vectors keep every native value without repeating column names per candidate."""
    from .session_store import identity

    packet = native_working_set(measurement, arms)
    assert measurement.native_evidence is not None
    native = {c.candidate_id: c for c in measurement.native_evidence.candidates}
    ids = sorted(packet["pass_candidates"])
    columns = sorted({k for i in ids for k in native[i].metrics})
    directions = list(METRIC_DIRECTIONS)
    facts: dict[str, Any] = {}
    contexts = {}
    for arm, fact in packet["scientific_arms"].items():
        intent = fact["design_intent"]
        context = intent["target_context"]
        context_id = identity(context)
        contexts[context_id] = context
        intent["target_context"] = {"shared_context_id": context_id}
        facts[arm] = {
            **fact,
            "all_candidate_distributions": [
                fact["all_candidate_distributions"][m] for m in directions
            ],
            "pass_candidate_distributions": [
                fact["pass_candidate_distributions"][m] for m in directions
            ],
        }
    for i, fact in packet["pass_candidates"].items():
        ranks = fact["within_pilot_pass_ranks"]
        facts[i] = {
            "arm_id": fact["arm_id"],
            "strategy_id": fact["strategy_id"],
            "native_pass": True,
            "profile_sha256": fact["profile_sha256"],
            "native_metric_values": [native[i].metrics.get(k) for k in columns],
            "runtime_metrics": native[i].additional_metrics,
            "within_pilot_pass_ranks": {
                k: [v["rank"], v["population"], v["fraction_strictly_worse"]]
                for k, v in ranks.items()
            },
            "missing_metrics": fact["missing_metrics"],
        }
    return {
        "version": packet["version"],
        "measurement_sha256": packet["measurement_sha256"],
        "execution": packet["execution"],
        "facts": facts,
        "scientific_arm_ids": list(packet["scientific_arms"]),
        "native_pass_candidate_ids": ids,
        "native_metric_columns": columns,
        "distribution_metric_columns": directions,
        "metric_directions": METRIC_DIRECTIONS,
        "shared_target_contexts": contexts,
        "vector_semantics": "Each native_metric_values position names the matching "
        "native_metric_columns entry. Distribution arrays use distribution_metric_columns. "
        "Each rank tuple is [rank, population, fraction_strictly_worse]. Null is missing.",
        "filter_profiles": packet["filter_profiles"],
        "interpretation_limits": packet["interpretation_limits"],
    }
