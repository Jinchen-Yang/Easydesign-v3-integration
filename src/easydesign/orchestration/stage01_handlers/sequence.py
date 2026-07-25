"""FASTA 与裸序列入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption

from ..workspace import PreparedRun

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def handle_sequence_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """先检索合格实验结构；否则返回显式 Protenix fallback。"""

    from ..stage01_sources import (
        PredictionFallback,
        Stage01SourceOutcome,
        _execute_experimental,
        _sequence_selection,
    )

    selection = _sequence_selection(
        prepared,
        attempt_id=attempt_id,
        approved_option=approved_option,
    )
    if isinstance(selection, Stage01SourceOutcome):
        return selection
    if isinstance(selection, PredictionFallback):
        return Stage01SourceOutcome(
            status="prediction-required",
            run_root=prepared.workspace.run_root,
            run_manifest=prepared.workspace.run_manifest,
            prediction_fallback=selection,
        )
    return _execute_experimental(prepared, selection, attempt_id=attempt_id)
