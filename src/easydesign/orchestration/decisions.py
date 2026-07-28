"""通用 Decision Gate 的文件协议与 CLI/API 入口。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    DecisionAuthority,
    DecisionRecord,
    DecisionRequest,
    ManifestStateError,
    canonical_model_sha256,
    dump_model,
    load_model,
)
from easydesign.safe_writes import append_pointer_revision, read_last_text_line


def _atomic_pointer(value: str, path: Path) -> None:
    append_pointer_revision(path, value)


def publish_decision_request(run_root: Path, request: DecisionRequest) -> Path:
    """发布一个 pending gate；相同 decision/revision 永不覆盖。"""

    root = run_root.resolve()
    path = (
        root
        / "decisions"
        / request.decision_id
        / f"request.v{request.revision:04d}.json"
    )
    if path.exists():
        raise ManifestStateError(f"DecisionRequest 已存在，禁止覆盖: {path}")
    dump_model(request, path)
    _atomic_pointer(
        f"{path.relative_to(root).as_posix()}\n",
        root / "decisions" / "LATEST",
    )
    return path


def load_pending_decision(run_root: Path) -> tuple[DecisionRequest, Path]:
    root = run_root.resolve()
    pointer = root / "decisions" / "LATEST"
    try:
        relative = read_last_text_line(pointer)
    except OSError as error:
        raise ManifestStateError(f"Run 没有 pending decision: {root}") from error
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ManifestStateError("Decision LATEST 指向 run 外或不存在")
    request = load_model(path, DecisionRequest)
    record = path.parent / f"record.v{request.revision:04d}.json"
    if record.exists():
        raise ManifestStateError("LATEST decision 已有 record，不再是 pending")
    return request, path


def show_decision(run_root: Path) -> DecisionRequest:
    return load_pending_decision(run_root)[0]


def export_decision(run_root: Path, *, output: Path) -> Path:
    request, path = load_pending_decision(run_root)
    destination = output.expanduser().resolve()
    if destination.exists():
        raise ManifestStateError(f"Decision 导出目标已存在，禁止覆盖: {destination}")
    payload = {
        "schema_version": "0.1",
        "decision_id": request.decision_id,
        "request_revision": request.revision,
        "request_sha256": canonical_model_sha256(request),
        "request_path": path.relative_to(run_root.resolve()).as_posix(),
        "selected_option_ids": [],
        "approved_by": None,
        "acknowledgement": None,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    return destination


def approve_decision(
    run_root: Path,
    *,
    input_path: Path,
    approved_at: datetime | None = None,
) -> Path:
    request, request_path = load_pending_decision(run_root)
    try:
        raw: Any = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise ManifestStateError(f"Decision 审批文件无法读取: {input_path}") from error
    if not isinstance(raw, dict):
        raise ManifestStateError("Decision 审批文件顶层必须是 mapping")
    if raw.get("decision_id") != request.decision_id:
        raise ManifestStateError("Decision 审批 decision_id 与当前 request 不一致")
    if raw.get("request_revision") != request.revision:
        raise ManifestStateError("Decision 审批 request_revision 已过期")
    expected_sha = canonical_model_sha256(request)
    if raw.get("request_sha256") != expected_sha:
        raise ManifestStateError("Decision 审批 request SHA-256 不一致")
    selected = raw.get("selected_option_ids")
    if not isinstance(selected, list) or not selected:
        raise ManifestStateError("Decision 审批必须选择至少一个 option")
    if request.stage_id == "01-target-preparation" and len(selected) != 1:
        raise ManifestStateError("Stage 01 Decision 必须且只能选择一个 option")
    option_by_id = {option.option_id: option for option in request.options}
    if any(option not in option_by_id for option in selected):
        raise ManifestStateError("Decision 审批包含当前 request 未声明的 option")
    if any(not option_by_id[option].eligible for option in selected):
        raise ManifestStateError("Decision 审批不能选择 ineligible option")
    approved_by = raw.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise ManifestStateError("Decision 审批必须填写 approved_by")
    timestamp = datetime.now(UTC) if approved_at is None else approved_at
    record = DecisionRecord(
        decision_id=request.decision_id,
        request_revision=request.revision,
        request_sha256=expected_sha,
        authority=DecisionAuthority.HUMAN,
        selected_option_ids=tuple(str(item) for item in selected),
        approved_at=timestamp,
        approved_by=approved_by.strip(),
        acknowledgement=(
            str(raw["acknowledgement"])
            if raw.get("acknowledgement") is not None
            else None
        ),
    )
    record_path = request_path.parent / f"record.v{request.revision:04d}.json"
    if record_path.exists():
        raise ManifestStateError(f"DecisionRecord 已存在，禁止覆盖: {record_path}")
    dump_model(record, record_path)
    _atomic_pointer(
        f"{record_path.relative_to(run_root.resolve()).as_posix()}\n",
        run_root.resolve() / "decisions" / "LATEST_RECORD",
    )
    return record_path


def load_decision_record_context(
    run_root: Path,
    record_path: Path,
) -> tuple[DecisionRequest, DecisionRecord]:
    """加载并交叉验证刚批准的 request/record，供同一 run 新 attempt 恢复。"""

    root = run_root.resolve()
    resolved_record = record_path.resolve()
    if not resolved_record.is_relative_to(root) or not resolved_record.is_file():
        raise ManifestStateError("DecisionRecord 必须位于目标 run 内")
    record = load_model(resolved_record, DecisionRecord)
    request_path = (
        resolved_record.parent
        / f"request.v{record.request_revision:04d}.json"
    )
    request = load_model(request_path, DecisionRequest)
    if request.decision_id != record.decision_id:
        raise ManifestStateError("DecisionRequest/Record decision_id 不一致")
    if canonical_model_sha256(request) != record.request_sha256:
        raise ManifestStateError("DecisionRequest 已变更或 Record hash 不匹配")
    option_ids = {option.option_id for option in request.options}
    if any(value not in option_ids for value in record.selected_option_ids):
        raise ManifestStateError("DecisionRecord 选择了 request 不存在的 option")
    return request, record
