"""Plan-bound project approval records for major research mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import (
    DecisionAuthority,
    DecisionOption,
    DecisionRecord,
    DecisionRequest,
    ManifestStateError,
    canonical_model_sha256,
    dump_model,
    load_model,
)

from .research_plans import ExecutionPlan, plan_sha256

_PLAN_STAGE = {
    "strategy-freeze": "03-boltzgen-configuration",
    "pilot-execution": "04-pilot-generation",
    "promotion": "05-pilot-filtering",
    "scale-execution": "06-scale-generation-and-refolding",
    "selection": "07-final-filtering-and-selection",
}


def approve_execution_plan(
    project_root: Path,
    plan: ExecutionPlan,
    *,
    approved_by: str = "cli-confirmation",
) -> tuple[DecisionRequest, DecisionRecord, Path]:
    """Create or verify the immutable request/record for exactly one plan."""

    digest = plan_sha256(plan)
    root = (
        project_root.resolve()
        / "approvals"
        / plan.plan_type
        / digest
    )
    request_path = root / "request.json"
    record_path = root / "record.json"
    request = DecisionRequest(
        schema_version="0.2",
        decision_id=f"approve-{plan.plan_type}",
        stage_id=_PLAN_STAGE[plan.plan_type],
        gate=f"approve-{plan.plan_type}",
        created_at=plan.created_at,
        message=f"Approve exact immutable {plan.plan_type} plan {digest}",
        options=(
            DecisionOption(
                option_id="approve-exact-plan",
                label="Approve exact plan",
                description="Approval is invalid if any bound input or parameter changes.",
                evidence_sha256=(digest,),
            ),
        ),
        source_artifact_sha256=(digest,),
        plan_type=plan.plan_type,
        plan_sha256=digest,
    )
    if request_path.exists():
        stored_request = load_model(request_path, DecisionRequest)
        if stored_request != request:
            raise ManifestStateError("现有 plan approval request identity 不一致")
    else:
        dump_model(request, request_path)
    request_sha = canonical_model_sha256(request)
    if record_path.exists():
        record = load_model(record_path, DecisionRecord)
    else:
        record = DecisionRecord(
            schema_version="0.2",
            decision_id=request.decision_id,
            request_revision=request.revision,
            request_sha256=request_sha,
            authority=DecisionAuthority.HUMAN,
            selected_option_ids=("approve-exact-plan",),
            approved_at=datetime.now(UTC),
            approved_by=approved_by,
            acknowledgement="CLI --confirm applies only to this exact immutable plan.",
            plan_type=plan.plan_type,
            plan_sha256=digest,
        )
        dump_model(record, record_path)
    if (
        record.request_sha256 != request_sha
        or record.plan_type != plan.plan_type
        or record.plan_sha256 != digest
    ):
        raise ManifestStateError("stale or mismatched plan approval record")
    return request, record, record_path


__all__ = ["approve_execution_plan"]
