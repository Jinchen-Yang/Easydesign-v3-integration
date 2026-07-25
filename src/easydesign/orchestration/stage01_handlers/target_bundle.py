"""已有 Target Bundle 入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption

from ..workspace import PreparedRun

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def handle_target_bundle_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """验证全部 ArtifactRef 后复制并重建当前 attempt 引用。"""

    del approved_option
    from ..stage01_sources import _import_bundle

    return _import_bundle(prepared, attempt_id=attempt_id)
