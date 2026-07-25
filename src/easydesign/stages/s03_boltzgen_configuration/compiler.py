"""Deterministic Stage 03 basic VHH strategy compilation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from easydesign.core import ManifestStateError, sha256_file
from easydesign.stages.s02_hotspot_discovery import HotspotsFile

from .models import (
    BOLTZGEN_COMMIT,
    SCAFFOLD_REGISTRY_ID,
    STRATEGY_PROFILE_ID,
    ScaffoldAsset,
    StrategyRecord,
)

SCAFFOLD_IDS = (
    "7eow",
    "7xl0",
    "8coh",
    "8z8v",
    "gontivimab",
    "isecarosmab",
    "sonelokimab",
)
ASSET_PACKAGE = (
    "easydesign.resources.scaffolds.vhh.official_boltzgen_0_3_2"
)
SOURCE_REPOSITORY = "https://github.com/HannesStark/boltzgen"
EXPECTED_ASSET_SHA256 = {
    "7eow.cif": "c642dd357cd364463d9cc78203ee31dc67b3ee0dad6efc3043b94576897dcbea",
    "7eow.yaml": "970d152c7834b32ae99a6f80fe30fd87602682106c4a833ce1aef6f030213ffc",
    "7xl0.cif": "0042fd3761f1aee883db62f72f86b8a5fca75198d9e2f265be197b7d44320c34",
    "7xl0.yaml": "15dba3e9eaf55b6e5a24cc0b52ee58abe26d7357ba5419eb0fe998bf5eefe7f0",
    "8coh.cif": "9d4f66737ca499933bf7a31e3ac064a52a094a388a597c4164f8469cd2b6579f",
    "8coh.yaml": "f09e48b23df8a1d3e5b41f2a8f99201476861ffffc5f4aaa1d13d46a2ac35450",
    "8z8v.cif": "71674d0516398244d2543d0863dd588689cc8e9b3dcfded1a404784adad57638",
    "8z8v.yaml": "d76d2a421edd3c86b04ead4ec72c7f4022906dd703e2b48015222d61b5d82cb5",
    "gontivimab.cif": "e91fa5a772c3b7a9f1a6c51190abe3b879925d2a2a18ae093ac14ddcb96e3cab",
    "gontivimab.yaml": "237b439cb309b6fcba244aa85cdb408e62c8382cb47ee7c81931df7589898166",
    "isecarosmab.cif": "b41d13efbed1ca989d04e3238c48a8b02b145a6927c850596c8f673d515a7f67",
    "isecarosmab.yaml": "bf25cd10dc65e99b947e915bfe2be3316956fc71216263a66aeb4415edf48b0d",
    "sonelokimab.cif": "2a95c49075263ac4aa7580bf225ed512be1ca4deb9d5637e02e73e58d31a2f95",
    "sonelokimab.yaml": "87c4d65ea8bac576c4c89acb2d2e0f66fddb2729124d0719ae6c0b6a91580888",
    "BOLTZGEN_LICENSE.txt": (
        "1d3aafee1429a716ca9afbe1760adf3a461cf61e750e92756dee510bdc0b7911"
    ),
}


def _exclusive_bytes(content: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 03 禁止覆盖 artifact: {path}") from error


def _exclusive_text(content: str, path: Path) -> None:
    _exclusive_bytes(content.encode("utf-8"), path)


def _atomic_json(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if path.exists():
            raise ManifestStateError(f"Stage 03 禁止覆盖 artifact: {path}")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def materialize_scaffold_registry(destination: Path) -> tuple[ScaffoldAsset, ...]:
    """Copy byte-identical reviewed package assets into an immutable run attempt."""

    root = resources.files(ASSET_PACKAGE)
    assets: list[ScaffoldAsset] = []
    for scaffold_id in SCAFFOLD_IDS:
        specification = destination / f"{scaffold_id}.yaml"
        structure = destination / f"{scaffold_id}.cif"
        specification_name = f"{scaffold_id}.yaml"
        structure_name = f"{scaffold_id}.cif"
        specification_bytes = root.joinpath(specification_name).read_bytes()
        structure_bytes = root.joinpath(structure_name).read_bytes()
        if (
            hashlib.sha256(specification_bytes).hexdigest()
            != EXPECTED_ASSET_SHA256[specification_name]
            or hashlib.sha256(structure_bytes).hexdigest()
            != EXPECTED_ASSET_SHA256[structure_name]
        ):
            raise ManifestStateError(
                f"官方 scaffold package asset checksum 不一致: {scaffold_id}"
            )
        _exclusive_bytes(specification_bytes, specification)
        _exclusive_bytes(structure_bytes, structure)
        assets.append(
            ScaffoldAsset(
                scaffold_id=scaffold_id,
                specification_path=specification.as_posix(),
                specification_sha256=sha256_file(specification),
                structure_path=structure.as_posix(),
                structure_sha256=sha256_file(structure),
                source_repository=SOURCE_REPOSITORY,
                source_commit=BOLTZGEN_COMMIT,
            )
        )
    license_bytes = root.joinpath("BOLTZGEN_LICENSE.txt").read_bytes()
    if (
        hashlib.sha256(license_bytes).hexdigest()
        != EXPECTED_ASSET_SHA256["BOLTZGEN_LICENSE.txt"]
    ):
        raise ManifestStateError("BoltzGen license checksum 不一致")
    _exclusive_bytes(license_bytes, destination / "BOLTZGEN_LICENSE.txt")
    return tuple(assets)


def _strategy_id(region_id: str, scaffold_id: str) -> str:
    return (
        f"region-{region_id.lower()}-h-all-c-full-scaffold-{scaffold_id}"
    )


def _design_specification(
    *,
    binding_label_seq_ids: tuple[int, ...],
    scaffold_id: str,
) -> dict[str, object]:
    return {
        "entities": [
            {
                "file": {
                    "path": "../../assets/target.cif",
                    "include": [{"chain": {"id": "A"}}],
                    "binding_types": [
                        {
                            "chain": {
                                "id": "A",
                                "binding": ",".join(
                                    str(value)
                                    for value in binding_label_seq_ids
                                ),
                            }
                        }
                    ],
                }
            },
            {
                "file": {
                    "path": f"../../assets/scaffolds/{scaffold_id}.yaml"
                }
            },
        ]
    }


def compile_basic_vhh_matrix(
    *,
    target_cif: Path,
    hotspots: HotspotsFile,
    artifacts_root: Path,
    candidates_per_strategy: int,
) -> tuple[tuple[ScaffoldAsset, ...], tuple[StrategyRecord, ...]]:
    """Compile the complete region × official VHH scaffold matrix.

    Non-hotspot residues are deliberately absent from ``binding_types``. The
    compiler never emits ``not_binding``.
    """

    target_hash = sha256_file(target_cif)
    if target_hash != hotspots.target_structure_sha256:
        raise ManifestStateError(
            "hotspots.yaml 的 target_structure_sha256 与 Target Bundle 不一致"
        )
    if candidates_per_strategy < 1:
        raise ManifestStateError("candidates_per_strategy 必须为正整数")
    if artifacts_root.exists() and any(artifacts_root.iterdir()):
        raise ManifestStateError(
            f"Stage 03 artifacts 目录必须为空: {artifacts_root}"
        )

    target_asset = artifacts_root / "assets" / "target.cif"
    _exclusive_bytes(target_cif.read_bytes(), target_asset)
    raw_assets = materialize_scaffold_registry(
        artifacts_root / "assets" / "scaffolds"
    )
    assets = tuple(
        asset.model_copy(
            update={
                "specification_path": Path(asset.specification_path)
                .relative_to(artifacts_root)
                .as_posix(),
                "structure_path": Path(asset.structure_path)
                .relative_to(artifacts_root)
                .as_posix(),
            }
        )
        for asset in raw_assets
    )

    records: list[StrategyRecord] = []
    for hotspot_set in hotspots.hotspot_sets:
        region_id = hotspot_set.id.lower()
        labels = tuple(hotspot_set.label_seq_ids)
        for scaffold_id in SCAFFOLD_IDS:
            strategy_id = _strategy_id(hotspot_set.id, scaffold_id)
            strategy_dir = artifacts_root / "strategies" / strategy_id
            specification_path = strategy_dir / "design.yaml"
            _exclusive_text(
                yaml.safe_dump(
                    _design_specification(
                        binding_label_seq_ids=labels,
                        scaffold_id=scaffold_id,
                    ),
                    allow_unicode=True,
                    sort_keys=False,
                ),
                specification_path,
            )
            record = StrategyRecord(
                strategy_id=strategy_id,
                region_id=region_id,
                source_hotspot_set_id=hotspot_set.id,
                scaffold_id=scaffold_id,
                binding_label_seq_ids=labels,
                candidates_per_strategy=candidates_per_strategy,
                design_specification_path=specification_path.relative_to(
                    artifacts_root
                ).as_posix(),
                design_specification_sha256=sha256_file(specification_path),
            )
            _atomic_json(
                {
                    "schema_version": "0.1",
                    "compilation_status": "compiled",
                    "strategy_profile": STRATEGY_PROFILE_ID,
                    "scaffold_registry": SCAFFOLD_REGISTRY_ID,
                    **record.model_dump(mode="json"),
                },
                strategy_dir / "strategy-manifest.json",
            )
            records.append(record)
    return assets, tuple(records)


def write_design_matrix(
    records: Iterable[StrategyRecord],
    *,
    json_path: Path,
    tsv_path: Path,
) -> None:
    rows = tuple(record.model_dump(mode="json") for record in records)
    _atomic_json(
        {"schema_version": "0.1", "strategies": rows},
        json_path,
    )
    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    if tsv_path.exists():
        raise ManifestStateError(f"Stage 03 禁止覆盖 artifact: {tsv_path}")
    fields = (
        "strategy_id",
        "region_id",
        "source_hotspot_set_id",
        "scaffold_id",
        "hotspot_strategy",
        "crop_strategy",
        "crop_enabled",
        "target_chain",
        "binding_label_seq_ids",
        "neutral_residue_policy",
        "candidates_per_strategy",
        "design_specification_path",
        "design_specification_sha256",
    )
    with tsv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            normalized["binding_label_seq_ids"] = ",".join(
                str(value) for value in normalized["binding_label_seq_ids"]
            )
            writer.writerow(normalized)
