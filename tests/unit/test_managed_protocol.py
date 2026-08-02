from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from easydesign.core import ConfigurationError
from easydesign.managed_protocol import (
    ManagedJobRevision,
    ManagedWorkerProbe,
    RemoteJobBundle,
)
from easydesign.orchestration import remote_execution
from easydesign.orchestration.remote_execution import (
    require_managed_probe_compatible,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "managed_protocol"


@pytest.mark.parametrize(
    ("name", "model_type"),
    (
        ("bundle-v0.2.json", RemoteJobBundle),
        ("bundle-stage06-user-count-v0.2.json", RemoteJobBundle),
        ("probe-v0.3.json", ManagedWorkerProbe),
        ("revision-v0.1.json", ManagedJobRevision),
    ),
)
def test_managed_protocol_golden_json(name: str, model_type: type) -> None:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    restored = model_type.model_validate(payload)

    assert restored.model_dump(mode="json", exclude_none=False) == payload


def test_managed_bundle_rejects_single_stage_or_shell_field() -> None:
    payload = json.loads((FIXTURES / "bundle-v0.2.json").read_text(encoding="utf-8"))
    payload["stage_range"] = [4]
    with pytest.raises(ValidationError, match="04→05"):
        RemoteJobBundle.model_validate(payload)

    payload["stage_range"] = [4, 5]
    payload["command"] = "rm -rf /"
    with pytest.raises(ValidationError, match="Extra inputs"):
        RemoteJobBundle.model_validate(payload)


def test_managed_bundle_accepts_manifest_closed_empty_file() -> None:
    payload = json.loads((FIXTURES / "bundle-v0.2.json").read_text(encoding="utf-8"))

    bundle = RemoteJobBundle.model_validate(payload)

    empty = next(item for item in bundle.inputs if item.size_bytes == 0)
    assert empty.sha256 == (
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )


def test_managed_stage06_bundle_preserves_exact_user_count() -> None:
    payload = json.loads(
        (FIXTURES / "bundle-stage06-user-count-v0.2.json").read_text(
            encoding="utf-8"
        )
    )

    bundle = RemoteJobBundle.model_validate(payload)

    assert bundle.stage_range == (6, 7)
    assert bundle.candidate_budget == 37


def test_managed_manifest_closure_includes_pointer_revisions(tmp_path: Path) -> None:
    pointer = tmp_path / "manifests" / "LATEST"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("run-manifest.v0001.json\n", encoding="utf-8")
    revisions = pointer.with_name("LATEST.revisions")
    revisions.mkdir()
    (revisions / "revision-000001.txt").write_text(
        "run-manifest.v0002.json\n",
        encoding="utf-8",
    )

    closure = remote_execution._pointer_revision_closure(tmp_path, pointer)

    assert closure == (
        "manifests/LATEST",
        "manifests/LATEST.revisions/revision-000001.txt",
    )


def test_managed_config_input_closure_preserves_safe_relative_paths(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config" / "stage04.yaml"
    config.parent.mkdir()
    config.write_text("schema_version: '0.7'\n", encoding="utf-8")
    source = config.parent / "inputs" / "continuation" / "target.pse"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"frozen-pse")

    closure = remote_execution._managed_config_input_closure(
        config,
        (source, None),
    )

    assert closure == (("inputs/continuation/target.pse", source.resolve()),)

    outside = tmp_path / "outside.pse"
    outside.write_bytes(b"outside")
    with pytest.raises(ConfigurationError, match="配置目录内"):
        remote_execution._managed_config_input_closure(config, (outside,))


def test_managed_observation_uses_allow_listed_status_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = json.loads((FIXTURES / "revision-v0.1.json").read_text(encoding="utf-8"))
    progress = {
        "schema_version": "0.1",
        "stage_id": "04-pilot-generation",
        "phase": "running",
        "updated_at": "2026-08-01T14:00:00Z",
        "status": "running",
        "total_tasks": 1,
        "pending_tasks": 0,
        "waiting_tasks": 0,
        "running_tasks": 1,
        "succeeded_tasks": 0,
        "failed_tasks": 0,
        "planned_candidates": 1,
        "collected_candidates": 0,
        "per_device": {"0": "task-1"},
        "elapsed_seconds": 10.0,
        "throughput_candidates_per_hour": None,
        "estimated_remaining_seconds": None,
        "task_heartbeats": [],
        "recent_errors": [],
    }

    class FakeExecutor:
        def managed_worker_json(self, *arguments: str) -> dict[str, object]:
            assert arguments == ("status", "job-stage04")
            return {
                "queue": queue,
                "result": None,
                "progress": progress,
                "progress_error": None,
            }

    monkeypatch.setattr(
        remote_execution,
        "_executor",
        lambda **_kwargs: FakeExecutor(),
    )

    observed = remote_execution.observe_managed_pipeline(
        executor_id="suzhou2",
        job_id="job-stage04",
    )

    assert observed.progress is not None
    assert observed.progress.stage_id == "04-pilot-generation"
    assert observed.progress_error is None


def test_managed_probe_ready_requires_both_chains_and_every_backend() -> None:
    payload = json.loads((FIXTURES / "probe-v0.3.json").read_text(encoding="utf-8"))
    assert ManagedWorkerProbe.model_validate(payload).ready is True

    payload["backends"][2]["ready"] = False
    assert ManagedWorkerProbe.model_validate(payload).ready is False

    payload["backends"][2]["ready"] = True
    payload["gpu_count"] = 7
    payload["gpu_devices"] = payload["gpu_devices"][:7]
    assert ManagedWorkerProbe.model_validate(payload).ready is False


def test_managed_probe_rejects_legacy_schema_or_inconsistent_gpu_summary() -> None:
    legacy = json.loads((FIXTURES / "probe-v0.2.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        ManagedWorkerProbe.model_validate(legacy)

    payload = json.loads((FIXTURES / "probe-v0.3.json").read_text(encoding="utf-8"))
    payload["eligible_gpu_count"] = 7
    with pytest.raises(ValidationError, match="逐卡状态"):
        ManagedWorkerProbe.model_validate(payload)


def test_controller_fails_closed_for_version_or_capability_mismatch() -> None:
    payload = json.loads((FIXTURES / "probe-v0.3.json").read_text(encoding="utf-8"))
    require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))

    payload["easydesign_version"] = "0.1.0.dev34"
    with pytest.raises(ConfigurationError, match="版本不一致"):
        require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))

    payload["easydesign_version"] = "0.1.0.dev43"
    payload["supported_stage_ranges"] = [[4, 5]]
    with pytest.raises(ConfigurationError, match="missing_stage_ranges"):
        require_managed_probe_compatible(ManagedWorkerProbe.model_validate(payload))
