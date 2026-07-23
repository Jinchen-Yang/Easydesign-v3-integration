"""跨契约共用的时区时间规范。"""

from __future__ import annotations

from datetime import UTC, datetime


def normalize_aware_datetime(value: datetime) -> datetime:
    """拒绝 naive datetime，并统一转换为 UTC。"""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return value.astimezone(UTC)
