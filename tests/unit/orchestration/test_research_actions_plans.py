from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.core import ManifestStateError
from easydesign.orchestration.research_actions import (
    ApproveSiteIntent,
    DraftStrategyIntent,
    InterpretPilotIntent,
    ReviewPilotIntent,
    RunScaleIntent,
    render_action,
)
from easydesign.orchestration.research_approvals import approve_execution_plan
from easydesign.orchestration.research_plans import (
    PilotExecutionPlan,
    ScaleExecutionPlan,
    load_current_execution_plan,
    plan_sha256,
    publish_execution_plan,
    require_exact_current_plan,
)
from easydesign.orchestration.research_protocols import (
    ExperimentalCondition,
    scale_protocol_summary,
    validate_first_pilot_protocol,
)
from easydesign.stages.s03_boltzgen_configuration import SCAFFOLD_IDS

NOW = datetime(2026, 9, 4, tzinfo=UTC)


def _scale_plan(count: int) -> ScaleExecutionPlan:
    return ScaleExecutionPlan(
        project_id="project-one",
        created_at=NOW,
        foundation_manifest_sha256="a" * 64,
        target_mapping_sha256="b" * 64,
        backend="boltzgen-0.3.2",
        resource_summary={"disk_free_gib": 100, "shards": 4},
        selection_id="selection-one",
        promotion_receipt_sha256="c" * 64,
        source_pilot_manifest_sha256="d" * 64,
        protocol=scale_protocol_summary(
            total_candidate_count=count,
            strategy_ids=("s1", "s2"),
        ),
    )


def test_plan_sha_is_canonical_and_count_mutation_invalidates_approval(
    tmp_path: Path,
) -> None:
    plan = _scale_plan(50_000)
    path, digest = publish_execution_plan(tmp_path, plan)
    assert digest == plan_sha256(plan)
    assert path.is_file()
    current, _ = load_current_execution_plan(tmp_path, "scale-execution")
    assert current == plan
    _, record, record_path = approve_execution_plan(tmp_path, plan, approved_by="tester")
    assert record.plan_sha256 == digest
    assert record.approved_by == "tester"
    assert record_path.is_file()

    changed = _scale_plan(100_000)
    assert plan_sha256(changed) != digest
    with pytest.raises(ManifestStateError, match="inputs/count/backend/mapping"):
        require_exact_current_plan(tmp_path, changed, supplied_sha256=digest)


def test_typed_action_is_the_source_of_shell_rendering(tmp_path: Path) -> None:
    intent = RunScaleIntent(
        project_id="project-one",
        project_path=tmp_path / "path with spaces",
        selection_id="selection-one",
        candidate_count=37,
        plan_sha256="e" * 64,
    )

    command = render_action(intent)
    assert "--count 37" in command
    assert "--plan-sha" in command
    assert "'" in command

    proposal = tmp_path / "site proposal.yaml"
    site = ApproveSiteIntent(
        project_id="project-one",
        project_path=tmp_path,
        input_path=proposal,
    )
    assert render_action(site).startswith("easydesign site approve")
    assert "--confirm" in render_action(site)

    review = ReviewPilotIntent(
        project_id="project-one",
        project_path=tmp_path,
        run_id="pilot-one",
    )
    assert render_action(review).endswith("--run pilot-one")
    interpretation = InterpretPilotIntent(
        project_id="project-one",
        project_path=tmp_path,
        run_id="pilot-one",
        input_path=tmp_path / "interpretation.yaml",
    )
    assert "pilot interpret" in render_action(interpretation)
    follow_up = DraftStrategyIntent(
        project_id="project-one",
        project_path=tmp_path,
        source_pilot_run_id="pilot-one",
        research_event_ids=("hypothesis-one", "observation-one", "interpretation-one"),
    )
    assert render_action(follow_up).endswith("--from-pilot pilot-one")


def test_pilot_plan_sha_is_stable_and_mapping_drift_changes_identity() -> None:
    protocol = validate_first_pilot_protocol(
        conditions=(
            ExperimentalCondition(
                condition_id="baseline",
                scaffold_ids=SCAFFOLD_IDS,
                candidates_per_scaffold=40,
            ),
        ),
        official_scaffold_ids=SCAFFOLD_IDS,
    )
    plan = PilotExecutionPlan(
        project_id="project-one",
        created_at=NOW,
        foundation_manifest_sha256="a" * 64,
        target_mapping_sha256="b" * 64,
        backend="boltzgen-0.3.2+protenix-v2",
        strategy_revision="strategy-r000001",
        strategy_sha256="c" * 64,
        prediction_backend="protenix-v2",
        protocol=protocol,
    )

    assert plan_sha256(plan) == plan_sha256(plan.model_copy(deep=True))
    assert plan_sha256(plan) != plan_sha256(
        plan.model_copy(update={"target_mapping_sha256": "d" * 64})
    )
