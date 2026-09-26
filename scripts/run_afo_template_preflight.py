#!/usr/bin/env python3
"""Replay 3-5 saved Pilot populations through the frozen AFO template protocol.

The script deliberately reuses the exact target A3M and BoltzGen stage-1
candidate population from each source run.  It writes into a new authority
namespace below that run and never publishes Agent decisions or replaces prior
prediction evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from easydesign.agent.phase34_measurement import MEASUREMENT_VERSION
from easydesign.agent.phase34_partial_reference import (
    partial_reference_required,
    recover_partial_reference_predictions,
)
from easydesign.core import (
    ManifestStateError,
    canonical_model_sha256,
    load_model,
    sha256_file,
)
from easydesign.orchestration.afo_template_protocol import (
    PROTOCOL_ID,
    AfoBinderTemplateReceipt,
    AfoFinalInputAudit,
    AfoTargetTemplateReceipt,
)
from easydesign.orchestration.application import (
    _complex_prediction_adapter_builder,
)
from easydesign.orchestration.config import stage05_config_for_backend
from easydesign.orchestration.profile import load_runtime_profile
from easydesign.orchestration.stage05 import (
    _load_upstream,
    _predict_selected_candidates,
)
from easydesign.orchestration.task_tracking import load_latest_runtime_model
from easydesign.orchestration.workspace import load_resolved_run_config
from easydesign.stages.s04_pilot_generation import PilotPlan
from easydesign.stages.s05_pilot_filtering import FullTargetExecutionState
from easydesign.workspace_context import WorkspaceContext


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="TARGET_ID=/absolute/path/to/source/run (repeat 3-5 times)",
    )
    parser.add_argument("--selection-seed", required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def _parse_cases(values: list[str]) -> tuple[tuple[str, Path], ...]:
    if not 3 <= len(values) <= 5:
        raise ManifestStateError("AFO template preflight 必须包含 3-5 个任务")
    cases: list[tuple[str, Path]] = []
    for value in values:
        label, separator, raw_path = value.partition("=")
        if not separator or not label or not raw_path:
            raise ManifestStateError(f"无效 preflight case: {value}")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise ManifestStateError(f"preflight source run 不存在: {path}")
        cases.append((label, path))
    if len({label for label, _ in cases}) != len(cases):
        raise ManifestStateError("preflight target_id 不能重复")
    if len({path for _, path in cases}) != len(cases):
        raise ManifestStateError("preflight source run 不能重复")
    return tuple(cases)


def _git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _authority_id(
    *,
    target_id: str,
    source_run: Path,
    selection_seed: str,
    code_commit: str,
    profile_sha256: str,
) -> str:
    payload = {
        "protocol_id": PROTOCOL_ID,
        "target_id": target_id,
        "source_run": str(source_run),
        "selection_seed": selection_seed,
        "code_commit": code_commit,
        "profile_sha256": profile_sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _source_measurement_root(source_run: Path) -> Path:
    candidates = tuple(
        sorted(
            path.parent.parent
            for path in source_run.glob(
                "phase34/*/measurement/artifacts/predictions-v2.json"
            )
        )
    )
    if len(candidates) != 1:
        raise ManifestStateError(
            "preflight source 必须恰好有一份历史 predictions-v2: "
            f"observed={len(candidates)}"
        )
    return candidates[0]


def _reuse_target_msa(*, source: Path, destination: Path) -> dict[str, str]:
    source_work = source / "work" / "target-msa"
    source_a3m = source / "artifacts" / "target-msa.a3m"
    if not source_work.is_dir() or not source_a3m.is_file():
        raise ManifestStateError("历史 target MSA/state 不完整，禁止静默重新搜索")
    destination_work = destination / "work" / "target-msa"
    if not destination_work.exists():
        destination_work.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_work, destination_work)
    return {
        "source_measurement_root": str(source),
        "target_a3m_sha256": sha256_file(source_a3m),
    }


def _run_case(
    *,
    context: WorkspaceContext,
    target_id: str,
    source_run: Path,
    selection_seed: str,
    code_commit: str,
    profile_sha256: str,
) -> dict[str, Any]:
    if not source_run.is_relative_to(context.runs_root.resolve()):
        raise ManifestStateError("preflight source run 逃出当前 workspace/runs")
    upstream = _load_upstream(source_run)
    resolved, _ = load_resolved_run_config(source_run)
    generation = resolved.user_config.stage04
    if generation is None:
        raise ManifestStateError("preflight source 缺少 Stage 04 config")
    profile = load_runtime_profile()
    prediction = stage05_config_for_backend(
        "openfold3-af3-jax"
    ).full_target_prediction
    if prediction.template_protocol != PROTOCOL_ID:
        raise ManifestStateError("当前 AFO Stage 05 默认值未启用冻结 template 协议")
    authority_id = _authority_id(
        target_id=target_id,
        source_run=source_run,
        selection_seed=selection_seed,
        code_commit=code_commit,
        profile_sha256=profile_sha256,
    )
    measurement = source_run / "phase34" / authority_id / "measurement"
    artifacts = measurement / "artifacts"
    runtime = measurement / "runtime"
    work = measurement / "work"
    artifacts.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    reused_msa = _reuse_target_msa(
        source=_source_measurement_root(source_run),
        destination=measurement,
    )
    plan = load_model(upstream.pilot_bundle.pilot_plan.verify(source_run), PilotPlan)
    selected_ids = {item.candidate_id for item in upstream.candidate_index.candidates}
    adapter_builder = _complex_prediction_adapter_builder(profile.profile, prediction)
    partial_reference = partial_reference_required(source_run, upstream)
    try:
        predictions, prediction_refs, msa_refs = _predict_selected_candidates(
            root=source_run,
            artifacts=artifacts,
            work=work,
            runtime=runtime,
            upstream=upstream,
            candidates=upstream.candidate_index.candidates,
            selected_ids=selected_ids,
            providers=prediction.target_msa.resolved_providers(),
            prediction_config=prediction,
            adapter_builder=adapter_builder,
            devices=plan.devices,
            maximum_attempts=(
                1 if partial_reference else generation.executor.max_task_attempts
            ),
            created_at=datetime.now(UTC),
        )
    except ManifestStateError:
        if not partial_reference:
            raise
        predictions, prediction_refs = recover_partial_reference_predictions(
            root=source_run,
            work=work,
            runtime=runtime,
            artifacts=artifacts,
            upstream=upstream,
            prediction_config=prediction,
            adapter_builder=adapter_builder,
            devices=plan.devices,
        )
        msa_refs = ()
    state = load_latest_runtime_model(
        runtime / "full-target-state.json",
        FullTargetExecutionState,
    )
    if (
        len(predictions) != len(selected_ids)
        or state.progress.status
        not in ({"incomplete"} if partial_reference else {"phase-succeeded"})
    ):
        raise ManifestStateError("AFO template preflight prediction 未全部成功")
    target_receipt_path = (
        work
        / "afo-template-protocol"
        / "de-novo"
        / "target"
        / "target-template-receipt.json"
    )
    target_receipt = load_model(target_receipt_path, AfoTargetTemplateReceipt)
    input_audits = tuple(sorted(work.glob("full-target/*/attempt-*/input-audit.json")))
    binder_receipts = tuple(
        sorted(
            work.glob(
                "full-target/*/attempt-*/binder-template-protocol/"
                "binder-template-receipt.json"
            )
        )
    )
    if len(input_audits) != len(selected_ids) or len(binder_receipts) != len(selected_ids):
        raise ManifestStateError("AFO template preflight audit/receipt 数量不完整")
    chain_rows: list[dict[str, Any]] = []
    input_hashes: list[str] = []
    for path in input_audits:
        audit = load_model(path, AfoFinalInputAudit)
        if audit.protocol_id != PROTOCOL_ID:
            raise ManifestStateError("AFO final input audit protocol identity 不一致")
        binder = next(item for item in audit.chains if item.role == "binder")
        if binder.paired_msa_depth < 1:
            raise ManifestStateError("binder paired MSA 被意外清空")
        input_hashes.append(audit.input_json_sha256)
        chain_rows.extend(
            {
                "target_id": target_id,
                "input_audit": str(path.relative_to(source_run)),
                **item.model_dump(mode="json"),
            }
            for item in audit.chains
        )
    binder_template_hashes = [
        load_model(path, AfoBinderTemplateReceipt).binder_template_mmcif_sha256
        for path in binder_receipts
    ]
    return {
        "status": "passed",
        "target_id": target_id,
        "source_run": str(source_run),
        "authority_id": authority_id,
        "candidate_count": len(selected_ids),
        "prediction_count": len(predictions),
        "partial_reference_recovery": partial_reference,
        "runtime_profile_sha256": profile_sha256,
        "target_template_count": target_receipt.template_count,
        "target_template_receipt": str(target_receipt_path.relative_to(source_run)),
        "target_template_receipt_sha256": sha256_file(target_receipt_path),
        "binder_template_mmcif_sha256": binder_template_hashes,
        "final_input_sha256": input_hashes,
        "chain_audit": chain_rows,
        "prediction_artifact_sha256": [item.sha256 for item in prediction_refs],
        "msa_artifact_sha256": [item.sha256 for item in msa_refs],
        "execution_state_sha256": canonical_model_sha256(state),
        **reused_msa,
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def main() -> int:
    arguments = _arguments()
    cases = _parse_cases(arguments.case)
    context = WorkspaceContext.discover()
    code_commit = _git_commit(Path(__file__).resolve().parents[1])
    profile = load_runtime_profile()
    template_runtime = profile.profile.backends.openfold3_af3_jax
    if template_runtime is None or template_runtime.template_pipeline is None:
        raise ManifestStateError("当前 runtime profile 尚未激活 AFO template component")
    report: dict[str, Any] = {
        "schema_version": "0.1",
        "protocol_id": PROTOCOL_ID,
        "measurement_version": MEASUREMENT_VERSION,
        "selection_seed": arguments.selection_seed,
        "code_commit": code_commit,
        "runtime_profile_sha256": profile.identity.sha256,
        "started_at": datetime.now(UTC).isoformat(),
        "cases": [],
    }
    failures = 0
    for target_id, source_run in cases:
        try:
            result = _run_case(
                context=context,
                target_id=target_id,
                source_run=source_run,
                selection_seed=arguments.selection_seed,
                code_commit=code_commit,
                profile_sha256=profile.identity.sha256,
            )
        except Exception as error:
            failures += 1
            result = {
                "status": "failed",
                "target_id": target_id,
                "source_run": str(source_run),
                "error": f"{type(error).__name__}: {str(error)[:4096]}",
            }
        report["cases"].append(result)
        report["updated_at"] = datetime.now(UTC).isoformat()
        report["status"] = "failed" if failures else "running"
        _write_report(arguments.report.resolve(), report)
    report["status"] = "passed" if not failures else "failed"
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["passed_count"] = len(cases) - failures
    report["failed_count"] = failures
    _write_report(arguments.report.resolve(), report)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
