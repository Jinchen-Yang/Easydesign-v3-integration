"""Verified Binder Strategy Skill templates consumed by the existing compiler."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]

from easydesign.core import ManifestStateError

ScaffoldTemplate = Literal["official-vhh7-v1", "gpcr-vhh7-v1"]
GPCR_TEMPLATE: ScaffoldTemplate = "gpcr-vhh7-v1"
GPCR_MANIFEST_SHA256 = "4b47ff565896a7c3e07286f2b45f23f6db668eee48cd9241333aa26bac7317b3"


def gpcr_template(scaffold_id: str) -> tuple[dict[str, Any], str]:
    """Load exact supplied YAML; reuse verified, equivalent registry coordinates."""
    from .compiler import ASSET_PACKAGE, EXPECTED_ASSET_SHA256, SCAFFOLD_IDS

    if scaffold_id not in SCAFFOLD_IDS:
        raise ManifestStateError(f"Unknown GPCR Skill scaffold: {scaffold_id}")
    root = resources.files("easydesign").joinpath(
        "agent/skills/binder-strategy/assets/gpcr-vhh7-v1"
    )
    manifest = root.joinpath("manifest.json").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != GPCR_MANIFEST_SHA256:
        raise ManifestStateError("GPCR Skill template manifest checksum mismatch")
    expected = json.loads(manifest)["files"]
    spec_name = f"{scaffold_id}-cdr3-50.yaml"
    structure_name = f"{scaffold_id}.cif"
    spec = root.joinpath(spec_name).read_bytes()
    structure = root.joinpath(structure_name).read_bytes()
    for name, content in ((spec_name, spec), (structure_name, structure)):
        if hashlib.sha256(content).hexdigest() != expected[name]:
            raise ManifestStateError(f"GPCR Skill template checksum mismatch: {name}")
    official = resources.files(ASSET_PACKAGE).joinpath(structure_name).read_bytes()
    if (
        hashlib.sha256(official).hexdigest() != EXPECTED_ASSET_SHA256[structure_name]
        or structure.splitlines() != official.splitlines()
    ):
        raise ManifestStateError(f"GPCR Skill/registry coordinates differ: {scaffold_id}")
    payload = yaml.safe_load(spec)
    if not isinstance(payload, dict) or payload.get("path") != structure_name:
        raise ManifestStateError(f"Invalid GPCR Skill scaffold specification: {scaffold_id}")
    return payload, str(expected[spec_name])
