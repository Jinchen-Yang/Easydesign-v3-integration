from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

from easydesign.core import StageManifest
from easydesign.orchestration import remote_execution
from easydesign.stages.s03_boltzgen_configuration import StrategyBundle


class _Reference:
    producer_stage = "03-boltzgen-configuration"

    def verify(self, _root: Path) -> Path:
        return Path("/verified")


def test_managed_stage04_budget_uses_continuation_config(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    stage03_reference = _Reference()
    manifest = SimpleNamespace(stage_manifest_refs=(stage03_reference,))
    strategy_reference = _Reference()
    stage03 = SimpleNamespace(require_output=lambda _role: strategy_reference)
    bundle = SimpleNamespace(
        strategies=(
            SimpleNamespace(candidates_per_strategy=1),
            SimpleNamespace(candidates_per_strategy=1),
        )
    )

    def fake_load_model(_path: Path, model_type: object) -> object:
        if model_type is StageManifest:
            return stage03
        assert model_type is StrategyBundle
        return bundle

    monkeypatch.setattr(remote_execution, "load_model", fake_load_model)
    config = SimpleNamespace(
        stage03=SimpleNamespace(candidates_per_strategy=20),
        stage06=None,
    )

    budget = remote_execution._managed_candidate_budget(
        source_run=tmp_path,
        manifest=manifest,
        stage_range=(4, 5),
        config=config,
    )

    assert budget == 40
