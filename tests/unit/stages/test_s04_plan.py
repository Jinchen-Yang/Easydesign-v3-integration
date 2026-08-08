from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from easydesign.core import ArtifactRef
from easydesign.orchestration.config import Stage04Config
from easydesign.orchestration.stage04 import _build_plan

SHA256 = "a" * 64


def _artifact(strategy_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"strategy-{strategy_id}",
        role="boltzgen-design-specification",
        relative_path=f"03-boltzgen-configuration/{strategy_id}.yaml",
        file_format="yaml",
        sha256=SHA256,
        size_bytes=1,
        producer_stage="03-boltzgen-configuration",
        producer_attempt="attempt-0001",
    )


def test_pilot_plan_uses_each_explicit_strategy_budget(tmp_path: Path) -> None:
    artifacts = {strategy_id: _artifact(strategy_id) for strategy_id in ("short", "long")}
    upstream = SimpleNamespace(
        strategy_bundle=SimpleNamespace(
            strategies=(
                SimpleNamespace(strategy_id="short", candidates_per_strategy=20),
                SimpleNamespace(strategy_id="long", candidates_per_strategy=55),
            )
        ),
        strategy_bundle_ref=SimpleNamespace(sha256=SHA256),
        stage03=SimpleNamespace(
            require_output=lambda artifact_id: artifacts[artifact_id.removeprefix("strategy-")]
        ),
    )
    resolved = SimpleNamespace(
        user_config=SimpleNamespace(
            stage04=Stage04Config(required_complete_candidates_per_strategy=40)
        )
    )

    plan = _build_plan(
        root=tmp_path,
        upstream=upstream,  # type: ignore[arg-type]
        resolved=resolved,  # type: ignore[arg-type]
        devices=(0,),
        generated_at=datetime(2026, 8, 8, tzinfo=UTC),
    )

    assert tuple(
        (item.strategy_id, item.required_complete_candidates) for item in plan.strategies
    ) == (("short", 20), ("long", 55))
