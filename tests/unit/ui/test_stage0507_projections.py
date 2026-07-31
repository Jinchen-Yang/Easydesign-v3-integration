from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import (
    ArtifactRef,
    Attempt,
    ExecutionStatus,
    StageId,
    StageManifest,
)
from easydesign.ui.projections import _stage_highlights

NOW = datetime(2026, 7, 31, 3, 0, tzinfo=UTC)


def _artifact(
    root: Path,
    stage: StageId,
    artifact_id: str,
    payload: object,
) -> ArtifactRef:
    relative = f"{stage}/attempt-0001/artifacts/{artifact_id}.json"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return ArtifactRef.from_file(
        run_root=root,
        relative_path=relative,
        artifact_id=artifact_id,
        role=artifact_id,
        file_format="json",
        producer_stage=str(stage),
        producer_attempt="attempt-0001",
    )


def _manifest(
    stage: StageId,
    artifacts: tuple[ArtifactRef, ...],
    *,
    contract_version: str,
) -> StageManifest:
    attempt = Attempt(
        attempt_id="attempt-0001",
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        started_at=NOW,
        ended_at=NOW,
        backend_name="fixture",
        backend_version="1",
        executor_name="fixture",
    )
    return StageManifest(
        stage_id=stage,
        contract_version=contract_version,
        status=ExecutionStatus.SUCCEEDED,
        created_at=NOW,
        completed_at=NOW,
        output_artifacts=artifacts,
        attempts=(attempt,),
        selected_attempt_id=attempt.attempt_id,
    )


def test_stage05_highlights_advisory_promotion_without_hiding_warning(
    tmp_path: Path,
) -> None:
    report = _artifact(
        tmp_path,
        StageId.PILOT_FILTERING,
        "pilot-filter-report",
        {
            "candidate_records": [{}, {}],
            "strategy_summaries": [
                {"strategy_id": "strategy-a", "tier": "tier-a"},
                {"strategy_id": "strategy-b", "tier": "tier-b"},
            ],
            "promoted_strategy_ids": ["strategy-a"],
        },
    )
    advisory = _artifact(
        tmp_path,
        StageId.PILOT_FILTERING,
        "advisory-validation-report",
        {
            "status": "strategies-promoted",
            "candidates": [
                {"candidate_id": "candidate-1", "local_gate_pass": True}
            ],
            "predictions": [
                {
                    "candidate_id": "candidate-1",
                    "structure_gate_pass": False,
                }
            ],
            "warnings": [{"code": "full-target-pose"}],
        },
    )

    highlights, _ = _stage_highlights(
        5,
        tmp_path,
        _manifest(
            StageId.PILOT_FILTERING,
            (report, advisory),
            contract_version="0.2",
        ),
    )

    assert highlights["selected_strategy_count"] == 1
    assert highlights["diagnostic_warning_count"] == 1
    assert highlights["tier_counts"] == {"tier-a": 1, "tier-b": 1}
    assert highlights["protenix_pass_count"] == 0
    assert highlights["status"] == "strategies-promoted"


def test_stage06_highlights_shared_budget_and_allocations(tmp_path: Path) -> None:
    plan = _artifact(
        tmp_path,
        StageId.SCALE_GENERATION_AND_REFOLDING,
        "scale-plan",
        {
            "profile": "production-50000",
            "total_candidate_budget": 50_000,
            "allocation_policy": "equal-across-promoted-v1",
            "strategy_allocations": [
                {"strategy_id": "strategy-a", "candidate_count": 25_000},
                {"strategy_id": "strategy-b", "candidate_count": 25_000},
            ],
            "shards": [{"shard_id": "a-01"}, {"shard_id": "b-01"}],
        },
    )
    progress = _artifact(
        tmp_path,
        StageId.SCALE_GENERATION_AND_REFOLDING,
        "scale-progress-final",
        {"collected_candidates": 50_000, "elapsed_seconds": 7200},
    )

    highlights, tables = _stage_highlights(
        6,
        tmp_path,
        _manifest(
            StageId.SCALE_GENERATION_AND_REFOLDING,
            (plan, progress),
            contract_version="0.2",
        ),
    )

    assert highlights["requested_candidates"] == 50_000
    assert highlights["strategy_count"] == 2
    assert highlights["collected_candidates"] == 50_000
    assert len(tables["strategy_allocations"]) == 2


def test_stage07_highlights_global_funnel_and_source_distribution(
    tmp_path: Path,
) -> None:
    report = _artifact(
        tmp_path,
        StageId.FINAL_FILTERING_AND_SELECTION,
        "final-filter-report",
        {
            "status": "candidates-selected",
            "sequence_prefilter": [
                {"candidate_id": "a", "hard_pass": True},
                {"candidate_id": "b", "hard_pass": False},
            ],
            "deep_filter": [
                {"candidate_id": "a", "absolute_gate_pass": True}
            ],
            "predictions": [{"candidate_id": "a", "seed": 101}],
            "consensus": [{"candidate_id": "a", "consensus_pass": True}],
        },
    )
    package = _artifact(
        tmp_path,
        StageId.FINAL_FILTERING_AND_SELECTION,
        "final-candidate-package",
        {
            "status": "smoke-review-package",
            "selection_scope": "global-across-strategies",
            "primary": [{"candidate_id": "a", "strategy_id": "strategy-a"}],
            "backup": [],
            "source_distribution": [
                {"strategy_id": "strategy-a", "selected_count": 1}
            ],
            "human_review_status": "pending",
        },
    )

    highlights, tables = _stage_highlights(
        7,
        tmp_path,
        _manifest(
            StageId.FINAL_FILTERING_AND_SELECTION,
            (report, package),
            contract_version="0.2",
        ),
    )

    assert highlights["selection_scope"] == "global-across-strategies"
    assert highlights["primary_count"] == 1
    assert highlights["funnel"]["scale_candidates"] == 2
    assert highlights["funnel"]["sequence_hard_pass"] == 1
    assert highlights["funnel"]["multi_seed_consensus"] == 1
    assert tables["primary_candidates"][0]["strategy_id"] == "strategy-a"
