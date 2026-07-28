"""与科研项目隔离的双层开发者自检。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml  # type: ignore[import-untyped]

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
from easydesign.orchestration.application import diagnose_runtime
from easydesign.orchestration.continuation import materialize_continuation_config
from easydesign.orchestration.profile import load_runtime_profile
from easydesign.orchestration.runtime_setup import (
    ENVIRONMENT_IDS,
    latest_asset_records,
    latest_environment_records,
)
from easydesign.orchestration.task_tracking import (
    atomic_dump_runtime_model,
    load_latest_runtime_model,
)
from easydesign.orchestration.workspace import RunIndexEntry, upsert_run_index_entries
from easydesign.safe_writes import quarantine_if_workspace_path, read_last_text_line
from easydesign.workspace_context import WorkspaceContext

from .models import SelfTestRecord


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if path.name in {"LATEST", "CURRENT"} else "x"
    with path.open(mode, encoding="utf-8") as handle:
        if mode == "a":
            handle.write(text.strip() + "\n")
        else:
            handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


class SelfTestStore:
    def __init__(
        self,
        root: Path,
        runs_root: Path,
        *,
        workspace: WorkspaceContext | None = None,
        profile_path: Path | None = None,
    ) -> None:
        self.root = root.expanduser().resolve()
        self.runs_root = runs_root.expanduser().resolve()
        self.workspace = workspace or WorkspaceContext.discover(self.root)
        self.profile_path = (
            self.workspace.profile_path
            if profile_path is None
            else profile_path.expanduser().resolve()
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, self_test_id: str) -> Path:
        if not self_test_id.startswith("selftest-") or "/" in self_test_id:
            raise ConfigurationError("无效的自检编号")
        return self.root / self_test_id / "self-test.json"

    def list(self) -> tuple[SelfTestRecord, ...]:
        records = (
            load_latest_runtime_model(path, SelfTestRecord)
            for path in self.root.glob("selftest-*/self-test.json")
        )
        return tuple(sorted(records, key=lambda item: item.updated_at, reverse=True))

    def load(self, self_test_id: str) -> SelfTestRecord:
        path = self._path(self_test_id)
        if not path.is_file():
            raise ConfigurationError(f"开发者自检不存在: {self_test_id}")
        return load_latest_runtime_model(path, SelfTestRecord)

    def save(self, record: SelfTestRecord) -> SelfTestRecord:
        path = self._path(record.self_test_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise ManifestStateError(f"自检记录已存在，拒绝覆盖: {record.self_test_id}")
        dump_model(record, path)
        return record

    def update(self, record: SelfTestRecord) -> SelfTestRecord:
        path = self._path(record.self_test_id)
        if not path.is_file():
            raise ConfigurationError(f"开发者自检不存在: {record.self_test_id}")
        atomic_dump_runtime_model(record, path)
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
            if final_root.exists():
                raise FileExistsError(f"自检发布目录已存在，拒绝覆盖: {final_root}")
            staging.rename(final_root)
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
                quarantine_if_workspace_path(
                    staging,
                    operation="developer-self-test",
                    reason="确定性七阶段自检未完成",
                )
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

    def prepare_real_backend(
        self,
        *,
        created_at: datetime | None = None,
    ) -> SelfTestRecord:
        """Freeze one non-APOE fixture and make Stage 01 ready to launch."""

        now = created_at or datetime.now(tz=UTC)
        self_test_id = (
            f"selftest-{now.strftime('%Y%m%dt%H%M%Sz').lower()}-{uuid4().hex[:6]}"
        )
        environment_records = latest_environment_records(self.workspace)
        asset_records = latest_asset_records(self.workspace)
        unavailable_environments = [
            environment_id
            for environment_id in ENVIRONMENT_IDS
            if environment_records.get(environment_id) is None
            or environment_records[environment_id].status != "available"
        ]
        required_assets = (
            "validation-1ubq-cif",
            "protenix-v2-checkpoint",
            "protenix-ccd-components",
            "protenix-ccd-rdkit-cache",
            "protenix-pdb-clusters",
            "protenix-obsolete-releases",
            "scannet-code-and-epitope-models",
            "boltzgen-inference-molecule-dataset",
            "boltzgen-source-a3149cf",
            "tnp-source-29dcac72",
        )
        unavailable_assets = [
            asset_id
            for asset_id in required_assets
            if asset_records.get(asset_id) is None
            or asset_records[asset_id].status != "available"
        ]
        readiness = {
            "unavailable_environments": ",".join(unavailable_environments),
            "unavailable_assets": ",".join(unavailable_assets),
            "fixture": "validation-1ubq-cif",
        }
        if unavailable_environments or unavailable_assets:
            record = SelfTestRecord(
                self_test_id=self_test_id,
                mode="real-backend-micro",
                status="blocked",
                engineering_status="not-started",
                backend_status="not-ready",
                scientific_status="not-started",
                stage_statuses={},
                current_stage=0,
                next_stage=1,
                fixture_asset_id="validation-1ubq-cif",
                environment=readiness,
                created_at=now,
                updated_at=now,
                message=(
                    "真实后端微型自检尚未启动：请先在“安装与环境”完成所有"
                    "环境、许可确认和模型资产。没有后端会被静默跳过。"
                ),
            )
            return self.save(record)

        fixture_record = asset_records["validation-1ubq-cif"]
        fixture_cif = (self.workspace.root / fixture_record.relative_path).resolve()
        fixture_dir = self.root / self_test_id / "fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=False)
        fixture_pse = fixture_dir / "1ubq-runtime.pse"
        loaded_profile = load_runtime_profile(self.profile_path)
        pymol_runtime = loaded_profile.profile.backends.pymol_pse
        if pymol_runtime is None:
            raise ConfigurationError("工作区 profile 没有可用 PyMOL backend")
        worker = (
            Path(__file__).resolve().parents[1]
            / "backends"
            / "target_sources"
            / "pymol_pse_fixture_worker.py"
        )
        child_environment = os.environ.copy()
        child_environment.update(self.workspace.child_environment())
        result = subprocess.run(
            (
                str(pymol_runtime.python),
                str(worker),
                "--input",
                str(fixture_cif),
                "--output",
                str(fixture_pse),
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
            env=child_environment,
        )
        if result.returncode != 0 or not fixture_pse.is_file():
            if fixture_pse.exists():
                quarantine_if_workspace_path(
                    fixture_pse,
                    operation="real-backend-selftest-fixture",
                    reason="PyMOL fixture 生成失败",
                )
            raise ConfigurationError(
                "PyMOL 未能生成真实后端自检 PSE: "
                f"returncode={result.returncode}; stderr={result.stderr[-2000:]}"
            )
        config_dir = self.root / self_test_id / "configs"
        config_dir.mkdir(parents=True, exist_ok=False)
        config_path = config_dir / "stage01.yaml"
        config_payload = {
            "schema_version": "0.7",
            "project_id": "developer-backend-selftest",
            "design": {
                "binder_profile": "vhh",
                "intent": "exploratory",
                "required_reviews": [],
            },
            "workflow": {
                "execution_mode": "unattended",
                "stop_after_stage": 1,
                "cache_mode": "online",
                "max_strategy_rounds": 1,
            },
            "stage01": {
                "target": {
                    "id": "validation-1ubq",
                    "source": {
                        "type": "local-file",
                        "path": "../fixtures/1ubq-runtime.pse",
                        "format": "pse",
                        "chain": None,
                        "chain_namespace": "auth",
                        "identity": {"uniprot_accession": None},
                    },
                    "scope": {"type": "full-sequence"},
                },
                "structure_selection": {
                    "policy": "experimental-first",
                    "quality_profile": "experimental-strict-v1",
                    "on_no_eligible_candidate": "predict",
                    "on_ambiguous_candidates": "predict",
                    "preserve_source_context": True,
                    "keep_ligands": [],
                },
                "structure_prediction": None,
            },
            **{f"stage{stage:02d}": None for stage in range(2, 8)},
        }
        with config_path.open("x", encoding="utf-8") as handle:
            handle.write(
                yaml.safe_dump(
                    config_payload,
                    allow_unicode=True,
                    sort_keys=False,
                )
            )
        record = SelfTestRecord(
            self_test_id=self_test_id,
            mode="real-backend-micro",
            status="ready",
            engineering_status="not-started",
            backend_status="ready",
            scientific_status="not-started",
            stage_statuses={"stage01": "ready"},
            current_stage=0,
            next_stage=1,
            config_relative_path=config_path.relative_to(self.workspace.root).as_posix(),
            fixture_asset_id="validation-1ubq-cif",
            environment={
                **readiness,
                "pymol_fixture": "created-and-verified",
            },
            created_at=now,
            updated_at=now,
            message=(
                "固定非 APOE 1UBQ fixture 已经由真实 PyMOL 环境生成 PSE；"
                "可以从第1步开始逐步点击运行。"
            ),
        )
        return self.save(record)

    def stage_config(
        self,
        self_test_id: str,
        *,
        stage_number: int,
        source_run_root: Path | None,
    ) -> Path:
        record = self.load(self_test_id)
        if record.mode != "real-backend-micro":
            raise ConfigurationError("只有真实后端微型自检支持逐阶段运行")
        if record.next_stage != stage_number:
            raise ConfigurationError(
                f"当前只能运行 Stage {record.next_stage or 1:02d}"
            )
        if stage_number == 1:
            if record.config_relative_path is None:
                raise ManifestStateError("真实后端自检缺少 Stage 01 配置")
            return self.workspace.root / record.config_relative_path
        if source_run_root is None:
            raise ManifestStateError("Stage 02–05 自检缺少上游 run")
        if stage_number > 5:
            raise ConfigurationError("Stage 06/07 使用独立 adapter probe")
        destination = (
            self.root
            / self_test_id
            / "configs"
            / f"stage{stage_number:02d}.yaml"
        )
        options: dict[str, object]
        if stage_number == 2:
            options = {
                "mode": "user-provided",
                "regions": [{"id": "A", "label_seq_ids": [5, 8, 12, 15, 16]}],
                "approved_by": "EasyDesign developer self-test",
                "acknowledge_user_provided_regions": True,
                "acknowledge_evidence_limitations": True,
            }
        elif stage_number == 3:
            options = {
                "profile": "boltzgen-vhh-basic-v1",
                "scaffold_registry": "official-vhh7-v1",
                "scaffold_ids": ["7eow"],
                "candidates_per_strategy": 1,
            }
        elif stage_number == 4:
            options = {
                "backend": "boltzgen-0.3.2",
                "executor": {
                    "type": "local-multi-gpu",
                    "devices": [0],
                    "workers_per_device": 1,
                },
                "required_complete_candidates_per_strategy": 1,
            }
        else:
            options = {
                "filter_profile": "nanobody-filter-standard-v1.5",
                "expanded_total_per_strategy": 2,
                "maximum_tier_a_strategies": 1,
                "strategy_selection": {
                    "full_target_refold_top_n": 1,
                    "require_unique_winner": True,
                },
            }
        return materialize_continuation_config(
            source_run_root=source_run_root,
            destination=destination,
            stage_number=stage_number,
            execution_mode="unattended",
            options=options,
            continue_after_stage=stage_number - 1,
        )

    def mark_job_started(
        self,
        self_test_id: str,
        *,
        stage_number: int,
        job_id: str,
        config_path: Path,
    ) -> SelfTestRecord:
        record = self.load(self_test_id)
        stages = dict(record.stage_statuses)
        stages[f"stage{stage_number:02d}"] = "running"
        return self.update(
            record.model_copy(
                update={
                    "status": "running",
                    "backend_status": "running",
                    "stage_statuses": stages,
                    "active_job_id": job_id,
                    "config_relative_path": (
                        config_path.relative_to(self.workspace.root).as_posix()
                    ),
                    "updated_at": datetime.now(tz=UTC),
                    "message": f"Stage {stage_number:02d} 真实后端微型自检正在运行。",
                }
            )
        )

    def mark_job_finished(
        self,
        self_test_id: str,
        *,
        stage_number: int,
        status: str,
        run_key: str | None,
        run_root: Path | None,
        error: str | None = None,
    ) -> SelfTestRecord:
        record = self.load(self_test_id)
        normalized = str(getattr(status, "value", status))
        stages = dict(record.stage_statuses)
        failed = normalized in {"failed", "operational-failed"}
        scientific_stop = normalized.startswith("stopped-") or normalized == "scientific-stop"
        stages[f"stage{stage_number:02d}"] = (
            "operational-failed"
            if failed
            else "scientific-stop"
            if scientific_stop
            else "passed"
        )
        next_stage = None if failed else (stage_number + 1 if stage_number < 7 else None)
        if run_root is not None:
            manifest_pointer = run_root / "manifests" / "LATEST"
            latest_manifest = read_last_text_line(manifest_pointer)
            run_manifest = load_model(run_root / "manifests" / latest_manifest, RunManifest)
            upsert_run_index_entries(
                self.runs_root,
                (
                    RunIndexEntry(
                        category="developer-smoke-run",
                        path=run_root.relative_to(self.runs_root).as_posix(),
                        layout_version="2",
                        status=normalized,
                        project_id=run_manifest.project_id,
                        run_id=run_manifest.run_id,
                        notes=(
                            "Real backend micro self-test; not scientific evidence.",
                            f"self_test_id={self_test_id}",
                        ),
                    ),
                ),
                generated_at=datetime.now(tz=UTC),
            )
        return self.update(
            record.model_copy(
                update={
                    "status": (
                        "operational-failed"
                        if failed
                        else "scientific-stop"
                        if scientific_stop
                        else "ready"
                        if next_stage is not None
                        else "passed"
                    ),
                    "engineering_status": "failed" if failed else "passed",
                    "backend_status": "failed" if failed else "passed",
                    "scientific_status": (
                        "stopped"
                        if scientific_stop
                        else "not-evaluated"
                        if stage_number < 5
                        else "completed"
                    ),
                    "stage_statuses": stages,
                    "run_key": run_key or record.run_key,
                    "run_relative_path": (
                        run_root.relative_to(self.runs_root).as_posix()
                        if run_root is not None
                        else record.run_relative_path
                    ),
                    "current_stage": stage_number,
                    "next_stage": next_stage,
                    "active_job_id": None,
                    "updated_at": datetime.now(tz=UTC),
                    "message": (
                        error
                        if failed and error
                        else (
                            f"Stage {stage_number:02d} 工具正常完成，但科学结果停止；"
                            "这不计为后端失败。"
                            if scientific_stop
                            else f"Stage {stage_number:02d} 真实后端自检通过。"
                        )
                    ),
                }
            )
        )

    def run_adapter_probe(
        self,
        self_test_id: str,
        *,
        stage_number: int,
    ) -> SelfTestRecord:
        if stage_number not in {6, 7}:
            raise ConfigurationError("独立 adapter probe 只用于 Stage 06/07")
        record = self.load(self_test_id)
        if record.next_stage != stage_number:
            raise ConfigurationError(f"当前只能运行 Stage {record.next_stage:02d}")
        report = diagnose_runtime(
            profile_path=self.profile_path,
            runs_root=self.runs_root,
            full=True,
        )
        selected = (
            {"boltzgen"}
            if stage_number == 6
            else {"protenix-v2", "tnp"}
        )
        failures = [
            check
            for check in report.checks
            if check.name in selected and str(check.status) != "passed"
        ]
        return self.mark_job_finished(
            self_test_id,
            stage_number=stage_number,
            status="operational-failed" if failures else "succeeded",
            run_key=record.run_key,
            run_root=(
                None
                if record.run_relative_path is None
                else self.runs_root / record.run_relative_path
            ),
            error=(
                "; ".join(f"{item.name}: {item.message}" for item in failures)
                if failures
                else None
            ),
        )


__all__ = ["SelfTestStore"]
