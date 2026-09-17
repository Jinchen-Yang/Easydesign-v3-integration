"""Bound Scale campaign inputs and deterministic global review preparation."""

from __future__ import annotations

from typing import Any

from easydesign.core import canonical_model_sha256
from easydesign.orchestration.local_jobs import ACTIVE_JOB_STATUSES

from .contracts import AgentBoundaryError
from .phase4 import build_candidate_dossiers, build_review_shortlist
from .phase34_batches import (
    ScaleBatchManifest,
    ScaleBatchReceipt,
    ScaleBatchStore,
    partition_campaign,
)
from .phase34_contracts import (
    ExecutionMode,
    ExecutionProjection,
    FinalSelectionInput,
    Gate4PromotionAuthority,
    GlobalCandidatePool,
    ScaleCampaignSpecification,
    ScientificContextReferences,
)
from .session_store import confined


def publish_review_inputs(
    bridge: Any,
    pool: GlobalCandidatePool,
    *,
    context: ScientificContextReferences,
    sequences: dict[str, str],
    concerns: dict[str, tuple[str, ...]],
    uncertainties: dict[str, tuple[str, ...]],
    provenance: dict[str, tuple[str, ...]],
    primary_count: int,
    backup_count: int,
    review_count: int = 30,
) -> None:
    """All batches compete first; then bounded dossiers enter the one selection model."""
    pilot = bridge.current_pilot_dossier()
    event = bridge.project_latest("phase34-scale-authority")
    if (
        pilot is None
        or event is None
        or (
            pool.campaign.promotion_authority.pilot_dossier_sha256 != canonical_model_sha256(pilot)
            or bridge.document(event["ref"])
            != pool.campaign.promotion_authority.model_dump(mode="json")
        )
    ):
        raise AgentBoundaryError("Scale evidence does not belong to current Gate 4 authority")
    upstream = pilot.upstream_fixture
    if (
        context.target_identity != upstream.target_identity
        or context.target_snapshot_sha256 != upstream.target_bundle_sha256
        or context.site_intent_sha256 != upstream.site_intent_sha256
        or context.design_specification_sha256 != upstream.strategy_sha256
        or context.pilot_dossier_sha256 != canonical_model_sha256(pilot)
    ):
        raise AgentBoundaryError(
            "Scale scientific context differs from the approved upstream facts"
        )
    if pool.campaign.evidence_policy == "boltzgen-native-v1" and (
        pool.failed_batch_ids
        or pool.resumable_batch_ids
        or len(pool.completed_batch_ids) != pool.planned_batches
        or any(
            c.native_evidence is None or c.native_evidence.native_pass is None
            for c in pool.candidates
        )
    ):
        raise AgentBoundaryError("Incomplete native Scale campaign cannot publish a final panel")
    strategy_groups = {
        s: arm.arm_id for arm in pilot.diagnosis.design_arms for s in arm.strategy_ids
    }
    native = pool.campaign.evidence_policy == "boltzgen-native-v1"
    shortlist = build_review_shortlist(
        pool=pool,
        requested_count=len(pool.global_ranking_candidate_ids) if native else review_count,
        sequence_cluster_cap=None if native else 2,
        strategy_groups=strategy_groups,
    )
    ids = {e.candidate_id for e in shortlist.entries}
    if not ids:
        raise AgentBoundaryError("Global pool has no evaluable candidates for Final Selection")
    dossiers = build_candidate_dossiers(
        pool=pool,
        shortlist=shortlist,
        context=context,
        sequences_by_candidate={i: sequences[i] for i in ids},
        concerns_by_candidate={i: concerns[i] for i in ids},
        uncertainties_by_candidate={i: uncertainties[i] for i in ids},
        provenance_by_candidate={i: provenance[i] for i in ids},
    )
    inputs = FinalSelectionInput(
        project_id=bridge.project_id,
        global_pool_sha256=canonical_model_sha256(pool),
        review_shortlist_sha256=canonical_model_sha256(shortlist),
        candidate_dossiers=dossiers,
        primary_count=primary_count,
        backup_count=backup_count,
    )
    bridge.publish_contract(
        kind="phase34-scale-campaign",
        contract=pool.campaign,
        dependencies={"pilot": canonical_model_sha256(pilot)},
    )
    bridge.publish_contract(
        kind="phase34-global-candidate-pool",
        contract=pool,
        dependencies={"campaign": canonical_model_sha256(pool.campaign)},
    )
    bridge.publish_contract(
        kind="phase34-review-shortlist",
        contract=shortlist,
        dependencies={"pool": canonical_model_sha256(pool)},
    )
    bridge.publish_contract(
        kind="phase34-final-selection-input",
        contract=inputs,
        dependencies={"shortlist": canonical_model_sha256(shortlist)},
    )
    bridge.store.event(
        bridge.thread,
        "phase34-scale-review-worker-state",
        {
            "pool": canonical_model_sha256(pool),
            "worker_state": scale_worker_state(bridge),
        },
    )


def advance_scale(bridge: Any) -> dict[str, Any]:
    from .phase34_scale_execution import dispatch_batch, measure_batch

    journal = current_batch_store(bridge)
    campaign = journal.manifest.campaign
    if campaign.execution.mode is ExecutionMode.SYNTHETIC_STRESS:
        return finalize_scale_inputs(bridge, journal)
    for batch in journal.manifest.batches:
        receipt = journal.read(batch.batch_id)
        if receipt and receipt.state == "completed":
            continue
        execution = dispatch_batch(bridge, journal, batch)
        if (
            receipt
            and receipt.state == "failed"
            and execution["status"] not in {*ACTIVE_JOB_STATUSES, "succeeded"}
        ):
            continue
        if (
            receipt
            and receipt.state == "failed"
            and (f"incomplete-native-worker:{execution.get('job_id')}" in receipt.source_refs)
        ):
            continue
        bridge.store.event(bridge.thread, "phase34-scale-execution", execution)
        if execution["status"] == "succeeded":
            return measure_batch(bridge, journal, batch, execution)
        if (
            execution["status"] in ACTIVE_JOB_STATUSES
            or execution["status"] == "waiting-for-project-worker"
        ):
            return execution
        # An exhausted backend attempt is retained as an operational batch failure.
        # Other authorized batches can continue; it is not a biological rejection.
        journal.append(
            ScaleBatchReceipt(
                manifest_sha256=journal.digest,
                batch_id=batch.batch_id,
                state="failed",
                source_run_id=execution.get("run_id"),
                operational_failures=(
                    f"Generation worker {execution.get('job_id')} ended: {execution['status']}",
                ),
            )
        )
        return {"status": "scale-batch-failed", "batch_id": batch.batch_id}
    return finalize_scale_inputs(bridge, journal)


def register_scale_campaign(
    bridge: Any, campaign: ScaleCampaignSpecification, *, batch_size: int = 100
) -> ScaleBatchStore:
    """Runtime registration only; a model cannot change the approved compute allocation."""
    pilot = bridge.current_pilot_dossier()
    authority = bridge.load_contract(
        kind="phase34-scale-authority", contract_type=Gate4PromotionAuthority
    )
    if (
        pilot is None
        or campaign.promotion_authority != authority
        or authority.pilot_dossier_sha256 != canonical_model_sha256(pilot)
    ):
        raise AgentBoundaryError("Scale campaign differs from the current Gate 4 authority")
    if campaign.evidence_policy != authority.evidence_policy:
        raise AgentBoundaryError("Scale evidence policy differs from the reviewed Gate 4 intent")
    plan = bridge.pilot_authority().pilot_plan
    if (
        campaign.execution.uses_real_generation_backend
        or campaign.execution.uses_real_prediction_backend
    ):
        if (
            campaign.generation_backend != "boltzgen-0.3.2"
            or campaign.prediction_backend != plan.prediction_backend
        ):
            raise AgentBoundaryError("Scale backend differs from the approved runtime policy")
    if campaign.execution.mode is ExecutionMode.PRODUCTION and (
        campaign.strategy_allocations != authority.production_strategy_allocations
    ):
        raise AgentBoundaryError("Production Scale cannot redistribute approved allocations")
    if (
        campaign.execution.mode is ExecutionMode.VALIDATION_MICRO
        and campaign.execution.execution_candidates > 6
    ):
        raise AgentBoundaryError("Scale micro-validation is bounded to six candidates")
    manifest = partition_campaign(bridge.project_id, campaign, batch_size=batch_size)
    bridge.publish_contract(
        kind="phase34-scale-batch-manifest",
        contract=manifest,
        dependencies={"promotion": canonical_model_sha256(authority)},
    )
    return ScaleBatchStore(
        confined(bridge.project, bridge.project / "agent/phase34-scale" / campaign.campaign_id),
        manifest,
    )


def current_batch_store(bridge: Any) -> ScaleBatchStore:
    authority = bridge.load_contract(
        kind="phase34-scale-authority", contract_type=Gate4PromotionAuthority
    )
    event = bridge.project_latest("phase34-scale-batch-manifest")
    if event and event["dependencies"].get("promotion") == canonical_model_sha256(authority):
        manifest = bridge.load_contract(
            kind="phase34-scale-batch-manifest", contract_type=ScaleBatchManifest
        )
        if (
            manifest.project_id != bridge.project_id
            or manifest.campaign.promotion_authority != authority
        ):
            raise AgentBoundaryError("Scale manifest is outside current project authority")
        return ScaleBatchStore(
            confined(
                bridge.project,
                bridge.project / "agent/phase34-scale" / manifest.campaign.campaign_id,
            ),
            manifest,
        )
    if not authority.authorizes_production_compute:
        raise AgentBoundaryError(
            "Validation Gate 4 needs explicitly registered precomputed or micro Scale evidence"
        )
    plan = bridge.pilot_authority().pilot_plan
    return register_scale_campaign(
        bridge,
        ScaleCampaignSpecification(
            campaign_id="scale-" + authority.authority_id[:32],
            promotion_authority=authority,
            execution=ExecutionProjection(
                mode=ExecutionMode.PRODUCTION,
                requested_production_candidates=authority.requested_scale_candidates,
                execution_candidates=authority.requested_scale_candidates,
                uses_real_generation_backend=True,
                uses_real_prediction_backend=authority.evidence_policy == "legacy-independent",
                purpose="Exact Scientist Gate 4 approved Scale allocation; global competition.",
            ),
            strategy_allocations=authority.production_strategy_allocations,
            generation_backend="boltzgen-0.3.2",
            prediction_backend=plan.prediction_backend,
            allocation_policy="exact-scientist-approved-strategy-counts",
            evidence_policy=authority.evidence_policy,
        ),
    )


def finalize_scale_inputs(bridge: Any, journal: ScaleBatchStore) -> dict[str, Any]:
    pool = journal.pool()
    if pool.resumable_batch_ids:
        return {"status": "scale-awaiting-batches", "batch_ids": pool.resumable_batch_ids}
    incomplete_native = pool.campaign.evidence_policy == "boltzgen-native-v1" and (
        bool(pool.failed_batch_ids)
        or any(
            c.native_evidence is None or c.native_evidence.native_pass is None
            for c in pool.candidates
        )
    )
    if not pool.global_ranking_candidate_ids or incomplete_native:
        complete_zero_pass = (
            pool.campaign.evidence_policy == "boltzgen-native-v1" and not incomplete_native
        )
        status = (
            "scale-no-native-pass" if complete_zero_pass else "scale-operationally-inconclusive"
        )
        message = (
            "The complete native campaign contains no PASS candidates. Preserve all FAIL "
            "evidence for Scientist review; no panel or automatic retry is authorized."
            if complete_zero_pass
            else "The campaign is incomplete or has no evaluable candidates. Recover missing "
            "evidence without interpreting operational failure as scientific FAIL."
        )
        bridge.store.event(
            bridge.thread,
            "phase34-scale-inconclusive",
            {
                "manifest": journal.digest,
                "worker_state": scale_worker_state(bridge),
                "failed_batch_ids": pool.failed_batch_ids,
                "incomplete_native_campaign": incomplete_native,
                "status": status,
                "message": message,
            },
        )
        return {
            "status": status,
            "failed_batches": pool.failed_batch_ids,
            "message": message,
        }
    sequences, provenance = {}, {}
    rows = bridge.store.db.execute(
        "SELECT payload FROM events WHERE kind='phase34-scale-batch-sequences' ORDER BY seq"
    ).fetchall()
    for row in rows:
        import json

        payload = json.loads(row["payload"])
        if payload.get("manifest") != journal.digest:
            continue
        receipt = journal.read(payload["batch"])
        if receipt is None or canonical_model_sha256(receipt) != payload["receipt_sha256"]:
            continue
        for c in receipt.candidates:
            if receipt.source_run_id:
                root, _ = bridge.run(receipt.source_run_id)
                for ref in c.lineage.artifact_refs:
                    ref.verify(root)
            elif pool.campaign.execution.mode is not ExecutionMode.SYNTHETIC_STRESS:
                raise AgentBoundaryError("Real Scale candidate has no source run")
            sequences[c.lineage.candidate_id] = payload["sequences"][c.lineage.candidate_id]
            provenance[c.lineage.candidate_id] = receipt.source_refs or (
                canonical_model_sha256(receipt),
            )
    ids = {c.lineage.candidate_id for c in pool.candidates}
    if ids != set(sequences):
        raise AgentBoundaryError("Scale sequence evidence does not cover the complete global pool")
    _, context, _ = bridge.pilot_inputs()
    pilot = bridge.current_pilot_dossier()
    assert pilot is not None
    references = ScientificContextReferences(
        target_identity=context.target_identity,
        target_snapshot_sha256=context.target_bundle_sha256,
        site_intent_sha256=context.site_intent_sha256,
        design_specification_sha256=context.strategy_sha256,
        pilot_dossier_sha256=canonical_model_sha256(pilot),
        evidence_refs=(
            context.target_bundle_sha256,
            context.site_intent_sha256,
            context.strategy_sha256,
            canonical_model_sha256(pilot),
        ),
    )
    native = pool.campaign.evidence_policy == "boltzgen-native-v1"
    count = (
        len(pool.global_ranking_candidate_ids)
        if native
        else min(30, len(pool.global_ranking_candidate_ids))
    )
    # All native PASS rows are reviewed. Deduplication limits the panel, not evidence visibility.
    actual = (
        len({c.lineage.sequence_sha256 for c in pool.candidates if c.competition_eligible})
        if native
        else len(
            build_review_shortlist(pool=pool, requested_count=count, sequence_cluster_cap=2).entries
        )
    )
    primary = min(6, max(1, actual // 2))
    publish_review_inputs(
        bridge,
        pool,
        context=references,
        sequences=sequences,
        concerns={
            i: ("Development ordering does not establish binding or efficacy.",) for i in ids
        },
        uncertainties={
            i: (
                "Wet-lab binding, function and developability untested.",
                f"Campaign contains {len(pool.failed_batch_ids)} failed batches; "
                "pose diversity is unverified.",
            )
            for i in ids
        },
        provenance=provenance,
        primary_count=primary,
        backup_count=min(6, actual - primary),
        review_count=count,
    )
    return {
        "status": "scale-global-review-ready",
        "global_pool_sha256": canonical_model_sha256(pool),
    }


def scale_worker_state(bridge: Any) -> str:
    from .session_store import identity

    return identity(
        [
            (j.job_id, j.status)
            for j in bridge.controller.list(project_id=bridge.project_id)
            if j.run_id and j.run_id.startswith("scale-v3-")
        ]
    )
