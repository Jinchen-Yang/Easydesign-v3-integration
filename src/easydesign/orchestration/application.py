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
from easydesign.backends.boltzgen import (
    BoltzGenCheckAdapter,
    BoltzGenGenerationAdapter,
)
from easydesign.backends.scannet import ScanNetBackendConfig, ScanNetEpitopeAdapter
from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.backends.tnp import TnpAdapter
from easydesign.core import (
    BackendContractError,
    ConfigurationError,
    EasyDesignError,
    ExecutionStatus,
    ManifestStateError,
    ProgressSnapshot,
    RunManifest,
    StageId,
    StageManifest,
    load_model,
    resolve_code_identity,
    sha256_file,
)
from easydesign.safe_writes import read_last_text_line
from easydesign.stages.s02_hotspot_discovery import RegionMethod

from .config import (
    ExecutionMode,
    LoadedPseRunConfig,
    LoadedRemoteRunConfig,
    LoadedRunConfig,
    LoadedSequenceRunConfig,
    LoadedStructureRunConfig,
    ResolvedProtenixMsaProviderConfig,
    Stage02Method,
    TargetInputFormat,
    load_run_config,
    migrate_run_config,
)
from .decisions import load_decision_record_context
from .hotspots import (
    approve_hotspots_by_policy,
    approve_hotspots_from_initial_config,
)
from .profile import (
    PROFILE_ENVIRONMENT_VARIABLE,
    BoltzGenRuntime,
    LoadedRuntimeProfile,
    ProtenixV2Runtime,
    PyMOLPseRuntime,
    RuntimeProfile,
    ScanNetEpitopeRuntime,
    TnpRuntime,
    load_runtime_profile,
    resolve_runtime_profile_path,
)
from .sequence_prediction import execute_sequence_prediction
from .stage01_handlers import execute_pse_source
from .stage01_sources import execute_stage01_source
from .stage02 import execute_stage02
from .stage03 import (
    continue_run_in_place,
    execute_stage03,
    initialize_continuation_run,
)
from .stage04 import Stage04Execution, execute_stage04
from .stage05 import ComplexAdapterBuilder, Stage05Execution, execute_stage05
from .stage06 import Stage06Execution, execute_stage06
from .stage07 import Stage07Execution, execute_stage07
from .task_tracking import load_latest_runtime_model
from .workspace import (
    PreparedRun,
    PreparedSequenceRun,
    PseRequestWriter,
    RunIndex,
    RunWorkspace,
    initialize_pse_run,
    initialize_run_workspace,
    load_resolved_run_config,
)

PROTENIX_V2_CHECKPOINT_SHA256 = "8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599"
IMPLEMENTED_STAGE_MAX = 7


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


def _load_latest_run_manifest(root: Path) -> tuple[RunManifest, Path]:
    pointer = root / "manifests" / "LATEST"
    try:
        name = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"无法读取 run LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


def _continuation_start_stage(
    source_run: Path,
    *,
    continue_after_stage: int | None = None,
) -> int:
    root = source_run.resolve()
    run, _ = _load_latest_run_manifest(root)
    if continue_after_stage is None and run.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("continuation source 必须是终态 succeeded run")
    selected: list[tuple[int, StageManifest]] = []
    for reference in run.stage_manifest_refs:
        if reference.producer_stage is None:
            raise ManifestStateError("continuation source StageManifest 缺少 producer_stage")
        stage_number = int(reference.producer_stage.split("-", maxsplit=1)[0])
        if continue_after_stage is not None and stage_number > continue_after_stage:
            continue
        selected.append((stage_number, load_model(reference.verify(root), StageManifest)))
    stage_numbers = sorted(number for number, _ in selected)
    expected_last = (
        continue_after_stage
        if continue_after_stage is not None
        else (max(stage_numbers) if stage_numbers else 0)
    )
    if not stage_numbers or stage_numbers != list(range(1, expected_last + 1)):
        raise ManifestStateError("continuation source Stage 序列必须从 01 连续")
    for stage_number, stage_manifest in selected:
        if stage_manifest.status is not ExecutionStatus.SUCCEEDED:
            raise ManifestStateError(
                f"continuation source Stage {stage_number:02d} 未成功"
            )
    if continue_after_stage is not None:
        start_stage = continue_after_stage + 1
    else:
        start_stage = max(stage_numbers) + 1
    if start_stage > IMPLEMENTED_STAGE_MAX:
        raise ManifestStateError("continuation source 已完成所有已实现 Stage")
    return start_stage


def migrate_run_configuration(source: Path, destination: Path) -> Path:
    """CLI/UI 共用的显式配置迁移入口。"""

    return migrate_run_config(source, destination)


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


def _required_backends(
    loaded: LoadedRunConfig,
    *,
    start_stage: int = 1,
) -> tuple[str, ...]:
    if start_stage < 1 or start_stage > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(f"start_stage 不在已实现范围: {start_stage}")
    backends: list[str] = []
    if start_stage <= 1 and isinstance(loaded, LoadedSequenceRunConfig):
        backends.append("protenix-v2")
    elif start_stage <= 1 and isinstance(loaded, LoadedPseRunConfig):
        backends.append("pymol-pse")
    elif (
        start_stage <= 1
        and isinstance(loaded, LoadedRemoteRunConfig)
        and loaded.config.structure_prediction is not None
    ):
        backends.append("protenix-v2")
    stop_after = loaded.config.workflow.stop_after_stage
    if start_stage <= 2 <= stop_after:
        stage02 = loaded.config.stage02
        assert stage02 is not None
        if Stage02Method.SCANNET in stage02.methods:
            backends.append("scannet-epitope")
    if start_stage <= 3 <= stop_after:
        backends.append("boltzgen-validation")
    if start_stage <= 6 and stop_after >= max(start_stage, 4):
        backends.append("boltzgen")
    if (
        (start_stage <= 5 <= stop_after or start_stage <= 7 <= stop_after)
        and "protenix-v2" not in backends
    ):
        backends.append("protenix-v2")
    if start_stage <= 7 <= stop_after:
        backends.append("tnp")
    return tuple(backends)


def validate_run_configuration(
    config_path: Path,
    *,
    profile_path: Path | None = None,
    runs_root: Path | None = None,
    source_base_dir: Path | None = None,
) -> RunPlan:
    """验证用户 YAML 与本机 profile 关联，但不探测 backend、不创建 run。"""

    loaded = load_run_config(config_path, source_base_dir=source_base_dir)
    runs_base_path = (
        loaded.config_path
        if source_base_dir is None
        else source_base_dir.expanduser().resolve(strict=True) / loaded.config_path.name
    )
    stop_after = loaded.config.workflow.stop_after_stage
    if stop_after > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(
            "Developer Preview 当前最高实现到 "
            f"Stage {IMPLEMENTED_STAGE_MAX:02d}: stop_after_stage={stop_after}"
        )
    selected_profile_path = resolve_runtime_profile_path(profile_path)
    profile = (
        load_runtime_profile(selected_profile_path).profile
        if selected_profile_path.is_file()
        else RuntimeProfile(profile_id="workspace-local")
    )
    if not selected_profile_path.is_file() and (
        profile_path is not None or os.environ.get(PROFILE_ENVIRONMENT_VARIABLE) is not None
    ):
        load_runtime_profile(selected_profile_path)
    return RunPlan(
        project_id=loaded.config.project_id,
        target_id=loaded.config.target.target_id,
        detected_input_format=str(loaded.detected_format),
        stop_after_stage=stop_after,
        required_backends=_required_backends(loaded),
        runs_root=_selected_runs_root(
            config_path=runs_base_path,
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
    start_stage: int = 1,
    source_base_dir: Path | None = None,
) -> _RuntimeContext:
    loaded = load_run_config(config_path, source_base_dir=source_base_dir)
    runs_base_path = (
        loaded.config_path
        if source_base_dir is None
        else source_base_dir.expanduser().resolve(strict=True) / loaded.config_path.name
    )
    stop_after = loaded.config.workflow.stop_after_stage
    if stop_after > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(
            "Developer Preview 当前最高实现到 "
            f"Stage {IMPLEMENTED_STAGE_MAX:02d}: stop_after_stage={stop_after}"
        )
    profile = load_runtime_profile(profile_path)
    plan = RunPlan(
        project_id=loaded.config.project_id,
        target_id=loaded.config.target.target_id,
        detected_input_format=str(loaded.detected_format),
        stop_after_stage=stop_after,
        required_backends=_required_backends(loaded, start_stage=start_stage),
        runs_root=_selected_runs_root(
            config_path=runs_base_path,
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
    provider: ResolvedProtenixMsaProviderConfig | None,
) -> ProtenixV2Adapter:
    prediction = loaded.config.structure_prediction
    assert prediction is not None
    if provider is None:
        return ProtenixV2Adapter(
            executable=runtime.executable,
            model_root=runtime.model_root,
            cuda_visible_devices=runtime.cuda_visible_devices,
            prediction_timeout_seconds=prediction.prediction_timeout_seconds,
        )
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
        raise BackendContractError(f"Protenix checkpoint 不存在: {runtime.model_checkpoint}")
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
        provider = loaded.msa_execution_plan[0] if loaded.msa_execution_plan else None
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
        raise BackendContractError(f"Protenix 版本探针失败: {completed.stderr.strip()}")
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


def _boltzgen_adapter(
    runtime: BoltzGenRuntime,
    *,
    require_generation_assets: bool = True,
) -> BoltzGenCheckAdapter:
    return BoltzGenCheckAdapter(
        executable=runtime.executable,
        repository_root=runtime.repository_root,
        cache_root=runtime.cache_root,
        timeout_seconds=runtime.timeout_seconds,
        validation_workers=runtime.validation_workers,
        offline_mode=runtime.offline_mode,
        require_generation_assets=require_generation_assets,
    )


def _boltzgen_generation_adapter(
    runtime: BoltzGenRuntime,
) -> BoltzGenGenerationAdapter:
    return BoltzGenGenerationAdapter(
        check_adapter=_boltzgen_adapter(runtime, require_generation_assets=True),
        generation_timeout_seconds=runtime.generation_timeout_seconds,
        data_loader_workers=runtime.data_loader_workers,
    )


def _complex_protenix_adapter_builder(
    runtime: ProtenixV2Runtime,
    *,
    prediction_timeout_seconds: int,
) -> ComplexAdapterBuilder:
    def build(
        provider: ResolvedProtenixMsaProviderConfig,
        device: int,
    ) -> ProtenixV2Adapter:
        return ProtenixV2Adapter(
            executable=runtime.executable,
            model_root=runtime.model_root,
            cuda_visible_devices=str(device),
            remote_msa_provider=provider.provider,
            remote_msa_endpoint=(
                provider.endpoint if str(provider.provider) == "custom-colabfold" else None
            ),
            remote_msa_timeout_seconds=provider.timeout_seconds,
            prediction_timeout_seconds=prediction_timeout_seconds,
        )

    return build


def _tnp_adapter(runtime: TnpRuntime) -> TnpAdapter:
    return TnpAdapter(
        python=runtime.python,
        executable=runtime.executable,
        repository_root=runtime.repository_root,
        timeout_seconds=runtime.timeout_seconds,
        ncores=runtime.ncores,
    )


def diagnose_runtime(
    *,
    profile_path: Path | None = None,
    config_path: Path | None = None,
    runs_root: Path | None = None,
    source_base_dir: Path | None = None,
    start_stage: int = 1,
    full: bool = False,
    backend_ids: tuple[str, ...] | None = None,
) -> DiagnosticReport:
    """探测显式 profile；配置存在时只要求本次运行需要的 backend。"""

    loaded_profile = load_runtime_profile(profile_path)
    loaded = (
        load_run_config(config_path, source_base_dir=source_base_dir)
        if config_path is not None
        else None
    )
    if loaded is not None and loaded.config.workflow.stop_after_stage > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(
            f"Developer Preview 当前最高实现到 Stage {IMPLEMENTED_STAGE_MAX:02d}"
        )
    known_backends = {
        "protenix-v2",
        "pymol-pse",
        "scannet-epitope",
        "boltzgen-validation",
        "boltzgen",
        "tnp",
    }
    if backend_ids is not None:
        if loaded is not None or full:
            raise ConfigurationError(
                "backend_ids 不能与 config_path 或 full runtime probe 同时使用"
            )
        unknown = set(backend_ids) - known_backends
        if unknown:
            raise ConfigurationError(f"未知 runtime backend: {sorted(unknown)}")
        required = set(backend_ids)
    elif loaded is not None:
        required = set(_required_backends(loaded, start_stage=start_stage))
    else:
        required = known_backends if full else set()
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
        else (runs_root.resolve() if runs_root is not None else loaded_profile.profile.runs_root)
    )
    if selected_runs is not None:
        parent = _nearest_existing_parent(selected_runs)
        writable = parent.is_dir() and os.access(parent, os.W_OK)
        checks.append(
            DiagnosticCheck(
                name="runs-root",
                status=(DiagnosticStatus.PASSED if writable else DiagnosticStatus.FAILED),
                message=f"{selected_runs}（最近存在父目录：{parent}）",
            )
        )

    backends = loaded_profile.profile.backends
    for name, runtime in (
        ("protenix-v2", backends.protenix_v2),
        ("pymol-pse", backends.pymol_pse),
        ("scannet-epitope", backends.scannet_epitope),
        (
            "boltzgen-validation",
            backends.boltzgen_validation or backends.boltzgen,
        ),
        ("boltzgen", backends.boltzgen),
        ("tnp", backends.tnp),
    ):
        if runtime is None:
            portable = loaded_profile.portable_profile
            binding_names = {
                "protenix-v2": "protenix_v2",
                "pymol-pse": "pymol_pse",
                "scannet-epitope": "scannet_epitope",
                "boltzgen-validation": "boltzgen",
                "boltzgen": "boltzgen",
                "tnp": "tnp",
            }
            declared = (
                portable is not None
                and getattr(
                    portable.backend_bindings,
                    binding_names[name],
                )
                is not None
            )
            checks.append(
                DiagnosticCheck(
                    name=name,
                    status=(
                        DiagnosticStatus.FAILED
                        if name in required
                        else DiagnosticStatus.NOT_CONFIGURED
                    ),
                    message=(
                        "工作区已声明该 backend，但当前锁版本的环境或必需资产尚未完整可用"
                        if declared
                        else "profile 未声明该 backend"
                    ),
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
                if (
                    loaded is not None
                    and loaded.config.workflow.stop_after_stage < 5
                    and not isinstance(
                        loaded,
                        (LoadedSequenceRunConfig, LoadedRemoteRunConfig),
                    )
                ):
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
            elif name == "scannet-epitope":
                assert isinstance(runtime, ScanNetEpitopeRuntime)
                probe = _scannet_adapter(runtime).probe_runtime()
                message = (
                    f"TensorFlow {probe.tensorflow_version}；device={probe.test_operation_device}"
                )
            elif name in {"boltzgen", "boltzgen-validation"}:
                assert isinstance(runtime, BoltzGenRuntime)
                boltz_probe = _boltzgen_adapter(
                    runtime,
                    require_generation_assets=name == "boltzgen",
                ).probe()
                message = f"BoltzGen {boltz_probe['version']}；commit={boltz_probe['commit']}"
            else:
                assert isinstance(runtime, TnpRuntime)
                tnp_probe = _tnp_adapter(runtime).probe()
                message = f"TNP commit={tnp_probe['commit']}；Python {tnp_probe['python_version']}"
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
    continue_from_run: Path | None = None,
    continue_after_stage: int | None = None,
) -> PipelineExecution:
    """验证后执行当前已实现阶段，或从已验证上游 run 继续。"""

    start_stage = (
        1
        if continue_from_run is None
        else _continuation_start_stage(
            continue_from_run,
            continue_after_stage=continue_after_stage,
        )
    )
    context = _context(
        config_path,
        profile_path=profile_path,
        runs_root=runs_root,
        start_stage=start_stage,
    )
    report = diagnose_runtime(
        profile_path=context.loaded_profile.path,
        config_path=context.loaded_config.config_path,
        runs_root=context.plan.runs_root,
        start_stage=start_stage,
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
    viewer_status: str | None
    if continue_from_run is not None:
        source_manifest, _ = _load_latest_run_manifest(continue_from_run.resolve())
        if run_id is None or run_id == source_manifest.run_id:
            prepared_continuation = continue_run_in_place(
                source_run_root=continue_from_run,
                config_path=loaded.config_path,
                code_identity=code_identity,
                runtime_profile=context.loaded_profile.identity,
                continue_after_stage=continue_after_stage,
            )
        else:
            prepared_continuation = initialize_continuation_run(
                source_run_root=continue_from_run,
                config_path=loaded.config_path,
                runs_root=context.plan.runs_root,
                run_id=run_id,
                code_identity=code_identity,
                runtime_profile=context.loaded_profile.identity,
                copy_through_stage=continue_after_stage,
            )
        run_root = prepared_continuation.workspace.run_root
        run_manifest = prepared_continuation.workspace.run_manifest
        viewer_status = None
    elif isinstance(loaded, LoadedPseRunConfig):
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
        completed_pse = execute_pse_source(prepared_pse, adapter=adapter)
        run_root = completed_pse.prepared.workspace.run_root
        run_manifest = completed_pse.run_manifest
        viewer_status = str(completed_pse.target_viewer.status)
    else:
        prepared_source = initialize_run_workspace(
            config_path=loaded.config_path,
            runs_root=context.plan.runs_root,
            easydesign_version=easydesign.__version__,
            code_identity=code_identity,
            runtime_profile=context.loaded_profile.identity,
            run_id=run_id,
        )
        source_outcome = execute_stage01_source(prepared_source)
        if source_outcome.status == "awaiting-human-approval":
            return PipelineExecution(
                status=source_outcome.status,
                plan=context.plan,
                run_root=source_outcome.run_root,
                run_manifest=source_outcome.run_manifest,
            )
        if source_outcome.status == "prediction-required":
            fallback = source_outcome.prediction_fallback
            assert fallback is not None
            prediction_config = loaded.config.structure_prediction
            assert prediction_config is not None
            from easydesign.backends.structure_prediction import (
                StructurePredictionRequest,
            )

            prediction_request = StructurePredictionRequest(
                job_name=loaded.config.target.target_id,
                target=fallback.target,
                seeds=prediction_config.seeds,
                sample_count=prediction_config.sample_count,
                msa_mode=prediction_config.msa.mode,
                template_mode=prediction_config.template_mode,
                parameter_profile=prediction_config.parameter_profile,
                cycle_count=prediction_config.cycle_count,
                diffusion_step_count=prediction_config.diffusion_step_count,
            )
            derived = LoadedSequenceRunConfig(
                config_path=loaded.config_path,
                config=loaded.config,
                source_path=prepared_source.workspace.input_snapshot,
                detected_format=TargetInputFormat.SEQUENCE,
                target=fallback.target,
                prediction_request=prediction_request,
                msa_execution_plan=prediction_config.msa.resolved_providers(),
                precomputed_msa_path=getattr(
                    loaded,
                    "precomputed_msa_path",
                    None,
                ),
                identity_report=fallback.identity_report,
                scope_report=fallback.scope_report,
                structure_candidates=tuple(fallback.candidates),
                retrieval_records=tuple(fallback.retrieval_records),
                reference_sequence=fallback.reference_sequence,
                prediction_fallback_reason=fallback.reason,
            )
            protenix_runtime = backends.protenix_v2
            assert isinstance(protenix_runtime, ProtenixV2Runtime)
            stage01_protenix_runtime = protenix_runtime
            first_provider = derived.msa_execution_plan[0] if derived.msa_execution_plan else None
            writer = _protenix_adapter(
                stage01_protenix_runtime,
                derived,
                first_provider,
            )
            protenix_input = writer.write_input(
                prediction_request,
                prepared_source.workspace.attempt_root(
                    StageId.TARGET_PREPARATION,
                    "attempt-0001",
                )
                / "inputs"
                / "protenix-input.json",
            )
            prepared_prediction = PreparedSequenceRun(
                loaded_config=derived,
                workspace=prepared_source.workspace,
                protenix_input=protenix_input,
                precomputed_msa=(
                    prepared_source.workspace.run_root / "input-snapshot" / "target-msa.a3m"
                    if derived.precomputed_msa_path is not None
                    else None
                ),
            )

            def remote_adapter_builder(
                provider: ResolvedProtenixMsaProviderConfig | None,
            ) -> ProtenixV2Adapter:
                return _protenix_adapter(
                    stage01_protenix_runtime,
                    derived,
                    provider,
                )

            completed_prediction = execute_sequence_prediction(
                prepared=prepared_prediction,
                adapter_builder=remote_adapter_builder,
                model_checkpoint_sha256=sha256_file(stage01_protenix_runtime.model_checkpoint),
            )
            run_root = completed_prediction.prepared.workspace.run_root
            run_manifest = completed_prediction.run_manifest
            viewer_status = str(completed_prediction.target_viewer.status)
        else:
            run_root = source_outcome.run_root
            run_manifest = source_outcome.run_manifest
            viewer_status = source_outcome.viewer_status

    completed_before_stage02: set[str | None] = set()
    if continue_from_run is not None:
        current_before_stage02, _ = _load_latest_run_manifest(run_root)
        completed_before_stage02 = {
            reference.producer_stage
            for reference in current_before_stage02.stage_manifest_refs
        }
    if (
        context.plan.stop_after_stage >= 2
        and str(StageId.HOTSPOT_DISCOVERY) not in completed_before_stage02
    ):
        stage02_config = loaded.config.stage02
        assert stage02_config is not None
        stage02_adapter: ScanNetEpitopeAdapter | None = None
        if Stage02Method.SCANNET in stage02_config.methods:
            scannet_runtime = backends.scannet_epitope
            assert scannet_runtime is not None
            stage02_adapter = _scannet_adapter(scannet_runtime)
        completed_stage02 = execute_stage02(
            run_root=run_root,
            adapter=stage02_adapter,
        )
        run_manifest = completed_stage02.run_manifest
        completed_manifest = load_model(
            completed_stage02.stage_manifest,
            StageManifest,
        )
        used_user_regions = any(
            reference.artifact_id == "user-provided-regions"
            for reference in completed_manifest.output_artifacts
        )
        user_regions = stage02_config.user_regions if used_user_regions else None
        explicit_user_approval = (
            user_regions is not None and user_regions.approval is not None
        )
        if explicit_user_approval:
            assert user_regions is not None
            assert user_regions.approval is not None
            approve_hotspots_from_initial_config(
                run_root,
                approval=user_regions.approval,
            )
            latest_name = read_last_text_line(run_root / "manifests" / "LATEST")
            run_manifest = run_root / "manifests" / latest_name
            status = "succeeded"
        elif loaded.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
            if used_user_regions:
                raise ConfigurationError(
                    "连续运行的用户区域缺少显式人员批准"
                )
            else:
                approval = stage02_config.unattended_approval
                assert approval is not None
                selected_method = stage02_config.methods[0]
                method = (
                    RegionMethod.SASA_SURFACE_DIVERSITY
                    if selected_method is Stage02Method.SASA
                    else RegionMethod.SCANNET_EPITOPE_NO_MSA
                )
                approve_hotspots_by_policy(
                    run_root,
                    method=method,
                    region_count=approval.region_count,
                    allow_structural_only=approval.allow_structural_only,
                )
            latest_name = read_last_text_line(run_root / "manifests" / "LATEST")
            run_manifest = run_root / "manifests" / latest_name
            status = "succeeded"
        else:
            return PipelineExecution(
                status="awaiting-human-approval",
                plan=context.plan,
                run_root=run_root,
                run_manifest=run_manifest,
                viewer_status=viewer_status,
            )
    elif context.plan.stop_after_stage < 2:
        status = "succeeded"

    current_run, _ = _load_latest_run_manifest(run_root)
    completed_stage_ids = {
        reference.producer_stage for reference in current_run.stage_manifest_refs
    }
    if (
        context.plan.stop_after_stage >= 3
        and str(StageId.BOLTZGEN_CONFIGURATION) not in completed_stage_ids
    ):
        boltzgen_runtime = backends.boltzgen_validation or backends.boltzgen
        assert boltzgen_runtime is not None
        completed_stage03 = execute_stage03(
            run_root=run_root,
            adapter=_boltzgen_adapter(
                boltzgen_runtime,
                require_generation_assets=False,
            ),
        )
        run_manifest = completed_stage03.run_manifest
        status = "succeeded"
    current_run, _ = _load_latest_run_manifest(run_root)
    completed_stage_ids = {
        reference.producer_stage for reference in current_run.stage_manifest_refs
    }
    if (
        context.plan.stop_after_stage >= 4
        and str(StageId.PILOT_GENERATION) not in completed_stage_ids
    ):
        boltzgen_runtime = backends.boltzgen
        assert boltzgen_runtime is not None
        completed_stage04 = execute_stage04(
            run_root=run_root,
            adapter=_boltzgen_generation_adapter(boltzgen_runtime),
        )
        run_manifest = completed_stage04.run_manifest
        status = completed_stage04.status
    current_run, _ = _load_latest_run_manifest(run_root)
    completed_stage_ids = {
        reference.producer_stage for reference in current_run.stage_manifest_refs
    }
    if (
        context.plan.stop_after_stage >= 5
        and str(StageId.PILOT_FILTERING) not in completed_stage_ids
    ):
        boltzgen_runtime = backends.boltzgen
        protenix_runtime = backends.protenix_v2
        stage05_config = loaded.config.stage05
        assert boltzgen_runtime is not None
        assert protenix_runtime is not None
        assert stage05_config is not None
        completed_stage05 = execute_stage05(
            run_root=run_root,
            boltzgen_adapter=_boltzgen_generation_adapter(boltzgen_runtime),
            protenix_adapter_builder=_complex_protenix_adapter_builder(
                protenix_runtime,
                prediction_timeout_seconds=(
                    stage05_config.full_target_prediction.prediction_timeout_seconds
                ),
            ),
        )
        run_manifest = completed_stage05.run_manifest
        status = completed_stage05.status
    current_run, _ = _load_latest_run_manifest(run_root)
    completed_stage_ids = {
        reference.producer_stage for reference in current_run.stage_manifest_refs
    }
    if (
        current_run.status is ExecutionStatus.RUNNING
        and context.plan.stop_after_stage >= 6
        and str(StageId.SCALE_GENERATION_AND_REFOLDING) not in completed_stage_ids
    ):
        boltzgen_runtime = backends.boltzgen
        assert boltzgen_runtime is not None
        completed_stage06 = execute_stage06(
            run_root=run_root,
            adapter=_boltzgen_generation_adapter(boltzgen_runtime),
        )
        run_manifest = completed_stage06.run_manifest
        status = completed_stage06.status
    current_run, _ = _load_latest_run_manifest(run_root)
    completed_stage_ids = {
        reference.producer_stage for reference in current_run.stage_manifest_refs
    }
    if (
        current_run.status is ExecutionStatus.RUNNING
        and context.plan.stop_after_stage >= 7
        and str(StageId.FINAL_FILTERING_AND_SELECTION) not in completed_stage_ids
    ):
        protenix_runtime = backends.protenix_v2
        tnp_runtime = backends.tnp
        stage07_config = loaded.config.stage07
        assert protenix_runtime is not None
        assert tnp_runtime is not None
        assert stage07_config is not None
        completed_stage07 = execute_stage07(
            run_root=run_root,
            protenix_adapter_builder=_complex_protenix_adapter_builder(
                protenix_runtime,
                prediction_timeout_seconds=(
                    stage07_config.full_target_prediction.prediction_timeout_seconds
                ),
            ),
            tnp_adapter=_tnp_adapter(tnp_runtime),
        )
        run_manifest = completed_stage07.run_manifest
        status = completed_stage07.status
    return PipelineExecution(
        status=status,
        plan=context.plan,
        run_root=run_root,
        run_manifest=run_manifest,
        viewer_status=viewer_status,
    )


def resume_pipeline(
    run_root: Path,
    *,
    profile_path: Path | None = None,
) -> Stage04Execution | Stage05Execution | Stage06Execution | Stage07Execution:
    """Resume the current manifest-declared running stage without changing config."""

    root = run_root.expanduser().resolve()
    current, _ = _load_latest_run_manifest(root)
    if current.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("runs resume 只接受 running run")
    resolved, _ = load_resolved_run_config(root)
    completed = {reference.producer_stage for reference in current.stage_manifest_refs}
    if (
        resolved.stop_after_stage >= 4
        and str(StageId.BOLTZGEN_CONFIGURATION) in completed
        and str(StageId.PILOT_GENERATION) not in completed
    ):
        profile = load_runtime_profile(profile_path)
        runtime = profile.profile.backends.boltzgen
        if runtime is None:
            raise ConfigurationError("runtime profile 缺少 BoltzGen backend")
        return execute_stage04(
            run_root=root,
            adapter=_boltzgen_generation_adapter(runtime),
        )
    if (
        resolved.stop_after_stage >= 5
        and str(StageId.PILOT_GENERATION) in completed
        and str(StageId.PILOT_FILTERING) not in completed
    ):
        profile = load_runtime_profile(profile_path)
        boltzgen_runtime = profile.profile.backends.boltzgen
        protenix_runtime = profile.profile.backends.protenix_v2
        config = resolved.user_config.stage05
        if boltzgen_runtime is None or protenix_runtime is None:
            raise ConfigurationError("runtime profile 缺少 Stage 05 所需 BoltzGen/Protenix backend")
        if config is None:
            raise ConfigurationError("resolved config 缺少 Stage 05")
        return execute_stage05(
            run_root=root,
            boltzgen_adapter=_boltzgen_generation_adapter(boltzgen_runtime),
            protenix_adapter_builder=_complex_protenix_adapter_builder(
                protenix_runtime,
                prediction_timeout_seconds=(
                    config.full_target_prediction.prediction_timeout_seconds
                ),
            ),
        )
    if (
        resolved.stop_after_stage >= 6
        and str(StageId.PILOT_FILTERING) in completed
        and str(StageId.SCALE_GENERATION_AND_REFOLDING) not in completed
    ):
        profile = load_runtime_profile(profile_path)
        runtime = profile.profile.backends.boltzgen
        if runtime is None:
            raise ConfigurationError("runtime profile 缺少 Stage 06 BoltzGen backend")
        return execute_stage06(
            run_root=root,
            adapter=_boltzgen_generation_adapter(runtime),
        )
    if (
        resolved.stop_after_stage >= 7
        and str(StageId.SCALE_GENERATION_AND_REFOLDING) in completed
        and str(StageId.FINAL_FILTERING_AND_SELECTION) not in completed
    ):
        profile = load_runtime_profile(profile_path)
        protenix_runtime = profile.profile.backends.protenix_v2
        tnp_runtime = profile.profile.backends.tnp
        stage07_config_resolved = resolved.user_config.stage07
        if protenix_runtime is None or tnp_runtime is None:
            raise ConfigurationError("runtime profile 缺少 Stage 07 所需 Protenix/TNP backend")
        if stage07_config_resolved is None:
            raise ConfigurationError("resolved config 缺少 Stage 07")
        return execute_stage07(
            run_root=root,
            protenix_adapter_builder=_complex_protenix_adapter_builder(
                protenix_runtime,
                prediction_timeout_seconds=(
                    stage07_config_resolved.full_target_prediction.prediction_timeout_seconds
                ),
            ),
            tnp_adapter=_tnp_adapter(tnp_runtime),
        )
    raise ConfigurationError("当前 run 没有可恢复的已实现 Stage")


def read_pipeline_progress(run_root: Path) -> ProgressSnapshot:
    """Read the manifest-declared terminal progress or the expected active stage."""

    root = run_root.expanduser().resolve()
    current, _ = _load_latest_run_manifest(root)
    resolved, _ = load_resolved_run_config(root)
    refs = {item.producer_stage: item for item in current.stage_manifest_refs}
    stage05_id = str(StageId.PILOT_FILTERING)
    stage04_id = str(StageId.PILOT_GENERATION)
    stage06_id = str(StageId.SCALE_GENERATION_AND_REFOLDING)
    stage07_id = str(StageId.FINAL_FILTERING_AND_SELECTION)
    if stage07_id in refs:
        manifest = load_model(refs[stage07_id].verify(root), StageManifest)
        return load_model(
            manifest.require_output("stage07-progress-final").verify(root),
            ProgressSnapshot,
        )
    if (
        current.status is ExecutionStatus.RUNNING
        and resolved.stop_after_stage >= 7
        and stage06_id in refs
    ):
        return load_latest_runtime_model(
            root / stage07_id / "attempt-0001" / "runtime" / "progress.json",
            ProgressSnapshot,
        )
    if stage06_id in refs:
        manifest = load_model(refs[stage06_id].verify(root), StageManifest)
        return load_model(
            manifest.require_output("scale-progress-final").verify(root),
            ProgressSnapshot,
        )
    if (
        current.status is ExecutionStatus.RUNNING
        and resolved.stop_after_stage >= 6
        and stage05_id in refs
    ):
        return load_latest_runtime_model(
            root / stage06_id / "attempt-0001" / "runtime" / "progress.json",
            ProgressSnapshot,
        )
    if stage05_id in refs:
        manifest = load_model(refs[stage05_id].verify(root), StageManifest)
        return load_model(
            manifest.require_output("stage05-progress-final").verify(root),
            ProgressSnapshot,
        )
    if (
        current.status is ExecutionStatus.RUNNING
        and resolved.stop_after_stage >= 5
        and stage04_id in refs
    ):
        return load_latest_runtime_model(
            root / stage05_id / "attempt-0001" / "runtime" / "progress.json",
            ProgressSnapshot,
        )
    if stage04_id in refs:
        manifest = load_model(refs[stage04_id].verify(root), StageManifest)
        return load_model(
            manifest.require_output("pilot-progress-final").verify(root),
            ProgressSnapshot,
        )
    if current.status is ExecutionStatus.RUNNING and resolved.stop_after_stage >= 4:
        return load_latest_runtime_model(
            root / stage04_id / "attempt-0001" / "runtime" / "progress.json",
            ProgressSnapshot,
        )
    raise ManifestStateError("当前 run 没有 Stage 04–07 progress")


def _prepared_existing_run(run_root: Path) -> PreparedRun:
    """从 run 内不可变快照重建 Stage 01 continuation，不读取原项目文件。"""

    root = run_root.resolve()
    resolved, resolved_path = load_resolved_run_config(root)
    source_snapshot = resolved.input_snapshot.verify(root)
    precomputed_msa_snapshot = (
        resolved.precomputed_msa_snapshot.verify(root)
        if resolved.precomputed_msa_snapshot is not None
        else None
    )
    current_run, _ = _load_latest_run_manifest(root)
    config_path = current_run.config_snapshot.verify(root)
    if resolved.detected_input_format in {
        TargetInputFormat.SEQUENCE,
        TargetInputFormat.FASTA,
    }:
        if resolved.target is None or resolved.prediction_request is None:
            raise ManifestStateError("sequence continuation 缺少 resolved target/request")
        loaded: LoadedRunConfig = LoadedSequenceRunConfig(
            config_path=config_path,
            config=resolved.user_config,
            source_path=source_snapshot,
            detected_format=resolved.detected_input_format,
            target=resolved.target,
            prediction_request=resolved.prediction_request,
            msa_execution_plan=resolved.msa_execution_plan,
            precomputed_msa_path=precomputed_msa_snapshot,
        )
    elif resolved.detected_input_format in {
        TargetInputFormat.PDB,
        TargetInputFormat.MMCIF,
    }:
        loaded = LoadedStructureRunConfig(
            config_path=config_path,
            config=resolved.user_config,
            source_path=source_snapshot,
            detected_format=resolved.detected_input_format,
        )
    elif resolved.detected_input_format in {
        TargetInputFormat.PDB_ID,
        TargetInputFormat.UNIPROT,
        TargetInputFormat.UNIPROT_SEARCH,
    }:
        loaded = LoadedRemoteRunConfig(
            config_path=config_path,
            config=resolved.user_config,
            source_path=None,
            detected_format=resolved.detected_input_format,
            precomputed_msa_path=precomputed_msa_snapshot,
        )
    elif resolved.detected_input_format is TargetInputFormat.TARGET_BUNDLE:
        raise ManifestStateError("Target Bundle 导入不会创建 Stage 01 decision gate")
    else:
        raise ManifestStateError(
            f"当前 Stage 01 source 不支持 decision continuation: {resolved.detected_input_format}"
        )
    latest_name = read_last_text_line(root / "manifests" / "LATEST")
    current_manifest = root / "manifests" / latest_name
    workspace = RunWorkspace(
        runs_root=root.parents[1],
        run_root=root,
        project_id=resolved.project_id,
        run_id=resolved.run_id,
        config_snapshot=config_path,
        input_snapshot=source_snapshot,
        resolved_config=resolved_path,
        run_manifest=current_manifest,
        latest_manifest_pointer=root / "manifests" / "LATEST",
    )
    return PreparedRun(loaded_config=loaded, workspace=workspace)


def _next_stage01_attempt(run_root: Path) -> tuple[str, int]:
    stage_root = run_root / str(StageId.TARGET_PREPARATION)
    numbers = []
    for path in stage_root.glob("attempt-*"):
        if path.is_dir() and path.name[8:].isdigit():
            numbers.append(int(path.name[8:]))
    number = max(numbers, default=0) + 1
    return f"attempt-{number:04d}", number


def continue_pipeline_after_decision(
    run_root: Path,
    *,
    decision_record: Path,
    profile_path: Path | None = None,
) -> PipelineExecution:
    """消费已批准 DecisionRecord，在同一 run 中创建新 attempt 并继续。"""

    prepared = _prepared_existing_run(run_root)
    request, record = load_decision_record_context(run_root, decision_record)
    if request.stage_id != str(StageId.TARGET_PREPARATION):
        raise ManifestStateError(
            "当前 continuation 只实现 Stage 01 decision；Stage 02 使用 hotspots approve"
        )
    if len(record.selected_option_ids) != 1:
        raise ManifestStateError("Stage 01 decision 必须且只能选择一个 option")
    option_by_id = {option.option_id: option for option in request.options}
    selected_option = option_by_id[record.selected_option_ids[0]]
    loaded_profile = load_runtime_profile(profile_path)
    attempt_id, attempt_number = _next_stage01_attempt(prepared.workspace.run_root)
    outcome = execute_stage01_source(
        prepared,
        attempt_id=attempt_id,
        approved_option=selected_option,
    )
    plan = RunPlan(
        project_id=prepared.loaded_config.config.project_id,
        target_id=prepared.loaded_config.config.target.target_id,
        detected_input_format=str(prepared.loaded_config.detected_format),
        stop_after_stage=prepared.loaded_config.config.workflow.stop_after_stage,
        required_backends=_required_backends(prepared.loaded_config),
        runs_root=prepared.workspace.runs_root,
        profile_id=loaded_profile.profile.profile_id,
    )
    if outcome.status == "awaiting-human-approval":
        return PipelineExecution(
            status=outcome.status,
            plan=plan,
            run_root=outcome.run_root,
            run_manifest=outcome.run_manifest,
        )

    backends = loaded_profile.profile.backends
    viewer_status = outcome.viewer_status
    if outcome.status == "prediction-required":
        fallback = outcome.prediction_fallback
        assert fallback is not None
        prediction_config = prepared.loaded_config.config.structure_prediction
        assert prediction_config is not None
        from easydesign.backends.structure_prediction import StructurePredictionRequest

        prediction_request = StructurePredictionRequest(
            job_name=prepared.loaded_config.config.target.target_id,
            target=fallback.target,
            seeds=prediction_config.seeds,
            sample_count=prediction_config.sample_count,
            msa_mode=prediction_config.msa.mode,
            template_mode=prediction_config.template_mode,
            parameter_profile=prediction_config.parameter_profile,
            cycle_count=prediction_config.cycle_count,
            diffusion_step_count=prediction_config.diffusion_step_count,
        )
        derived = LoadedSequenceRunConfig(
            config_path=prepared.loaded_config.config_path,
            config=prepared.loaded_config.config,
            source_path=prepared.workspace.input_snapshot,
            detected_format=TargetInputFormat.SEQUENCE,
            target=fallback.target,
            prediction_request=prediction_request,
            msa_execution_plan=prediction_config.msa.resolved_providers(),
            precomputed_msa_path=getattr(
                prepared.loaded_config,
                "precomputed_msa_path",
                None,
            ),
            identity_report=fallback.identity_report,
            scope_report=fallback.scope_report,
            structure_candidates=tuple(fallback.candidates),
            retrieval_records=tuple(fallback.retrieval_records),
            reference_sequence=fallback.reference_sequence,
            prediction_fallback_reason=fallback.reason,
        )
        protenix_runtime = backends.protenix_v2
        if protenix_runtime is None:
            raise ConfigurationError(
                "已批准 Protenix fallback，但 runtime profile 未配置 protenix-v2"
            )
        first_provider = derived.msa_execution_plan[0] if derived.msa_execution_plan else None
        writer = _protenix_adapter(protenix_runtime, derived, first_provider)
        protenix_input = writer.write_input(
            prediction_request,
            prepared.workspace.attempt_root(
                StageId.TARGET_PREPARATION,
                attempt_id,
            )
            / "inputs"
            / "protenix-input.json",
        )
        prepared_prediction = PreparedSequenceRun(
            loaded_config=derived,
            workspace=prepared.workspace,
            protenix_input=protenix_input,
            precomputed_msa=(
                prepared.workspace.run_root / "input-snapshot" / "target-msa.a3m"
                if derived.precomputed_msa_path is not None
                else None
            ),
        )

        def adapter_builder(
            provider: ResolvedProtenixMsaProviderConfig | None,
        ) -> ProtenixV2Adapter:
            return _protenix_adapter(protenix_runtime, derived, provider)

        completed = execute_sequence_prediction(
            prepared=prepared_prediction,
            adapter_builder=adapter_builder,
            model_checkpoint_sha256=sha256_file(protenix_runtime.model_checkpoint),
            attempt_start=attempt_number,
        )
        current_run_manifest = completed.run_manifest
        viewer_status = str(completed.target_viewer.status)
    else:
        current_run_manifest = outcome.run_manifest

    if prepared.loaded_config.config.workflow.stop_after_stage == 2:
        stage02_config = prepared.loaded_config.config.stage02
        assert stage02_config is not None
        stage02_adapter: ScanNetEpitopeAdapter | None = None
        if Stage02Method.SCANNET in stage02_config.methods:
            scannet_runtime = backends.scannet_epitope
            if scannet_runtime is None:
                raise ConfigurationError(
                    "Stage 02 选择 ScanNet，但 runtime profile 未配置 scannet-epitope"
                )
            stage02_adapter = _scannet_adapter(scannet_runtime)
        completed_stage02 = execute_stage02(
            run_root=prepared.workspace.run_root,
            adapter=stage02_adapter,
        )
        current_run_manifest = completed_stage02.run_manifest
        completed_manifest = load_model(
            completed_stage02.stage_manifest,
            StageManifest,
        )
        used_user_regions = any(
            reference.artifact_id == "user-provided-regions"
            for reference in completed_manifest.output_artifacts
        )
        user_regions = stage02_config.user_regions if used_user_regions else None
        explicit_user_approval = (
            user_regions is not None and user_regions.approval is not None
        )
        if explicit_user_approval:
            assert user_regions is not None
            assert user_regions.approval is not None
            approve_hotspots_from_initial_config(
                prepared.workspace.run_root,
                approval=user_regions.approval,
            )
            latest_name = read_last_text_line(
                prepared.workspace.run_root / "manifests" / "LATEST"
            )
            current_run_manifest = (
                prepared.workspace.run_root / "manifests" / latest_name
            )
            status = "succeeded"
        elif (
            prepared.loaded_config.config.workflow.execution_mode
            is ExecutionMode.UNATTENDED
        ):
            if used_user_regions:
                raise ConfigurationError(
                    "连续运行的用户区域缺少显式人员批准"
                )
            else:
                approval = stage02_config.unattended_approval
                assert approval is not None
                selected_method = stage02_config.methods[0]
                method = (
                    RegionMethod.SASA_SURFACE_DIVERSITY
                    if selected_method is Stage02Method.SASA
                    else RegionMethod.SCANNET_EPITOPE_NO_MSA
                )
                approve_hotspots_by_policy(
                    prepared.workspace.run_root,
                    method=method,
                    region_count=approval.region_count,
                    allow_structural_only=approval.allow_structural_only,
                )
            latest_name = read_last_text_line(
                prepared.workspace.run_root / "manifests" / "LATEST"
            )
            current_run_manifest = prepared.workspace.run_root / "manifests" / latest_name
            status = "succeeded"
        else:
            status = "awaiting-human-approval"
    else:
        status = "succeeded"
    return PipelineExecution(
        status=status,
        plan=plan,
        run_root=prepared.workspace.run_root,
        run_manifest=current_run_manifest,
        viewer_status=viewer_status,
    )


def _resolve_run_from_index(runs_root: Path, selector: str) -> Path:
    index_path = runs_root / "run-index.json"
    if not index_path.is_file():
        raise ManifestStateError(f"run-index 不存在: {index_path}")
    index = load_latest_runtime_model(index_path, RunIndex)
    matches = [
        entry
        for entry in index.entries
        if entry.category == "project-run" and (entry.run_id == selector or entry.path == selector)
    ]
    if not matches:
        raise ManifestStateError(f"run-index 没有匹配 run: {selector}")
    if len(matches) > 1:
        raise ManifestStateError(f"run_id={selector} 在多个项目中重复，请使用 project_id/run_id")
    return (runs_root / matches[0].path).resolve()


def show_run(runs_root: Path, selector: str) -> RunSummary:
    """只通过 index 和 manifest 返回 run 摘要，并验证所有当前正式引用。"""

    root = runs_root.resolve()
    run_root = _resolve_run_from_index(root, selector)
    latest_pointer = run_root / "manifests" / "LATEST"
    try:
        latest_name = read_last_text_line(latest_pointer)
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
    index = load_latest_runtime_model(index_path, RunIndex)
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
