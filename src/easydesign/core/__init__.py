"""EasyDesign 跨阶段基础契约。"""

from .artifacts import ArtifactRef
from .attempts import Attempt, ErrorInfo, ExecutionStatus
from .errors import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    BackendContractError,
    ConfigurationError,
    ContractError,
    EasyDesignError,
    ManifestStateError,
    PathPolicyError,
    PredictionOutputError,
    SequenceInputError,
    SerializationError,
    TargetInputError,
    UndeclaredArtifactError,
)
from .hashing import sha256_file, verify_sha256
from .identity import package_tree_sha256, resolve_code_identity
from .manifests import (
    CodeIdentity,
    CodeIdentitySource,
    EvidenceStatus,
    RunManifest,
    RuntimeProfileRef,
    StageId,
    StageManifest,
)
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
    "ConfigurationError",
    "CodeIdentity",
    "CodeIdentitySource",
    "ContractError",
    "EasyDesignError",
    "ErrorInfo",
    "EvidenceStatus",
    "ExecutionStatus",
    "ManifestStateError",
    "PathPolicyError",
    "PredictionOutputError",
    "RunManifest",
    "RuntimeProfileRef",
    "SequenceInputError",
    "SerializationError",
    "StageId",
    "StageManifest",
    "TargetInputError",
    "UndeclaredArtifactError",
    "canonical_json_bytes",
    "canonical_model_sha256",
    "dump_model",
    "load_model",
    "package_tree_sha256",
    "resolve_code_identity",
    "sha256_file",
    "verify_sha256",
]
