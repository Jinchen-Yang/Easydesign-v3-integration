"""Stage 01 sequence/FASTA remote-MSA、Protenix 预测与 Target Bundle 发布。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from easydesign.backends.structure_prediction import (
    BackendInvocation,
    MsaMode,
    OpenFold3Af3JaxAdapter,
    PredictionParameterProfile,
    ProtenixV2Adapter,
)
from easydesign.core import (
    ArtifactRef,
    Attempt,
    EasyDesignError,
    ErrorInfo,
    ExecutionStatus,
    ManifestStateError,
    MsaSourceReceipt,
    RunManifest,
    StageId,
    StageManifest,
    dump_model,
    load_model,
    sha256_file,
)
from easydesign.reporting import (
    TargetViewerOutcome,
    generate_stage01_target_viewer_nonblocking,
)
from easydesign.safe_writes import append_pointer_revision, read_last_text_line
from easydesign.stages.s01_target_preparation import (
    BuiltTargetBundle,
    build_predicted_target_bundle,
)
from easydesign.workspace_context import WorkspaceContext

from .config import (
    CacheMode,
    RemoteProtenixMsaConfig,
    ResolvedProtenixMsaProviderConfig,
)
from .workspace import (
    PreparedSequenceRun,
    ResolvedRunConfig,
    RunIndexEntry,
    upsert_run_index_entries,
)

AdapterBuilder = Callable[
    [ResolvedProtenixMsaProviderConfig | None],
    ProtenixV2Adapter | OpenFold3Af3JaxAdapter,
]
PredictionAdapter = ProtenixV2Adapter | OpenFold3Af3JaxAdapter


class SequencePredictionExecutionError(RuntimeError):
    """Stage 01 sequence 执行失败，manifest 证据已尽可能保留。"""


class _InvocationFailure(SequencePredictionExecutionError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        retryable: bool,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True, slots=True)
class _MsaEvidence:
    updated_input: Path
    source_a3m: Path | None
    published_a3m: Path | None
    published_receipt: Path | None
    sha256: str | None
    depth: int | None
    cache_status: str


def _a3m_query_and_depth(path: Path) -> tuple[str, int]:
    """解析可换行 A3M；首条 query 必须由调用方逐位验证。"""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise _InvocationFailure(
            f"MSA A3M 无法读取: {path}",
            error_code="msa-output-invalid",
            retryable=False,
        ) from error
    records: list[str] = []
    current: list[str] | None = None
    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            current = []
            records.append("")
            continue
        if current is None:
            raise _InvocationFailure(
                f"MSA A3M 在首个 header 前出现序列: line={line_number}",
                error_code="msa-output-invalid",
                retryable=False,
            )
        if any(not (character.isalpha() or character in "-.*") for character in line):
            raise _InvocationFailure(
                f"MSA A3M 含非法字符: line={line_number}",
                error_code="msa-output-invalid",
                retryable=False,
            )
        current.append(line)
        records[-1] = "".join(current)
    if not records or not records[0]:
        raise _InvocationFailure(
            "MSA A3M 缺少 query record",
            error_code="msa-output-invalid",
            retryable=False,
        )
    if any(not record for record in records):
        raise _InvocationFailure(
            "MSA A3M 包含空 sequence record",
            error_code="msa-output-invalid",
            retryable=False,
        )
    if len(records) < 2:
        raise _InvocationFailure(
            f"MSA 只有 query，没有同源序列: depth={len(records)}",
            error_code="msa-insufficient-depth",
            retryable=False,
        )
    return records[0], len(records)


def _validated_a3m(
    *,
    source: Path,
    expected_query: str,
) -> tuple[str, int]:
    query, depth = _a3m_query_and_depth(source)
    if query != expected_query:
        raise _InvocationFailure(
            "MSA A3M query 与规范 target 序列不一致",
            error_code="msa-query-mismatch",
            retryable=False,
        )
    return sha256_file(source), depth


def _publish_explicit_msa(
    *,
    prepared: PreparedSequenceRun,
    adapter: PredictionAdapter,
    input_json: Path,
    attempt_root: Path,
    source: Path,
    cache_status: str,
) -> _MsaEvidence:
    sha256, depth = _validated_a3m(
        source=source,
        expected_query=prepared.loaded_config.target.sequence,
    )
    published = _exclusive_copy(
        source,
        attempt_root / "artifacts" / "target-msa.a3m",
    )
    updated = adapter.prepare_precomputed_msa_input(
        input_json=input_json,
        msa_path=published,
    )
    return _MsaEvidence(
        updated_input=updated,
        source_a3m=source,
        published_a3m=published,
        published_receipt=None,
        sha256=sha256,
        depth=depth,
        cache_status=cache_status,
    )


def _msa_cache_paths(
    *,
    sequence_sha256: str,
    provider: ResolvedProtenixMsaProviderConfig,
) -> tuple[Path, Path]:
    identity = json.dumps(
        {
            "schema_version": "0.1",
            "sequence_sha256": sequence_sha256,
            "provider": str(provider.provider),
            "server_mode": provider.server_mode,
            "endpoint_sha256": hashlib.sha256(provider.endpoint.encode()).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    key = hashlib.sha256(identity).hexdigest()
    root = WorkspaceContext.discover().msa_cache_root / sequence_sha256 / key
    return root / "target.a3m", root / "manifest.json"


def _load_msa_cache(
    *,
    prepared: PreparedSequenceRun,
    provider: ResolvedProtenixMsaProviderConfig,
) -> Path | None:
    a3m, manifest_path = _msa_cache_paths(
        sequence_sha256=prepared.loaded_config.target.sequence_sha256,
        provider=provider,
    )
    cache_root = a3m.parent
    pointer = cache_root / "CURRENT"
    if pointer.is_file():
        try:
            revision = (cache_root / read_last_text_line(pointer)).resolve()
            revision.relative_to(cache_root.resolve())
        except (OSError, ValueError):
            return None
        a3m = revision / "target.a3m"
        manifest_path = revision / "manifest.json"
    if not a3m.is_file() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        "query_sequence_sha256": prepared.loaded_config.target.sequence_sha256,
        "a3m_sha256": sha256_file(a3m),
        "provider": str(provider.provider),
        "server_mode": provider.server_mode,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        return None
    _validated_a3m(
        source=a3m,
        expected_query=prepared.loaded_config.target.sequence,
    )
    return a3m


def _store_msa_cache(
    *,
    prepared: PreparedSequenceRun,
    provider: ResolvedProtenixMsaProviderConfig,
    evidence: _MsaEvidence,
) -> None:
    if (
        evidence.sha256 is None
        or evidence.depth is None
        or evidence.published_a3m is None
    ):
        raise ManifestStateError("remote MSA cache 不能保存空 evidence")
    legacy_a3m, _legacy_manifest = _msa_cache_paths(
        sequence_sha256=prepared.loaded_config.target.sequence_sha256,
        provider=provider,
    )
    cache_root = legacy_a3m.parent
    revisions = cache_root / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    revision_id = (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        + f"-{evidence.sha256[:12]}"
    )
    revision = revisions / revision_id
    revision.mkdir()
    a3m = revision / "target.a3m"
    manifest_path = revision / "manifest.json"
    _exclusive_copy(evidence.published_a3m, a3m)
    _exclusive_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "query_sequence_sha256": prepared.loaded_config.target.sequence_sha256,
                "a3m_sha256": evidence.sha256,
                "depth": evidence.depth,
                "provider": str(provider.provider),
                "server_mode": provider.server_mode,
                "endpoint_sha256": hashlib.sha256(
                    provider.endpoint.encode()
                ).hexdigest(),
                "generated_at": datetime.now(UTC).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        manifest_path,
    )
    _atomic_pointer(
        revision.relative_to(cache_root).as_posix(),
        cache_root / "CURRENT",
    )


@dataclass(frozen=True, slots=True)
class CompletedSequenceRun:
    prepared: PreparedSequenceRun
    built_bundle: BuiltTargetBundle
    msa_artifact: ArtifactRef | None
    attempt_manifests: tuple[Path, ...]
    stage_manifest: Path
    run_manifest: Path
    target_viewer: TargetViewerOutcome


def _strictly_later(candidate: datetime, previous: datetime) -> datetime:
    return candidate if candidate > previous else previous + timedelta(microseconds=1)


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _exclusive_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _exclusive_copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_handle, destination.open("xb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle)
    return destination


def _atomic_pointer(text: str, path: Path) -> None:
    append_pointer_revision(path, text)


def _artifact(
    *,
    run_root: Path,
    path: Path,
    artifact_id: str,
    role: str,
    file_format: str,
    attempt_id: str,
) -> ArtifactRef:
    return ArtifactRef.from_file(
        run_root=run_root,
        relative_path=path.relative_to(run_root).as_posix(),
        artifact_id=artifact_id,
        role=role,
        file_format=file_format,
        producer_stage=str(StageId.TARGET_PREPARATION),
        producer_attempt=attempt_id,
    )


def _run_invocation(
    invocation: BackendInvocation,
    *,
    error_code: str,
    retryable: bool,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(dict(invocation.environment))
    try:
        completed = subprocess.run(
            list(invocation.argv),
            check=False,
            capture_output=True,
            text=True,
            env=environment,
            timeout=invocation.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise _InvocationFailure(
            f"Backend 调用超时: timeout={invocation.timeout_seconds}, argv={invocation.argv[:2]}",
            error_code=f"{error_code}-timeout",
            retryable=retryable,
            stdout=_subprocess_text(error.stdout),
            stderr=_subprocess_text(error.stderr),
        ) from error
    if completed.returncode != 0:
        raise _InvocationFailure(
            f"Backend 调用失败: returncode={completed.returncode}, argv={invocation.argv[:2]}",
            error_code=error_code,
            retryable=retryable,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    return completed


def _validate_and_publish_msa(
    *,
    prepared: PreparedSequenceRun,
    adapter: PredictionAdapter,
    attempt_root: Path,
    msa_output_dir: Path,
) -> _MsaEvidence:
    input_json = attempt_root / "inputs" / "protenix-input.json"
    try:
        updated, source = adapter.remote_msa_artifacts(
            input_json=input_json,
            msa_output_dir=msa_output_dir,
        )
    except EasyDesignError as error:
        raise _InvocationFailure(
            str(error),
            error_code="remote-msa-output-invalid",
            retryable=True,
        ) from error
    try:
        _, depth = _validated_a3m(
            source=source,
            expected_query=prepared.loaded_config.target.sequence,
        )
    except _InvocationFailure as error:
        raise _InvocationFailure(
            str(error),
            error_code=f"remote-{error.error_code}",
            retryable=error.error_code != "msa-query-mismatch",
        ) from error
    published = _exclusive_copy(
        source,
        attempt_root / "artifacts" / "target-msa.a3m",
    )
    published_receipt: Path | None = None
    if isinstance(adapter, OpenFold3Af3JaxAdapter):
        receipt_source = adapter.remote_msa_receipt_path(input_json, msa_output_dir)
        published_receipt = _exclusive_copy(
            receipt_source,
            attempt_root / "artifacts" / "remote-msa-receipt.json",
        )
    return _MsaEvidence(
        updated_input=updated,
        source_a3m=source,
        published_a3m=published,
        published_receipt=published_receipt,
        sha256=sha256_file(published),
        depth=depth,
        cache_status="remote-refresh",
    )


def _write_logs(
    *,
    run_root: Path,
    attempt_root: Path,
    attempt_id: str,
    logs: dict[str, str],
) -> tuple[ArtifactRef, ...]:
    references: list[ArtifactRef] = []
    for name in sorted(logs):
        path = _exclusive_text(logs[name], attempt_root / "logs" / f"{name}.log")
        references.append(
            _artifact(
                run_root=run_root,
                path=path,
                artifact_id=f"{name}-log",
                role="backend-log",
                file_format="text",
                attempt_id=attempt_id,
            )
        )
    return tuple(references)


def _publish_run_revision(
    *,
    prepared: PreparedSequenceRun,
    stage_manifest_path: Path,
    attempt_id: str,
    ended_at: datetime,
    succeeded: bool,
) -> Path:
    workspace = prepared.workspace
    current = load_model(workspace.run_manifest, RunManifest)
    stage_ref = _artifact(
        run_root=workspace.run_root,
        path=stage_manifest_path,
        artifact_id="stage-01-manifest",
        role="stage-manifest",
        file_format="json",
        attempt_id=attempt_id,
    )
    updated = _strictly_later(ended_at, current.updated_at)
    stop_after_stage = prepared.loaded_config.config.workflow.stop_after_stage
    if not succeeded:
        status = ExecutionStatus.FAILED
        completed_at: datetime | None = updated
    elif stop_after_stage == 1:
        status = ExecutionStatus.SUCCEEDED
        completed_at = updated
    else:
        status = ExecutionStatus.RUNNING
        completed_at = None
    next_manifest = current.next_revision(
        updated_at=updated,
        status=status,
        completed_at=completed_at,
        stage_manifest_refs=(stage_ref,),
        clear_workflow_state=True,
    )
    path = (
        workspace.run_root
        / "manifests"
        / f"run-manifest.v{next_manifest.revision:04d}.json"
    )
    dump_model(next_manifest, path)
    _atomic_pointer(f"{path.name}\n", workspace.latest_manifest_pointer)
    upsert_run_index_entries(
        workspace.runs_root,
        (
            RunIndexEntry(
                category="project-run",
                path=workspace.run_root.relative_to(workspace.runs_root).as_posix(),
                layout_version="1",
                status=str(status),
                project_id=workspace.project_id,
                run_id=workspace.run_id,
                notes=((
                    "Stage 01 MSA-backed sequence target published."
                    if succeeded
                    else "Stage 01 MSA-backed sequence target failed; evidence retained."
                ),),
            ),
        ),
        generated_at=updated,
    )
    return path


def execute_sequence_prediction(
    *,
    prepared: PreparedSequenceRun,
    adapter_builder: AdapterBuilder,
    model_checkpoint_sha256: str,
    attempt_start: int = 1,
    started_at: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> CompletedSequenceRun:
    """按 YAML provider 顺序执行 MSA 和单结构预测，并发布完整 Stage 01 交接。"""

    workspace = prepared.workspace
    resolved_config = load_model(workspace.resolved_config, ResolvedRunConfig)
    msa_source_receipt: MsaSourceReceipt | None = None
    if resolved_config.precomputed_msa_source_snapshot is not None:
        msa_source_receipt = load_model(
            resolved_config.precomputed_msa_source_snapshot.verify(workspace.run_root),
            MsaSourceReceipt,
        )
    request = prepared.loaded_config.prediction_request
    prediction_config = prepared.loaded_config.config.structure_prediction
    if prediction_config is None or request is None:
        raise SequencePredictionExecutionError(
            "sequence prediction 需要已冻结的显式 Stage 1 后端选择"
        )
    remote_msa_config = next(
        (
            item
            for item in (
                prediction_config.target_msa,
                prediction_config.target_paired_msa,
            )
            if isinstance(item, RemoteProtenixMsaConfig)
        ),
        None,
    )
    unpaired_mode = request.resolved_target_unpaired_msa_mode
    paired_mode = request.resolved_target_paired_msa_mode
    paired_msa_input_sha256: str | None = None
    if paired_mode is MsaMode.PRECOMPUTED:
        paired_path = request.target_paired_msa_path
        if paired_path is None:
            raise SequencePredictionExecutionError(
                "Stage 1 precomputed paired MSA path 缺失"
            )
        paired_msa_input_sha256, _ = _validated_a3m(
            source=paired_path,
            expected_query=prepared.loaded_config.target.sequence,
        )
    elif paired_mode is MsaMode.QUERY_ONLY:
        paired_msa_input_sha256 = hashlib.sha256(
            f">query\n{prepared.loaded_config.target.sequence}\n".encode()
        ).hexdigest()
    start = datetime.now(UTC) if started_at is None else started_at
    attempts: list[Attempt] = []
    attempt_paths: list[Path] = []
    built: BuiltTargetBundle | None = None
    selected_msa_ref: ArtifactRef | None = None
    selected_msa_receipt_ref: ArtifactRef | None = None
    selected_provider: ResolvedProtenixMsaProviderConfig | None = None
    failure: _InvocationFailure | None = None
    selected_attempt_id: str | None = None
    if attempt_start < 1:
        raise SequencePredictionExecutionError("attempt_start 必须至少为 1")
    attempt_number = attempt_start - 1
    execution_count = 0
    execution_plan: tuple[ResolvedProtenixMsaProviderConfig | None, ...] = (
        tuple(prepared.loaded_config.msa_execution_plan)
        if request.has_remote_msa
        else (None,)
    )
    if not execution_plan:
        raise SequencePredictionExecutionError("remote MSA execution plan 不能为空")

    for provider_index, provider in enumerate(execution_plan):
        provider_max_attempts = provider.max_attempts if provider is not None else 1
        for provider_attempt in range(provider_max_attempts):
            execution_count += 1
            attempt_number += 1
            attempt_id = f"attempt-{attempt_number:04d}"
            attempt_root = workspace.attempt_root(
                StageId.TARGET_PREPARATION,
                attempt_id,
            )
            input_json = attempt_root / "inputs" / "protenix-input.json"
            adapter = adapter_builder(provider)
            if adapter.prediction_timeout_seconds != prediction_config.prediction_timeout_seconds:
                raise SequencePredictionExecutionError(
                    "adapter_builder 返回的 prediction timeout 与 resolved config 不一致"
                )
            if provider is not None and (
                adapter.remote_msa_provider != provider.provider
                or adapter.remote_msa_endpoint != provider.endpoint
                or adapter.remote_msa_server_mode != provider.server_mode
                or adapter.remote_msa_timeout_seconds != provider.timeout_seconds
            ):
                raise SequencePredictionExecutionError(
                    "adapter_builder 返回的 provider/endpoint/mode/timeout 与 resolved plan 不一致"
                )
            if execution_count == 1:
                if input_json != prepared.protenix_input or not input_json.is_file():
                    raise SequencePredictionExecutionError(
                        f"{attempt_id} Protenix input 与 workspace 不一致"
                    )
            else:
                adapter.write_input(request, input_json)
            attempt_started = _strictly_later(datetime.now(UTC), start)
            logs: dict[str, str] = {}
            current_failure: _InvocationFailure | None = None
            msa_evidence: _MsaEvidence | None = None
            try:
                version = _run_invocation(
                    adapter.version_invocation(),
                    error_code="structure-backend-version-probe-failed",
                    retryable=False,
                )
                logs["version-stdout"] = version.stdout
                logs["version-stderr"] = version.stderr
                adapter.validate_version_output(version.stdout)

                working_input = input_json
                if provider is not None:
                    assert remote_msa_config is not None
                    cached = (
                        _load_msa_cache(prepared=prepared, provider=provider)
                        if unpaired_mode is MsaMode.REMOTE
                        and paired_mode is not MsaMode.REMOTE
                        and remote_msa_config.cache_mode
                        in {CacheMode.PREFER_CACHE, CacheMode.OFFLINE}
                        else None
                    )
                    if cached is not None:
                        msa_evidence = _publish_explicit_msa(
                            prepared=prepared,
                            adapter=adapter,
                            input_json=input_json,
                            attempt_root=attempt_root,
                            source=cached,
                            cache_status="cache-hit",
                        )
                        working_input = msa_evidence.updated_input
                        logs["msa-source"] = "validated sequence-hash cache hit\n"
                    elif (
                        unpaired_mode is MsaMode.REMOTE
                        and paired_mode is not MsaMode.REMOTE
                        and remote_msa_config.cache_mode is CacheMode.OFFLINE
                    ):
                        raise _InvocationFailure(
                            "offline MSA cache miss",
                            error_code="msa-cache-miss",
                            retryable=False,
                        )
                    else:
                        msa_output = attempt_root / "work" / "msa"
                        msa = _run_invocation(
                            adapter.msa_invocation(
                                request,
                                input_json=input_json,
                                output_dir=msa_output,
                            ),
                            error_code="remote-msa-failed",
                            retryable=True,
                        )
                        logs["msa-stdout"] = msa.stdout
                        logs["msa-stderr"] = msa.stderr
                        if unpaired_mode is MsaMode.REMOTE:
                            msa_evidence = _validate_and_publish_msa(
                                prepared=prepared,
                                adapter=adapter,
                                attempt_root=attempt_root,
                                msa_output_dir=msa_output,
                            )
                            working_input = msa_evidence.updated_input
                            if paired_mode is not MsaMode.REMOTE:
                                _store_msa_cache(
                                    prepared=prepared,
                                    provider=provider,
                                    evidence=msa_evidence,
                                )
                        else:
                            working_input = adapter.updated_msa_input_path(
                                input_json,
                                msa_output,
                            )
                            if not working_input.is_file():
                                raise _InvocationFailure(
                                    "paired remote MSA 未发布 updated input",
                                    error_code="remote-msa-output-invalid",
                                    retryable=True,
                                )

                if unpaired_mode is MsaMode.PRECOMPUTED:
                    if prepared.precomputed_msa is None:
                        raise _InvocationFailure(
                            "precomputed MSA snapshot 缺失",
                            error_code="precomputed-msa-missing",
                            retryable=False,
                        )
                    msa_evidence = _publish_explicit_msa(
                        prepared=prepared,
                        adapter=adapter,
                        input_json=working_input,
                        attempt_root=attempt_root,
                        source=prepared.precomputed_msa,
                        cache_status="precomputed",
                    )
                    logs["msa-source"] = "precomputed A3M validated\n"
                elif unpaired_mode is MsaMode.QUERY_ONLY:
                    query_only = _exclusive_text(
                        f">query\n{prepared.loaded_config.target.sequence}\n",
                        attempt_root / "work" / "target-query-only.a3m",
                    )
                    msa_evidence = _publish_explicit_msa(
                        prepared=prepared,
                        adapter=adapter,
                        input_json=working_input,
                        attempt_root=attempt_root,
                        source=query_only,
                        cache_status="query-only",
                    )
                    logs["msa-source"] = "query-only A3M generated\n"
                elif unpaired_mode is MsaMode.DISABLED:
                    msa_evidence = _MsaEvidence(
                        updated_input=working_input,
                        source_a3m=None,
                        published_a3m=None,
                        published_receipt=None,
                        sha256=None,
                        depth=None,
                        cache_status="disabled",
                    )
                    logs["msa-source"] = "target unpaired MSA disabled\n"
                elif msa_evidence is None:
                    raise _InvocationFailure(
                        "remote target unpaired MSA evidence 缺失",
                        error_code="remote-msa-output-invalid",
                        retryable=True,
                    )

                prediction_output = attempt_root / "work" / "prediction"
                prediction = _run_invocation(
                    adapter.prediction_invocation(
                        request,
                        input_json=msa_evidence.updated_input,
                        output_dir=prediction_output,
                    ),
                    error_code="protenix-prediction-failed",
                    retryable=False,
                )
                logs["prediction-stdout"] = prediction.stdout
                logs["prediction-stderr"] = prediction.stderr
                products = adapter.collect_products(
                    request,
                    output_dir=prediction_output,
                )
                if len(products) != 1:
                    raise _InvocationFailure(
                        f"Stage 01 v0.1 需要恰好一个预测结果，实际 {len(products)}",
                        error_code="prediction-selection-ambiguous",
                        retryable=False,
                    )
                if request.parameter_profile is PredictionParameterProfile.MODEL_DEFAULT:
                    cycle_count = 10
                    diffusion_steps = 200
                else:
                    assert request.cycle_count is not None
                    assert request.diffusion_step_count is not None
                    cycle_count = request.cycle_count
                    diffusion_steps = request.diffusion_step_count
                built = build_predicted_target_bundle(
                    run_root=workspace.run_root,
                    attempt_id=attempt_id,
                    target=prepared.loaded_config.target,
                    product=products[0],
                    model_checkpoint_sha256=model_checkpoint_sha256,
                    msa_mode=unpaired_mode,
                    msa_input_sha256=msa_evidence.sha256,
                    msa_server_mode=(
                        provider.server_mode
                        if provider is not None and unpaired_mode is MsaMode.REMOTE
                        else None
                    ),
                    template_mode=request.template_mode,
                    parameter_profile=request.parameter_profile,
                    resolved_cycle_count=cycle_count,
                    resolved_diffusion_step_count=diffusion_steps,
                    msa_provider=(
                        str(provider.provider)
                        if provider is not None and unpaired_mode is MsaMode.REMOTE
                        else (
                            "precomputed"
                            if unpaired_mode is MsaMode.PRECOMPUTED
                            else (
                                "query-only"
                                if unpaired_mode is MsaMode.QUERY_ONLY
                                else None
                            )
                        )
                    ),
                    msa_endpoint=(
                        provider.endpoint
                        if provider is not None and unpaired_mode is MsaMode.REMOTE
                        else None
                    ),
                    msa_depth=msa_evidence.depth,
                    msa_query_sha256=(
                        prepared.loaded_config.target.sequence_sha256
                        if msa_evidence.sha256 is not None
                        else None
                    ),
                    msa_ticket=None,
                    msa_ticket_status=(
                        None
                        if unpaired_mode is MsaMode.DISABLED
                        else (
                            "not-exposed-by-protenix-cli-2.0.0"
                            if msa_evidence.cache_status == "remote-refresh"
                            else msa_evidence.cache_status
                        )
                    ),
                    msa_source_type=(
                        None if msa_source_receipt is None else msa_source_receipt.source_type
                    ),
                    msa_library_schema_version=(
                        None
                        if msa_source_receipt is None
                        else msa_source_receipt.library_schema_version
                    ),
                    msa_release_id=(
                        None if msa_source_receipt is None else msa_source_receipt.release_id
                    ),
                    msa_library_manifest_sha256=(
                        None
                        if msa_source_receipt is None
                        else msa_source_receipt.library_manifest_sha256
                    ),
                    msa_release_receipt_sha256=(
                        None
                        if msa_source_receipt is None
                        else msa_source_receipt.release_receipt_sha256
                    ),
                    paired_msa_mode=paired_mode,
                    paired_msa_input_sha256=paired_msa_input_sha256,
                    template_data_sha256=request.target_template_data_sha256,
                    identity_report=prepared.loaded_config.identity_report,
                    scope_report=prepared.loaded_config.scope_report,
                    structure_candidates=prepared.loaded_config.structure_candidates,
                    retrieval_records=prepared.loaded_config.retrieval_records,
                    reference_sequence=prepared.loaded_config.reference_sequence,
                    prediction_fallback_reason=(
                        prepared.loaded_config.prediction_fallback_reason
                    ),
                )
            except _InvocationFailure as error:
                current_failure = error
                logs.setdefault("failure-stdout", error.stdout)
                logs.setdefault("failure-stderr", error.stderr)
            except (EasyDesignError, OSError, ValueError) as error:
                current_failure = _InvocationFailure(
                    str(error) or type(error).__name__,
                    error_code="sequence-target-publication-failed",
                    retryable=False,
                )

            ended = _strictly_later(datetime.now(UTC), attempt_started)
            log_refs = _write_logs(
                run_root=workspace.run_root,
                attempt_root=attempt_root,
                attempt_id=attempt_id,
                logs=logs,
            )
            if current_failure is None:
                assert built is not None
                assert msa_evidence is not None
                attempt = Attempt(
                    attempt_id=attempt_id,
                    status=ExecutionStatus.SUCCEEDED,
                    created_at=attempt_started,
                    started_at=attempt_started,
                    ended_at=ended,
                    backend_name=adapter.backend_name,
                    backend_version=adapter.backend_version,
                    executor_name="local-subprocess",
                    seed=request.seeds[0],
                    log_artifacts=log_refs,
                )
                selected_attempt_id = attempt_id
                selected_provider = provider
                if msa_evidence.published_a3m is not None:
                    selected_msa_ref = _artifact(
                        run_root=workspace.run_root,
                        path=msa_evidence.published_a3m,
                        artifact_id="target-msa",
                        role="target-msa",
                        file_format="a3m",
                        attempt_id=attempt_id,
                    )
                if msa_evidence.published_receipt is not None:
                    selected_msa_receipt_ref = _artifact(
                        run_root=workspace.run_root,
                        path=msa_evidence.published_receipt,
                        artifact_id="remote-msa-receipt",
                        role="remote-msa-provenance",
                        file_format="json",
                        attempt_id=attempt_id,
                    )
            else:
                failure = current_failure
                attempt = Attempt(
                    attempt_id=attempt_id,
                    status=ExecutionStatus.FAILED,
                    created_at=attempt_started,
                    started_at=attempt_started,
                    ended_at=ended,
                    backend_name=adapter.backend_name,
                    backend_version=adapter.backend_version,
                    executor_name="local-subprocess",
                    seed=request.seeds[0],
                    log_artifacts=log_refs,
                    error=ErrorInfo(
                        code=current_failure.error_code,
                        message=str(current_failure)[:4096],
                        retryable=current_failure.retryable,
                    ),
                )
            manifest_path = dump_model(
                attempt,
                attempt_root / "attempt-manifest.json",
            )
            attempts.append(attempt)
            attempt_paths.append(manifest_path)
            if current_failure is None:
                break
            if not current_failure.retryable:
                break
            is_last_provider_attempt = provider_attempt + 1 == provider_max_attempts
            is_last_provider = provider_index + 1 == len(execution_plan)
            if not (is_last_provider_attempt and is_last_provider):
                sleep(provider.retry_backoff_seconds if provider is not None else 0)
        if built is not None or (failure is not None and not failure.retryable):
            break

    ended = _strictly_later(datetime.now(UTC), start)
    if built is None:
        output_artifacts: tuple[ArtifactRef, ...] = ()
        stage_status = ExecutionStatus.FAILED
    else:
        bundle = built.bundle
        core_artifacts = (
            bundle.target_structure,
            bundle.sequence,
            bundle.residue_mapping,
            bundle.quality_report,
            bundle.provenance,
            built.bundle_artifact,
        )
        msa_artifacts = tuple(
            item
            for item in (selected_msa_ref, selected_msa_receipt_ref)
            if item is not None
        )
        optional_artifacts = tuple(
            artifact
            for artifact in (
                bundle.reference_sequence,
                bundle.residue_mapping_tsv,
                bundle.identity_report,
                bundle.scope_report,
                bundle.structure_candidates,
                bundle.structure_candidates_tsv,
                bundle.retrieval_manifest,
                bundle.prediction_confidence,
                bundle.target_pdb,
            )
            if artifact is not None
        )
        output_artifacts = core_artifacts + msa_artifacts + optional_artifacts
        stage_status = ExecutionStatus.SUCCEEDED
    assert attempts
    last_attempt_id = attempts[-1].attempt_id
    stage_warnings: tuple[str, ...]
    if unpaired_mode is MsaMode.PRECOMPUTED:
        stage_warnings = (
            "Precomputed MSA was supplied and validated by exact query identity.",
        )
    elif unpaired_mode is MsaMode.DISABLED:
        stage_warnings = ("Target unpaired MSA was explicitly disabled.",)
    elif unpaired_mode is MsaMode.QUERY_ONLY:
        stage_warnings = ("Target unpaired MSA contains only the query sequence.",)
    elif (
        selected_provider is not None
        and str(selected_provider.provider) == "colabfold-public"
    ):
        stage_warnings = (
            "External public MSA data provider receives the target sequence.",
            "Protenix 2.0.0 CLI does not expose the online MSA ticket identifier.",
        )
    else:
        stage_warnings = (
            "Protenix 2.0.0 CLI does not expose the online MSA ticket identifier.",
        )
    feature_inputs = tuple(
        item
        for item in (
            resolved_config.precomputed_msa_snapshot,
            resolved_config.precomputed_msa_source_snapshot,
            resolved_config.precomputed_paired_msa_snapshot,
            resolved_config.precomputed_template_snapshot,
        )
        if item is not None
    )
    stage = StageManifest(
        stage_id=StageId.TARGET_PREPARATION,
        contract_version="0.4",
        status=stage_status,
        created_at=start,
        completed_at=ended,
        input_artifacts=(resolved_config.input_snapshot,) + feature_inputs,
        output_artifacts=output_artifacts,
        attempts=tuple(attempts),
        selected_attempt_id=selected_attempt_id,
        warnings=stage_warnings,
    )
    stage_manifest = dump_model(
        stage,
        workspace.stage_root(StageId.TARGET_PREPARATION)
        / "stage-manifest.v0001.json",
    )
    run_manifest = _publish_run_revision(
        prepared=prepared,
        stage_manifest_path=stage_manifest,
        attempt_id=selected_attempt_id or last_attempt_id,
        ended_at=ended,
        succeeded=built is not None,
    )
    if built is None:
        assert failure is not None
        raise failure
    target_viewer = generate_stage01_target_viewer_nonblocking(
        prepared.workspace.run_root
    )
    return CompletedSequenceRun(
        prepared=prepared,
        built_bundle=built,
        msa_artifact=selected_msa_ref,
        attempt_manifests=tuple(attempt_paths),
        stage_manifest=stage_manifest,
        run_manifest=run_manifest,
        target_viewer=target_viewer,
    )
