"""RCSB PDB ID 入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption, ManifestStateError

from ..workspace import PreparedRun

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def handle_pdb_id_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """下载用户显式指定的原始 mmCIF，并按严格质量门处理。"""

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
        raise ManifestStateError(
            "显式 PDB ID 不允许转换为 prediction fallback"
        )
    return _execute_experimental(prepared, selection, attempt_id=attempt_id)
