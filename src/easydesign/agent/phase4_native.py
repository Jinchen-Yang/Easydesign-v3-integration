"""Scale lineage projection of the shared native evidence; no second filter policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from easydesign.core import ArtifactRef, canonical_model_sha256, load_model
from easydesign.stages.s04_pilot_generation import CandidateIndex

from .contracts import AgentBoundaryError
from .phase3_native import measure_native_execution, verify_native_measurement
from .phase34_batches import ScaleBatchPlan, ScaleBatchReceipt, ScaleBatchStore
from .phase34_contracts import (
    DiversityContext,
    ExecutionProjection,
    FinalCandidateDossier,
    MetricObservation,
    PilotMeasurement,
    ScaleCandidateLineageV3,
    ScaleCandidateObservation,
    ScaleCandidateValidity,
)
from .phase34_measurement import PilotPredictionEvidence, attach_prediction_metrics
from .session_store import identity


def selection_decision_view(
    dossiers: tuple[FinalCandidateDossier, ...], primary_count: int, backup_count: int
) -> dict[str, Any]:
    """Reuse Pilot's decision dimensions; complete raw dossiers remain in Runtime."""
    from .phase3_capacity import CONTEXT_METRICS
    from .phase3_ranking import METRIC_DIRECTIONS

    columns = [*METRIC_DIRECTIONS, *CONTEXT_METRICS]
    profiles, facts, independent_columns = {}, {}, {}
    for dossier in dossiers:
        c = dossier.candidate
        native, profile = c.native_evidence, c.native_profile
        assert native is not None and profile is not None
        profiles[native.profile_sha256] = {
            "backend": profile.backend,
            "source_commit": profile.source_commit,
            "filter_source_sha256": profile.filter_source_sha256,
            "configuration_sha256": profile.configuration_ref.sha256,
            "rules": [r.model_dump(mode="json") for r in profile.rules],
        }
        values = {**native.metrics, **native.additional_metrics}
        independent = {}
        for m in c.metrics:
            if m.metric_id.startswith("independent-prediction-"):
                independent_columns[m.metric_id] = {
                    "unit": m.unit,
                    "definition_version": m.definition_version,
                }
                independent[m.metric_id] = {
                    "value": m.value,
                    "available": m.available,
                    "missing_reason": m.missing_reason,
                    "source": m.source,
                }
        facts[c.lineage.candidate_id] = {
            "strategy_id": c.lineage.strategy_id,
            "sequence": dossier.sequence,
            "native_pass": native.native_pass,
            "native_profile_ref": native.profile_sha256,
            "metrics": {
                f"group_{i // 6}": [values.get(k) for k in columns[i : i + 6]]
                for i in range(0, len(columns), 6)
            },
            "independent_prediction_status": c.independent_prediction_status,
            "independent_metrics": independent,
            "diversity": c.diversity.model_dump(mode="json"),
            "development_rank": c.global_development_rank,
            "risks": dossier.known_concerns,
            "uncertainties": dossier.uncertainties,
            "scientific_claim_scope": dossier.scientific_claim_scope,
            "full_dossier_ref": canonical_model_sha256(dossier),
        }
    return {
        "version": "native-final-selection-view-v1",
        "requested_primary_count": primary_count,
        "requested_backup_count": backup_count,
        "global_pool_sha256": dossiers[0].global_pool_sha256,
        "context": dossiers[0].context.model_dump(mode="json"),
        "metric_columns": {
            f"group_{i // 6}": columns[i : i + 6] for i in range(0, len(columns), 6)
        },
        "metric_directions": METRIC_DIRECTIONS,
        "independent_metric_definitions": independent_columns,
        "native_profiles": profiles,
        "facts": facts,
        "interpretation_limits": "All shortlisted candidates are native PASS under their own "
        "recorded profiles. Native engineering order uses bb_rmsd_design, then bb_rmsd, then "
        "candidate ID; it is not biological fitness. AFO is optional. Null means unavailable, "
        "never zero. Exact sequence identity is not pose diversity. Shared Pilot metric "
        "dimensions are projected without rounding; all other raw fields and provenance "
        "remain in the referenced full dossiers. Scientist alone approves the exact panel.",
    }


def native_scale_observations(
    *,
    root: Path,
    campaign_id: str,
    batch_id: str,
    run_id: str,
    measurement: PilotMeasurement,
    predictions: PilotPredictionEvidence | None = None,
    prediction_requested: bool = False,
    source_refs: tuple[ArtifactRef, ...] = (),
) -> tuple[ScaleCandidateObservation, ...]:
    """Preserve the original candidate ID inside native evidence and all source refs."""
    native = measurement.native_evidence
    if native is None:
        raise AgentBoundaryError("Scale requires native evidence, not legacy filter decisions")
    verify_native_measurement(root, measurement)
    if predictions is not None:
        if predictions.candidate_index_sha256 != measurement.source_candidate_index_sha256:
            raise AgentBoundaryError("Independent enrichment belongs to a different population")
        if set(p.candidate_id for p in predictions.predictions) - {
            c.lineage.candidate_id for c in measurement.candidates
        }:
            raise AgentBoundaryError("Independent enrichment contains foreign candidates")
        for ref in predictions.evidence_refs:
            ref.verify(root)
        measurement = attach_prediction_metrics(measurement, predictions.predictions)
    by_id = {c.candidate_id: c for c in native.candidates}
    independent = {p.candidate_id: p for p in predictions.predictions} if predictions else {}
    observations = []
    for c in measurement.candidates:
        line = c.lineage
        evidence = by_id[line.candidate_id]
        profile = native.profiles[evidence.profile_sha256]
        prediction = independent.get(line.candidate_id)
        if prediction is not None and prediction.strategy_id != line.strategy_id:
            raise AgentBoundaryError("Independent enrichment changed the candidate strategy")
        pid = (
            "prediction-"
            + identity({"run": run_id, "candidate": line.candidate_id, "seed": prediction.seed})[
                :24
            ]
            if prediction
            else None
        )
        refs = [
            line.original_structure,
            line.refolded_structure,
            profile.configuration_ref,
            *native.source_refs,
            *source_refs,
        ]
        if line.design_mask_source is not None:
            refs.append(line.design_mask_source)
        if prediction is not None:
            refs.extend(
                (
                    prediction.predicted_structure,
                    prediction.summary_confidence,
                    prediction.full_confidence,
                )
            )
        for ref in refs:
            ref.verify(root)
        extras = tuple(
            MetricObservation(
                metric_id="runtime-" + name.replace("_", "-"),
                value=value,
                available=value is not None,
                missing_reason="Native runtime measurement unavailable" if value is None else None,
                source=evidence.metric_sources.get(name, "native-refold-runtime"),
                definition_version="boltzgen-pilot-metrics-v1",
            )
            for name, value in evidence.additional_metrics.items()
        )
        observations.append(
            ScaleCandidateObservation(
                lineage=ScaleCandidateLineageV3(
                    campaign_id=campaign_id,
                    source_run_id=run_id,
                    batch_id=batch_id,
                    shard_id=batch_id,
                    candidate_id="candidate-"
                    + identity({"run": run_id, "candidate": line.candidate_id})[:32],
                    strategy_id=line.strategy_id,
                    strategy_ordinal=line.ordinal_within_strategy,
                    generation_task_id=line.task_id,
                    generation_attempt=line.task_attempt_number,
                    backend_candidate_id=line.backend_candidate_id,
                    sequence_sha256=line.sequence_sha256,
                    artifact_refs=tuple(refs),
                    prediction_id=pid,
                    prediction_seed=prediction.seed if prediction else None,
                    prediction_ids=(pid,) if pid else (),
                    prediction_seeds=(prediction.seed,) if prediction else (),
                ),
                validity=ScaleCandidateValidity.VALID_EVALUATED
                if evidence.native_pass is not None
                else ScaleCandidateValidity.UNEVALUABLE,
                metrics=(*c.metrics, *extras),
                native_evidence=evidence,
                native_profile=profile,
                # Phase 3's native adapter does not invent a biological scalar. Native
                # Scale uses an explicit refold lexicographic ordering in the global pool.
                development_score=c.development_score if evidence.native_pass is not None else None,
                failure_reason="Incomplete native filter evidence"
                if evidence.native_pass is None
                else None,
                evaluation_level="deep" if prediction else "refold",
                independent_prediction_status="available"
                if prediction
                else (
                    "unavailable"
                    if prediction_requested or predictions is not None
                    else "not-requested"
                ),
                diversity=DiversityContext(
                    sequence_cluster_id="seq-" + line.sequence_sha256[:32],
                    method="exact-sequence-sha256; advisory identity clusters; pose unverified",
                ),
            )
        )
    return tuple(observations)


def verify_native_dossiers(bridge: Any, dossiers: tuple[FinalCandidateDossier, ...]) -> None:
    """Recheck selected native source bytes on model and Gate approval reads."""
    roots, seen = {}, set()
    for dossier in dossiers:
        candidate = dossier.candidate
        if candidate.native_evidence is None:
            continue
        run_id = candidate.lineage.source_run_id
        if run_id is None:
            raise AgentBoundaryError("Native review candidate lacks its source run")
        if run_id not in roots:
            roots[run_id], _ = bridge.run(run_id)
        for ref in candidate.lineage.artifact_refs:
            key = (run_id, ref.relative_path, ref.sha256)
            if key not in seen:
                ref.verify(roots[run_id])
                seen.add(key)


def measure_native_batch(
    bridge: Any, journal: ScaleBatchStore, batch: ScaleBatchPlan, execution: dict[str, Any]
) -> dict[str, Any]:
    campaign = journal.manifest.campaign
    authority = bridge.pilot_authority()
    assert authority is not None and authority.pilot_plan is not None
    count = sum(batch.strategy_allocations.values())
    result = measure_native_execution(
        bridge,
        authority_id="scale-" + identity({"manifest": journal.digest, "batch": batch.batch_id}),
        plan=authority.pilot_plan,
        execution=execution,
        allocations=batch.strategy_allocations,
        projection=ExecutionProjection(
            mode=campaign.execution.mode,
            requested_production_candidates=count,
            execution_candidates=count,
            uses_real_generation_backend=True,
            uses_real_prediction_backend=False,
            purpose="Exact approved Scale batch; shared BoltzGen/Boltz2 native evidence.",
        ),
    )
    root, _ = bridge.run(execution["run_id"])
    index = load_model(
        ArtifactRef.model_validate(result["sources"]["candidate_index"]).verify(root),
        CandidateIndex,
    )
    source_refs = tuple(
        f"{execution['run_id']}:{ref['relative_path']}#{ref['sha256']}"
        for name, ref in result["sources"].items()
        if name in {"candidate_index", "native_evidence"}
    )
    if any(c.native_pass is None for c in result["measurement"].native_evidence.candidates):
        # Full incomplete rows remain in the immutable native-evidence artifact.
        # Do not freeze an incomplete candidate into a completed batch receipt.
        journal.append(
            ScaleBatchReceipt(
                manifest_sha256=journal.digest,
                batch_id=batch.batch_id,
                state="failed",
                source_run_id=execution["run_id"],
                source_refs=(*source_refs, f"incomplete-native-worker:{execution['job_id']}"),
                operational_failures=("Native evidence incomplete; recover the original batch.",),
            )
        )
        return {"status": "scale-batch-operationally-incomplete", "batch_id": batch.batch_id}
    predictions = None
    if campaign.execution.uses_real_prediction_backend:
        # Only an explicitly registered enrichment policy reaches this path.
        # Legacy outputs are supplemental; they cannot replace the native partition.
        from .phase34_measurement import measure_execution

        enriched = measure_execution(
            bridge,
            authority_id="scale-enrichment-"
            + identity({"manifest": journal.digest, "batch": batch.batch_id}),
            plan=authority.pilot_plan,
            execution=execution,
            allocations=batch.strategy_allocations,
            projection=ExecutionProjection(
                mode=campaign.execution.mode,
                requested_production_candidates=count,
                execution_candidates=count,
                uses_real_generation_backend=True,
                uses_real_prediction_backend=True,
                purpose="Explicit optional Scale enrichment.",
            ),
        )
        if enriched["status"] != "measured":
            return enriched
        predictions = load_model(
            ArtifactRef.model_validate(enriched["sources"]["predictions"]).verify(root),
            PilotPredictionEvidence,
        )
    observations = native_scale_observations(
        root=root,
        campaign_id=campaign.campaign_id,
        batch_id=batch.batch_id,
        run_id=execution["run_id"],
        measurement=result["measurement"],
        predictions=predictions,
        prediction_requested=campaign.execution.uses_real_prediction_backend,
        source_refs=tuple(
            ArtifactRef.model_validate(result["sources"][key])
            for key in ("candidate_index", "native_evidence")
        ),
    )
    receipt = ScaleBatchReceipt(
        manifest_sha256=journal.digest,
        batch_id=batch.batch_id,
        state="completed",
        source_run_id=execution["run_id"],
        candidates=observations,
        source_refs=source_refs,
    )
    original_sequences = {
        c.candidate_id: c.metrics["designed_chain_sequence"] for c in index.candidates
    }
    bridge.store.event(
        bridge.thread,
        "phase34-scale-batch-sequences",
        {
            "manifest": journal.digest,
            "batch": batch.batch_id,
            "sequences": {
                c.lineage.candidate_id: original_sequences[c.native_evidence.candidate_id]
                for c in observations
                if c.native_evidence is not None
            },
            "receipt_sha256": canonical_model_sha256(receipt),
        },
    )
    journal.append(receipt)
    return {
        "status": "scale-batch-measured",
        "batch_id": batch.batch_id,
        "candidate_count": len(observations),
        "evidence_policy": campaign.evidence_policy,
    }
