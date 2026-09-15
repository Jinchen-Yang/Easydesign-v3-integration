"""Read native BoltzGen measurements without running an independent predictor."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import ArtifactRef, TaskRecord, canonical_model_sha256, load_model
from easydesign.stages.s04_pilot_generation import CandidateRecord, TaskTable

from .contracts import AgentBoundaryError
from .phase3_native_contracts import (
    NativeCandidateEvidence,
    NativeFilterDecision,
    NativeFilterProfile,
    NativeFilterRule,
    NativePilotEvidence,
)
from .phase34_contracts import (
    ExecutionProjection,
    MetricObservation,
    PilotArmDenominator,
    PilotCandidateLineage,
    PilotCandidateObservation,
    PilotMeasurement,
)
from .session_store import confined


def native_profile(config: dict[str, Any], ref: ArtifactRef) -> NativeFilterProfile:
    """Version-specific translation of Filter.__init__, not an EasyDesign filter policy.

    Defaults and constants are those of the pinned source recorded in the returned profile.
    Actual enabled switches/overrides come from this task's saved filtering.yaml.
    A future backend version needs a separately verified adapter.
    """
    if config.get("_target_") != "boltzgen.task.filter.filter.Filter":
        raise AgentBoundaryError("Unrecognized native filter implementation")
    threshold = config.get("refolding_rmsd_threshold", 2.5)
    rules = [
        NativeFilterRule(feature="has_x", lower_is_better=True, threshold=0),
        NativeFilterRule(feature="filter_rmsd", lower_is_better=True, threshold=threshold),
        NativeFilterRule(feature="filter_rmsd_design", lower_is_better=True, threshold=threshold),
    ]
    if config.get("filter_designfolding", True):
        rules.append(
            NativeFilterRule(
                feature="designfolding-filter_rmsd", lower_is_better=True, threshold=threshold
            )
        )
    if config.get("filter_bindingsite", False):
        rules.append(
            NativeFilterRule(
                feature="bindsite_under_8rmsd", lower_is_better=False, threshold=0.0001
            )
        )
    if config.get("filter_target_aligned", False):
        # The pinned upstream implementation omits this rule's threshold; don't invent one.
        raise AgentBoundaryError("Pinned native target-aligned filter lacks a threshold")
    if config.get("filter_cysteine", True):
        rules.append(NativeFilterRule(feature="CYS_fraction", lower_is_better=True, threshold=0))
    if config.get("filter_biased", True):
        rules.extend(
            NativeFilterRule(feature=aa + "_fraction", lower_is_better=True, threshold=0.3)
            for aa in ("ALA", "GLY", "GLU", "LEU", "VAL")
        )
    rules.extend(NativeFilterRule.model_validate(r) for r in config.get("additional_filters", []))
    return NativeFilterProfile(configuration=config, configuration_ref=ref, rules=tuple(rules))


def native_candidate(
    candidate: CandidateRecord,
    profile: NativeFilterProfile,
    additional_metrics: dict[str, Any] | None = None,
) -> NativeCandidateEvidence:
    metrics = {
        k: (None if isinstance(v, float) and not math.isfinite(v) else v)
        for k, v in candidate.metrics.items()
    }
    flags = {k for k in metrics if k.startswith("pass_") and k.endswith("_filter")}
    expected = {f"pass_{r.feature}_filter" for r in profile.rules}
    if flags - expected:
        raise AgentBoundaryError("Native output contains filters absent from the saved profile")
    decisions = []
    for rule in profile.rules:
        value = metrics.get(rule.feature)
        flag = metrics.get(f"pass_{rule.feature}_filter")
        if not isinstance(value, (int, float, bool)) or not isinstance(flag, bool):
            decisions.append(
                NativeFilterDecision(
                    **rule.model_dump(),
                    value=None,
                    passed=None,
                    missing_reason="Native filter value or recorded decision unavailable",
                )
            )
            continue
        passed = value <= rule.threshold if rule.lower_is_better else value >= rule.threshold
        if passed != flag:
            raise AgentBoundaryError("Native filter decision contradicts its value/threshold")
        decisions.append(NativeFilterDecision(**rule.model_dump(), value=value, passed=passed))
    result = None if any(d.passed is None for d in decisions) else all(d.passed for d in decisions)
    if result is not None and (
        candidate.pass_filters is not result or metrics.get("pass_filters") is not result
    ):
        raise AgentBoundaryError("Native aggregate pass flag contradicts its active filters")
    return NativeCandidateEvidence(
        candidate_id=candidate.candidate_id,
        profile_sha256=canonical_model_sha256(profile),
        native_pass=result,
        decisions=tuple(decisions),
        metrics=metrics,
        additional_metrics=additional_metrics or {},
        metric_sources={key: "easydesign-refold-heavy-atom-v1" for key in additional_metrics or {}},
    )


def project_native_measurement(
    *,
    candidates: tuple[CandidateRecord, ...],
    profiles: dict[str, NativeFilterProfile],
    planned: dict[str, int],
    execution: ExecutionProjection,
    source_sha256: str,
    source_refs: tuple[ArtifactRef, ...] = (),
    additional_metrics: dict[str, dict[str, Any]] | None = None,
    failed_attempts: dict[str, int] | None = None,
) -> PilotMeasurement:
    """Project native PASS; optional metrics do not set eligibility."""
    if len({c.candidate_id for c in candidates}) != len(candidates):
        raise AgentBoundaryError("Duplicate native candidate identity")
    candidate_ids = {c.candidate_id for c in candidates}
    if set(profiles) - (set(planned) | candidate_ids) or any(
        c.candidate_id not in profiles and c.strategy_id not in profiles for c in candidates
    ):
        raise AgentBoundaryError("Native candidate/filter profile has a foreign strategy")
    ordered = sorted(candidates, key=lambda c: (c.strategy_id, c.ordinal_within_strategy))
    native = tuple(
        native_candidate(
            c,
            profiles.get(c.candidate_id) or profiles[c.strategy_id],
            (additional_metrics or {}).get(c.candidate_id),
        )
        for c in ordered
    )
    observations = []
    per_strategy: Counter[str] = Counter()
    for rank, (candidate, evidence) in enumerate(zip(ordered, native, strict=True), 1):
        sequence = candidate.metrics.get("designed_chain_sequence")
        if not isinstance(sequence, str) or not sequence:
            raise AgentBoundaryError("Native candidate lacks its full binder sequence")
        per_strategy[candidate.strategy_id] += 1
        metrics = tuple(
            MetricObservation(
                metric_id="boltzgen-" + name.lower(),
                value=value,
                available=value is not None,
                missing_reason=None if value is not None else "Native metric not reported",
                source="boltzgen-0.3.2",
                definition_version="native-boltz2-pilot-v1",
            )
            for name, value in evidence.metrics.items()
            if re.fullmatch(r"[\w.-]+", name)
        )
        observations.append(
            PilotCandidateObservation(
                lineage=PilotCandidateLineage(
                    **{
                        key: getattr(candidate, key)
                        for key in PilotCandidateLineage.model_fields
                        if key != "sequence_sha256"
                    },
                    sequence_sha256=hashlib.sha256(sequence.encode()).hexdigest(),
                ),
                metrics=metrics,
                legacy_policy_annotations=(),
                legacy_policy_pass=False,
                development_score=0,
                development_rank_global=rank,
                development_rank_within_strategy=per_strategy[candidate.strategy_id],
            )
        )
    arms = []
    by_id = {c.candidate_id: c for c in native}
    for strategy, count in sorted(planned.items()):
        group = [c for c in observations if c.lineage.strategy_id == strategy]
        valid = len(group)
        if valid > count:
            raise AgentBoundaryError("Native population exceeds approved allocation")
        evaluable = sum(by_id[c.lineage.candidate_id].native_pass is not None for c in group)
        arms.append(
            PilotArmDenominator(
                strategy_id=strategy,
                planned_candidates=count,
                generated_candidates=valid,
                valid_execution_products=valid,
                predicted_candidates=0,
                metric_evaluable_candidates=evaluable,
                unique_sequences=len({c.lineage.sequence_sha256 for c in group}),
                legacy_policy_pass_count=0,
                operational_failure_count=count - evaluable,
                failed_generation_attempts=(failed_attempts or {}).get(strategy, 0),
                missing_by_metric={"native-filter-decision": valid - evaluable},
            )
        )
    native_evidence = NativePilotEvidence(
        profiles={canonical_model_sha256(p): p for p in profiles.values()},
        candidates=native,
        source_refs=source_refs,
    )
    return PilotMeasurement(
        execution=execution,
        source_candidate_index_sha256=source_sha256,
        source_filter_report_sha256=canonical_model_sha256(native_evidence),
        candidates=tuple(observations),
        arms=tuple(arms),
        native_evidence=native_evidence,
    )


def task_filter_profiles(
    root: Path, upstream: Any
) -> tuple[dict[str, NativeFilterProfile], tuple[ArtifactRef, ...]]:
    tasks = load_model(upstream.pilot_bundle.task_table.verify(root), TaskTable)
    return profiles_from_tasks(root, upstream.candidate_index.candidates, tasks.tasks)


def profiles_from_tasks(
    root: Path, candidates: tuple[CandidateRecord, ...], tasks: tuple[TaskRecord, ...]
) -> tuple[dict[str, NativeFilterProfile], tuple[ArtifactRef, ...]]:
    by_id = {t.task_id: t for t in tasks}
    profiles: dict[str, NativeFilterProfile] = {}
    refs: dict[str, ArtifactRef] = {}
    for candidate in candidates:
        task = by_id.get(candidate.task_id)
        if task is None or task.strategy_id != candidate.strategy_id:
            raise AgentBoundaryError("Native candidate is outside its execution task")
        attempt = next(
            (a for a in task.attempts if a.attempt_number == candidate.task_attempt_number), None
        )
        if attempt is None or not attempt.output_relative_path:
            raise AgentBoundaryError("Native candidate has no declared execution attempt")
        output = confined(root, root / attempt.output_relative_path)
        if not candidate.original_structure.verify(root).is_relative_to(output):
            raise AgentBoundaryError("Native candidate structure is outside its declared task")
        for ref in (candidate.refolded_structure, candidate.design_mask_source):
            if ref:
                ref.verify(root)
        path = confined(root, output / "config/filtering.yaml")
        ref = ArtifactRef.from_file(
            run_root=root,
            relative_path=path.relative_to(root).as_posix(),
            artifact_id="native-filter-config-" + task.task_id,
            role="native-filter-configuration",
            file_format="yaml",
        )
        profile = native_profile(yaml.safe_load(path.read_text()), ref)
        # Each candidate keeps the exact attempt profile, including legitimate retries.
        profiles[candidate.candidate_id] = profile
        refs[ref.relative_path] = ref
    return profiles, tuple(refs.values())


def refold_contact_metrics(root: Path, candidate: CandidateRecord, strategy: Any) -> dict[str, Any]:
    """Reuse existing atom parsing/distance kernels; distinguish whole-VHH and design masks."""
    import numpy as np

    from easydesign.filtering.structure_metrics import (
        CONTACT_ANGSTROM,
        SEVERE_CLASH_ANGSTROM,
        _pairwise_distances,
        parse_protein_chain,
    )

    path = candidate.refolded_structure.verify(root)
    target, binder = parse_protein_chain(path, "A"), parse_protein_chain(path, "B")
    original = candidate.original_structure.verify(root)
    for chain, parsed in (("A", target), ("B", binder)):
        before = parse_protein_chain(original, chain)
        if [(r.residue_id, r.one_letter) for r in before.residues] != [
            (r.residue_id, r.one_letter) for r in parsed.residues
        ]:
            raise AgentBoundaryError("Refold changed target/binder residue identity")
    target_ids = {r.residue_id for r in target.residues}
    binding = set(strategy.binding_label_seq_ids)
    if not binding or not binding <= target_ids:
        raise AgentBoundaryError("Approved binding residues missing from native refold")
    designed = set(candidate.designed_binder_residue_ids)
    if not designed or not designed <= {r.residue_id for r in binder.residues}:
        raise AgentBoundaryError("Native design mask does not identify binder residues")
    if candidate.design_mask_source is None:
        raise AgentBoundaryError("Native candidate lacks its design mask source")
    candidate.design_mask_source.verify(root)
    distances = _pairwise_distances(target.atoms, binder.atoms)
    contact = distances <= CONTACT_ANGSTROM
    design_atoms = np.array([a.residue_id in designed for a in binder.atoms])
    target_all = {target.atoms[i].residue_id for i in np.flatnonzero(contact.any(axis=1))}
    target_design = {
        target.atoms[i].residue_id for i in np.flatnonzero(contact[:, design_atoms].any(axis=1))
    }
    binder_all = {binder.atoms[i].residue_id for i in np.flatnonzero(contact.any(axis=0))}
    pairs = {
        (target.atoms[i].residue_id, binder.atoms[j].residue_id) for i, j in np.argwhere(contact)
    }
    result: dict[str, Any] = {
        "refold_interface_atom_contacts": int(contact.sum()),
        "refold_interface_residue_pairs": len(pairs),
        "refold_severe_clash_count": int((distances < SEVERE_CLASH_ANGSTROM).sum()),
        "refold_minimum_heavy_atom_distance": float(distances.min()),
        "refold_design_contact_fraction": len(binder_all & designed) / len(designed),
        "refold_design_interface_fraction": len(binder_all & designed) / len(binder_all)
        if binder_all
        else 0.0,
    }
    avoid = set(strategy.avoid_label_seq_ids)
    for name, touched in (("binder", target_all), ("design", target_design)):
        hotspots = sorted(binding & touched)
        avoided = sorted(avoid & touched)
        result.update(
            {
                f"refold_hotspot_to_{name}_contact_count": len(hotspots),
                f"refold_hotspot_to_{name}_contact_fraction": len(hotspots) / len(binding),
                f"refold_hotspot_to_{name}_contact_residues": ",".join(map(str, hotspots)),
                f"refold_avoid_to_{name}_contact_count": len(avoided),
                f"refold_avoid_to_{name}_contact_residues": ",".join(map(str, avoided)),
            }
        )
    return result


def verify_native_measurement(root: Path, measurement: PilotMeasurement) -> None:
    """Recheck source bytes on interpretation/approval reads, including direct API calls."""
    native = measurement.native_evidence
    if native is None:
        return
    refs = [*native.source_refs, *(p.configuration_ref for p in native.profiles.values())]
    for candidate in measurement.candidates:
        lineage = candidate.lineage
        refs.extend((lineage.original_structure, lineage.refolded_structure))
        if lineage.design_mask_source is not None:
            refs.append(lineage.design_mask_source)
    seen = set()
    for ref in refs:
        key = (ref.relative_path, ref.sha256)
        if key not in seen:
            ref.verify(root)
            seen.add(key)


def measure_native_execution(
    bridge: Any, *, authority_id: str, plan: Any, execution: dict[str, Any]
) -> dict[str, Any]:
    from easydesign.orchestration.stage05 import _load_upstream
    from easydesign.orchestration.workspace import load_resolved_run_config

    from .phase34_measurement import _save_exact

    root, _ = bridge.run(execution["run_id"])
    upstream = _load_upstream(root)
    resolved, _ = load_resolved_run_config(root)
    if canonical_model_sha256(resolved.user_config) != execution["config_sha256"]:
        raise AgentBoundaryError("Native Pilot run configuration changed")
    index = upstream.candidate_index
    if dict(Counter(c.strategy_id for c in index.candidates)) != plan.execution_allocations:
        raise AgentBoundaryError(
            "Native Pilot population differs from its exact approved allocation"
        )
    profiles, refs = task_filter_profiles(root, upstream)
    strategies = {s.strategy_id: s for s in upstream.strategy_bundle.strategies}
    tasks = load_model(upstream.pilot_bundle.task_table.verify(root), TaskTable)
    failed = {t.strategy_id: sum(a.status == "failed" for a in t.attempts) for t in tasks.tasks}
    additions = {
        c.candidate_id: refold_contact_metrics(root, c, strategies[c.strategy_id])
        for c in index.candidates
    }
    measurement = project_native_measurement(
        candidates=index.candidates,
        profiles=profiles,
        planned=plan.execution_allocations,
        source_sha256=upstream.candidate_index_ref.sha256,
        source_refs=refs,
        additional_metrics=additions,
        failed_attempts=failed,
        execution=ExecutionProjection(
            mode=plan.mode,
            requested_production_candidates=sum(plan.production_allocations.values()),
            execution_candidates=sum(plan.execution_allocations.values()),
            uses_real_generation_backend=True,
            uses_real_prediction_backend=False,
            purpose="Exact approved native BoltzGen/Boltz2 Pilot; independent prediction optional.",
        ),
    )
    artifacts = confined(root, root / "phase34" / authority_id / "native-measurement")
    artifacts.mkdir(parents=True, exist_ok=True)
    assert measurement.native_evidence is not None
    ref = _save_exact(
        root,
        artifacts / "native-evidence-v1.json",
        measurement.native_evidence,
        "native-pilot-evidence",
    )
    return {
        "status": "measured",
        "measurement": measurement,
        "sources": {
            "authority": authority_id,
            "run_id": execution["run_id"],
            "candidate_index": upstream.candidate_index_ref.model_dump(mode="json"),
            "native_evidence": ref.model_dump(mode="json"),
        },
    }
