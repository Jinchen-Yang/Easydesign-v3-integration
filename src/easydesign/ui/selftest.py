"""与科研项目隔离的双层开发者自检。"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import easydesign
from easydesign.core import (
    ArtifactRef,
    Attempt,
    EvidenceStatus,
    ExecutionStatus,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    resolve_code_identity,
)
from easydesign.core.errors import ConfigurationError, ManifestStateError
from easydesign.orchestration.workspace import RunIndexEntry, upsert_run_index_entries

from .models import SelfTestRecord


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class SelfTestStore:
    def __init__(self, root: Path, runs_root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.runs_root = runs_root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, self_test_id: str) -> Path:
        if not self_test_id.startswith("selftest-") or "/" in self_test_id:
            raise ConfigurationError("无效的自检编号")
        return self.root / self_test_id / "self-test.json"

    def list(self) -> tuple[SelfTestRecord, ...]:
        records = (
            load_model(path, SelfTestRecord)
            for path in self.root.glob("selftest-*/self-test.json")
        )
        return tuple(sorted(records, key=lambda item: item.updated_at, reverse=True))

    def load(self, self_test_id: str) -> SelfTestRecord:
        path = self._path(self_test_id)
        if not path.is_file():
            raise ConfigurationError(f"开发者自检不存在: {self_test_id}")
        return load_model(path, SelfTestRecord)

    def save(self, record: SelfTestRecord) -> SelfTestRecord:
        path = self._path(record.self_test_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ManifestStateError(f"自检记录已存在，拒绝覆盖: {record.self_test_id}")
        dump_model(record, path)
        return record

    def run_deterministic(self, *, created_at: datetime | None = None) -> SelfTestRecord:
        """真实创建七个 manifest/attempt/artifact，但不冒充科学输入。"""

        now = created_at or datetime.now(tz=UTC)
        self_test_id = f"selftest-{now.strftime('%Y%m%dt%H%M%Sz').lower()}-{uuid4().hex[:6]}"
        run_id = f"synthetic-{uuid4().hex[:12]}"
        project_id = "developer-self-test"
        relative_root = Path("_selftests") / self_test_id / run_id
        final_root = self.runs_root / relative_root
        if final_root.exists():
            raise ManifestStateError(f"自检 run 已存在: {final_root}")
        staging_parent = self.runs_root / "_selftests" / self_test_id
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{run_id}.creating-", dir=staging_parent))
        try:
            config_path = staging / "config-snapshot" / "developer-self-test.json"
            _atomic_text(
                config_path,
                json.dumps(
                    {
                        "schema_version": "self-test-0.1",
                        "mode": "synthetic-engineering-smoke",
                        "reusable_as_scientific_input": False,
                        "stage_count": 7,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            config_ref = ArtifactRef.from_file(
                run_root=staging,
                relative_path=config_path.relative_to(staging).as_posix(),
                artifact_id="self-test-config",
                role="developer-self-test-config",
                file_format="json",
            )
            package_root = Path(easydesign.__file__).resolve().parent
            repository_candidate = package_root.parents[1]
            code_identity = resolve_code_identity(
                package_root=package_root,
                repository_root=(
                    repository_candidate
                    if (repository_candidate / ".git").is_dir()
                    else None
                ),
                distribution_version=easydesign.__version__,
            )
            current = RunManifest(
                schema_version="1.2",
                revision=1,
                project_id=project_id,
                run_id=run_id,
                easydesign_version=easydesign.__version__,
                code_identity=code_identity,
                status=ExecutionStatus.RUNNING,
                evidence_status=EvidenceStatus.IMPLEMENTED,
                created_at=now,
                updated_at=now,
                config_snapshot=config_ref,
            )
            manifests = staging / "manifests"
            current_path = dump_model(current, manifests / "run-manifest.v0001.json")
            _atomic_text(manifests / "LATEST", f"{current_path.name}\n")
            stage_refs: list[ArtifactRef] = []
            upstream_output: ArtifactRef | None = None
            upstream_stage: StageManifest | None = None
            stage_statuses: dict[str, str] = {}
            for index, stage_id in enumerate(StageId, start=1):
                timestamp = now + timedelta(microseconds=index)
                attempt_id = "attempt-0001"
                artifact_path = (
                    staging
                    / str(stage_id)
                    / attempt_id
                    / "artifacts"
                    / "engineering-smoke.json"
                )
                _atomic_text(
                    artifact_path,
                    json.dumps(
                        {
                            "schema_version": "0.1",
                            "stage_number": index,
                            "stage_id": str(stage_id),
                            "adapter": "deterministic-test-double",
                            "reusable_as_scientific_input": False,
                            "message": "Engineering contract and lineage passed.",
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                )
                output = ArtifactRef.from_file(
                    run_root=staging,
                    relative_path=artifact_path.relative_to(staging).as_posix(),
                    artifact_id=f"self-test-stage-{index:02d}",
                    role="synthetic-engineering-evidence",
                    file_format="json",
                    producer_stage=str(stage_id),
                    producer_attempt=attempt_id,
                )
                attempt = Attempt(
                    attempt_id=attempt_id,
                    status=ExecutionStatus.SUCCEEDED,
                    created_at=timestamp,
                    started_at=timestamp,
                    ended_at=timestamp,
                    backend_name="deterministic-test-double",
                    backend_version="0.1",
                    executor_name="in-process",
                )
                dump_model(
                    attempt,
                    artifact_path.parent.parent / "attempt-manifest.json",
                )
                stage = StageManifest(
                    stage_id=stage_id,
                    contract_version="0.1",
                    status=ExecutionStatus.SUCCEEDED,
                    created_at=timestamp,
                    completed_at=timestamp,
                    input_artifacts=(() if upstream_output is None else (upstream_output,)),
                    output_artifacts=(output,),
                    attempts=(attempt,),
                    selected_attempt_id=attempt_id,
                    warnings=(
                        "Synthetic engineering evidence; forbidden as scientific input.",
                    ),
                )
                if upstream_stage is not None:
                    stage.validate_inputs_declared_by((upstream_stage,))
                stage_path = artifact_path.parent / "stage-manifest.json"
                dump_model(stage, stage_path)
                stage_ref = ArtifactRef.from_file(
                    run_root=staging,
                    relative_path=stage_path.relative_to(staging).as_posix(),
                    artifact_id=f"stage-{index:02d}-manifest",
                    role="stage-manifest",
                    file_format="json",
                    producer_stage=str(stage_id),
                    producer_attempt=attempt_id,
                )
                stage_refs.append(stage_ref)
                next_time = timestamp + timedelta(microseconds=1)
                current = current.next_revision(
                    updated_at=next_time,
                    status=(
                        ExecutionStatus.SUCCEEDED
                        if index == 7
                        else ExecutionStatus.RUNNING
                    ),
                    completed_at=next_time if index == 7 else None,
                    stage_manifest_refs=tuple(stage_refs),
                    clear_workflow_state=True,
                )
                current_path = dump_model(
                    current,
                    manifests / f"run-manifest.v{current.revision:04d}.json",
                )
                _atomic_text(manifests / "LATEST", f"{current_path.name}\n")
                upstream_output = output
                upstream_stage = stage
                stage_statuses[f"stage{index:02d}"] = "passed"
            final_root.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, final_root)
            upsert_run_index_entries(
                self.runs_root,
                (
                    RunIndexEntry(
                        category="developer-smoke-run",
                        path=relative_root.as_posix(),
                        layout_version="1",
                        status="succeeded",
                        project_id=project_id,
                        run_id=run_id,
                        notes=(
                            "Synthetic engineering smoke; not a scientific run.",
                            "All seven manifest contracts completed deterministically.",
                        ),
                    ),
                ),
                generated_at=now + timedelta(seconds=1),
            )
        except Exception:
            if staging.exists():
                import shutil

                shutil.rmtree(staging)
            raise
        record = SelfTestRecord(
            self_test_id=self_test_id,
            mode="deterministic-seven-stage",
            status="passed",
            engineering_status="passed",
            backend_status="not-requested",
            scientific_status="not-applicable",
            stage_statuses=stage_statuses,
            run_key=relative_root.as_posix(),
            created_at=now,
            updated_at=now + timedelta(seconds=1),
            message=(
                "七阶段 manifest、ArtifactRef、attempt 和 lineage 均已通过；"
                "结果被标记为 synthetic-engineering-smoke，禁止用于科学结论。"
            ),
        )
        return self.save(record)

    def record_real_backend_plan(
        self,
        *,
        environment: dict[str, str],
        created_at: datetime | None = None,
    ) -> SelfTestRecord:
        """登记真实后端检查；执行器后续逐项更新，不能伪造为通过。"""

        now = created_at or datetime.now(tz=UTC)
        record = SelfTestRecord(
            self_test_id=f"selftest-{now.strftime('%Y%m%dt%H%M%Sz').lower()}-{uuid4().hex[:6]}",
            mode="real-backend-micro",
            status="ready",
            engineering_status="not-started",
            backend_status="not-started",
            scientific_status="not-started",
            stage_statuses={},
            environment=environment,
            created_at=now,
            updated_at=now,
            message=(
                "真实后端微型自检已登记但尚未启动；必须先完成 doctor、GPU、"
                "磁盘、模型与固定非 APOE fixture 预检。"
            ),
        )
        return self.save(record)


__all__ = ["SelfTestStore"]
