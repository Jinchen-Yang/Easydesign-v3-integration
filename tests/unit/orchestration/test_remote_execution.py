from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

import easydesign
from easydesign.core import StageManifest
from easydesign.managed_protocol import ManagedWorkerProbe
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


def test_managed_stage06_budget_uses_exact_user_count(tmp_path: Path) -> None:
    config = SimpleNamespace(
        stage03=None,
        stage06=SimpleNamespace(total_candidate_count=37),
    )

    budget = remote_execution._managed_candidate_budget(
        source_run=tmp_path,
        manifest=SimpleNamespace(stage_manifest_refs=()),
        stage_range=(6, 7),
        config=config,
    )

    assert budget == 37


def test_managed_probe_forwards_bounded_timeout(monkeypatch: MonkeyPatch) -> None:
    payload = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "managed_protocol"
            / "probe-v0.3.json"
        ).read_text(encoding="utf-8")
    )
    payload["easydesign_version"] = easydesign.__version__
    calls: list[tuple[tuple[str, ...], float | None]] = []

    class FakeExecutor:
        def managed_worker_json(
            self, *arguments: str, timeout_seconds: float | None = None
        ) -> dict[str, object]:
            calls.append((arguments, timeout_seconds))
            return payload

    monkeypatch.setattr(remote_execution, "_executor", lambda **_kwargs: FakeExecutor())

    result = remote_execution.probe_managed_executor(
        executor_id="suzhou2", timeout_seconds=8.0
    )

    assert isinstance(result, ManagedWorkerProbe)
    assert calls == [(('probe',), 8.0)]
