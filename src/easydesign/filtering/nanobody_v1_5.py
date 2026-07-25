"""Nanobody Filter Standard v1.5 pilot gates, scoring, deduplication, and tiers."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from statistics import median

import numpy as np

from easydesign.core import ManifestStateError
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering.models import (
    CandidateFilterRecord,
    ExpansionCandidateRecord,
    ExpansionValidationReport,
    FilterDecision,
    FilterMetric,
    FullTargetPredictionRecord,
    PilotFilterReport,
    StrategyExpansionSummary,
    StrategyFilterSummary,
    StrategyTier,
)

from .structure_metrics import METRIC_DEFINITION_VERSION, InterfaceMetricValues

PROFILE_ID = "nanobody-filter-standard-v1.5"
PROFILE_SOURCE_SHA256 = "c28c82d30420c49d5f55dc2c055c6ee2520e3a7f9ed021c3efcba7681a5be905"


@dataclass(frozen=True, slots=True)
class _ScoredInput:
    candidate: CandidateRecord
    sequence: str
    structure: InterfaceMetricValues
    boltzgen: _BoltzgenValues
    empirical_values: dict[str, float]
    fixed_values: dict[str, float]


@dataclass(frozen=True, slots=True)
class _BoltzgenValues:
    pass_filters: bool
    design_to_target_iptm: float
    min_design_to_target_pae: float
    filter_rmsd: float
    filter_rmsd_design: float
    binder_ptm: float
    delta_sasa_refolded: float


_ProvisionalRecord = tuple[
    _ScoredInput,
    float,
    tuple[FilterMetric, ...],
    tuple[FilterDecision, ...],
]


def _required_number(
    candidate: CandidateRecord,
    name: str,
) -> float:
    value = candidate.metrics.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestStateError(
            f"candidate={candidate.candidate_id} 缺少数值型 BoltzGen metric={name}"
        )
    floating = float(value)
    if not math.isfinite(floating):
        raise ManifestStateError(
            f"candidate={candidate.candidate_id} BoltzGen metric 非有限值: {name}"
        )
    return floating


def _required_sequence(candidate: CandidateRecord) -> str:
    value = candidate.metrics.get("designed_chain_sequence")
    if not isinstance(value, str) or not value:
        raise ManifestStateError(f"candidate={candidate.candidate_id} 缺少 designed_chain_sequence")
    sequence = value.strip().upper()
    if any(character not in "ACDEFGHIKLMNPQRSTVWY" for character in sequence):
        raise ManifestStateError(f"candidate={candidate.candidate_id} binder sequence 含未知残基")
    return sequence


def _up(value: float, gate: float, ideal: float) -> float:
    return min(max((value - gate) / (ideal - gate), 0.0), 1.0)


def _down(value: float, gate: float, ideal: float) -> float:
    return min(max((gate - value) / (gate - ideal), 0.0), 1.0)


def _midrank_percentiles(values: tuple[float, ...]) -> tuple[float, ...]:
    """1%–99% winsorize 后返回 [0,1] 确定性经验 midrank。"""

    if not values:
        return ()
    array = np.asarray(values, dtype=np.float64)
    lower, upper = np.percentile(array, (1.0, 99.0))
    clipped = np.clip(array, lower, upper)
    if np.allclose(clipped, clipped[0]):
        return tuple(0.5 for _ in values)
    result: list[float] = []
    denominator = max(len(clipped) - 1, 1)
    for value in clipped:
        below = int(np.sum(clipped < value))
        equal = int(np.sum(clipped == value))
        average_rank = below + (equal - 1) / 2.0
        result.append(float(average_rank / denominator))
    return tuple(result)


def normalize_up(value: float, gate: float, ideal: float) -> float:
    """Public fixed-range normalization shared by Stage 05 and Stage 07."""

    return _up(value, gate, ideal)


def normalize_down(value: float, gate: float, ideal: float) -> float:
    """Public inverse fixed-range normalization shared by Stage 05 and Stage 07."""

    return _down(value, gate, ideal)


def empirical_midranks(values: tuple[float, ...]) -> tuple[float, ...]:
    """Public 1%–99% winsorized empirical midranks for one frozen pool."""

    return _midrank_percentiles(values)


def empirical_percentile_against_reference(
    value: float,
    reference_values: tuple[float, ...],
) -> float:
    """Score one later prediction against a frozen seed-101 reference pool."""

    if not reference_values:
        raise ManifestStateError("empirical normalization reference 不能为空")
    array = np.asarray(reference_values, dtype=np.float64)
    if any(not math.isfinite(float(item)) for item in array):
        raise ManifestStateError("empirical normalization reference 包含非有限值")
    lower, upper = np.percentile(array, (1.0, 99.0))
    clipped = np.clip(array, lower, upper)
    query = float(np.clip(value, lower, upper))
    if np.allclose(clipped, clipped[0]):
        return 0.5
    below = int(np.sum(clipped < query))
    equal = int(np.sum(clipped == query))
    average_rank = below + max(equal - 1, 0) / 2.0
    return float(average_rank / max(len(clipped) - 1, 1))


def _metric(
    metric_id: str,
    value: float | int | bool | str,
    *,
    source: str,
    unit: str | None = None,
) -> FilterMetric:
    return FilterMetric(
        metric_id=metric_id,
        value=value,
        unit=unit,
        source=source,  # type: ignore[arg-type]
        definition_version=(
            "boltzgen-0.3.2" if source == "boltzgen" else METRIC_DEFINITION_VERSION
        ),
    )


def _decision(
    *,
    rule_id: str,
    metric_id: str,
    operator: str,
    threshold: float | int | bool | str,
    observed: float | int | bool | str,
    passed: bool,
) -> FilterDecision:
    return FilterDecision(
        rule_id=rule_id,
        metric_id=metric_id,
        operator=operator,  # type: ignore[arg-type]
        threshold=threshold,
        observed=observed,
        passed=passed,
        reason=(
            f"{metric_id}={observed!r} 满足 {operator} {threshold!r}"
            if passed
            else f"{metric_id}={observed!r} 不满足 {operator} {threshold!r}"
        ),
    )


def _prepare_candidate(
    candidate: CandidateRecord,
    structure: InterfaceMetricValues,
) -> _ScoredInput:
    pass_filters = candidate.pass_filters
    if pass_filters is None:
        raise ManifestStateError(f"candidate={candidate.candidate_id} 缺少 bool pass_filters")
    boltzgen = _BoltzgenValues(
        pass_filters=pass_filters,
        design_to_target_iptm=_required_number(
            candidate,
            "design_to_target_iptm",
        ),
        min_design_to_target_pae=_required_number(
            candidate,
            "min_design_to_target_pae",
        ),
        filter_rmsd=_required_number(candidate, "filter_rmsd"),
        filter_rmsd_design=_required_number(candidate, "filter_rmsd_design"),
        binder_ptm=_required_number(candidate, "design_ptm"),
        delta_sasa_refolded=_required_number(candidate, "delta_sasa_refolded"),
    )
    interface_bsa = structure.interface_bsa_angstrom2
    if interface_bsa is None:
        interface_bsa = boltzgen.delta_sasa_refolded
    if interface_bsa < 0:
        raise ManifestStateError("interface BSA/fallback 不能为负数")
    if interface_bsa == 0:
        if any(
            value > 0
            for value in (
                structure.residue_pair_contact_count,
                structure.atom_contact_count,
                structure.hydrogen_bond_count,
                structure.salt_bridge_count,
            )
        ):
            raise ManifestStateError("BSA=0 但跨链接触非零，指标定义不一致")
        density_scale = 0.0
    else:
        density_scale = 1000.0 / interface_bsa
    empirical = {
        "interface_bsa": interface_bsa,
        "residue_pair_contact_density": (structure.residue_pair_contact_count * density_scale),
        "atom_contact_density": structure.atom_contact_count * density_scale,
        "hydrogen_bond_density": structure.hydrogen_bond_count * density_scale,
        "salt_bridge_density": structure.salt_bridge_count * density_scale,
    }
    fixed = {
        "hotspot_coverage": _up(structure.hotspot_coverage, 0.40, 1.00),
        "binder_contact_coverage": structure.binder_contact_coverage,
        "cdr_dominance": structure.cdr_dominance,
        "cdr_utilization": structure.cdr_utilization,
        "polar_contact_fraction": structure.polar_contact_fraction,
        "design_to_target_iptm": _up(
            boltzgen.design_to_target_iptm,
            0.50,
            0.85,
        ),
        "min_design_to_target_pae": _down(
            boltzgen.min_design_to_target_pae,
            10.0,
            3.0,
        ),
        "filter_rmsd": _down(boltzgen.filter_rmsd, 2.5, 0.5),
        "filter_rmsd_design": _down(
            boltzgen.filter_rmsd_design,
            2.5,
            0.5,
        ),
        "target_ca_rmsd": _down(structure.target_ca_rmsd_angstrom, 3.0, 0.5),
        "binder_ptm": _up(boltzgen.binder_ptm, 0.75, 0.90),
    }
    return _ScoredInput(
        candidate=candidate,
        sequence=_required_sequence(candidate),
        structure=structure,
        boltzgen=boltzgen,
        empirical_values=empirical,
        fixed_values=fixed,
    )


_SCREEN_WEIGHTS = {
    "interface_bsa": 0.25,
    "residue_pair_contact_density": 0.10,
    "atom_contact_density": 0.05,
    "hotspot_coverage": 0.10,
    "binder_contact_coverage": 0.05,
    "cdr_dominance": 0.07,
    "cdr_utilization": 0.06,
    "hydrogen_bond_density": 0.05,
    "salt_bridge_density": 0.04,
    "polar_contact_fraction": 0.03,
    "design_to_target_iptm": 0.06,
    "min_design_to_target_pae": 0.04,
    "filter_rmsd": 0.04,
    "filter_rmsd_design": 0.02,
    "target_ca_rmsd": 0.02,
    "binder_ptm": 0.02,
}


def evaluate_pilot_candidates(
    *,
    candidates: tuple[CandidateRecord, ...],
    structural_metrics: dict[str, InterfaceMetricValues],
    profile_sha256: str,
    candidate_index_sha256: str,
    maximum_tier_a_strategies: int,
    generated_at: datetime,
) -> PilotFilterReport:
    """应用完整 pilot gate、S_screen、序列去重、Tier 和 F_YAML。"""

    if not candidates:
        raise ManifestStateError("Stage 05 pilot filtering 没有 candidate")
    if profile_sha256 != PROFILE_SOURCE_SHA256:
        raise ManifestStateError("Nanobody Filter Standard v1.5 profile SHA-256 不匹配")
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    if set(structural_metrics) != candidate_ids:
        raise ManifestStateError("structural metric candidate identity 与 CandidateIndex 不一致")
    prepared = tuple(
        _prepare_candidate(candidate, structural_metrics[candidate.candidate_id])
        for candidate in candidates
    )
    empirical_names = (
        "interface_bsa",
        "residue_pair_contact_density",
        "atom_contact_density",
        "hydrogen_bond_density",
        "salt_bridge_density",
    )
    empirical_normalized: dict[str, dict[str, float]] = {
        item.candidate.candidate_id: {} for item in prepared
    }
    for name in empirical_names:
        values = tuple(item.empirical_values[name] for item in prepared)
        percentiles = _midrank_percentiles(values)
        for item, value in zip(prepared, percentiles, strict=True):
            empirical_normalized[item.candidate.candidate_id][name] = value

    provisional: dict[str, _ProvisionalRecord] = {}
    for item in prepared:
        candidate_id = item.candidate.candidate_id
        normalized = {
            **item.fixed_values,
            **empirical_normalized[candidate_id],
        }
        score = sum(_SCREEN_WEIGHTS[name] * normalized[name] for name in _SCREEN_WEIGHTS)
        structure = item.structure
        boltzgen = item.boltzgen
        bsa_source = (
            "easydesign-structure" if structure.interface_bsa_angstrom2 is not None else "boltzgen"
        )
        metrics: tuple[FilterMetric, ...] = (
            _metric(
                "pass-filters",
                boltzgen.pass_filters,
                source="boltzgen",
            ),
            _metric(
                "hotspot-coverage",
                structure.hotspot_coverage,
                source="easydesign-structure",
                unit="fraction",
            ),
            _metric(
                "design-to-target-iptm",
                boltzgen.design_to_target_iptm,
                source="boltzgen",
            ),
            _metric(
                "min-design-to-target-pae",
                boltzgen.min_design_to_target_pae,
                source="boltzgen",
                unit="angstrom",
            ),
            _metric(
                "filter-rmsd",
                boltzgen.filter_rmsd,
                source="boltzgen",
                unit="angstrom",
            ),
            _metric(
                "filter-rmsd-design",
                boltzgen.filter_rmsd_design,
                source="boltzgen",
                unit="angstrom",
            ),
            _metric(
                "target-ca-rmsd",
                structure.target_ca_rmsd_angstrom,
                source="easydesign-structure",
                unit="angstrom",
            ),
            _metric(
                "binder-ptm",
                boltzgen.binder_ptm,
                source="boltzgen",
            ),
            _metric(
                "severe-clash-count",
                structure.severe_clash_count,
                source="easydesign-structure",
                unit="atom-pairs",
            ),
            _metric(
                "moderate-clash-count",
                structure.moderate_clash_count,
                source="easydesign-structure",
                unit="atom-pairs",
            ),
            _metric(
                "interface-bsa",
                item.empirical_values["interface_bsa"],
                source=bsa_source,
                unit="angstrom2",
            ),
            _metric(
                "interface-bsa-fallback-used",
                structure.interface_bsa_angstrom2 is None,
                source="derived",
            ),
            _metric(
                "residue-pair-contact-count",
                structure.residue_pair_contact_count,
                source="easydesign-structure",
                unit="residue-pairs",
            ),
            _metric(
                "atom-contact-count",
                structure.atom_contact_count,
                source="easydesign-structure",
                unit="atom-pairs",
            ),
            _metric(
                "binder-contact-coverage",
                structure.binder_contact_coverage,
                source="easydesign-structure",
                unit="fraction",
            ),
            _metric(
                "cdr-dominance",
                structure.cdr_dominance,
                source="easydesign-structure",
                unit="fraction",
            ),
            _metric(
                "cdr-utilization",
                structure.cdr_utilization,
                source="easydesign-structure",
                unit="fraction",
            ),
            _metric(
                "hydrogen-bond-count",
                structure.hydrogen_bond_count,
                source="easydesign-structure",
                unit="atom-pairs",
            ),
            _metric(
                "salt-bridge-count",
                structure.salt_bridge_count,
                source="easydesign-structure",
                unit="atom-pairs",
            ),
            _metric(
                "polar-contact-fraction",
                structure.polar_contact_fraction,
                source="easydesign-structure",
                unit="fraction",
            ),
        )
        decisions: tuple[FilterDecision, ...] = (
            _decision(
                rule_id="require-boltzgen-pass",
                metric_id="pass-filters",
                operator="eq",
                threshold=True,
                observed=boltzgen.pass_filters,
                passed=boltzgen.pass_filters,
            ),
            _decision(
                rule_id="require-hotspot-coverage",
                metric_id="hotspot-coverage",
                operator="ge",
                threshold=0.40,
                observed=structure.hotspot_coverage,
                passed=structure.hotspot_coverage >= 0.40,
            ),
            _decision(
                rule_id="require-iptm",
                metric_id="design-to-target-iptm",
                operator="ge",
                threshold=0.50,
                observed=boltzgen.design_to_target_iptm,
                passed=boltzgen.design_to_target_iptm >= 0.50,
            ),
            _decision(
                rule_id="require-interface-pae",
                metric_id="min-design-to-target-pae",
                operator="le",
                threshold=10.0,
                observed=boltzgen.min_design_to_target_pae,
                passed=boltzgen.min_design_to_target_pae <= 10.0,
            ),
            _decision(
                rule_id="require-target-rmsd",
                metric_id="target-ca-rmsd",
                operator="le",
                threshold=3.0,
                observed=structure.target_ca_rmsd_angstrom,
                passed=structure.target_ca_rmsd_angstrom <= 3.0,
            ),
            _decision(
                rule_id="forbid-severe-clash",
                metric_id="severe-clash-count",
                operator="eq",
                threshold=0,
                observed=structure.severe_clash_count,
                passed=structure.severe_clash_count == 0,
            ),
            _decision(
                rule_id="limit-moderate-clash",
                metric_id="moderate-clash-count",
                operator="le",
                threshold=3,
                observed=structure.moderate_clash_count,
                passed=structure.moderate_clash_count <= 3,
            ),
        )
        provisional[candidate_id] = (item, score, metrics, decisions)

    representative_by_sequence: dict[tuple[str, str], str] = {}
    for item, score, _, decisions in provisional.values():
        key = (item.candidate.strategy_id, item.sequence)
        existing = representative_by_sequence.get(key)
        if existing is None:
            representative_by_sequence[key] = item.candidate.candidate_id
            continue
        existing_item = provisional[existing]
        current_rank = (
            all(decision.passed for decision in decisions),
            score,
            item.candidate.candidate_id,
        )
        existing_rank = (
            all(decision.passed for decision in existing_item[3]),
            existing_item[1],
            existing,
        )
        if current_rank > existing_rank:
            representative_by_sequence[key] = item.candidate.candidate_id

    records: list[CandidateFilterRecord] = []
    for candidate in candidates:
        item, score, metrics, gate_decisions = provisional[candidate.candidate_id]
        representative = representative_by_sequence[(candidate.strategy_id, item.sequence)]
        duplicate_of = None if representative == candidate.candidate_id else representative
        unique_decision = _decision(
            rule_id="deduplicate-sequence",
            metric_id="binder-sequence",
            operator="unique",
            threshold="unique-within-strategy",
            observed=("unique" if duplicate_of is None else f"duplicate-of:{duplicate_of}"),
            passed=duplicate_of is None,
        )
        hard_pass = all(decision.passed for decision in gate_decisions)
        records.append(
            CandidateFilterRecord(
                candidate_id=candidate.candidate_id,
                strategy_id=candidate.strategy_id,
                sequence=item.sequence,
                sequence_sha256=hashlib.sha256(item.sequence.encode()).hexdigest(),
                metrics=metrics,
                hard_gate_decisions=(*gate_decisions, unique_decision),
                hard_gate_pass=hard_pass,
                duplicate_of=duplicate_of,
                eligible_unique_pass=hard_pass and duplicate_of is None,
                score_screen=score,
                normalization_group="pilot-full-target",
            )
        )

    summaries: list[StrategyFilterSummary] = []
    strategy_ids = tuple(dict.fromkeys(candidate.strategy_id for candidate in candidates))
    for strategy_id in strategy_ids:
        strategy_records = tuple(record for record in records if record.strategy_id == strategy_id)
        unique_records = tuple(record for record in strategy_records if record.duplicate_of is None)
        qualified = tuple(record for record in unique_records if record.eligible_unique_pass)
        boltzgen_pass = sum(
            1
            for record in unique_records
            if next(metric for metric in record.metrics if metric.metric_id == "pass-filters").value
            is True
        )
        final_pass = len(qualified)
        tier = (
            StrategyTier.A
            if final_pass >= 2
            else (
                StrategyTier.B
                if final_pass == 1
                else StrategyTier.C
                if boltzgen_pass >= 2
                else StrategyTier.D
            )
        )
        qualified_scores = sorted(
            (record.score_screen for record in qualified),
            reverse=True,
        )
        top_count = max(math.ceil(len(qualified_scores) * 0.25), 1)
        top_mean = sum(qualified_scores[:top_count]) / top_count if qualified_scores else 0.0
        all_median = float(median(record.score_screen for record in unique_records))
        pass_rate = final_pass / len(unique_records)
        score_yaml = 0.40 * pass_rate + 0.35 * top_mean + 0.25 * all_median
        summaries.append(
            StrategyFilterSummary(
                strategy_id=strategy_id,
                candidate_count=len(strategy_records),
                unique_sequence_count=len(unique_records),
                boltzgen_hard_pass_count=boltzgen_pass,
                final_gate_pass_count=final_pass,
                final_gate_pass_rate=pass_rate,
                score_screen_top_quartile_mean=top_mean,
                score_screen_all_median=all_median,
                score_yaml=score_yaml,
                tier=tier,
            )
        )
    summaries.sort(
        key=lambda summary: (
            {
                StrategyTier.A: 0,
                StrategyTier.B: 1,
                StrategyTier.C: 2,
                StrategyTier.D: 3,
            }[summary.tier],
            -summary.score_yaml,
            summary.strategy_id,
        )
    )
    selected_ids = tuple(
        summary.strategy_id for summary in summaries if summary.tier is StrategyTier.A
    )[:maximum_tier_a_strategies]
    finalized_summaries = tuple(
        summary.model_copy(update={"selected_for_expansion": summary.strategy_id in selected_ids})
        for summary in summaries
    )
    return PilotFilterReport(
        generated_at=generated_at,
        profile_sha256=profile_sha256,
        candidate_index_sha256=candidate_index_sha256,
        candidate_records=tuple(records),
        strategy_summaries=finalized_summaries,
        selected_strategy_ids=selected_ids,
        status="tier-a-selected" if selected_ids else "stopped-no-tier-a",
    )


_EXPANSION_WEIGHTS = {
    "design_to_target_iptm": 0.10,
    "min_design_to_target_pae": 0.10,
    "filter_rmsd": 0.30,
    "filter_rmsd_design": 0.25,
    "target_ca_rmsd": 0.20,
    "binder_ptm": 0.05,
}


def evaluate_expansion_candidates(
    *,
    candidates: tuple[CandidateRecord, ...],
    structural_metrics: dict[str, InterfaceMetricValues],
    full_target_top_n: int,
) -> tuple[ExpansionCandidateRecord, ...]:
    """Apply the v1.5 local gate and S_expand_structure within each strategy."""

    if not candidates or full_target_top_n < 1:
        raise ManifestStateError("expansion evaluation 需要 candidate 且 top_n > 0")
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    if set(structural_metrics) != candidate_ids:
        raise ManifestStateError("expansion structural metrics 与 CandidateIndex 不一致")
    provisional: dict[str, ExpansionCandidateRecord] = {}
    for candidate in candidates:
        prepared = _prepare_candidate(
            candidate,
            structural_metrics[candidate.candidate_id],
        )
        structure = prepared.structure
        boltzgen = prepared.boltzgen
        decisions = (
            _decision(
                rule_id="require-boltzgen-pass",
                metric_id="pass-filters",
                operator="eq",
                threshold=True,
                observed=boltzgen.pass_filters,
                passed=boltzgen.pass_filters,
            ),
            _decision(
                rule_id="require-target-ca-rmsd",
                metric_id="target-ca-rmsd",
                operator="le",
                threshold=3.0,
                observed=structure.target_ca_rmsd_angstrom,
                passed=structure.target_ca_rmsd_angstrom <= 3.0,
            ),
            _decision(
                rule_id="require-zero-severe-clash",
                metric_id="severe-clash-count",
                operator="eq",
                threshold=0,
                observed=structure.severe_clash_count,
                passed=structure.severe_clash_count == 0,
            ),
            _decision(
                rule_id="limit-moderate-clash",
                metric_id="moderate-clash-count",
                operator="le",
                threshold=3,
                observed=structure.moderate_clash_count,
                passed=structure.moderate_clash_count <= 3,
            ),
        )
        normalized = {
            "design_to_target_iptm": _up(
                boltzgen.design_to_target_iptm,
                0.50,
                0.85,
            ),
            "min_design_to_target_pae": _down(
                boltzgen.min_design_to_target_pae,
                10.0,
                3.0,
            ),
            "filter_rmsd": _down(boltzgen.filter_rmsd, 2.5, 0.5),
            "filter_rmsd_design": _down(
                boltzgen.filter_rmsd_design,
                2.5,
                0.5,
            ),
            "target_ca_rmsd": _down(
                structure.target_ca_rmsd_angstrom,
                3.0,
                0.5,
            ),
            "binder_ptm": _up(boltzgen.binder_ptm, 0.75, 0.90),
        }
        score = sum(_EXPANSION_WEIGHTS[name] * normalized[name] for name in _EXPANSION_WEIGHTS)
        provisional[candidate.candidate_id] = ExpansionCandidateRecord(
            candidate_id=candidate.candidate_id,
            strategy_id=candidate.strategy_id,
            sequence=prepared.sequence,
            sequence_sha256=hashlib.sha256(prepared.sequence.encode()).hexdigest(),
            local_gate_decisions=decisions,
            local_gate_pass=all(decision.passed for decision in decisions),
            score_expand_structure=score,
        )
    selected: set[str] = set()
    strategy_ids = sorted({candidate.strategy_id for candidate in candidates})
    for strategy_id in strategy_ids:
        passing = sorted(
            (
                record
                for record in provisional.values()
                if record.strategy_id == strategy_id and record.local_gate_pass
            ),
            key=lambda item: (-item.score_expand_structure, item.candidate_id),
        )
        selected.update(item.candidate_id for item in passing[:full_target_top_n])
    return tuple(
        provisional[candidate.candidate_id].model_copy(
            update={
                "selected_for_full_target": candidate.candidate_id in selected,
            }
        )
        for candidate in sorted(
            candidates,
            key=lambda item: (item.strategy_id, item.ordinal_within_strategy),
        )
    )


def select_scale_strategy(
    *,
    expanded_total_per_strategy: int,
    full_target_top_n: int,
    candidates: tuple[ExpansionCandidateRecord, ...],
    predictions: tuple[FullTargetPredictionRecord, ...],
    generated_at: datetime,
) -> ExpansionValidationReport:
    """Rank strategies only after full-target structure validation."""

    candidate_by_id = {item.candidate_id: item for item in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ManifestStateError("expansion candidate_id 不能重复")
    selected = {item.candidate_id for item in candidates if item.selected_for_full_target}
    predicted = {item.candidate_id for item in predictions}
    if predicted != selected:
        raise ManifestStateError("full-target prediction 必须覆盖全部且仅覆盖 selected candidate")
    by_strategy: dict[str, list[ExpansionCandidateRecord]] = {}
    predictions_by_strategy: dict[str, list[FullTargetPredictionRecord]] = {}
    for candidate_record in candidates:
        by_strategy.setdefault(candidate_record.strategy_id, []).append(candidate_record)
    for prediction_record in predictions:
        predictions_by_strategy.setdefault(
            prediction_record.strategy_id,
            [],
        ).append(prediction_record)
    summaries: list[StrategyExpansionSummary] = []
    for strategy_id in sorted(by_strategy):
        group = by_strategy[strategy_id]
        if len(group) != expanded_total_per_strategy:
            raise ManifestStateError(
                f"strategy={strategy_id} expansion 未达到 {expanded_total_per_strategy}"
            )
        selected_group = [item for item in group if item.selected_for_full_target]
        predicted_group = predictions_by_strategy.get(strategy_id, [])
        passing = [item for item in predicted_group if item.structure_gate_pass]
        median_passing = (
            float(median(item.binder_pose_rmsd_angstrom for item in passing)) if passing else None
        )
        mean_score = (
            float(sum(item.score_expand_structure for item in selected_group) / len(selected_group))
            if selected_group
            else 0.0
        )
        summaries.append(
            StrategyExpansionSummary(
                strategy_id=strategy_id,
                complete_candidate_count=len(group),
                local_gate_pass_count=sum(item.local_gate_pass for item in group),
                selected_for_full_target_count=len(selected_group),
                full_target_pass_count=len(passing),
                full_target_pass_rate=(
                    len(passing) / len(predicted_group) if predicted_group else 0.0
                ),
                median_passing_binder_pose_rmsd_angstrom=median_passing,
                mean_selected_score_expand_structure=mean_score,
                eligible_for_scale=bool(passing),
            )
        )
    eligible = [item for item in summaries if item.eligible_for_scale]
    winner_id: str | None = None
    if eligible:

        def scientific_rank(item: StrategyExpansionSummary) -> tuple[float, ...]:
            return (
                -item.full_target_pass_count,
                -item.full_target_pass_rate,
                (
                    item.median_passing_binder_pose_rmsd_angstrom
                    if item.median_passing_binder_pose_rmsd_angstrom is not None
                    else math.inf
                ),
                -item.mean_selected_score_expand_structure,
            )

        ranked = sorted(
            eligible,
            key=lambda item: (*scientific_rank(item), item.strategy_id),
        )
        if len(ranked) == 1 or scientific_rank(ranked[0]) != scientific_rank(ranked[1]):
            winner_id = ranked[0].strategy_id
            summaries = [
                item.model_copy(update={"winner": item.strategy_id == winner_id})
                for item in summaries
            ]
    return ExpansionValidationReport(
        generated_at=generated_at,
        expanded_total_per_strategy=expanded_total_per_strategy,
        full_target_refold_top_n=full_target_top_n,
        candidates=candidates,
        predictions=predictions,
        strategies=tuple(summaries),
        winner_strategy_id=winner_id,
        status=("winner-selected" if winner_id is not None else "stopped-no-scale-winner"),
    )
