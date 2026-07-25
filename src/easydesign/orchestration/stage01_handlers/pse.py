"""严格单 Target PyMOL PSE 入口。"""

from __future__ import annotations

from easydesign.backends.target_sources import PyMOLPseAdapter

from ..pse_import import CompletedPseRun, execute_pse_import
from ..workspace import PreparedPseRun


def execute_pse_source(
    prepared: PreparedPseRun,
    *,
    adapter: PyMOLPseAdapter,
) -> CompletedPseRun:
    """通过独立 PyMOL worker 导入，不在 core 进程加载 PyMOL。"""

    return execute_pse_import(prepared=prepared, adapter=adapter)
