"""Pinned BoltzGen capability manifest and fail-closed resolver."""

from __future__ import annotations

from importlib import resources
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import ManifestStateError
from easydesign.core.artifacts import SHA256_PATTERN

from .models import BOLTZGEN_COMMIT, BOLTZGEN_VERSION

BOLTZGEN_SOURCE_TREE_SHA256 = (
    "1f9e0b2405e89ac7778ea5b98d5ce4eddf739be0f3ac4c6432378a8811fe7590"
)


class BoltzGenSupports(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    binding: bool
    not_binding: bool
    target_crop: bool
    cdr_override: bool
    msa: bool
    template: bool
    multi_chain: bool


class BoltzGenCapabilityManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    backend: Literal["boltzgen"]
    version: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_tree_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_version: str
    supports: BoltzGenSupports
    known_quirks: tuple[str, ...]
    validation_sources: tuple[str, ...]


def load_boltzgen_capabilities() -> BoltzGenCapabilityManifest:
    resource = resources.files("easydesign.resources").joinpath(
        "backend_capabilities/boltzgen-0.3.2.yaml"
    )
    try:
        payload = yaml.safe_load(resource.read_text(encoding="utf-8"))
        manifest = BoltzGenCapabilityManifest.model_validate(payload)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise ManifestStateError("BoltzGen capability manifest 无法验证") from error
    if (
        manifest.version != BOLTZGEN_VERSION
        or manifest.commit != BOLTZGEN_COMMIT
        or manifest.source_tree_sha256 != BOLTZGEN_SOURCE_TREE_SHA256
    ):
        raise ManifestStateError("BoltzGen capability/version/commit drift")
    return manifest


def require_boltzgen_capability(feature: str) -> BoltzGenCapabilityManifest:
    manifest = load_boltzgen_capabilities()
    if feature not in BoltzGenSupports.model_fields:
        raise ManifestStateError(f"未知 BoltzGen capability: {feature}")
    if not bool(getattr(manifest.supports, feature)):
        raise ManifestStateError(
            f"pinned BoltzGen {manifest.version} 不支持 required capability: {feature}"
        )
    return manifest


__all__ = [
    "BoltzGenCapabilityManifest",
    "BoltzGenSupports",
    "BOLTZGEN_SOURCE_TREE_SHA256",
    "load_boltzgen_capabilities",
    "require_boltzgen_capability",
]
