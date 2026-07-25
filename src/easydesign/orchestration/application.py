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
from easydesign.backends.hotspot import ScanNetBackendConfig, ScanNetEpitopeAdapter
from easydesign.backends.structure_prediction import ProtenixV2Adapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.core import (
    BackendContractError,
    ConfigurationError,
    EasyDesignError,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageId,
    StageManifest,
    load_model,
    resolve_code_identity,
    sha256_file,
)
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
    load_runtime_profile,
    resolve_runtime_profile_path,
)
from .sequence_prediction import execute_sequence_prediction
from .stage01_handlers import execute_pse_source
from .stage01_sources import execute_stage01_source
from .stage02 import execute_stage02
from .stage03 import execute_stage03, initialize_continuation_run
from .stage04 import Stage04Execution, execute_stage04
from .workspace import (
    PreparedRun,
    PreparedSequenceRun,
    PseRequestWriter,
    ResolvedRunConfig,
    RunIndex,
    RunWorkspace,
    initialize_pse_run,
    initialize_run_workspace,
)

PROTENIX_V2_CHECKPOINT_SHA256 = "8f931f9774a396b67033d0e58628e1834f4a1448165e04254b40a780b0c0d599"
IMPLEMENTED_STAGE_MAX = 4


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
        name = pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 run LATEST: {pointer}") from error
    path = root / "manifests" / name
    return load_model(path, RunManifest), path


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


def _required_backends(loaded: LoadedRunConfig) -> tuple[str, ...]:
    backends: list[str] = []
    if isinstance(loaded, LoadedSequenceRunConfig):
        backends.append("protenix-v2")
    elif isinstance(loaded, LoadedPseRunConfig):
        backends.append("pymol-pse")
    elif (
        isinstance(loaded, LoadedRemoteRunConfig) and loaded.config.structure_prediction is not None
    ):
        backends.append("protenix-v2")
    if loaded.config.workflow.stop_after_stage >= 2:
        stage02 = loaded.config.stage02
        assert stage02 is not None
        if Stage02Method.SCANNET in stage02.methods:
            backends.append("scannet-epitope")
    if loaded.config.workflow.stop_after_stage >= 3:
        backends.append("boltzgen")
    if loaded.config.workflow.stop_after_stage >= 5 and "protenix-v2" not in backends:
        backends.append("protenix-v2")
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
    if stop_after > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(
            "Developer Preview 当前最高实现到 "
            f"Stage {IMPLEMENTED_STAGE_MAX:02d}: stop_after_stage={stop_after}"
        )
    selected_profile_path = resolve_runtime_profile_path(profile_path)
    profile = (
        load_runtime_profile(selected_profile_path).profile
        if selected_profile_path.is_file()
        else RuntimeProfile(profile_id="unconfigured")
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


def _boltzgen_adapter(runtime: BoltzGenRuntime) -> BoltzGenCheckAdapter:
    return BoltzGenCheckAdapter(
        executable=runtime.executable,
        repository_root=runtime.repository_root,
        cache_root=runtime.cache_root,
        timeout_seconds=runtime.timeout_seconds,
        validation_workers=runtime.validation_workers,
        offline_mode=runtime.offline_mode,
    )


def _boltzgen_generation_adapter(
    runtime: BoltzGenRuntime,
) -> BoltzGenGenerationAdapter:
    return BoltzGenGenerationAdapter(
        check_adapter=_boltzgen_adapter(runtime),
        generation_timeout_seconds=runtime.generation_timeout_seconds,
        data_loader_workers=runtime.data_loader_workers,
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
    if loaded is not None and loaded.config.workflow.stop_after_stage > IMPLEMENTED_STAGE_MAX:
        raise ConfigurationError(
            f"Developer Preview 当前最高实现到 Stage {IMPLEMENTED_STAGE_MAX:02d}"
        )
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
        ("boltzgen", backends.boltzgen),
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
                if loaded is not None and not isinstance(
                    loaded,
                    (LoadedSequenceRunConfig, LoadedRemoteRunConfig),
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
            else:
                assert isinstance(runtime, BoltzGenRuntime)
                boltz_probe = _boltzgen_adapter(runtime).probe()
                message = f"BoltzGen {boltz_probe['version']}；commit={boltz_probe['commit']}"
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
) -> PipelineExecution:
    """验证后执行当前已实现阶段，或从已验证上游 run 继续。"""

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
    viewer_status: str | None
    if continue_from_run is not None:
        if context.plan.stop_after_stage < 3:
            raise ConfigurationError("--from-run 只用于继续 Stage 03 及后续阶段")
        if run_id is None:
            raise ConfigurationError("--from-run 必须显式提供 --run-id")
        prepared_continuation = initialize_continuation_run(
            source_run_root=continue_from_run,
            config_path=loaded.config_path,
            runs_root=context.plan.runs_root,
            run_id=run_id,
            code_identity=code_identity,
            runtime_profile=context.loaded_profile.identity,
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
            assert protenix_runtime is not None
            first_provider = derived.msa_execution_plan[0] if derived.msa_execution_plan else None
            writer = _protenix_adapter(protenix_runtime, derived, first_provider)
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
                return _protenix_adapter(protenix_runtime, derived, provider)

            completed_prediction = execute_sequence_prediction(
                prepared=prepared_prediction,
                adapter_builder=remote_adapter_builder,
                model_checkpoint_sha256=sha256_file(protenix_runtime.model_checkpoint),
            )
            run_root = completed_prediction.prepared.workspace.run_root
            run_manifest = completed_prediction.run_manifest
            viewer_status = str(completed_prediction.target_viewer.status)
        else:
            run_root = source_outcome.run_root
            run_manifest = source_outcome.run_manifest
            viewer_status = source_outcome.viewer_status

    if continue_from_run is None and context.plan.stop_after_stage >= 2:
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
        if loaded.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
            completed_manifest = load_model(
                completed_stage02.stage_manifest,
                StageManifest,
            )
            used_user_regions = any(
                reference.artifact_id == "user-provided-regions"
                for reference in completed_manifest.output_artifacts
            )
            if used_user_regions:
                user_regions = stage02_config.user_regions
                assert user_regions is not None
                assert user_regions.approval is not None
                approve_hotspots_from_initial_config(
                    run_root,
                    approval=user_regions.approval,
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
            latest_name = (run_root / "manifests" / "LATEST").read_text(encoding="utf-8").strip()
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
        boltzgen_runtime = backends.boltzgen
        assert boltzgen_runtime is not None
        completed_stage03 = execute_stage03(
            run_root=run_root,
            adapter=_boltzgen_adapter(boltzgen_runtime),
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
) -> Stage04Execution:
    """Resume the current manifest-declared running stage without changing config."""

    root = run_root.expanduser().resolve()
    current, _ = _load_latest_run_manifest(root)
    if current.status is not ExecutionStatus.RUNNING:
        raise ManifestStateError("runs resume 只接受 running run")
    resolved = load_model(
        root / "config-snapshot" / "resolved-config.json",
        ResolvedRunConfig,
    )
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
    raise ConfigurationError("当前 run 没有可恢复的已实现 Stage")


def _prepared_existing_run(run_root: Path) -> PreparedRun:
    """从 run 内不可变快照重建 Stage 01 continuation，不读取原项目文件。"""

    root = run_root.resolve()
    resolved_path = root / "config-snapshot" / "resolved-config.json"
    resolved = load_model(resolved_path, ResolvedRunConfig)
    source_snapshot = resolved.input_snapshot.verify(root)
    config_path = root / "config-snapshot" / "easydesign.yaml"
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
        )
    elif resolved.detected_input_format is TargetInputFormat.TARGET_BUNDLE:
        raise ManifestStateError("Target Bundle 导入不会创建 Stage 01 decision gate")
    else:
        raise ManifestStateError(
            f"当前 Stage 01 source 不支持 decision continuation: {resolved.detected_input_format}"
        )
    latest_name = (root / "manifests" / "LATEST").read_text(encoding="utf-8").strip()
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
        if prepared.loaded_config.config.workflow.execution_mode is ExecutionMode.UNATTENDED:
            completed_manifest = load_model(
                completed_stage02.stage_manifest,
                StageManifest,
            )
            used_user_regions = any(
                reference.artifact_id == "user-provided-regions"
                for reference in completed_manifest.output_artifacts
            )
            if used_user_regions:
                user_regions = stage02_config.user_regions
                assert user_regions is not None
                assert user_regions.approval is not None
                approve_hotspots_from_initial_config(
                    prepared.workspace.run_root,
                    approval=user_regions.approval,
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
            latest_name = (
                (prepared.workspace.run_root / "manifests" / "LATEST")
                .read_text(encoding="utf-8")
                .strip()
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
    index = load_model(index_path, RunIndex)
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
