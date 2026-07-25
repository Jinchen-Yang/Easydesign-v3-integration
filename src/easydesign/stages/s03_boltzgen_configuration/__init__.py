"""Stage 03 deterministic BoltzGen configuration contracts."""

from .compiler import (
    EXPECTED_ASSET_SHA256,
    SCAFFOLD_IDS,
    compile_basic_vhh_matrix,
    materialize_scaffold_registry,
    write_design_matrix,
)
from .models import (
    BOLTZGEN_COMMIT,
    BOLTZGEN_VERSION,
    SCAFFOLD_REGISTRY_ID,
    STRATEGY_PROFILE_ID,
    ScaffoldAsset,
    StrategyBundle,
    StrategyRecord,
    StrategyValidationItem,
    StrategyValidationReport,
)

__all__ = [
    "BOLTZGEN_COMMIT",
    "BOLTZGEN_VERSION",
    "EXPECTED_ASSET_SHA256",
    "SCAFFOLD_IDS",
    "SCAFFOLD_REGISTRY_ID",
    "STRATEGY_PROFILE_ID",
    "ScaffoldAsset",
    "StrategyBundle",
    "StrategyRecord",
    "StrategyValidationItem",
    "StrategyValidationReport",
    "compile_basic_vhh_matrix",
    "materialize_scaffold_registry",
    "write_design_matrix",
]
