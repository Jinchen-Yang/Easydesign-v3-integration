"""Stage 02 可替换区域来源的薄 provider 包装。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from easydesign.stages.s01_target_preparation import ResidueMapping, TargetBundle

from .geometry import StructureContext
from .models import RecommendedRegionSet, UserProvidedRegionSet
from .user_regions import normalize_manual_regions, normalize_pse_color_regions


class RegionProposalProvider(Protocol):
    provider_name: str

    def propose(self) -> RecommendedRegionSet | UserProvidedRegionSet: ...


@dataclass(frozen=True, slots=True)
class PseAnnotationRegionProvider:
    run_root: Path
    bundle: TargetBundle
    context: StructureContext
    mapping: ResidueMapping
    provider_name = "pse-color-annotation"

    def propose(self) -> UserProvidedRegionSet:
        regions, _evidence, _validation = normalize_pse_color_regions(
            run_root=self.run_root,
            bundle=self.bundle,
            context=self.context,
            mapping=self.mapping,
        )
        return regions


@dataclass(frozen=True, slots=True)
class ManualRegionProvider:
    bundle: TargetBundle
    context: StructureContext
    mapping: ResidueMapping
    numbering: str
    chain: str | None
    configured_regions: Iterable[tuple[str, tuple[str, ...]]]
    input_config_sha256: str
    provider_name = "manual-residue-list"

    def propose(self) -> UserProvidedRegionSet:
        regions, _evidence, _validation = normalize_manual_regions(
            bundle=self.bundle,
            context=self.context,
            mapping=self.mapping,
            numbering=self.numbering,
            chain=self.chain,
            configured_regions=self.configured_regions,
            input_config_sha256=self.input_config_sha256,
        )
        return regions
