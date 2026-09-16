"""Bounded Pilot decision views; full measurements and provenance stay in Runtime."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import AgentBoundaryError
from .phase3_ranking import METRIC_DIRECTIONS
from .session_store import compact, identity

VIEW_VERSION = "pilot-ranking-decision-view-v1"
SUBMISSION_PROTOCOL = "native-ranking-tool-first-v4"


def ranking_submission_model(model: Any, config: Any) -> Any:
    """Reserve the fixed output allowance for the actual ranked proposal, on the same model."""
    selected = config.for_role("pilot-diagnosis")
    credential = getattr(model, "anthropic_api_key", None)
    if selected.provider == "deepseek" and credential is not None:
        # The compatibility endpoint returned empty tool input despite billed output.
        # Use the provider's native tools transport for this bounded submission only.
        # Reuse the SDK-held credential; never restore it into environment or evidence.
        from langchain.chat_models import init_chat_model

        return init_chat_model(
            selected.model,
            model_provider="openai",
            api_key=credential,
            base_url="https://api.deepseek.com",
            use_responses_api=False,
            timeout=selected.timeout_seconds,
            max_retries=0,
            extra_body={"thinking": {"type": "disabled"}, "max_tokens": selected.max_output_tokens},
        )
    return model


# Keep the existing ranking dimensions, plus sequence/chemistry/contact context.
# This is a projection, not a new filter, score, or candidate selection policy.
CONTEXT_METRICS = (
    "design_chain_hydrophobicity",
    "design_hydrophobicity",
    "liability_score",
    "liability_num_violations",
    "liability_high_severity_violations",
    "liability_medium_severity_violations",
    "liability_low_severity_violations",
    "liability_violations_summary",
    "refold_hotspot_to_binder_contact_residues",
    "refold_hotspot_to_design_contact_residues",
    "refold_avoid_to_binder_contact_residues",
    "refold_avoid_to_design_contact_residues",
)
PROVENANCE_FIELDS = {
    "evidence_refs",
    "design_specification_path",
    "design_specification_sha256",
    "variant_scaffold_path",
    "variant_scaffold_sha256",
    "native_source_sha256",
}


def common_fields(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Exact recursive common values; lists are atomic, null is never absence."""
    if not records:
        return {}
    common = {}
    for key, value in records[0].items():
        if not all(key in record for record in records):
            continue
        values = [record[key] for record in records]
        if all(compact(v) == compact(value) for v in values):
            common[key] = deepcopy(value)
        elif all(isinstance(v, dict) for v in values):
            nested = common_fields(values)
            if nested:
                common[key] = nested
    return common


def delta_fields(record: dict[str, Any], common: dict[str, Any]) -> dict[str, Any]:
    delta = {}
    for key, value in record.items():
        if key not in common:
            delta[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(common[key], dict):
            nested = delta_fields(value, common[key])
            if nested:
                delta[key] = nested
        elif compact(value) != compact(common[key]):
            delta[key] = deepcopy(value)
    return delta


def _scientific_settings(value: dict[str, Any]) -> dict[str, Any]:
    return {k: deepcopy(v) for k, v in value.items() if k not in PROVENANCE_FIELDS}


def candidate_reference_map(ids: list[str]) -> dict[str, str]:
    """Packet-local references; canonical IDs and the population binding remain authoritative."""
    ordered = sorted(ids)
    prefix = "c"
    while set(f"{prefix}{i:04}" for i in range(1, len(ids) + 1)) & set(ids):
        prefix = "view-" + prefix
    return {f"{prefix}{i:04}": value for i, value in enumerate(ordered, 1)}


def expand_candidate_references(measurement: Any, opinion: Any) -> Any:
    """Expand only addressed IDs, before every existing scientific/authority validator."""
    if measurement.native_evidence is None:
        return opinion
    refs = candidate_reference_map(
        [c.candidate_id for c in measurement.native_evidence.candidates if c.native_pass is True]
    )
    return opinion.model_copy(
        update={
            "candidate_order": [refs.get(i, i) for i in opinion.candidate_order],
            "supporting_candidate_ids": [refs.get(i, i) for i in opinion.supporting_candidate_ids],
            "candidate_rankings": [
                r.model_copy(update={"candidate_id": refs.get(r.candidate_id, r.candidate_id)})
                for r in opinion.candidate_rankings
            ],
        }
    )


def _target_context_view(context_id: str, context: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(context)
    exclusions = projected.get("gpcr_exclusions")
    if isinstance(exclusions, dict) and ("sources" in exclusions or "source_refs" in exclusions):
        # Preserve constraints, missing residues, status and limitations. Per-source
        # annotation/provenance expansions stay addressable in the original context.
        exclusions.pop("sources", None)
        exclusions.pop("source_refs", None)
        exclusions["source_details_ref"] = context_id + ":gpcr_exclusions"
    return projected


def ranking_decision_view(packet: dict[str, Any]) -> dict[str, Any]:
    """Project all PASS rows; never alter or truncate the authoritative source packet."""
    arm_ids = packet["scientific_arm_ids"]
    ids = packet["native_pass_candidate_ids"]
    candidate_refs = {value: key for key, value in candidate_reference_map(ids).items()}
    originals = {a: packet["facts"][a]["design_intent"] for a in arm_ids}
    settings = {}
    for a, intent in originals.items():
        compiled = intent["compiled_settings"]
        settings[a] = [
            _scientific_settings({**compiled["common"], **s}) for s in compiled["strategies"]
        ]
    shared_settings = common_fields([s for records in settings.values() for s in records])
    intents = {}
    for a, intent in originals.items():
        records = [delta_fields(s, shared_settings) for s in settings[a]]
        arm_common = common_fields(records)
        intents[a] = {
            **_scientific_settings(intent),
            "compiled_settings": {
                "arm_common": arm_common,
                "strategies": [delta_fields(s, arm_common) for s in records],
            },
        }
    shared_intent = common_fields(list(intents.values()))
    arms = {}
    denominator_rows: list[list[Any]] = []
    denominator_columns = sorted(
        {k for a in arm_ids for d in packet["facts"][a]["strategy_denominators"] for k in d}
    )
    for a in arm_ids:
        fact = packet["facts"][a]
        arms[a] = {
            k: deepcopy(v)
            for k, v in fact.items()
            if k not in {"design_intent", "strategy_denominators", "pass_candidate_ids"}
        }
        arms[a]["design_delta"] = delta_fields(intents[a], shared_intent)
        arms[a]["design_intent_ref"] = identity(originals[a])
        if arms[a]["all_candidate_distributions"] == arms[a]["pass_candidate_distributions"]:
            arms[a]["pass_candidate_distributions"] = {"same_as": "all_candidate_distributions"}
        denominator_rows.extend(
            [d.get(k) for k in denominator_columns] for d in fact["strategy_denominators"]
        )
    strategy_rows = [
        [s["strategy_id"], a, s.get("scaffold_id")] for a in arm_ids for s in settings[a]
    ]
    strategies = {row[0]: i for i, row in enumerate(strategy_rows)}
    profile_ids = sorted(packet["filter_profiles"])
    profiles = {p: i for i, p in enumerate(profile_ids)}
    # Missing projected values stay null. All remaining raw columns are durable in
    # native_evidence, addressed by measurement hash + candidate ID, not discarded.
    metric_columns = list(METRIC_DIRECTIONS) + list(CONTEXT_METRICS)
    values = {}
    sequence_groups: dict[str, int] = {}
    sequence_ids: dict[str, int | None] = {}
    for candidate_id in ids:
        fact = packet["facts"][candidate_id]
        vector = dict(
            zip(
                packet["native_metric_columns"],
                fact["native_metric_values"],
                strict=True,
            )
        )
        vector.update(fact["runtime_metrics"])
        values[candidate_id] = {k: vector.get(k) for k in metric_columns}
        sequence = vector.get("designed_chain_sequence")
        if sequence:
            sequence_groups.setdefault(sequence, len(sequence_groups))
            sequence_ids[candidate_id] = sequence_groups[sequence]
        else:
            sequence_ids[candidate_id] = None
    shared_values = common_fields(list(values.values()))
    variable_columns = [k for k in metric_columns if k not in shared_values]
    # Exact categorical values (e.g. liability descriptions/contact residue sets)
    # are shared once. Numeric observations are never rounded or rescaled.
    value_tables = {
        k: list(dict.fromkeys(values[i][k] for i in ids if values[i][k] is not None))
        for k in variable_columns
        if all(values[i][k] is None or isinstance(values[i][k], str) for i in ids)
    }
    rows: list[list[Any]] = [
        [
            candidate_refs[i],
            strategies[packet["facts"][i]["strategy_id"]],
            profiles[packet["facts"][i]["profile_sha256"]],
            sequence_ids[i],
            *[
                value_tables[k].index(values[i][k])
                if k in value_tables and values[i][k] is not None
                else values[i][k]
                for k in variable_columns
            ],
        ]
        for i in ids
    ]
    metric_groups = [
        {
            "column": f"metrics_{start // 6 + 1}",
            "metrics": variable_columns[start : start + 6],
            "directions": [METRIC_DIRECTIONS.get(k) for k in variable_columns[start : start + 6]],
        }
        for start in range(0, len(variable_columns), 6)
    ]
    identities = [
        [
            row[0],
            strategy_rows[row[1]][1],
            *row[1:4],
            *[row[4 + start : 4 + start + 6] for start in range(0, len(variable_columns), 6)],
        ]
        for row in rows
    ]
    return {
        "version": VIEW_VERSION,
        "source_packet_sha256": identity(packet),
        "measurement_sha256": packet["measurement_sha256"],
        **{
            k: packet[k]
            for k in (
                "run_id",
                "gate_type",
                "evidence_id",
                "request_identity",
                "user_goal",
            )
            if k in packet
        },
        "execution": packet["execution"],
        "shared_target_contexts": {
            k: _target_context_view(k, v) for k, v in packet["shared_target_contexts"].items()
        },
        "shared_design_intent": shared_intent,
        "shared_compiled_settings": shared_settings,
        "arms": arms,
        "strategy_columns": ["strategy_id", "arm_id", "scaffold_id"],
        "strategies": strategy_rows,
        "denominator_columns": denominator_columns,
        "strategy_denominators": denominator_rows,
        "candidate_columns": [
            "candidate_id",
            "arm_id",
            "strategy_index",
            "profile_index",
            "sequence_group",
            *[g["column"] for g in metric_groups],
        ],
        "metric_groups": metric_groups,
        "candidate_common_metrics": shared_values,
        "metric_value_tables": value_tables,
        "candidates": identities,
        "candidate_count": len(rows),
        "filter_profile_count": len(profile_ids),
        "filter_profile_binding": identity(profile_ids),
        "filter_definition_by_profile": [
            list(packet["shared_filter_definitions"]).index(
                packet["filter_profiles"][p]["shared_filter_definition_id"]
            )
            for p in profile_ids
        ],
        "filter_definition_ids": list(packet["shared_filter_definitions"]),
        "shared_filter_definitions": packet["shared_filter_definitions"],
        "distribution_metric_columns": packet["distribution_metric_columns"],
        "distribution_statistic_columns": packet["distribution_statistic_columns"],
        "metric_directions": [
            packet["metric_directions"][m] for m in packet["distribution_metric_columns"]
        ],
        "view_semantics": (
            "All PASS rows retained. Short candidate IDs resolve in sorted canonical PASS order "
            "under measurement_sha256; Runtime expands before validation/publishing. "
            "Indices are zero-based. metrics_N values/directions follow metric_groups names. "
            "Inherit candidate_common_metrics; null means unavailable. metric_value_tables "
            "indices resolve exact strings. sequence_group = exact full-binder equality. "
            "Profiles follow sorted source IDs bound by filter_profile_binding; "
            "filter_definition_by_profile indexes filter_definition_ids. "
            "metric_directions follows distribution_metric_columns. Merge shared_design_intent "
            "with design_delta, and shared_compiled_settings with arm_common then strategy deltas. "
            "Context refs resolve in shared_target_contexts. Full raw metrics, sequences, masks, "
            "structures/provenance remain at measurement_sha256/native_evidence.candidates:<ID>; "
            "design_intent_ref resolves the source intent. Values/scopes are unchanged."
        ),
    }


def validate_compact_ranking_output(raw: dict[str, Any]) -> None:
    """Bound prose, not the ranked population; the legacy opinion path is unchanged."""
    if raw.get("candidate_order"):
        if len(raw.get("candidate_rankings", [])) > 12:
            raise AgentBoundaryError("Compact ranking allows at most 12 detailed candidate notes")
        # Exclude the complete ID order: its size grows with the population, not prose.
        prose = {k: v for k, v in raw.items() if k != "candidate_order"}
        if len(compact(prose)) > 14000:
            raise AgentBoundaryError(
                "Compact ranking prose exceeds 14000 characters; retain IDs and shorten notes"
            )


def ranking_repair_context(
    submission: dict[str, Any], diagnostic: Any, packet: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Bound only the model view of a failed proposal; the ledger retains it verbatim."""
    preview: dict[str, Any] = {}
    retained = []
    # Keep ranking/allocation identity first. Oversized malformed fields remain in
    # the ledger, never echoed unboundedly into a repair prompt.
    priority = [
        "candidate_order",
        "selected_strategy_ids",
        "scale_allocations",
        "supporting_candidate_ids",
    ]
    for key in [*priority, *sorted(set(submission) - set(priority))]:
        if key not in submission:
            continue
        value = submission[key]
        if len(compact(value)) <= 6000 and len(compact({**preview, key: value})) <= 12000:
            preview[key] = value
        else:
            retained.append(key)
    errors = diagnostic
    if isinstance(diagnostic, list) and all(isinstance(e, dict) for e in diagnostic):
        grouped: dict[str, list[str]] = {}
        for error in diagnostic:
            message = str(error.get("msg", error.get("type", "invalid")))
            grouped.setdefault(message, []).append(".".join(map(str, error.get("loc", []))))
        errors = [{"message": message, "fields": fields} for message, fields in grouped.items()]
    # Show correlated note coverage even when a schema error prevents the scientific
    # binder from running. This is advice only; the complete binder still decides.
    order, support = submission.get("candidate_order"), submission.get("supporting_candidate_ids")
    required_notes = []
    if isinstance(order, list) and isinstance(support, list):
        required_notes = list(
            dict.fromkeys(i for i in [*order[:3], *support] if isinstance(i, str))
        )
    context: dict[str, Any] = {}
    if packet is not None:
        by_arm: dict[str, list[str]] = {}
        for row in packet.get("candidates", []):
            by_arm.setdefault(row[1], []).append(row[0])
        strategy_arms = {row[0]: row[1] for row in packet.get("strategies", [])}
        selected = submission.get("selected_strategy_ids", [])
        allowed = {i for ids in by_arm.values() for i in ids}
        if (
            isinstance(selected, list)
            and isinstance(support, list)
            and all(isinstance(i, str) and i in allowed for i in support)
        ):
            missing_arms = sorted(
                {strategy_arms[s] for s in selected if isinstance(s, str) and s in strategy_arms}
                - {
                    a
                    for a, ids in by_arm.items()
                    if set(ids) & {s for s in support if isinstance(s, str)}
                }
            )
            context["selected_arms_missing_support"] = {
                a: {"allowed_candidate_refs": by_arm.get(a, [])} for a in missing_arms
            }
        if isinstance(order, list) and any(isinstance(i, str) and i in allowed for i in order):
            supplied = {i for i in order if isinstance(i, str)}
            context["candidate_order_set_errors"] = {
                "missing_refs": sorted(allowed - supplied),
                "unknown_refs": sorted(supplied - allowed),
            }
    text = compact(errors)
    return {
        **context,
        "errors": errors if len(text) <= 2500 else text[:2500],
        "required_detailed_candidate_ids": required_notes[:33],
        "previous_unvalidated_fields": preview,
        "fields_retained_only_in_runtime": retained,
        "instruction": (
            "Submit ONLY changed top-level fields through PilotDiagnosisOpinion. "
            "Replace any corrected array in full; omitted fields remain exactly as previously "
            "submitted in Runtime. Correct every reported error. All merged fields are "
            "revalidated against current evidence. Do not repeat unchanged facts or prose."
        ),
    }
