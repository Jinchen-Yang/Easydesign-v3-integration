"""CLI、未来 UI 与开发脚本共用的应用编排 API。"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

import easydesign
from easydesign.backends.hotspot import ScanNetBackendConfig, ScanNetEpitopeAdapter
from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.core import (
    BackendContractError,
    ConfigurationError,
    EasyDesignError,
    ManifestStateError,
    RunManifest,
    load_model,
    resolve_code_identity,
    sha256_file,
)

from .config import (
    LoadedRunConfig,
    LoadedSequenceRunConfig,
    ResolvedProtenixMsaProviderConfig,
    load_run_config,
)
from .profile import (
    PROFILE_ENVIRONMENT_VARIABLE,
    LoadedRuntimeProfile,
    ProtenixV2Runtime,
    PyMOLPseRuntime,
    RuntimeProfile,
    ScanNetEpitopeRuntime,
    load_runtime_profile,
    resolve_runtime_profile_path,
)
from .pse_import import execute_pse_import
from .sequence_prediction import execute_sequence_prediction
from .stage02 import execute_stage02_comparison
from .workspace import (
    PseRequestWriter,
    RunIndex,
    initialize_pse_run,
    initialize_sequence_run,
)

PROTENIX_V2_CHECKPOINT_SHA256 = (
    "8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599"
)


class DiagnosticStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_CONFIGURED = "not-configured"


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: DiagnosticStatus
    message: str


class DiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    profile_id: str
    profile_sha256: str
    checks: tuple[DiagnosticCheck, ...]


class RunPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    target_id: str
    detected_input_format: str
    stop_after_stage: int
    required_backends: tuple[str, ...]
    runs_root: Path
    profile_id: str


class PipelineExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    plan: RunPlan
    run_root: Path | None = None
    run_manifest: Path | None = None
    viewer_status: str | None = None


class RunSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    run_id: str
    path: Path
    status: str
    latest_manifest: Path
    manifest_revision: int
    completed_stages: tuple[str, ...]
    integrity_status: str = "verified"
    integrity_message: str | None = None


@dataclass(frozen=True, slots=True)
class _RuntimeContext:
    loaded_config: LoadedRunConfig
    loaded_profile: LoadedRuntimeProfile
    plan: RunPlan


def _selected_runs_root(
    *,
    config_path: Path,
    profile: RuntimeProfile,
    explicit: Path | None,
) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if profile.runs_root is not None:
        return profile.runs_root.resolve()
    return (config_path.resolve().parent / "runs").resolve()


def _required_backends(loaded: LoadedRunConfig) -> tuple[str, ...]:
    backends = [
        "protenix-v2"
        if isinstance(loaded, LoadedSequenceRunConfig)
        else "pymol-pse"
    ]
    if loaded.config.workflow.stop_after_stage >= 2:
        backends.append("scannet-epitope")
    return tuple(backends)


def validate_run_configuration(
    config_path: Path,
    *,
    profile_path: Path | None = None,
    runs_root: Path | None = None,
) -> RunPlan:
    """验证用户 YAML 与本机 profile 关联，但不探测 backend、不创建 run。"""

    loaded = load_run_config(config_path)
    stop_after = loaded.config.workflow.stop_after_stage
    if stop_after > 2:
        raise ConfigurationError(
            f"Developer Preview 尚未实现 Stage 03–07: stop_after_stage={stop_after}"
        )
    selected_profile_path = resolve_runtime_profile_path(profile_path)
    profile = (
        load_runtime_profile(selected_profile_path).profile
        if selected_profile_path.is_file()
        else RuntimeProfile(profile_id="unconfigured")
    )
    if (
        not selected_profile_path.is_file()
        and (
            profile_path is not None
            or os.environ.get(PROFILE_ENVIRONMENT_VARIABLE) is not None
        )
    ):
        load_runtime_profile(selected_profile_path)
    return RunPlan(
        project_id=loaded.config.project_id,
        target_id=loaded.config.target.target_id,
        detected_input_format=str(loaded.detected_format),
        stop_after_stage=stop_after,
        required_backends=_required_backends(loaded),
        runs_root=_selected_runs_root(
            config_path=loaded.config_path,
            profile=profile,
            explicit=runs_root,
        ),
        profile_id=profile.profile_id,
    )


def _context(
    config_path: Path,
    *,
    profile_path: Path | None,
    runs_root: Path | None,
) -> _RuntimeContext:
    loaded = load_run_config(config_path)
    stop_after = loaded.config.workflow.stop_after_stage
    if stop_after > 2:
        raise ConfigurationError(
            f"Developer Preview 尚未实现 Stage 03–07: stop_after_stage={stop_after}"
        )
    profile = load_runtime_profile(profile_path)
    plan = RunPlan(
        project_id=loaded.config.project_id,
        target_id=loaded.config.target.target_id,
        detected_input_format=str(loaded.detected_format),
        stop_after_stage=stop_after,
        required_backends=_required_backends(loaded),
        runs_root=_selected_runs_root(
            config_path=loaded.config_path,
            profile=profile.profile,
            explicit=runs_root,
        ),
        profile_id=profile.profile.profile_id,
    )
    return _RuntimeContext(loaded_config=loaded, loaded_profile=profile, plan=plan)


def _nearest_existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _protenix_adapter(
    runtime: ProtenixV2Runtime,
    loaded: LoadedSequenceRunConfig,
    provider: ResolvedProtenixMsaProviderConfig,
) -> ProtenixV2Adapter:
    prediction = loaded.config.structure_prediction
    assert prediction is not None
    return ProtenixV2Adapter(
        executable=runtime.executable,
        model_root=runtime.model_root,
        cuda_visible_devices=runtime.cuda_visible_devices,
        remote_msa_provider=provider.provider,
        remote_msa_endpoint=(
            provider.endpoint if str(provider.provider) == "custom-colabfold" else None
        ),
        remote_msa_timeout_seconds=provider.timeout_seconds,
        prediction_timeout_seconds=prediction.prediction_timeout_seconds,
    )


def _probe_protenix(
    runtime: ProtenixV2Runtime,
    loaded: LoadedSequenceRunConfig | None,
) -> str:
    if not runtime.executable.is_file():
        raise BackendContractError(f"Protenix executable 不存在: {runtime.executable}")
    if not runtime.model_root.is_dir():
        raise BackendContractError(f"Protenix model_root 不存在: {runtime.model_root}")
    if not runtime.model_checkpoint.is_file():
        raise BackendContractError(
            f"Protenix checkpoint 不存在: {runtime.model_checkpoint}"
        )
    checkpoint_sha256 = sha256_file(runtime.model_checkpoint)
    if checkpoint_sha256 != PROTENIX_V2_CHECKPOINT_SHA256:
        raise BackendContractError(
            "Protenix checkpoint SHA-256 不匹配: "
            f"expected={PROTENIX_V2_CHECKPOINT_SHA256}, actual={checkpoint_sha256}"
        )
    if loaded is None:
        adapter = ProtenixV2Adapter(
            executable=runtime.executable,
            model_root=runtime.model_root,
            cuda_visible_devices=runtime.cuda_visible_devices,
        )
    else:
        provider = loaded.msa_execution_plan[0]
        adapter = _protenix_adapter(runtime, loaded, provider)
    invocation = adapter.version_invocation()
    environment = os.environ.copy()
    environment.update(dict(invocation.environment))
    completed = subprocess.run(
        list(invocation.argv),
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=invocation.timeout_seconds,
    )
    if completed.returncode != 0:
        raise BackendContractError(
            f"Protenix 版本探针失败: {completed.stderr.strip()}"
        )
    adapter.validate_version_output(completed.stdout)
    return checkpoint_sha256


def _pymol_adapter(runtime: PyMOLPseRuntime) -> PyMOLPseAdapter:
    return PyMOLPseAdapter(
        python_executable=runtime.python,
        timeout_seconds=runtime.timeout_seconds,
    )


def _scannet_adapter(runtime: ScanNetEpitopeRuntime) -> ScanNetEpitopeAdapter:
    return ScanNetEpitopeAdapter(
        ScanNetBackendConfig(
            python_path=runtime.python,
            repository_root=runtime.repository_root,
            execution_device=runtime.execution_device,
            gpu_device=runtime.gpu_device,
            timeout_seconds=runtime.timeout_seconds,
        )
    )


def diagnose_runtime(
    *,
    profile_path: Path | None = None,
    config_path: Path | None = None,
    runs_root: Path | None = None,
) -> DiagnosticReport:
    """探测显式 profile；配置存在时只要求本次运行需要的 backend。"""

    loaded_profile = load_runtime_profile(profile_path)
    loaded = load_run_config(config_path) if config_path is not None else None
    if loaded is not None and loaded.config.workflow.stop_after_stage > 2:
        raise ConfigurationError("Developer Preview 尚未实现 Stage 03–07")
    required = set(_required_backends(loaded)) if loaded is not None else set()
    checks: list[DiagnosticCheck] = []
    python_ok = (3, 11) <= sys.version_info[:2] < (3, 13)
    checks.append(
        DiagnosticCheck(
            name="easydesign-core",
            status=DiagnosticStatus.PASSED if python_ok else DiagnosticStatus.FAILED,
            message=f"EasyDesign {easydesign.__version__}; Python {sys.version.split()[0]}",
        )
    )
    selected_runs = (
        _selected_runs_root(
            config_path=loaded.config_path,
            profile=loaded_profile.profile,
            explicit=runs_root,
        )
        if loaded is not None
        else (
            runs_root.resolve()
            if runs_root is not None
            else loaded_profile.profile.runs_root
        )
    )
    if selected_runs is not None:
        parent = _nearest_existing_parent(selected_runs)
        writable = parent.is_dir() and os.access(parent, os.W_OK)
        checks.append(
            DiagnosticCheck(
                name="runs-root",
                status=(
                    DiagnosticStatus.PASSED if writable else DiagnosticStatus.FAILED
                ),
                message=f"{selected_runs}（最近存在父目录：{parent}）",
            )
        )

    backends = loaded_profile.profile.backends
    for name, runtime in (
        ("protenix-v2", backends.protenix_v2),
        ("pymol-pse", backends.pymol_pse),
        ("scannet-epitope", backends.scannet_epitope),
    ):
        if runtime is None:
            checks.append(
                DiagnosticCheck(
                    name=name,
                    status=(
                        DiagnosticStatus.FAILED
                        if name in required
                        else DiagnosticStatus.NOT_CONFIGURED
                    ),
                    message="profile 未配置该 backend",
                )
            )
            continue
        if loaded is not None and name not in required:
            checks.append(
                DiagnosticCheck(
                    name=name,
                    status=DiagnosticStatus.NOT_CONFIGURED,
                    message="本次配置不需要该 backend，未执行探针",
                )
            )
            continue
        try:
            if name == "protenix-v2":
                if loaded is not None and not isinstance(loaded, LoadedSequenceRunConfig):
                    checks.append(
                        DiagnosticCheck(
                            name=name,
                            status=DiagnosticStatus.NOT_CONFIGURED,
                            message="未提供 sequence 配置，未执行 Protenix 探针",
                        )
                    )
                    continue
                assert isinstance(runtime, ProtenixV2Runtime)
                checkpoint = _probe_protenix(
                    runtime,
                    loaded if isinstance(loaded, LoadedSequenceRunConfig) else None,
                )
                message = f"Protenix 2.0.0；checkpoint={checkpoint}"
            elif name == "pymol-pse":
                assert isinstance(runtime, PyMOLPseRuntime)
                message = f"PyMOL {_pymol_adapter(runtime).probe_version()}"
            else:
                assert isinstance(runtime, ScanNetEpitopeRuntime)
                probe = _scannet_adapter(runtime).probe_runtime()
                message = (
                    f"TensorFlow {probe.tensorflow_version}；"
                    f"device={probe.test_operation_device}"
                )
            checks.append(
                DiagnosticCheck(
                    name=name,
                    status=DiagnosticStatus.PASSED,
                    message=message,
                )
            )
        except Exception as error:
            checks.append(
                DiagnosticCheck(
                    name=name,
                    status=DiagnosticStatus.FAILED,
                    message=str(error)[:4096] or type(error).__name__,
                )
            )
    return DiagnosticReport(
        ok=all(check.status is not DiagnosticStatus.FAILED for check in checks),
        profile_id=loaded_profile.profile.profile_id,
        profile_sha256=loaded_profile.identity.sha256,
        checks=tuple(checks),
    )


def execute_pipeline(
    config_path: Path,
    *,
    profile_path: Path | None = None,
    runs_root: Path | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> PipelineExecution:
    """验证后执行当前已实现的 Stage 01/02；不实现或猜测 Stage 03。"""

    context = _context(
        config_path,
        profile_path=profile_path,
        runs_root=runs_root,
    )
    report = diagnose_runtime(
        profile_path=context.loaded_profile.path,
        config_path=context.loaded_config.config_path,
        runs_root=context.plan.runs_root,
    )
    if not report.ok:
        failures = "; ".join(
            f"{check.name}: {check.message}"
            for check in report.checks
            if check.status is DiagnosticStatus.FAILED
        )
        raise ConfigurationError(f"Runtime preflight 失败: {failures}")
    if dry_run:
        return PipelineExecution(status="dry-run", plan=context.plan)

    package_root = Path(easydesign.__file__).resolve().parent
    candidate_repository = package_root.parents[1]
    repository_root = (
        candidate_repository
        if (candidate_repository / ".git").exists()
        and (candidate_repository / "pyproject.toml").is_file()
        else None
    )
    code_identity = resolve_code_identity(
        package_root=package_root,
        repository_root=repository_root,
        distribution_version=easydesign.__version__,
    )
    backends = context.loaded_profile.profile.backends
    loaded = context.loaded_config
    if isinstance(loaded, LoadedSequenceRunConfig):
        protenix_runtime = backends.protenix_v2
        assert protenix_runtime is not None
        checkpoint_sha256 = sha256_file(protenix_runtime.model_checkpoint)
        first_provider = loaded.msa_execution_plan[0]
        writer = _protenix_adapter(protenix_runtime, loaded, first_provider)
        prepared = initialize_sequence_run(
            config_path=loaded.config_path,
            runs_root=context.plan.runs_root,
            input_writer=writer,
            easydesign_version=easydesign.__version__,
            code_identity=code_identity,
            runtime_profile=context.loaded_profile.identity,
            run_id=run_id,
        )

        def adapter_builder(
            provider: ResolvedProtenixMsaProviderConfig,
        ) -> ProtenixV2Adapter:
            return _protenix_adapter(protenix_runtime, loaded, provider)

        completed_stage01 = execute_sequence_prediction(
            prepared=prepared,
            adapter_builder=adapter_builder,
            model_checkpoint_sha256=checkpoint_sha256,
        )
        run_root = completed_stage01.prepared.workspace.run_root
        run_manifest = completed_stage01.run_manifest
        viewer_status = str(completed_stage01.target_viewer.status)
    else:
        pymol_runtime = backends.pymol_pse
        assert pymol_runtime is not None
        adapter = _pymol_adapter(pymol_runtime)
        prepared_pse = initialize_pse_run(
            config_path=loaded.config_path,
            runs_root=context.plan.runs_root,
            request_writer=cast(PseRequestWriter, adapter),
            easydesign_version=easydesign.__version__,
            code_identity=code_identity,
            runtime_profile=context.loaded_profile.identity,
            run_id=run_id,
        )
        completed_pse = execute_pse_import(prepared=prepared_pse, adapter=adapter)
        run_root = completed_pse.prepared.workspace.run_root
        run_manifest = completed_pse.run_manifest
        viewer_status = str(completed_pse.target_viewer.status)

    if context.plan.stop_after_stage == 2:
        scannet_runtime = backends.scannet_epitope
        assert scannet_runtime is not None
        completed_stage02 = execute_stage02_comparison(
            run_root=run_root,
            adapter=_scannet_adapter(scannet_runtime),
        )
        run_manifest = completed_stage02.run_manifest
    return PipelineExecution(
        status="succeeded",
        plan=context.plan,
        run_root=run_root,
        run_manifest=run_manifest,
        viewer_status=viewer_status,
    )


def _resolve_run_from_index(runs_root: Path, selector: str) -> Path:
    index_path = runs_root / "run-index.json"
    if not index_path.is_file():
        raise ManifestStateError(f"run-index 不存在: {index_path}")
    index = load_model(index_path, RunIndex)
    matches = [
        entry
        for entry in index.entries
        if entry.category == "project-run"
        and (entry.run_id == selector or entry.path == selector)
    ]
    if not matches:
        raise ManifestStateError(f"run-index 没有匹配 run: {selector}")
    if len(matches) > 1:
        raise ManifestStateError(
            f"run_id={selector} 在多个项目中重复，请使用 project_id/run_id"
        )
    return (runs_root / matches[0].path).resolve()


def show_run(runs_root: Path, selector: str) -> RunSummary:
    """只通过 index 和 manifest 返回 run 摘要，并验证所有当前正式引用。"""

    root = runs_root.resolve()
    run_root = _resolve_run_from_index(root, selector)
    latest_pointer = run_root / "manifests" / "LATEST"
    try:
        latest_name = latest_pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 run LATEST: {latest_pointer}") from error
    manifest_path = run_root / "manifests" / latest_name
    manifest = load_model(manifest_path, RunManifest)
    manifest.config_snapshot.verify(run_root)
    completed: list[str] = []
    for reference in manifest.stage_manifest_refs:
        reference.verify(run_root)
        if reference.producer_stage is not None:
            completed.append(reference.producer_stage)
    return RunSummary(
        project_id=manifest.project_id,
        run_id=manifest.run_id,
        path=run_root,
        status=str(manifest.status),
        latest_manifest=manifest_path,
        manifest_revision=manifest.revision,
        completed_stages=tuple(completed),
    )


def list_runs(runs_root: Path) -> tuple[RunSummary, ...]:
    """列出 index 声明的 project run；不扫描 runs 目录。"""

    root = runs_root.resolve()
    index_path = root / "run-index.json"
    if not index_path.is_file():
        return ()
    index = load_model(index_path, RunIndex)
    summaries = []
    for entry in index.entries:
        if entry.category != "project-run" or entry.run_id is None:
            continue
        try:
            summaries.append(show_run(root, entry.path))
        except (EasyDesignError, OSError, ValueError) as error:
            summaries.append(
                RunSummary(
                    project_id=entry.project_id or "unknown",
                    run_id=entry.run_id,
                    path=(root / entry.path).resolve(),
                    status=entry.status,
                    latest_manifest=(root / entry.path / "manifests" / "LATEST").resolve(),
                    manifest_revision=0,
                    completed_stages=(),
                    integrity_status="unavailable",
                    integrity_message=str(error)[:4096] or type(error).__name__,
                )
            )
    return tuple(summaries)
