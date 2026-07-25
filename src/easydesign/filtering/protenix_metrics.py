"""Strict Protenix-v2 target+binder confidence extraction."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from easydesign.core import ManifestStateError

PROTENIX_METRIC_DEFINITION_VERSION = "protenix-v2-complex-confidence-v1"


class _SummaryConfidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    chain_pair_iptm: tuple[tuple[float, ...], ...]
    chain_ptm: tuple[float, ...]


class _FullConfidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    token_pair_pae: tuple[tuple[float, ...], ...]
    token_asym_id: tuple[int, ...]
    token_has_frame: tuple[bool | int, ...]


@dataclass(frozen=True, slots=True)
class ProtenixComplexConfidence:
    pairwise_iptm: float
    minimum_interface_pae_angstrom: float
    binder_ptm: float
    target_token_count: int
    binder_token_count: int


def _matrix_shape(matrix: tuple[tuple[float, ...], ...]) -> tuple[int, int]:
    if not matrix:
        return (0, 0)
    widths = {len(row) for row in matrix}
    if len(widths) != 1:
        raise ManifestStateError("Protenix confidence matrix 不是矩形")
    return len(matrix), next(iter(widths))


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestStateError(f"Protenix confidence JSON 无法读取: {path}") from error


def extract_protenix_complex_confidence(
    *,
    summary_path: Path,
    full_confidence_path: Path,
    target_chain_index: int = 0,
    binder_chain_index: int = 1,
) -> ProtenixComplexConfidence:
    """Extract pair ipTM, cross-chain min PAE, and binder pTM without proxies."""

    try:
        summary = _SummaryConfidence.model_validate(_read_json(summary_path))
        full = _FullConfidence.model_validate(_read_json(full_confidence_path))
    except ValidationError as error:
        raise ManifestStateError("Protenix complex confidence schema 不完整") from error
    if target_chain_index == binder_chain_index or min(
        target_chain_index,
        binder_chain_index,
    ) < 0:
        raise ManifestStateError("target/binder chain index 必须不同且非负")
    chain_count = len(summary.chain_ptm)
    if max(target_chain_index, binder_chain_index) >= chain_count:
        raise ManifestStateError("Protenix summary 缺少 target/binder chain")
    pair_shape = _matrix_shape(summary.chain_pair_iptm)
    if pair_shape != (chain_count, chain_count):
        raise ManifestStateError("chain_pair_iptm 维度与 chain_ptm 不一致")

    token_count = len(full.token_asym_id)
    if len(full.token_has_frame) != token_count:
        raise ManifestStateError("token_has_frame 与 token_asym_id 长度不一致")
    pae_shape = _matrix_shape(full.token_pair_pae)
    if pae_shape != (token_count, token_count):
        raise ManifestStateError("token_pair_pae 必须是 N_token × N_token")
    target_tokens = tuple(
        index
        for index, asym_id in enumerate(full.token_asym_id)
        if asym_id == target_chain_index and bool(full.token_has_frame[index])
    )
    binder_tokens = tuple(
        index
        for index, asym_id in enumerate(full.token_asym_id)
        if asym_id == binder_chain_index and bool(full.token_has_frame[index])
    )
    if not target_tokens or not binder_tokens:
        raise ManifestStateError("Protenix full confidence 缺少可形成 frame 的 target/binder token")
    interface_pae = [
        full.token_pair_pae[first][second]
        for first in target_tokens
        for second in binder_tokens
    ] + [
        full.token_pair_pae[second][first]
        for first in target_tokens
        for second in binder_tokens
    ]
    values = (
        summary.chain_pair_iptm[target_chain_index][binder_chain_index],
        summary.chain_ptm[binder_chain_index],
        *interface_pae,
    )
    if any(not math.isfinite(value) for value in values):
        raise ManifestStateError("Protenix complex confidence 包含非有限值")
    return ProtenixComplexConfidence(
        pairwise_iptm=float(
            summary.chain_pair_iptm[target_chain_index][binder_chain_index]
        ),
        minimum_interface_pae_angstrom=float(min(interface_pae)),
        binder_ptm=float(summary.chain_ptm[binder_chain_index]),
        target_token_count=len(target_tokens),
        binder_token_count=len(binder_tokens),
    )
