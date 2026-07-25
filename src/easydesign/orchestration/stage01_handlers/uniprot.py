"""UniProt accession 与名称检索入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption

from ..workspace import PreparedRun

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def handle_uniprot_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """解析 canonical identity/scope，再选择实验结构或预测 fallback。"""

    from ..stage01_sources import (
        PredictionFallback,
        Stage01SourceOutcome,
        _execute_experimental,
    )
    from ..stage01_sources import _remote_selection as select_remote

    selection = select_remote(
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
