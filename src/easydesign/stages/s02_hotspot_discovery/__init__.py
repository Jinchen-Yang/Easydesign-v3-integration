"""Stage 02 独立候选表面区域发现契约。"""

from .automatic import (
    RegionParameters,
    SasaParameters,
    compare_independent_methods,
    run_sasa_surface_diversity,
    run_scannet_region_proposals,
)
from .geometry import StructureContext, load_structure_context
from .models import (
    AnnotationStatus,
    CandidateRegionPool,
    CandidateSurfaceRegion,
    MethodComparison,
    PairwiseSeparation,
    ProviderExecutionStatus,
    RecommendedRegionSet,
    RegionMethod,
    RegionMetrics,
    RegionOverlap,
    RegionReviewStatus,
    ResidueEvidence,
    ResidueEvidenceReport,
    ResidueIdentity,
    Stage02Report,
)
from .providers import (
    ManualRegionProvider,
    PseAnnotationRegionProvider,
    RegionProposalProvider,
)

__all__ = [
    "AnnotationStatus",
    "CandidateRegionPool",
    "CandidateSurfaceRegion",
    "MethodComparison",
    "ManualRegionProvider",
    "PairwiseSeparation",
    "ProviderExecutionStatus",
    "PseAnnotationRegionProvider",
    "RecommendedRegionSet",
    "RegionMethod",
    "RegionMetrics",
    "RegionOverlap",
    "RegionReviewStatus",
    "RegionProposalProvider",
    "ResidueEvidence",
    "ResidueEvidenceReport",
    "ResidueIdentity",
    "Stage02Report",
    "RegionParameters",
    "SasaParameters",
    "StructureContext",
    "compare_independent_methods",
    "load_structure_context",
    "run_sasa_surface_diversity",
    "run_scannet_region_proposals",
]
