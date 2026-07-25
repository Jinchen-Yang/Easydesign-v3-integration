"""Stage 01 六类 source handler。

每个模块只负责一个用户入口的分支选择；结构选择、发布和失败证据等共享
实现仍由 Stage 01 engine 提供，避免六份科学逻辑逐渐分叉。
"""

from .dispatcher import dispatch_stage01_source
from .pse import execute_pse_source

__all__ = [
    "dispatch_stage01_source",
    "execute_pse_source",
]
