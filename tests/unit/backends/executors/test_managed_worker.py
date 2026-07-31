from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from easydesign.backends.executors.managed_worker import (
    ManagedQueue,
    ManagedWorker,
    ManagedWorkerLayout,
    RemoteJobBundle,
    RemoteJobInput,
)
from easydesign.core import ConfigurationError
from easydesign.orchestration.execution_targets import GpuLeaseStore


def _bundle(job_id: str = "job-1", *, maximum_gpus: int | None = 2) -> RemoteJobBundle:
    return RemoteJobBundle(
        job_id=job_id,
        controller_id="controller-a",
        controller_key_fingerprint="SHA256:controller-a",
        project_id="project-a",
        run_id="run-a",
        submitted_at=datetime(2026, 8, 1, tzinfo=UTC),
        stage_range=(4, 5),
        candidate_budget=40,
        easydesign_version="0.1.0.dev32",
        config_sha256="1" * 64,
        upstream_manifest_sha256="2" * 64,
        inputs=(
            RemoteJobInput(
                relative_path="source-run/manifests/run-manifest-0001.json",
                size_bytes=10,
                sha256="3" * 64,
                role="manifest-closure",
            ),
        ),
        maximum_gpus=maximum_gpus,
    )


def test_queue_is_append_only_and_rejects_duplicate_job_id(tmp_path: Path) -> None:
    queue = ManagedQueue(ManagedWorkerLayout(tmp_path / "managed-worker"))
    first = queue.enqueue(_bundle())
    assert first.status == "queued"
    with pytest.raises(ConfigurationError, match="禁止覆盖"):
        queue.enqueue(_bundle())
    assert queue.latest("job-1").revision == 1


def test_worker_claims_one_job_with_distinct_gpu_leases(tmp_path: Path) -> None:
    layout = ManagedWorkerLayout(tmp_path / "managed-worker")
    queue = ManagedQueue(layout)
    queue.enqueue(_bundle())
    worker = ManagedWorker(
        layout=layout,
        queue=queue,
        lease_store=GpuLeaseStore(
            lease_root=layout.runtime / "state/gpu-leases",
            host="suzhou2",
        ),
    )
    launched: list[tuple[str, tuple[int, ...]]] = []
    result = worker.admit_one(
        eligible_devices=tuple(range(8)),
        launcher=lambda bundle, devices: (
            launched.append((bundle.job_id, devices)) or 1234
        ),
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert result is not None
    assert result.status == "running"
    assert result.assigned_devices == (0, 1)
    assert launched == [("job-1", (0, 1))]
    assert len(result.lease_ids) == 2


def test_worker_reports_waiting_without_failing_job(tmp_path: Path) -> None:
    layout = ManagedWorkerLayout(tmp_path / "managed-worker")
    queue = ManagedQueue(layout)
    queue.enqueue(_bundle(maximum_gpus=1))
    worker = ManagedWorker(
        layout=layout,
        queue=queue,
        lease_store=GpuLeaseStore(
            lease_root=layout.runtime / "state/gpu-leases",
            host="suzhou2",
        ),
    )
    result = worker.admit_one(
        eligible_devices=(),
        launcher=lambda _bundle, _devices: 1234,
    )
    assert result is not None
    assert result.status == "waiting-resource"
    assert result.error_code is None


def test_queue_reservation_prevents_a_second_admission(tmp_path: Path) -> None:
    queue = ManagedQueue(ManagedWorkerLayout(tmp_path / "managed-worker"))
    queue.enqueue(_bundle())

    reserved = queue.reserve_next(resources_available=True)

    assert reserved is not None
    assert reserved.status == "admitting"
    assert queue.reserve_next(resources_available=True) is None


def test_remote_bundle_rejects_arbitrary_stage_sequence() -> None:
    with pytest.raises(ValueError, match="Stage 04"):
        RemoteJobBundle.model_validate(
            {**_bundle().model_dump(mode="json"), "stage_range": [4, 6]}
        )
