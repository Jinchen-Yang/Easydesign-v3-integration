"""从已验证上游 run 生成下一阶段 canonical 配置。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from easydesign.core import (
    ConfigurationError,
    ExecutionStatus,
    ManifestStateError,
    RunManifest,
    StageManifest,
    load_model,
    sha256_file,
)

from .config import (
    Stage03Config,
    Stage04Config,
    Stage05Config,
    Stage06Config,
    Stage07Config,
    load_run_config,
)
from .workspace import ResolvedRunConfig


def _latest_run(run_root: Path) -> RunManifest:
    pointer = run_root / "manifests" / "LATEST"
    try:
        name = pointer.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ManifestStateError(f"无法读取 continuation source: {run_root}") from error
    return load_model(run_root / "manifests" / name, RunManifest)


def next_stage_number(run_root: Path) -> int:
    root = run_root.resolve()
    run = _latest_run(root)
    if run.status is not ExecutionStatus.SUCCEEDED:
        raise ManifestStateError("只有 succeeded run 可以配置下一阶段")
    numbers: list[int] = []
    for reference in run.stage_manifest_refs:
        if reference.producer_stage is None:
            raise ManifestStateError("StageManifest 引用缺少 producer_stage")
        stage = load_model(reference.verify(root), StageManifest)
        if stage.status is not ExecutionStatus.SUCCEEDED:
            raise ManifestStateError(f"上游阶段未成功: {reference.producer_stage}")
        numbers.append(int(reference.producer_stage.split("-", maxsplit=1)[0]))
    if not numbers:
        raise ManifestStateError("source run 没有已完成阶段")
    ordered = sorted(numbers)
    if ordered != list(range(1, ordered[-1] + 1)):
        raise ManifestStateError("source run 的阶段序列不连续")
    if ordered[-1] >= 7:
        raise ManifestStateError("Stage 07 已完成，没有下一阶段")
    return ordered[-1] + 1


def stage_form_definition(stage_number: int) -> dict[str, Any]:
    """返回由 Python 契约生成的产品表单默认值。"""

    names = (
        "准备目标结构",
        "选择结合区域",
        "生成设计方案",
        "小规模生成",
        "筛选与验证",
        "规模化生成",
        "最终候选",
    )
    if stage_number not in range(1, 8):
        raise ConfigurationError("stage_number 必须在 1–7")
    if stage_number == 1:
        defaults: dict[str, Any] = {
            "source_types": [
                "local-file",
                "pdb-id",
                "sequence",
                "uniprot",
                "uniprot-search",
                "target-bundle",
            ],
        }
    elif stage_number == 2:
        defaults = {
            "mode": "automatic",
            "methods": ["sasa", "scannet"],
            "annotations": {"uniprot": "if_available"},
            "available_modes": ["automatic", "user-provided"],
        }
    else:
        model = {
            3: Stage03Config(),
            4: Stage04Config(),
            5: Stage05Config(),
            6: Stage06Config(),
            7: Stage07Config(),
        }[stage_number]
        defaults = model.model_dump(mode="json")
    return {
        "schema_version": "0.1",
        "stage_number": stage_number,
        "title": names[stage_number - 1],
        "defaults": defaults,
    }


def _stage_payload(
    stage_number: int,
    *,
    execution_mode: str,
    options: dict[str, Any] | None,
) -> dict[str, Any]:
    selected = options or {}
    if stage_number == 2:
        if selected.get("mode") == "user-provided":
            regions = selected.get("regions")
            if not isinstance(regions, list) or not 1 <= len(regions) <= 3:
                raise ConfigurationError("人工区域必须提供 1–3 个区域")
            normalized: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            seen_residues: set[int] = set()
            for region in regions:
                if not isinstance(region, dict):
                    raise ConfigurationError("人工区域必须是 object")
                region_id = str(region.get("id") or "")
                if region_id not in {"A", "B", "C"} or region_id in seen_ids:
                    raise ConfigurationError("人工区域 ID 必须是唯一的 A/B/C")
                values = region.get("label_seq_ids")
                if not isinstance(values, list) or not values:
                    raise ConfigurationError(f"区域 {region_id} 不能为空")
                residues = sorted({int(value) for value in values})
                if any(value < 1 for value in residues):
                    raise ConfigurationError("label_seq_id 必须为正整数")
                overlap = seen_residues.intersection(residues)
                if overlap:
                    raise ConfigurationError(
                        f"残基不能同时属于多个编辑区域: {sorted(overlap)}"
                    )
                seen_ids.add(region_id)
                seen_residues.update(residues)
                normalized.append({"id": region_id, "residues": residues})
            normalized.sort(key=lambda item: "ABC".index(str(item["id"])))
            user_payload: dict[str, Any] = {
                "mode": "user-provided",
                "methods": [],
                "automatic": None,
                "user_regions": {
                    "source": {
                        "type": "residue-list",
                        "numbering": "label",
                        "regions": [
                            {
                                "id": item["id"],
                                "residues": [str(value) for value in item["residues"]],
                            }
                            for item in normalized
                        ],
                    }
                },
                "annotations": {"uniprot": "if_available"},
            }
            approvals = selected.get("approvals")
            if approvals is not None:
                if not isinstance(approvals, list) or len(approvals) != len(normalized):
                    raise ConfigurationError("人工区域必须为每个区域提供理由")
                user_regions = user_payload["user_regions"]
                assert isinstance(user_regions, dict)
                user_regions["approval"] = {
                    "approved_by": str(selected.get("approved_by") or ""),
                    "acknowledge_user_provided_regions": bool(
                        selected.get("acknowledge_user_provided_regions")
                    ),
                    "acknowledge_evidence_limitations": bool(
                        selected.get("acknowledge_evidence_limitations")
                    ),
                    "selections": approvals,
                }
            elif execution_mode == "unattended":
                raise ConfigurationError("连续运行的人工区域必须为每个区域提供理由")
            return user_payload
        method = str(selected.get("method", "both"))
        if method not in {"sasa", "scannet", "both"}:
            raise ConfigurationError("Stage 02 method 只允许 sasa/scannet/both")
        if execution_mode == "unattended" and method == "both":
            raise ConfigurationError("连续运行的 Stage 02 必须选择一种自动方法")
        methods = ["sasa", "scannet"] if method == "both" else [method]
        automatic_payload: dict[str, Any] = {
            "mode": "automatic",
            "methods": methods,
            "annotations": {"uniprot": "if_available"},
        }
        if execution_mode == "unattended":
            automatic_payload["unattended_approval"] = {
                "region_count": int(selected.get("region_count", 3)),
                "allow_structural_only": bool(
                    selected.get("allow_structural_only", False)
                ),
            }
        return automatic_payload
    if stage_number == 3:
        return Stage03Config.model_validate(selected).model_dump(mode="json")
    if stage_number == 4:
        return Stage04Config.model_validate(selected).model_dump(mode="json")
    if stage_number == 5:
        return Stage05Config.model_validate(selected).model_dump(mode="json")
    if stage_number == 6:
        return Stage06Config.model_validate(selected).model_dump(mode="json")
    if stage_number == 7:
        return Stage07Config.model_validate(selected).model_dump(mode="json")
    raise ConfigurationError("Stage 01 不能通过 continuation 配置")


def _copy_verified_continuation_input(
    source: Path,
    destination: Path,
    expected_sha256: str,
) -> Path:
    """把冻结输入复制到产品项目；已存在同字节文件可安全复用。"""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != expected_sha256:
            raise ConfigurationError(f"continuation 输入已存在但内容不同: {destination}")
        return destination
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        shutil.copyfile(source, temporary)
        if sha256_file(temporary) != expected_sha256:
            raise ManifestStateError("continuation 输入复制后 SHA-256 不一致")
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _rebase_continuation_inputs(
    *,
    source_run_root: Path,
    output: Path,
    payload: dict[str, Any],
) -> None:
    """让新 revision 只引用已冻结、可解析的输入，不依赖旧项目目录。"""

    resolved_path = source_run_root / "config-snapshot" / "resolved-config.json"
    if not resolved_path.is_file():
        raise ManifestStateError("continuation source 缺少 resolved-config.json")
    resolved = load_model(resolved_path, ResolvedRunConfig)
    stage01 = payload.get("stage01")
    if not isinstance(stage01, dict):
        return
    target = stage01.get("target")
    source_config = target.get("source") if isinstance(target, dict) else None
    if not isinstance(source_config, dict):
        return
    source_type = str(source_config.get("type") or "")
    inputs_root = output.parent / "inputs" / "continuation" / resolved.run_id

    if source_type == "local-file":
        snapshot = resolved.input_snapshot.verify(source_run_root)
        copied = _copy_verified_continuation_input(
            snapshot,
            inputs_root / snapshot.name,
            resolved.input_snapshot.sha256,
        )
        source_config["path"] = Path(os.path.relpath(copied, output.parent)).as_posix()
    elif source_type == "target-bundle":
        snapshot = resolved.input_snapshot.verify(source_run_root)
        copied = _copy_verified_continuation_input(
            snapshot,
            inputs_root / snapshot.name,
            resolved.input_snapshot.sha256,
        )
        source_config["path"] = Path(os.path.relpath(copied, output.parent)).as_posix()
        source_config["source_run_root"] = Path(
            os.path.relpath(source_run_root, output.parent)
        ).as_posix()

    if resolved.precomputed_msa_snapshot is not None:
        msa_snapshot = resolved.precomputed_msa_snapshot.verify(source_run_root)
        copied_msa = _copy_verified_continuation_input(
            msa_snapshot,
            inputs_root / "target-msa.a3m",
            resolved.precomputed_msa_snapshot.sha256,
        )
        prediction = stage01.get("structure_prediction")
        msa = prediction.get("msa") if isinstance(prediction, dict) else None
        if isinstance(msa, dict) and msa.get("mode") == "precomputed":
            msa["path"] = Path(os.path.relpath(copied_msa, output.parent)).as_posix()


def materialize_continuation_config(
    *,
    source_run_root: Path,
    destination: Path,
    stage_number: int,
    execution_mode: str,
    options: dict[str, Any] | None = None,
    continue_after_stage: int | None = None,
) -> Path:
    """生成下一 Stage 配置；不覆盖现有 revision。"""

    source = source_run_root.resolve()
    expected = (
        next_stage_number(source)
        if continue_after_stage is None
        else continue_after_stage + 1
    )
    if stage_number != expected:
        raise ConfigurationError(f"下一阶段必须是 Stage {expected:02d}")
    run = _latest_run(source)
    frozen = run.config_snapshot.verify(source)
    try:
        payload = yaml.safe_load(frozen.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError("上游冻结配置无法读取") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("上游冻结配置根节点必须是 object")
    workflow = payload.setdefault("workflow", {})
    if not isinstance(workflow, dict):
        raise ConfigurationError("workflow 必须是 object")
    if execution_mode not in {"unattended", "review-gated"}:
        raise ConfigurationError("execution_mode 无效")
    workflow["execution_mode"] = execution_mode
    workflow["stop_after_stage"] = stage_number
    payload[f"stage{stage_number:02d}"] = _stage_payload(
        stage_number,
        execution_mode=execution_mode,
        options=options,
    )
    for future in range(stage_number + 1, 8):
        payload[f"stage{future:02d}"] = None
    output = destination.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    _rebase_continuation_inputs(
        source_run_root=source,
        output=output,
        payload=payload,
    )
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
    except FileExistsError as error:
        raise ConfigurationError(f"配置 revision 已存在，拒绝覆盖: {output}") from error
    try:
        load_run_config(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return output
