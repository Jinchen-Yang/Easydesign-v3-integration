"""Stage 05 的产品级只读投影。

所有来源先由当前 StageManifest 声明，再验证 ArtifactRef。这里不扫描 backend
目录，也不复制筛选门槛；阈值和通过状态均读取冻结的 decision record。
"""

from __future__ import annotations

import json
import math
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from easydesign.core import ArtifactRef, ManifestStateError, RunManifest, StageManifest, load_model

from .models import (
    ArtifactProjection,
    CandidateDetailProjection,
    CandidateListItem,
    CandidatePage,
    FilterOverviewProjection,
    MetricPresentation,
    StrategyMetricAggregate,
    StrategyProjection,
)
from .projections import _latest_run_manifest, _state_for_manifest
from .security import ArtifactTokenSigner, UiRunRegistry

Phase = Literal["pilot", "expansion", "full-target"]

METRIC_PRESENTATIONS: dict[str, dict[str, str | None]] = {
    "pass-filters": {
        "name": "BoltzGen 原始筛选",
        "abbreviation": "pass_filters",
        "group": "原始后端与序列风险",
        "definition": "BoltzGen 自带筛选流程给出的总体通过标记。",
        "unit": None,
        "source": "BoltzGen",
        "direction": "通过为好",
        "role": "参考指标",
    },
    "hotspot-coverage": {
        "name": "结合区域覆盖率",
        "abbreviation": None,
        "group": "结合质量",
        "definition": "被候选界面接触的目标结合区域残基比例。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "越大越好",
        "role": "硬门",
    },
    "design-to-target-iptm": {
        "name": "设计链与目标链界面置信度",
        "abbreviation": "iPTM",
        "group": "结合质量",
        "definition": "设计链与目标链之间的预测界面模板建模分数。",
        "unit": None,
        "source": "BoltzGen",
        "direction": "越大越好",
        "role": "硬门",
    },
    "min-design-to-target-pae": {
        "name": "最小设计链—目标链预测对齐误差",
        "abbreviation": "PAE",
        "group": "结合质量",
        "definition": "设计链和目标链界面残基对中的最小预测对齐误差。",
        "unit": "Å",
        "source": "BoltzGen",
        "direction": "越小越好",
        "role": "硬门",
    },
    "binder-ptm": {
        "name": "结合分子整体结构置信度",
        "abbreviation": "pTM",
        "group": "结合质量",
        "definition": "结合分子自身折叠的预测模板建模分数。",
        "unit": None,
        "source": "BoltzGen / Protenix",
        "direction": "越大越好",
        "role": "排序指标",
    },
    "filter-rmsd": {
        "name": "筛选整体骨架偏差",
        "abbreviation": "RMSD",
        "group": "结构稳定性",
        "definition": "后端筛选阶段计算的整体结构骨架偏差。",
        "unit": "Å",
        "source": "BoltzGen",
        "direction": "越小越好",
        "role": "参考指标",
    },
    "filter-rmsd-design": {
        "name": "筛选设计链骨架偏差",
        "abbreviation": "RMSD",
        "group": "结构稳定性",
        "definition": "后端筛选阶段计算的设计链骨架偏差。",
        "unit": "Å",
        "source": "BoltzGen",
        "direction": "越小越好",
        "role": "排序指标",
    },
    "bb_target_aligned_rmsd_design": {
        "name": "目标对齐后的设计链骨架偏差",
        "abbreviation": "RMSD",
        "group": "结构稳定性",
        "definition": "先对齐目标链，再计算设计链主链原子位置偏差。",
        "unit": "Å",
        "source": "BoltzGen",
        "direction": "越小越好",
        "role": "原始后端指标",
    },
    "target-ca-rmsd": {
        "name": "目标结构偏差",
        "abbreviation": "CA RMSD",
        "group": "结构稳定性",
        "definition": "候选复合物中目标链 CA 原子相对输入目标的均方根偏差。",
        "unit": "Å",
        "source": "EasyDesign 结构指标",
        "direction": "越小越好",
        "role": "硬门",
    },
    "severe-clash-count": {
        "name": "严重原子冲突数",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "界面中距离低于严重冲突阈值的重原子对数量。",
        "unit": "对",
        "source": "EasyDesign 结构指标",
        "direction": "越小越好",
        "role": "硬门",
    },
    "moderate-clash-count": {
        "name": "中等原子冲突数",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "界面中距离落入中等冲突区间的重原子对数量。",
        "unit": "对",
        "source": "EasyDesign 结构指标",
        "direction": "越小越好",
        "role": "硬门",
    },
    "interface-bsa": {
        "name": "界面埋藏表面积",
        "abbreviation": "BSA",
        "group": "冲突与界面",
        "definition": "目标与结合分子形成复合物后被埋藏的溶剂可及表面积。",
        "unit": "Å²",
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "interface-bsa-fallback-used": {
        "name": "界面面积备用算法标记",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "是否因标准计算不可用而采用备用界面面积算法。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "仅作说明",
        "role": "参考指标",
    },
    "residue-pair-contact-count": {
        "name": "界面残基接触对数",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "目标与结合分子之间满足接触距离的残基对数量。",
        "unit": "对",
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "atom-contact-count": {
        "name": "界面原子接触数",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "目标与结合分子之间满足接触距离的重原子对数量。",
        "unit": "对",
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "binder-contact-coverage": {
        "name": "结合分子界面覆盖率",
        "abbreviation": None,
        "group": "冲突与界面",
        "definition": "结合分子中参与目标接触的残基比例。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "cdr-dominance": {
        "name": "CDR 接触主导比例",
        "abbreviation": "CDR",
        "group": "CDR 与化学作用",
        "definition": "界面接触中由 CDR 残基贡献的比例。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "按设计目标解释",
        "role": "排序指标",
    },
    "cdr-utilization": {
        "name": "CDR 利用率",
        "abbreviation": "CDR",
        "group": "CDR 与化学作用",
        "definition": "全部 CDR 残基中实际参与目标接触的比例。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "hydrogen-bond-count": {
        "name": "界面氢键数",
        "abbreviation": None,
        "group": "CDR 与化学作用",
        "definition": "按冻结几何规则识别的跨链氢键数量。",
        "unit": "个",
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "salt-bridge-count": {
        "name": "界面盐桥数",
        "abbreviation": None,
        "group": "CDR 与化学作用",
        "definition": "按冻结距离规则识别的跨链相反电荷残基对数量。",
        "unit": "个",
        "source": "EasyDesign 结构指标",
        "direction": "越大通常越好",
        "role": "排序指标",
    },
    "polar-contact-fraction": {
        "name": "极性接触比例",
        "abbreviation": None,
        "group": "CDR 与化学作用",
        "definition": "界面接触中由极性原子或残基参与的比例。",
        "unit": None,
        "source": "EasyDesign 结构指标",
        "direction": "按界面环境解释",
        "role": "排序指标",
    },
    "protenix-target-rmsd": {
        "name": "Protenix 目标结构偏差",
        "abbreviation": "RMSD",
        "group": "Protenix 复核",
        "definition": "Protenix 独立预测中目标链相对输入结构的 CA RMSD。",
        "unit": "Å",
        "source": "Protenix",
        "direction": "越小越好",
        "role": "复核硬门",
    },
    "protenix-binder-pose-rmsd": {
        "name": "Protenix 结合位姿偏差",
        "abbreviation": "RMSD",
        "group": "Protenix 复核",
        "definition": "对齐目标链后，Protenix 结合分子位姿相对设计结构的偏差。",
        "unit": "Å",
        "source": "Protenix",
        "direction": "越小越好",
        "role": "复核硬门",
    },
    "protenix-pairwise-iptm": {
        "name": "Protenix 链对界面置信度",
        "abbreviation": "iPTM",
        "group": "Protenix 复核",
        "definition": "Protenix 对目标链与结合分子链对给出的界面置信度。",
        "unit": None,
        "source": "Protenix",
        "direction": "越大越好",
        "role": "复核指标",
    },
    "protenix-min-interface-pae": {
        "name": "Protenix 最小界面预测对齐误差",
        "abbreviation": "PAE",
        "group": "Protenix 复核",
        "definition": "Protenix 目标—结合分子界面中的最小预测对齐误差。",
        "unit": "Å",
        "source": "Protenix",
        "direction": "越小越好",
        "role": "复核指标",
    },
}

MISSING_VALUE_POLICY = "缺失值保留为不可用，不按通过处理，也不以零代替。"


@lru_cache(maxsize=16)
def _cached_json(path_text: str, sha256: str) -> dict[str, Any]:
    del sha256  # cache identity includes the verified content hash
    value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ManifestStateError("Stage 05 产品投影只接受 JSON object")
    return value


def _artifact_map(stage: StageManifest) -> dict[str, ArtifactRef]:
    return {
        item.artifact_id: item
        for item in (*stage.input_artifacts, *stage.output_artifacts)
    }


def _load_json(run_root: Path, ref: ArtifactRef) -> dict[str, Any]:
    path = ref.verify(run_root)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ManifestStateError(f"Stage 05 产品投影文件超过 32 MiB: {ref.artifact_id}")
    return _cached_json(str(path), ref.sha256)


def _stage05_sources(run_root: Path) -> tuple[RunManifest, StageManifest, dict[str, ArtifactRef]]:
    run, _ = _latest_run_manifest(run_root)
    stage_ref = next(
        (
            item
            for item in run.stage_manifest_refs
            if item.producer_stage == "05-pilot-filtering"
        ),
        None,
    )
    if stage_ref is None:
        raise ManifestStateError("当前运行没有正式发布第5步运行记录")
    stage = load_model(stage_ref.verify(run_root), StageManifest)
    return run, stage, _artifact_map(stage)


def _required_json(
    run_root: Path,
    artifacts: dict[str, ArtifactRef],
    artifact_id: str,
) -> dict[str, Any]:
    try:
        ref = artifacts[artifact_id]
    except KeyError as error:
        raise ManifestStateError(f"第5步没有声明必需输出文件: {artifact_id}") from error
    return _load_json(run_root, ref)


def _optional_json(
    run_root: Path,
    artifacts: dict[str, ArtifactRef],
    artifact_id: str,
) -> dict[str, Any] | None:
    ref = artifacts.get(artifact_id)
    return None if ref is None else _load_json(run_root, ref)


def _metric_map(record: dict[str, Any]) -> dict[str, Any]:
    return {
        str(metric.get("metric_id")): metric.get("value")
        for metric in record.get("metrics") or []
        if metric.get("metric_id")
    }


def _index_map(value: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    return {
        str(item.get("candidate_id")): item
        for item in value.get("candidates") or []
        if item.get("candidate_id")
    }


def _failed(decisions: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    return tuple(
        str(item.get("rule_id"))
        for item in decisions
        if item.get("passed") is False and item.get("rule_id")
    )


def _product_metric(
    metric_id: str,
    *,
    value: Any = None,
    source: str | None = None,
    unit: str | None = None,
    available: bool = True,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    item = METRIC_PRESENTATIONS.get(metric_id)
    fallback_name = metric_id.replace("_", " ").replace("-", " ")
    return {
        "metric_id": metric_id,
        "name": str(item["name"]) if item else fallback_name,
        "abbreviation": item.get("abbreviation") if item else None,
        "group": str(item["group"]) if item else "原始后端与序列风险",
        "definition": (
            str(item["definition"])
            if item
            else "后端原始输出指标；定义以固定后端版本为准。"
        ),
        "unit": unit if unit is not None else (item.get("unit") if item else None),
        "source": source if source is not None else (str(item["source"]) if item else "BoltzGen"),
        "direction": str(item["direction"]) if item else "按后端定义解释",
        "role": str(item["role"]) if item else "原始后端指标",
        "available": available,
        "missing_reason": missing_reason,
        "value": value,
    }


def _pilot_items(
    report: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items = []
    for record in report.get("candidate_records") or []:
        candidate_id = str(record.get("candidate_id"))
        backend = index.get(candidate_id) or {}
        metrics = _metric_map(record)
        metrics.update(backend.get("metrics") or {})
        items.append(
            {
                "candidate_id": candidate_id,
                "phase": "pilot",
                "strategy_id": str(record.get("strategy_id") or "—"),
                "sequence": record.get("sequence"),
                "gate_status": "通过" if record.get("eligible_unique_pass") else "未通过",
                "score": record.get("score_screen"),
                "metrics": metrics,
                "decisions": record.get("hard_gate_decisions") or [],
                "failed_rules": _failed(record.get("hard_gate_decisions") or []),
                "backend": backend,
            }
        )
    return items


def _expansion_items(
    expansion: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    predictions = {
        str(item.get("candidate_id")): item
        for item in expansion.get("predictions") or []
    }
    items = []
    for record in expansion.get("candidates") or []:
        candidate_id = str(record.get("candidate_id"))
        backend = index.get(candidate_id) or {}
        items.append(
            {
                "candidate_id": candidate_id,
                "phase": "expansion",
                "strategy_id": str(record.get("strategy_id") or "—"),
                "sequence": record.get("sequence"),
                "gate_status": "通过" if record.get("local_gate_pass") else "未通过",
                "score": record.get("score_expand_structure"),
                "metrics": dict(backend.get("metrics") or {}),
                "decisions": record.get("local_gate_decisions") or [],
                "failed_rules": _failed(record.get("local_gate_decisions") or []),
                "backend": backend,
                "prediction": predictions.get(candidate_id),
            }
        )
    return items


def _full_target_items(
    expansion: dict[str, Any],
    index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expansion_records = {
        str(item.get("candidate_id")): item for item in expansion.get("candidates") or []
    }
    items = []
    for prediction in expansion.get("predictions") or []:
        candidate_id = str(prediction.get("candidate_id"))
        candidate = expansion_records.get(candidate_id) or {}
        metrics = {
            "protenix-target-rmsd": prediction.get("target_ca_rmsd_angstrom"),
            "protenix-binder-pose-rmsd": prediction.get("binder_pose_rmsd_angstrom"),
            "protenix-pairwise-iptm": prediction.get("pairwise_iptm"),
            "protenix-min-interface-pae": prediction.get(
                "minimum_interface_pae_angstrom"
            ),
            "binder-ptm": prediction.get("binder_ptm"),
            "severe-clash-count": prediction.get("severe_clash_count"),
            "moderate-clash-count": prediction.get("moderate_clash_count"),
        }
        backend = index.get(candidate_id) or {}
        items.append(
            {
                "candidate_id": candidate_id,
                "phase": "full-target",
                "strategy_id": str(
                    prediction.get("strategy_id")
                    or candidate.get("strategy_id")
                    or "—"
                ),
                "sequence": candidate.get("sequence"),
                "gate_status": (
                    "通过"
                    if prediction.get("structure_gate_pass", prediction.get("passed"))
                    else "未通过"
                ),
                "score": candidate.get("score_expand_structure"),
                "metrics": metrics,
                "decisions": prediction.get("structure_gate_decisions") or [],
                "failed_rules": _failed(prediction.get("structure_gate_decisions") or []),
                "backend": backend,
                "prediction": prediction,
            }
        )
    return items


def _all_phase_items(
    run_root: Path,
    artifacts: dict[str, ArtifactRef],
    phase: Phase,
) -> list[dict[str, Any]]:
    report = _required_json(run_root, artifacts, "pilot-filter-report")
    pilot_index = _index_map(_optional_json(run_root, artifacts, "candidate-index"))
    if phase == "pilot":
        return _pilot_items(report, pilot_index)
    expansion = _required_json(run_root, artifacts, "expansion-validation-report")
    expansion_index = _index_map(
        _optional_json(run_root, artifacts, "expansion-candidate-index")
    )
    if phase == "expansion":
        return _expansion_items(expansion, expansion_index)
    return _full_target_items(expansion, expansion_index)


def get_filter_overview(
    run_root: Path,
    *,
    registry: UiRunRegistry,
) -> FilterOverviewProjection:
    root = run_root.resolve()
    run_key = registry.register(root)
    _, stage, artifacts = _stage05_sources(root)
    report = _required_json(root, artifacts, "pilot-filter-report")
    expansion = _optional_json(root, artifacts, "expansion-validation-report") or {}
    pilot = report.get("candidate_records") or []
    strategies = report.get("strategy_summaries") or []
    expanded = expansion.get("candidates") or []
    predictions = expansion.get("predictions") or []
    tier_counts: dict[str, int] = {}
    for item in strategies:
        tier = str(item.get("tier") or "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    failed_counts: dict[str, int] = {}
    for item in pilot:
        for rule in _failed(item.get("hard_gate_decisions") or []):
            failed_counts[rule] = failed_counts.get(rule, 0) + 1
    status = str(expansion.get("status") or report.get("status") or "completed")
    scientific_stop = status.startswith("stopped-")
    local_pass = sum(bool(item.get("local_gate_pass")) for item in expanded)
    protenix_pass = sum(
        bool(item.get("structure_gate_pass", item.get("passed"))) for item in predictions
    )
    counts = {
        "pilot": len(pilot),
        "strategies": len(strategies),
        "selected_strategies": len(report.get("selected_strategy_ids") or []),
        "expanded": len(expanded),
        "local_gate_pass": local_pass,
        "full_target": len(predictions),
        "full_target_pass": protenix_pass,
    }
    return FilterOverviewProjection(
        run_key=run_key,
        state=_state_for_manifest(stage),
        conclusion_title=(
            "当前没有可进入规模化生成的设计策略"
            if scientific_stop
            else "已选出可进入规模化生成的设计策略"
        ),
        conclusion=(
            "程序已正常完成，但当前结果没有达到进入下一步的科学门槛。"
            if scientific_stop
            else "筛选和完整目标复核已完成，并形成唯一可放大策略。"
        ),
        next_actions=(
            (
                "查看候选淘汰原因与指标分布",
                "按 VAL-003 进行 Protenix 受控复核",
                "保留本次结论，不自动放宽门槛",
            )
            if scientific_stop
            else ("审阅胜出策略", "确认规模化预算")
        ),
        counts=counts,
        tier_counts=tier_counts,
        step_chain=(
            {"id": "pilot", "label": "小规模候选", "count": len(pilot)},
            {
                "id": "hard-gates",
                "label": "逐项硬门筛选",
                "count": sum(
                    bool(item.get("eligible_unique_pass")) for item in pilot
                ),
            },
            {"id": "strategies", "label": "进入扩展的策略", "count": counts["selected_strategies"]},
            {"id": "expansion", "label": "扩展候选", "count": len(expanded)},
            {"id": "local-gate", "label": "通过初步结构筛选", "count": local_pass},
            {"id": "full-target", "label": "进入 Protenix 完整目标复核", "count": len(predictions)},
            {"id": "winner", "label": "满足结合位姿稳定性", "count": protenix_pass},
        ),
        failed_rule_counts=failed_counts,
    )


_STRATEGY_AGGREGATE_METRICS = (
    "hotspot-coverage",
    "design-to-target-iptm",
    "min-design-to-target-pae",
    "filter-rmsd-design",
    "bb_target_aligned_rmsd_design",
    "target-ca-rmsd",
    "interface-bsa",
    "severe-clash-count",
    "moderate-clash-count",
)


def _strategy_identity_sources(
    run_root: Path,
    run: RunManifest,
    artifacts: dict[str, ArtifactRef],
) -> tuple[dict[str, dict[str, Any]], dict[str, ArtifactRef]]:
    stage03_ref = next(
        (
            item
            for item in run.stage_manifest_refs
            if item.producer_stage == "03-boltzgen-configuration"
        ),
        None,
    )
    if stage03_ref is None:
        raise ManifestStateError("当前运行没有 Stage 03 策略运行记录")
    stage03 = load_model(stage03_ref.verify(run_root), StageManifest)
    stage03_artifacts = {item.artifact_id: item for item in stage03.output_artifacts}
    bundle_ref = stage03_artifacts.get("strategy-bundle")
    if bundle_ref is None:
        raise ManifestStateError("Stage 03 未声明 strategy-bundle")
    consumed_bundle_ref = artifacts.get("strategy-bundle")
    if consumed_bundle_ref is not None and consumed_bundle_ref.sha256 != bundle_ref.sha256:
        raise ManifestStateError("Stage 05 消费的 strategy-bundle 与当前 Stage 03 不一致")
    bundle = _load_json(run_root, bundle_ref)
    identities = {
        str(item.get("strategy_id")): item
        for item in bundle.get("strategies") or []
        if item.get("strategy_id")
    }
    yaml_artifacts = {
        item.artifact_id.removeprefix("strategy-"): item
        for item in stage03_artifacts.values()
        if item.artifact_id.startswith("strategy-") and item.file_format in {"yaml", "yml"}
    }
    return identities, yaml_artifacts


def _strategy_metric_aggregates(
    records: list[dict[str, Any]],
) -> tuple[StrategyMetricAggregate, ...]:
    rows: list[StrategyMetricAggregate] = []
    for metric_id in _STRATEGY_AGGREGATE_METRICS:
        observed: list[float] = []
        for record in records:
            value = record["metrics"].get(metric_id)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            number = float(value)
            if math.isfinite(number):
                observed.append(number)
        rows.append(
            StrategyMetricAggregate(
                metric_id=metric_id,
                observed_count=len(observed),
                missing_count=len(records) - len(observed),
                mean=statistics.fmean(observed) if observed else None,
                median=statistics.median(observed) if observed else None,
                minimum=min(observed) if observed else None,
                maximum=max(observed) if observed else None,
            )
        )
    return tuple(rows)


def list_filter_strategies(
    run_root: Path,
    *,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
) -> tuple[StrategyProjection, ...]:
    root = run_root.resolve()
    run, _, artifacts = _stage05_sources(root)
    run_key = registry.register(root)
    report = _required_json(root, artifacts, "pilot-filter-report")
    identities, yaml_artifacts = _strategy_identity_sources(root, run, artifacts)
    pilot_records = _all_phase_items(root, artifacts, "pilot")
    records_by_strategy: dict[str, list[dict[str, Any]]] = {}
    for record in pilot_records:
        records_by_strategy.setdefault(record["strategy_id"], []).append(record)
    rows = []
    for item in report.get("strategy_summaries") or []:
        strategy_id = str(item.get("strategy_id"))
        identity = identities.get(strategy_id)
        if identity is None:
            raise ManifestStateError(f"Stage 03 strategy bundle 缺少策略: {strategy_id}")
        yaml_ref = yaml_artifacts.get(strategy_id)
        if yaml_ref is not None and identity.get("design_specification_sha256") != yaml_ref.sha256:
            raise ManifestStateError(f"策略 YAML identity 不一致: {strategy_id}")
        yaml_projection = (
            None
            if yaml_ref is None
            else ArtifactProjection(
                artifact_id=yaml_ref.artifact_id,
                role=yaml_ref.role,
                file_format=yaml_ref.file_format,
                size_bytes=yaml_ref.size_bytes,
                sha256=yaml_ref.sha256,
                token=signer.sign(run_key, yaml_ref),
            )
        )
        rows.append(
            StrategyProjection(
                strategy_id=strategy_id,
                region_id=str(
                    identity.get("source_hotspot_set_id")
                    or identity.get("region_id")
                    or "—"
                ),
                scaffold_id=str(identity.get("scaffold_id") or "—"),
                candidate_count=int(item.get("candidate_count") or 0),
                unique_sequence_count=int(item.get("unique_sequence_count") or 0),
                hard_pass_count=int(item.get("boltzgen_hard_pass_count") or 0),
                final_gate_pass_count=int(item.get("final_gate_pass_count") or 0),
                final_gate_pass_rate=float(item.get("final_gate_pass_rate") or 0),
                tier=str(item.get("tier") or "unknown"),
                score_screen=float(item.get("score_screen_all_median") or 0),
                score_screen_top_quartile_mean=float(
                    item.get("score_screen_top_quartile_mean") or 0
                ),
                score_yaml=float(item.get("score_yaml") or 0),
                selected_for_expansion=bool(item.get("selected_for_expansion")),
                configuration={
                    "hotspot_strategy": identity.get("hotspot_strategy"),
                    "crop_strategy": identity.get("crop_strategy"),
                    "crop_enabled": identity.get("crop_enabled"),
                    "neutral_residue_policy": identity.get("neutral_residue_policy"),
                    "candidates_per_strategy": identity.get("candidates_per_strategy"),
                    "binding_residue_count": len(
                        identity.get("binding_label_seq_ids") or []
                    ),
                },
                metric_aggregates=_strategy_metric_aggregates(
                    records_by_strategy.get(strategy_id, [])
                ),
                yaml_artifact=yaml_projection,
            )
        )
    return tuple(rows)


SORT_FIELDS = {
    "candidate_id",
    "strategy_id",
    "gate_status",
    "score",
    *METRIC_PRESENTATIONS.keys(),
}


def list_filter_candidates(
    run_root: Path,
    *,
    phase: Phase,
    strategy_id: str | None = None,
    gate_status: str | None = None,
    failed_rule: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort_key: str = "candidate_id",
    sort_order: Literal["asc", "desc"] = "asc",
) -> CandidatePage:
    if page < 1:
        raise ValueError("page 必须至少为 1")
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size 必须在 1–100")
    if sort_key not in SORT_FIELDS:
        raise ValueError("sort_key 不在允许列表")
    root = run_root.resolve()
    _, _, artifacts = _stage05_sources(root)
    items = _all_phase_items(root, artifacts, phase)
    if strategy_id:
        items = [item for item in items if item["strategy_id"] == strategy_id]
    if gate_status:
        items = [item for item in items if item["gate_status"] == gate_status]
    if failed_rule:
        items = [item for item in items if failed_rule in item["failed_rules"]]

    def sort_value(item: dict[str, Any]) -> Any:
        value = (
            item.get(sort_key)
            if sort_key in {"candidate_id", "strategy_id", "gate_status", "score"}
            else item["metrics"].get(sort_key)
        )
        return value

    available = [item for item in items if sort_value(item) is not None]
    missing = [item for item in items if sort_value(item) is None]
    available.sort(key=sort_value, reverse=sort_order == "desc")
    items = [*available, *missing]
    total = len(items)
    start = (page - 1) * page_size
    selected = items[start : start + page_size]
    return CandidatePage(
        phase=phase,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
        items=tuple(
            CandidateListItem(
                candidate_id=item["candidate_id"],
                phase=phase,
                strategy_id=item["strategy_id"],
                sequence_length=(
                    len(item["sequence"]) if isinstance(item.get("sequence"), str) else None
                ),
                gate_status=item["gate_status"],
                score=item["score"],
                metrics=item["metrics"],
                failed_rules=item["failed_rules"],
            )
            for item in selected
        ),
    )


def _structure_projection(
    value: Any,
    *,
    root: Path,
    run_key: str,
    signer: ArtifactTokenSigner,
    key: str,
) -> ArtifactProjection | None:
    if not isinstance(value, dict):
        return None
    try:
        ref = ArtifactRef.model_validate(value)
        ref.verify(root)
    except (ValueError, ManifestStateError):
        return None
    return ArtifactProjection(
        artifact_id=key,
        role=ref.role,
        file_format=ref.file_format,
        size_bytes=ref.size_bytes,
        sha256=ref.sha256,
        token=signer.sign(run_key, ref),
    )


def get_filter_candidate(
    run_root: Path,
    candidate_id: str,
    *,
    phase: Phase,
    registry: UiRunRegistry,
    signer: ArtifactTokenSigner,
) -> CandidateDetailProjection:
    root = run_root.resolve()
    run_key = registry.register(root)
    _, _, artifacts = _stage05_sources(root)
    item = next(
        (
            value
            for value in _all_phase_items(root, artifacts, phase)
            if value["candidate_id"] == candidate_id
        ),
        None,
    )
    if item is None:
        raise ValueError("当前阶段和 phase 中不存在该候选")
    structures: dict[str, ArtifactProjection] = {}
    backend = item.get("backend") or {}
    for key, source_key in (
        ("BoltzGen 原始结构", "original_structure"),
        ("BoltzGen 复折叠结构", "refolded_structure"),
    ):
        projection = _structure_projection(
            backend.get(source_key),
            root=root,
            run_key=run_key,
            signer=signer,
            key=source_key,
        )
        if projection is not None:
            structures[key] = projection
    prediction = item.get("prediction") or {}
    projection = _structure_projection(
        prediction.get("predicted_structure"),
        root=root,
        run_key=run_key,
        signer=signer,
        key="protenix-predicted-structure",
    )
    if projection is not None:
        structures["Protenix 预测结构"] = projection

    normalized_metrics: list[dict[str, Any]] = []
    source_by_id = {
        str(metric.get("metric_id")): metric
        for metric in (
            next(
                (
                    record.get("metrics") or []
                    for record in (
                        _required_json(root, artifacts, "pilot-filter-report").get(
                            "candidate_records"
                        )
                        or []
                    )
                    if record.get("candidate_id") == candidate_id
                ),
                [],
            )
        )
    }
    for metric_id, value in item["metrics"].items():
        source = source_by_id.get(metric_id) or {}
        normalized_metrics.append(
            _product_metric(
                metric_id,
                value=value,
                source=source.get("source"),
                unit=source.get("unit"),
                available=bool(source.get("available", value is not None)),
                missing_reason=source.get("missing_reason"),
            )
        )
    return CandidateDetailProjection(
        candidate_id=candidate_id,
        phase=phase,
        strategy_id=item["strategy_id"],
        sequence=item.get("sequence"),
        gate_status=item["gate_status"],
        score=item["score"],
        metrics=tuple(normalized_metrics),
        decisions=tuple(item["decisions"]),
        failed_reasons=tuple(
            str(value.get("reason"))
            for value in item["decisions"]
            if value.get("passed") is False and value.get("reason")
        ),
        backend_metrics=dict(backend.get("metrics") or {}),
        structures=structures,
    )


def metric_catalog(
    run_root: Path,
) -> tuple[MetricPresentation, ...]:
    root = run_root.resolve()
    _, _, artifacts = _stage05_sources(root)
    report = _required_json(root, artifacts, "pilot-filter-report")
    expansion = _optional_json(root, artifacts, "expansion-validation-report") or {}
    decisions: dict[str, dict[str, Any]] = {}
    for record in report.get("candidate_records") or []:
        for item in record.get("hard_gate_decisions") or []:
            decisions.setdefault(str(item.get("metric_id")), item)
    for record in expansion.get("candidates") or []:
        for item in record.get("local_gate_decisions") or []:
            decisions.setdefault(str(item.get("metric_id")), item)
    for record in expansion.get("predictions") or []:
        for item in record.get("structure_gate_decisions") or []:
            decisions.setdefault(str(item.get("metric_id")), item)
    rows = []
    for metric_id, item in METRIC_PRESENTATIONS.items():
        decision = decisions.get(metric_id)
        rows.append(
            MetricPresentation(
                metric_id=metric_id,
                name=str(item["name"]),
                abbreviation=(
                    None if item.get("abbreviation") is None else str(item["abbreviation"])
                ),
                group=str(item["group"]),
                definition=str(item["definition"]),
                unit=None if item.get("unit") is None else str(item["unit"]),
                source=str(item["source"]),
                direction=str(item["direction"]),
                role=str(item["role"]),
                missing_value_policy=MISSING_VALUE_POLICY,
                operator=None if decision is None else str(decision.get("operator")),
                threshold=None if decision is None else decision.get("threshold"),
            )
        )
    return tuple(rows)


__all__ = [
    "get_filter_candidate",
    "get_filter_overview",
    "list_filter_candidates",
    "list_filter_strategies",
    "metric_catalog",
]
