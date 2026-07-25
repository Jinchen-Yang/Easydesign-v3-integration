"""Stage 01 非 PSE workspace 的单一 source dispatcher。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from easydesign.core import DecisionOption, ManifestStateError

from ..config import (
    LoadedRemoteRunConfig,
    LoadedSequenceRunConfig,
    LoadedStructureRunConfig,
    LoadedTargetBundleRunConfig,
    PdbIdSourceConfig,
)
from ..workspace import PreparedRun
from .local_structure import handle_local_structure_source
from .pdb_id import handle_pdb_id_source
from .sequence import handle_sequence_source
from .target_bundle import handle_target_bundle_source
from .uniprot import handle_uniprot_source

if TYPE_CHECKING:
    from ..stage01_sources import Stage01SourceOutcome


def dispatch_stage01_source(
    prepared: PreparedRun,
    *,
    attempt_id: str,
    approved_option: DecisionOption | None,
) -> Stage01SourceOutcome:
    """按 config discriminated union 精确分派，不猜测或 fallback。"""

    loaded = prepared.loaded_config
    if isinstance(loaded, LoadedSequenceRunConfig):
        return handle_sequence_source(
            prepared,
            attempt_id=attempt_id,
            approved_option=approved_option,
        )
    if isinstance(loaded, LoadedStructureRunConfig):
        return handle_local_structure_source(
            prepared,
            attempt_id=attempt_id,
            approved_option=approved_option,
        )
    if isinstance(loaded, LoadedTargetBundleRunConfig):
        return handle_target_bundle_source(
            prepared,
            attempt_id=attempt_id,
            approved_option=approved_option,
        )
    if isinstance(loaded, LoadedRemoteRunConfig):
        if isinstance(loaded.config.target.source, PdbIdSourceConfig):
            return handle_pdb_id_source(
                prepared,
                attempt_id=attempt_id,
                approved_option=approved_option,
            )
        return handle_uniprot_source(
            prepared,
            attempt_id=attempt_id,
            approved_option=approved_option,
        )
    raise ManifestStateError(
        f"Stage 01 dispatcher 不接受 loaded config: {type(loaded).__name__}"
    )
