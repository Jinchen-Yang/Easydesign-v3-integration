"""Generic structure-prediction contracts and adapters."""

from .contracts import (
    BackendInvocation,
    ComplexStructurePredictionRequest,
    MsaMode,
    PredictionParameterProfile,
    PredictionRequest,
    ProteinPredictionChain,
    StructurePredictionProduct,
    StructurePredictionRequest,
    TemplateMode,
)
from .protenix_v2 import (
    ProtenixMsaProvider,
    ProtenixV2Adapter,
    ResolvedProtenixMsaProvider,
    resolve_protenix_msa_provider,
)

__all__ = [
    "BackendInvocation",
    "ComplexStructurePredictionRequest",
    "MsaMode",
    "PredictionRequest",
    "PredictionParameterProfile",
    "ProteinPredictionChain",
    "ProtenixMsaProvider",
    "ProtenixV2Adapter",
    "ResolvedProtenixMsaProvider",
    "StructurePredictionProduct",
    "StructurePredictionRequest",
    "TemplateMode",
    "resolve_protenix_msa_provider",
]
