"""Deterministic Nanobody Final v1.5 prefilter, scoring, consensus, and diversity."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from statistics import median

from Bio import Align

from easydesign.core import ManifestStateError
from easydesign.stages.s04_pilot_generation import CandidateRecord
from easydesign.stages.s05_pilot_filtering import (
    CandidateFilterRecord,
    FilterDecision,
    FilterMetric,
)
from easydesign.stages.s07_final_filtering_and_selection import (
    DeepFilterRecord,
    DevelopabilityRisk,
    FinalPredictionRecord,
    FinalSelectionRecord,
    MultiSeedConsensusRecord,
    SeedPairConsistency,
    SequenceLiability,
    SequencePrefilterRecord,
    TnpCandidateRecord,
)

from .nanobody_v1_5 import (
    empirical_percentile_against_reference,
    normalize_down,
    normalize_up,
)
from .structure_metrics import InterfaceMetricValues

FINAL_PROFILE_ID = "nanobody-final-v1.5"
FINAL_PROFILE_SOURCE_SHA256 = "c28c82d30420c49d5f55dc2c055c6ee2520e3a7f9ed021c3efcba7681a5be905"
FINAL_PROFILE_ID_V1_6 = "nanobody-final-v1.6"
FINAL_PROFILE_SOURCE_SHA256_V1_6 = (
    "e086b3daf6e59ad1d7a57a39cf982a49a952aacbb37a30bc9e98f648265aafaa"
)
FINAL_METRIC_DEFINITION_VERSION = "nanobody-final-v1.5"
MAXIMUM_DEEP_CANDIDATES = 20_000
SEED101_TOP_N = 400
MULTI_SEED_TOP_N = 60

_VALID_AA = frozenset("ACDEFGHIKLMNPQRSTVWY")
_LIABILITY_PATTERNS = (
    ("n-linked-glycosylation", "N-linked glycosylation motif", re.compile(r"N[^P][ST]")),
    ("met-oxidation", "Methionine oxidation warning", re.compile(r"M")),
    ("trp-oxidation", "Tryptophan oxidation warning", re.compile(r"W")),
    ("asn-deamidation", "Asparagine deamidation warning", re.compile(r"N[GST]")),
    ("asp-isomerisation", "Aspartate isomerisation warning", re.compile(r"D[GSTDH]")),
    ("lysine-glycation", "Lysine glycation warning", re.compile(r"KE|KD|EK|ED")),
    ("fragmentation", "Asp-Pro fragmentation warning", re.compile(r"DP")),
)


@dataclass(frozen=True, slots=True)
class FullPredictionEvidence:
    candidate_id: str
    seed: int
    pairwise_iptm: float
    minimum_interface_pae_angstrom: float
    binder_ptm: float
    binder_pose_rmsd_angstrom: float
    target_ca_rmsd_angstrom: float
    contacted_hotspot_residue_ids: tuple[int, ...]
    interface: InterfaceMetricValues
    confidence_metric_definition_version: str = (
        "protenix-v2-complex-confidence-v1"
    )


def _required_number(candidate: CandidateRecord, name: str) -> float:
    value = candidate.metrics.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestStateError(
            f"candidate={candidate.candidate_id} 缺少数值型 BoltzGen metric={name}"
        )
    result = float(value)
    if not math.isfinite(result):
        raise ManifestStateError(f"candidate={candidate.candidate_id} metric={name} 非有限值")
    return result


def _required_text(candidate: CandidateRecord, name: str) -> str:
    value = candidate.metrics.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ManifestStateError(
            f"candidate={candidate.candidate_id} 缺少字符串 BoltzGen metric={name}"
        )
    return value.strip().upper()


def _decision(
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


def _metric(
    metric_id: str,
    value: float | int | bool | str,
    *,
    source: str,
    unit: str | None = None,
    definition_version: str | None = None,
) -> FilterMetric:
    return FilterMetric(
        metric_id=metric_id,
        value=value,
        source=source,  # type: ignore[arg-type]
        unit=unit,
        definition_version=definition_version
        or (
            "protenix-v2-complex-confidence-v1"
            if source == "derived"
            else ("interface-geometry-v1" if source == "easydesign-structure" else "boltzgen-0.3.2")
        ),
    )


def _sequence_liabilities(sequence: str) -> tuple[SequenceLiability, ...]:
    results: list[SequenceLiability] = []
    for liability_id, name, pattern in _LIABILITY_PATTERNS:
        for match in pattern.finditer(sequence):
            results.append(
                SequenceLiability(
                    liability_id=liability_id,
                    name=name,
                    sequence_start=match.start() + 1,
                    sequence_end=match.end(),
                    matched_sequence=match.group(0),
                    evidence_scope="full-sequence-warning",
                )
            )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.sequence_start,
                item.sequence_end,
                item.liability_id,
            ),
        )
    )


def _score_refold(candidate: CandidateRecord) -> float:
    values = (
        0.35
        * normalize_up(
            _required_number(candidate, "design_to_target_iptm"),
            0.50,
            0.85,
        ),
        0.10
        * normalize_down(
            _required_number(candidate, "min_design_to_target_pae"),
            10.0,
            3.0,
        ),
        0.25
        * normalize_down(
            _required_number(candidate, "filter_rmsd"),
            2.5,
            0.5,
        ),
        0.15
        * normalize_down(
            _required_number(candidate, "filter_rmsd_design"),
            2.5,
            0.5,
        ),
        0.15
        * normalize_up(
            _required_number(candidate, "design_ptm"),
            0.75,
            0.90,
        ),
    )
    return float(sum(values))


def evaluate_sequence_prefilter(
    *,
    candidates: tuple[CandidateRecord, ...],
    unpaired_new_cysteines: dict[str, tuple[int, ...]],
    maximum_deep_candidates: int = MAXIMUM_DEEP_CANDIDATES,
) -> tuple[SequencePrefilterRecord, ...]:
    """Apply sequence legality, new-Cys, BoltzGen, dedup, and S_refold."""

    if maximum_deep_candidates < 1:
        raise ManifestStateError("maximum deep candidates 必须为正整数")
    prepared: list[tuple[CandidateRecord, str, str, int, tuple[int, ...], float]] = []
    for candidate in candidates:
        sequence = _required_text(candidate, "designed_chain_sequence")
        design_sequence = _required_text(candidate, "designed_sequence")
        unknown_count = sum(item not in _VALID_AA for item in sequence)
        cysteines = unpaired_new_cysteines.get(candidate.candidate_id)
        if cysteines is None:
            raise ManifestStateError(f"candidate={candidate.candidate_id} 缺少新生 Cys 结构审计")
        prepared.append(
            (
                candidate,
                sequence,
                design_sequence,
                unknown_count,
                cysteines,
                _score_refold(candidate),
            )
        )

    representatives: dict[str, str] = {}
    for candidate, sequence, _, unknown_count, cysteines, _score in sorted(
        prepared,
        key=lambda item: (-item[5], item[0].candidate_id),
    ):
        base_pass = unknown_count == 0 and not cysteines and candidate.pass_filters is True
        if base_pass and sequence not in representatives:
            representatives[sequence] = candidate.candidate_id

    provisional: list[SequencePrefilterRecord] = []
    for candidate, sequence, design_sequence, unknown_count, cysteines, score in prepared:
        representative = representatives.get(sequence)
        duplicate_of = (
            representative
            if representative is not None and representative != candidate.candidate_id
            else None
        )
        decisions = (
            _decision(
                "require-standard-amino-acids",
                "unknown-residue-count",
                "eq",
                0,
                unknown_count,
                unknown_count == 0,
            ),
            _decision(
                "require-no-unpaired-new-cysteine",
                "unpaired-new-cysteine-count",
                "eq",
                0,
                len(cysteines),
                not cysteines,
            ),
            _decision(
                "require-boltzgen-pass-filters",
                "pass-filters",
                "eq",
                True,
                candidate.pass_filters is True,
                candidate.pass_filters is True,
            ),
            _decision(
                "require-unique-full-binder-sequence",
                "sequence-sha256",
                "unique",
                "unique",
                (
                    hashlib.sha256(sequence.encode("ascii")).hexdigest()
                    if duplicate_of is None
                    else duplicate_of
                ),
                duplicate_of is None,
            ),
        )
        provisional.append(
            SequencePrefilterRecord(
                candidate_id=candidate.candidate_id,
                strategy_id=candidate.strategy_id,
                sequence=sequence,
                sequence_sha256=hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                design_sequence=design_sequence,
                unknown_residue_count=unknown_count,
                unpaired_new_cysteine_residue_ids=cysteines,
                liabilities=_sequence_liabilities(sequence),
                duplicate_of=duplicate_of,
                decisions=decisions,
                hard_pass=all(item.passed for item in decisions),
                score_refold=score,
            )
        )
    selected = {
        item.candidate_id
        for item in sorted(
            (item for item in provisional if item.hard_pass),
            key=lambda item: (-item.score_refold, item.candidate_id),
        )[:maximum_deep_candidates]
    }
    return tuple(
        item.model_copy(update={"selected_for_deep": item.candidate_id in selected})
        for item in provisional
    )


def convert_deep_filter_records(
    *,
    pilot_records: tuple[CandidateFilterRecord, ...],
    seed101_top_n: int = SEED101_TOP_N,
) -> tuple[DeepFilterRecord, ...]:
    """Convert the shared absolute-gate/S_screen evaluator into S_deep records."""

    converted: list[DeepFilterRecord] = []
    for value in pilot_records:
        converted.append(
            DeepFilterRecord(
                candidate_id=value.candidate_id,
                metrics=value.metrics,
                decisions=value.hard_gate_decisions,
                absolute_gate_pass=value.eligible_unique_pass,
                score_deep=value.score_screen,
            )
        )
    selected = {
        item.candidate_id
        for item in sorted(
            (item for item in converted if item.absolute_gate_pass),
            key=lambda item: (-item.score_deep, item.candidate_id),
        )[:seed101_top_n]
    }
    return tuple(
        item.model_copy(update={"selected_for_seed101": item.candidate_id in selected})
        for item in converted
    )


_EMPIRICAL_KEYS = (
    "interface_bsa",
    "residue_pair_contact_density",
    "atom_contact_density",
    "hydrogen_bond_density",
    "salt_bridge_density",
)
_FULL_WEIGHTS = {
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
    "pairwise_iptm": 0.06,
    "minimum_interface_pae": 0.04,
    "binder_pose_rmsd": 0.04,
    "target_ca_rmsd": 0.02,
    "binder_ptm": 0.02,
    "score_refold": 0.02,
}


def _full_components(
    evidence: FullPredictionEvidence,
    score_refold: float,
) -> tuple[dict[str, float], dict[str, float]]:
    bsa = evidence.interface.interface_bsa_angstrom2
    if bsa is None:
        raise ManifestStateError(
            "full-target S_full 必须有标准 interface BSA；不能跨模型回退 BoltzGen BSA"
        )
    scale = 1000.0 / bsa if bsa > 0 else 0.0
    empirical = {
        "interface_bsa": bsa,
        "residue_pair_contact_density": (evidence.interface.residue_pair_contact_count * scale),
        "atom_contact_density": evidence.interface.atom_contact_count * scale,
        "hydrogen_bond_density": (evidence.interface.hydrogen_bond_count * scale),
        "salt_bridge_density": evidence.interface.salt_bridge_count * scale,
    }
    fixed = {
        "hotspot_coverage": normalize_up(
            evidence.interface.hotspot_coverage,
            0.40,
            1.00,
        ),
        "binder_contact_coverage": evidence.interface.binder_contact_coverage,
        "cdr_dominance": evidence.interface.cdr_dominance,
        "cdr_utilization": evidence.interface.cdr_utilization,
        "polar_contact_fraction": evidence.interface.polar_contact_fraction,
        "pairwise_iptm": normalize_up(evidence.pairwise_iptm, 0.60, 0.85),
        "minimum_interface_pae": normalize_down(
            evidence.minimum_interface_pae_angstrom,
            10.0,
            3.0,
        ),
        "binder_pose_rmsd": normalize_down(
            evidence.binder_pose_rmsd_angstrom,
            3.0,
            0.5,
        ),
        "target_ca_rmsd": normalize_down(
            evidence.target_ca_rmsd_angstrom,
            3.0,
            0.5,
        ),
        "binder_ptm": normalize_up(evidence.binder_ptm, 0.60, 0.90),
        "score_refold": score_refold,
    }
    return empirical, fixed


def score_full_prediction_evidence(
    *,
    evidence: tuple[FullPredictionEvidence, ...],
    score_refold_by_candidate: dict[str, float],
    seed101_reference: dict[str, tuple[float, ...]] | None = None,
) -> tuple[dict[tuple[str, int], float], dict[str, tuple[float, ...]]]:
    """Compute S_full and freeze/consume seed-101 empirical normalization."""

    components: dict[tuple[str, int], tuple[dict[str, float], dict[str, float]]] = {}
    for item in evidence:
        try:
            score_refold = score_refold_by_candidate[item.candidate_id]
        except KeyError as error:
            raise ManifestStateError(f"candidate={item.candidate_id} 缺少 S_refold") from error
        components[(item.candidate_id, item.seed)] = _full_components(
            item,
            score_refold,
        )
    if seed101_reference is None:
        seed101 = [value for key, value in components.items() if key[1] == 101]
        if not seed101:
            raise ManifestStateError("S_full 缺少 seed 101 normalization pool")
        reference = {key: tuple(item[0][key] for item in seed101) for key in _EMPIRICAL_KEYS}
    else:
        reference = seed101_reference
        if set(reference) != set(_EMPIRICAL_KEYS):
            raise ManifestStateError("S_full seed101 normalization keys 不完整")
    scores: dict[tuple[str, int], float] = {}
    for identity, (empirical, fixed) in components.items():
        values = {
            key: empirical_percentile_against_reference(
                value,
                reference[key],
            )
            for key, value in empirical.items()
        }
        values.update(fixed)
        scores[identity] = float(sum(_FULL_WEIGHTS[key] * values[key] for key in _FULL_WEIGHTS))
    return scores, reference


def final_prediction_decisions(
    evidence: FullPredictionEvidence,
    *,
    consensus: bool,
) -> tuple[FilterDecision, ...]:
    pae_threshold = 7.0 if consensus else 10.0
    pose_threshold = 2.5 if consensus else 3.0
    return (
        _decision(
            "require-pairwise-iptm",
            "pairwise-iptm",
            "ge",
            0.60,
            evidence.pairwise_iptm,
            evidence.pairwise_iptm >= 0.60,
        ),
        _decision(
            "limit-interface-pae",
            "minimum-interface-pae",
            "le",
            pae_threshold,
            evidence.minimum_interface_pae_angstrom,
            evidence.minimum_interface_pae_angstrom <= pae_threshold,
        ),
        _decision(
            "limit-binder-pose-rmsd",
            "binder-pose-rmsd",
            "le",
            pose_threshold,
            evidence.binder_pose_rmsd_angstrom,
            evidence.binder_pose_rmsd_angstrom <= pose_threshold,
        ),
        _decision(
            "limit-target-ca-rmsd",
            "target-ca-rmsd",
            "le",
            3.0,
            evidence.target_ca_rmsd_angstrom,
            evidence.target_ca_rmsd_angstrom <= 3.0,
        ),
        _decision(
            "require-binder-ptm",
            "binder-ptm",
            "ge",
            0.60,
            evidence.binder_ptm,
            evidence.binder_ptm >= 0.60,
        ),
        _decision(
            "require-full-target-hotspot-coverage",
            "hotspot-coverage",
            "ge",
            0.40,
            evidence.interface.hotspot_coverage,
            evidence.interface.hotspot_coverage >= 0.40,
        ),
        _decision(
            "require-zero-severe-clash",
            "severe-clash-count",
            "eq",
            0,
            evidence.interface.severe_clash_count,
            evidence.interface.severe_clash_count == 0,
        ),
        _decision(
            "limit-moderate-clash",
            "moderate-clash-count",
            "le",
            3,
            evidence.interface.moderate_clash_count,
            evidence.interface.moderate_clash_count <= 3,
        ),
    )


def final_prediction_metrics(
    evidence: FullPredictionEvidence,
) -> tuple[FilterMetric, ...]:
    interface = evidence.interface
    return (
        _metric(
            "pairwise-iptm",
            evidence.pairwise_iptm,
            source="derived",
            definition_version=evidence.confidence_metric_definition_version,
        ),
        _metric(
            "minimum-interface-pae",
            evidence.minimum_interface_pae_angstrom,
            source="derived",
            unit="angstrom",
            definition_version=evidence.confidence_metric_definition_version,
        ),
        _metric(
            "binder-ptm",
            evidence.binder_ptm,
            source="derived",
            definition_version=evidence.confidence_metric_definition_version,
        ),
        _metric(
            "binder-pose-rmsd",
            evidence.binder_pose_rmsd_angstrom,
            source="easydesign-structure",
            unit="angstrom",
        ),
        _metric(
            "target-ca-rmsd",
            evidence.target_ca_rmsd_angstrom,
            source="easydesign-structure",
            unit="angstrom",
        ),
        _metric(
            "hotspot-coverage",
            interface.hotspot_coverage,
            source="easydesign-structure",
        ),
        _metric(
            "interface-bsa",
            interface.interface_bsa_angstrom2 or 0.0,
            source="easydesign-structure",
            unit="angstrom2",
        ),
        _metric(
            "severe-clash-count",
            interface.severe_clash_count,
            source="easydesign-structure",
        ),
        _metric(
            "moderate-clash-count",
            interface.moderate_clash_count,
            source="easydesign-structure",
        ),
    )


def build_multi_seed_consensus(
    *,
    candidate_id: str,
    predictions: tuple[FinalPredictionRecord, ...],
    score_deep: float,
    pair_metrics: tuple[SeedPairConsistency, ...],
    required_individually_passing_seeds: int = 2,
) -> MultiSeedConsensusRecord:
    ordered = tuple(sorted(predictions, key=lambda item: item.seed))
    passing = tuple(item.seed for item in ordered if item.consensus_seed_pass)
    passing_pairs = tuple(
        item
        for item in pair_metrics
        if item.passed and item.first_seed in passing and item.second_seed in passing
    )
    consensus_ids = tuple(
        sorted({seed for item in passing_pairs for seed in (item.first_seed, item.second_seed)})
    )
    consensus_pass = (
        len(passing) >= required_individually_passing_seeds
        and len(consensus_ids) >= required_individually_passing_seeds
    )
    if consensus_pass:
        selected = [item for item in ordered if item.seed in consensus_ids]
        median_full = float(median(item.score_full for item in selected))
        final = 0.70 * median_full + 0.30 * score_deep
        median_iptm = float(median(item.pairwise_iptm for item in selected))
    else:
        median_full = None
        final = None
        median_iptm = None
    return MultiSeedConsensusRecord(
        candidate_id=candidate_id,
        available_seeds=tuple(item.seed for item in ordered),
        individually_passing_seeds=passing,
        consistent_seed_pairs=pair_metrics,
        consensus_seed_ids=consensus_ids,
        required_individually_passing_seeds=required_individually_passing_seeds,
        consensus_pass=consensus_pass,
        score_final=final,
        median_score_full=median_full,
        score_deep=score_deep,
        median_pairwise_iptm=median_iptm,
    )


def classify_tnp_risk(
    *,
    candidate_id: str,
    total_cdr_length: int,
    cdr3_length: int,
    cdr3_compactness: float,
    psh: float,
    ppc: float,
    pnc: float,
    flags: dict[str, str],
    liabilities: tuple[SequenceLiability, ...],
) -> TnpCandidateRecord:
    normalized_flags = {key: value.lower() for key, value in flags.items()}
    red = sum(value == "red" for value in normalized_flags.values())
    amber = sum(value == "amber" for value in normalized_flags.values())
    liability_count = len(liabilities)
    risk = (
        DevelopabilityRisk.HIGH
        if red >= 1 or liability_count >= 2
        else (
            DevelopabilityRisk.MEDIUM
            if amber >= 2 or liability_count == 1
            else DevelopabilityRisk.LOW
        )
    )
    return TnpCandidateRecord(
        candidate_id=candidate_id,
        total_cdr_length=total_cdr_length,
        cdr3_length=cdr3_length,
        cdr3_compactness=cdr3_compactness,
        psh=psh,
        ppc=ppc,
        pnc=pnc,
        flags=normalized_flags,  # type: ignore[arg-type]
        red_flag_count=red,
        amber_flag_count=amber,
        cdr_vernier_liabilities=liabilities,
        risk=risk,
    )


def design_sequence_identity(first: str, second: str) -> float:
    """BoltzGen 0.3.2 PairwiseAligner score divided by maximum sequence length."""

    if not first or not second:
        raise ManifestStateError("design sequence identity 需要非空序列")
    aligner = Align.PairwiseAligner()  # type: ignore[no-untyped-call]
    return float(
        aligner.score(first, second)  # type: ignore[no-untyped-call]
        / max(len(first), len(second))
    )


def lazy_greedy_select(
    *,
    consensus: tuple[MultiSeedConsensusRecord, ...],
    tnp: tuple[TnpCandidateRecord, ...],
    design_sequences: dict[str, str],
    primary_count: int,
    backup_count: int,
) -> tuple[FinalSelectionRecord, ...]:
    """Select primary then backup candidates with frozen quality/diversity gain."""

    tnp_by_id = {item.candidate_id: item for item in tnp}
    eligible = {item.candidate_id: item for item in consensus if item.consensus_pass}
    if set(eligible) != set(tnp_by_id):
        raise ManifestStateError("TNP result identity 必须等于 multi-seed pass pool")
    if not set(eligible).issubset(design_sequences):
        raise ManifestStateError("final diversity 缺少 design sequence")
    risk_rank = {
        DevelopabilityRisk.LOW: 0,
        DevelopabilityRisk.MEDIUM: 1,
        DevelopabilityRisk.HIGH: 2,
    }
    selected_ids: list[str] = []
    results: list[FinalSelectionRecord] = []
    remaining = set(eligible)

    def choose(selection_class: str, requested: int) -> None:
        for rank in range(1, min(requested, len(remaining)) + 1):
            evaluated: list[tuple[tuple[float, int, float, float], str, float]] = []
            for candidate_id in sorted(remaining):
                record = eligible[candidate_id]
                assert record.score_final is not None
                assert record.median_pairwise_iptm is not None
                maximum_identity = (
                    max(
                        design_sequence_identity(
                            design_sequences[candidate_id],
                            design_sequences[selected],
                        )
                        for selected in selected_ids
                    )
                    if selected_ids
                    else 0.0
                )
                gain = 0.90 * record.score_final + 0.10 * (1.0 - maximum_identity)
                evaluated.append(
                    (
                        (
                            gain,
                            -risk_rank[tnp_by_id[candidate_id].risk],
                            record.score_final,
                            record.median_pairwise_iptm,
                        ),
                        candidate_id,
                        maximum_identity,
                    )
                )
            score_tuple, candidate_id, maximum_identity = min(
                evaluated,
                key=lambda item: (
                    tuple(-value for value in item[0]),
                    item[1],
                ),
            )
            gain, _, score_final, median_iptm = score_tuple
            selected_ids.append(candidate_id)
            remaining.remove(candidate_id)
            results.append(
                FinalSelectionRecord(
                    candidate_id=candidate_id,
                    selection_class=selection_class,  # type: ignore[arg-type]
                    selection_rank=rank,
                    gain=gain,
                    maximum_identity_to_previously_selected=maximum_identity,
                    score_final=score_final,
                    developability_risk=tnp_by_id[candidate_id].risk,
                    median_pairwise_iptm=median_iptm,
                )
            )

    choose("primary", primary_count)
    choose("backup", backup_count)
    return tuple(results)
