"""本地 PDB/mmCIF 入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption

from ..workspace import PreparedRun

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def handle_local_structure_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """执行 inventory、chain/scope 解析和结构规范化。"""

    from ..stage01_sources import (
        Stage01SourceOutcome,
        _execute_experimental,
        _local_selection,
    )

    selection = _local_selection(
        prepared,
        attempt_id=attempt_id,
        approved_option=approved_option,
    )
    if isinstance(selection, Stage01SourceOutcome):
        return selection
    return _execute_experimental(prepared, selection, attempt_id=attempt_id)
