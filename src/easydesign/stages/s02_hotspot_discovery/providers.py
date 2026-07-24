"""Stage 02 区域来源接口；首版只注册 automatic provider。"""

from __future__ import annotations

from typing import Protocol

from easydesign.core import ConfigurationError

from .models import RecommendedRegionSet


class RegionProposalProvider(Protocol):
    provider_name: str

    def propose(self) -> RecommendedRegionSet: ...


class PseAnnotationRegionProvider:
    provider_name = "pse_annotations"

    def propose(self) -> RecommendedRegionSet:
        raise ConfigurationError(
            "Stage 02 PSE 染色区域导入尚未实现；禁止回退到 automatic"
        )


class ManualRegionProvider:
    provider_name = "manual"

    def propose(self) -> RecommendedRegionSet:
        raise ConfigurationError(
            "Stage 02 人工区域上传尚未实现；禁止回退到 automatic"
        )
