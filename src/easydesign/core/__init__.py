"""EasyDesign 跨阶段基础契约。"""

from .artifacts import ArtifactRef
from .attempts import Attempt, ErrorInfo, ExecutionStatus
from .errors import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    BackendContractError,
    ContractError,
    EasyDesignError,
    ManifestStateError,
    PathPolicyError,
    PredictionOutputError,
    SequenceInputError,
    SerializationError,
    UndeclaredArtifactError,
)
from .hashing import sha256_file, verify_sha256
from .manifests import EvidenceStatus, RunManifest, StageId, StageManifest
from .serialization import (
    canonical_json_bytes,
    canonical_model_sha256,
    dump_model,
    load_model,
)

__all__ = [
    "ArtifactIntegrityError",
    "ArtifactNotFoundError",
    "ArtifactRef",
    "Attempt",
    "BackendContractError",
    "ContractError",
    "EasyDesignError",
    "ErrorInfo",
    "EvidenceStatus",
    "ExecutionStatus",
    "ManifestStateError",
    "PathPolicyError",
    "PredictionOutputError",
    "RunManifest",
    "SequenceInputError",
    "SerializationError",
    "StageId",
    "StageManifest",
    "UndeclaredArtifactError",
    "canonical_json_bytes",
    "canonical_model_sha256",
    "dump_model",
    "load_model",
    "sha256_file",
    "verify_sha256",
]
