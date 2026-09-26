"""Generic structure-prediction contracts and adapters."""

from .contracts import (
    BackendInvocation,
    ComplexConfidenceMetrics,
    ComplexStructurePredictionRequest,
    MsaMode,
    PredictionParameterProfile,
    PredictionRequest,
    ProteinPredictionChain,
    ScientificMode,
    StructurePredictionProduct,
    StructurePredictionRequest,
    TargetResidueNumbering,
    TargetStructureCondition,
    TemplateMode,
)
from .openfold3_af3_jax import (
    OPENFOLD3_METRIC_DEFINITION_VERSION,
    OpenFold3Af3JaxAdapter,
    OpenFold3TemplatePipelineAssets,
)
from .protenix_v2 import (
    ProtenixMsaProvider,
    ProtenixV2Adapter,
    ResolvedProtenixMsaProvider,
    resolve_protenix_msa_provider,
)

__all__ = [
    "BackendInvocation",
    "ComplexConfidenceMetrics",
    "ComplexStructurePredictionRequest",
    "MsaMode",
    "OPENFOLD3_METRIC_DEFINITION_VERSION",
    "OpenFold3Af3JaxAdapter",
    "OpenFold3TemplatePipelineAssets",
    "PredictionRequest",
    "PredictionParameterProfile",
    "ProteinPredictionChain",
    "ProtenixMsaProvider",
    "ProtenixV2Adapter",
    "ResolvedProtenixMsaProvider",
    "ScientificMode",
    "StructurePredictionProduct",
    "StructurePredictionRequest",
    "TargetResidueNumbering",
    "TargetStructureCondition",
    "TemplateMode",
    "resolve_protenix_msa_provider",
]
