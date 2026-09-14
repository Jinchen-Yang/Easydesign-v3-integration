"""Deterministic Stage 03 basic VHH strategy compilation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

from easydesign.core import ManifestStateError, sha256_file
from easydesign.stages.s02_hotspot_discovery import HotspotsFile

from .capabilities import require_boltzgen_capability
from .models import (
    BOLTZGEN_COMMIT,
    SCAFFOLD_REGISTRY_ID,
    STRATEGY_PROFILE_ID,
    ExplicitStrategyVariant,
    NativeStrategyVariant,
    ScaffoldAsset,
    StrategyRecord,
)
from .scaffold_templates import GPCR_TEMPLATE, gpcr_template

SCAFFOLD_IDS = (
    "7eow",
    "7xl0",
    "8coh",
    "8z8v",
    "gontivimab",
    "isecarosmab",
    "sonelokimab",
)
ASSET_PACKAGE = "easydesign.resources.scaffolds.vhh.official_boltzgen_0_3_2"
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
    "BOLTZGEN_LICENSE.txt": ("1d3aafee1429a716ca9afbe1760adf3a461cf61e750e92756dee510bdc0b7911"),
}


def _mmcif_column(raw: dict[str, object], name: str) -> list[str]:
    value = raw.get(name)
    if value is None:
        raise ManifestStateError(f"target.cif 缺少必需列: {name}")
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _coordinate_label_seq_ids(target_cif: Path) -> frozenset[int]:
    try:
        raw: dict[str, object] = MMCIF2Dict(str(target_cif))  # type: ignore[no-untyped-call]
    except Exception as error:
        raise ManifestStateError(f"无法解析 Stage 03 target.cif: {target_cif}") from error

    groups = _mmcif_column(raw, "_atom_site.group_PDB")
    chains = _mmcif_column(raw, "_atom_site.label_asym_id")
    labels = _mmcif_column(raw, "_atom_site.label_seq_id")
    if len({len(groups), len(chains), len(labels)}) != 1:
        raise ManifestStateError("target.cif atom_site 编号列长度不一致")
    present: set[int] = set()
    for group, chain, label in zip(groups, chains, labels, strict=True):
        if group != "ATOM" or chain != "A" or label in {".", "?"}:
            continue
        try:
            present.add(int(label))
        except ValueError as error:
            raise ManifestStateError(f"target.cif 含非法 label_seq_id={label}") from error
    if not present:
        raise ManifestStateError("target.cif 的标准链 A 没有 coordinate-present 残基")
    return frozenset(present)


def _validate_hotspot_coordinate_presence(target_cif: Path, hotspots: HotspotsFile) -> None:
    present = _coordinate_label_seq_ids(target_cif)
    approved = {
        label
        for hotspot_set in hotspots.hotspot_sets
        for label in hotspot_set.label_seq_ids
    }
    missing = sorted(approved - present)
    if missing:
        raise ManifestStateError(
            "approved hotspots 包含无坐标的 canonical label_seq_id；"
            f"不能交给 BoltzGen: {missing}"
        )


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
    try:
        with path.open("x", encoding="utf-8") as handle:
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
    except FileExistsError as error:
        raise ManifestStateError(f"Stage 03 禁止覆盖 artifact: {path}") from error


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
            or hashlib.sha256(structure_bytes).hexdigest() != EXPECTED_ASSET_SHA256[structure_name]
        ):
            raise ManifestStateError(f"官方 scaffold package asset checksum 不一致: {scaffold_id}")
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
    if hashlib.sha256(license_bytes).hexdigest() != EXPECTED_ASSET_SHA256["BOLTZGEN_LICENSE.txt"]:
        raise ManifestStateError("BoltzGen license checksum 不一致")
    _exclusive_bytes(license_bytes, destination / "BOLTZGEN_LICENSE.txt")
    return tuple(assets)


def _strategy_id(region_id: str, scaffold_id: str) -> str:
    return f"region-{region_id.lower()}-h-all-c-full-scaffold-{scaffold_id}"


def _design_specification(
    *,
    binding_label_seq_ids: tuple[int, ...],
    avoid_label_seq_ids: tuple[int, ...] = (),
    scaffold_id: str,
    target_crop: tuple[int, int] | None = None,
    scaffold_path: str | None = None,
) -> dict[str, object]:
    target_chain: dict[str, object] = {"id": "A"}
    if target_crop is not None:
        target_chain["res_index"] = f"{target_crop[0]}..{target_crop[1]}"
    binding_contract: dict[str, object] = {
        "id": "A",
        "binding": ",".join(str(value) for value in binding_label_seq_ids),
    }
    if avoid_label_seq_ids:
        binding_contract["not_binding"] = ",".join(
            str(value) for value in avoid_label_seq_ids
        )
    return {
        "entities": [
            {
                "file": {
                    "path": "../../assets/target.cif",
                    "include": [{"chain": target_chain}],
                    "binding_types": [
                        {
                            "chain": binding_contract
                        }
                    ],
                }
            },
            {"file": {"path": scaffold_path or f"../../assets/scaffolds/{scaffold_id}.yaml"}},
        ]
    }


def _variant_scaffold(
    *,
    artifacts_root: Path,
    strategy_dir: Path,
    scaffold_id: str,
    variant: ExplicitStrategyVariant,
) -> tuple[str | None, str | None]:
    if not variant.cdr_overrides and variant.scaffold_template != GPCR_TEMPLATE:
        return None, None
    if variant.scaffold_template == GPCR_TEMPLATE:
        payload, _ = gpcr_template(scaffold_id)
    else:
        source = artifacts_root / "assets" / "scaffolds" / f"{scaffold_id}.yaml"
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManifestStateError(f"scaffold YAML 顶层不是 mapping: {scaffold_id}")
    design = payload.get("design")
    insertions = payload.get("design_insertions")
    if not isinstance(design, list) or len(design) != 1 or not isinstance(insertions, list):
        raise ManifestStateError(f"scaffold CDR contract 无法解析: {scaffold_id}")
    chain = design[0].get("chain") if isinstance(design[0], dict) else None
    if not isinstance(chain, dict) or not isinstance(chain.get("res_index"), str):
        raise ManifestStateError(f"scaffold design range 无法解析: {scaffold_id}")
    ranges = chain["res_index"].split(",")
    if len(ranges) != 3 or len(insertions) != 3:
        raise ManifestStateError(f"scaffold 必须有三个 CDR range: {scaffold_id}")
    for override in variant.cdr_overrides:
        index = override.cdr - 1
        if override.design_res_index is not None:
            ranges[index] = override.design_res_index
        insertion = (
            insertions[index].get("insertion") if isinstance(insertions[index], dict) else None
        )
        if not isinstance(insertion, dict):
            raise ManifestStateError(
                f"scaffold insertion 无法解析: {scaffold_id}/CDR{override.cdr}"
            )
        insertion["num_residues"] = override.insertion_num_residues
    chain["res_index"] = ",".join(ranges)
    payload["path"] = f"../../assets/scaffolds/{scaffold_id}.cif"
    destination = strategy_dir / "scaffold.yaml"
    _exclusive_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), destination)
    return destination.relative_to(artifacts_root).as_posix(), sha256_file(destination)


def compile_vhh_strategy_plan(
    *,
    target_cif: Path,
    hotspots: HotspotsFile,
    artifacts_root: Path,
    variants: tuple[ExplicitStrategyVariant, ...],
    native_variants: tuple[NativeStrategyVariant, ...] = (),
) -> tuple[tuple[ScaffoldAsset, ...], tuple[StrategyRecord, ...]]:
    """Compile only explicitly requested experiments; no global Cartesian product."""

    if sha256_file(target_cif) != hotspots.target_structure_sha256:
        raise ManifestStateError("hotspots.yaml 的 target_structure_sha256 与 Target Bundle 不一致")
    _validate_hotspot_coordinate_presence(target_cif, hotspots)
    if not variants and not native_variants:
        raise ManifestStateError("strategy plan 至少包含一个 variant")
    selected_scaffolds = tuple(
        dict.fromkeys(
            [scaffold for variant in variants for scaffold in variant.scaffold_ids]
            + [variant.scaffold_id for variant in native_variants]
        )
    )
    unknown = sorted(set(selected_scaffolds) - set(SCAFFOLD_IDS))
    if unknown:
        raise ManifestStateError(f"strategy plan 包含未登记 scaffold: {unknown}")
    if artifacts_root.exists() and any(artifacts_root.iterdir()):
        raise ManifestStateError(f"Stage 03 artifacts 目录必须为空: {artifacts_root}")
    target_asset = artifacts_root / "assets" / "target.cif"
    _exclusive_bytes(target_cif.read_bytes(), target_asset)
    raw_assets = materialize_scaffold_registry(artifacts_root / "assets" / "scaffolds")
    assets = tuple(
        asset.model_copy(
            update={
                "specification_path": Path(asset.specification_path)
                .relative_to(artifacts_root)
                .as_posix(),
                "structure_path": Path(asset.structure_path).relative_to(artifacts_root).as_posix(),
            }
        )
        for asset in raw_assets
        if asset.scaffold_id in selected_scaffolds
    )
    by_hotspot = {item.id: tuple(item.label_seq_ids) for item in hotspots.hotspot_sets}
    all_approved = set(value for values in by_hotspot.values() for value in values)
    records: list[StrategyRecord] = []
    for variant in variants:
        if variant.hotspot_set_id is not None and variant.hotspot_set_id not in by_hotspot:
            raise ManifestStateError(f"variant 引用未知 approved hotspot: {variant.hotspot_set_id}")
        labels = variant.binding_label_seq_ids or by_hotspot.get(variant.hotspot_set_id or "", ())
        if not labels or not set(labels).issubset(all_approved):
            raise ManifestStateError("variant binding residues 必须是 approved hotspots 的非空子集")
        avoid = variant.avoid_label_seq_ids
        if avoid:
            require_boltzgen_capability("not_binding")
        if set(labels).intersection(avoid):
            raise ManifestStateError("binding 与 approved avoid residues 不能重叠")
        present = _coordinate_label_seq_ids(target_cif)
        missing_avoid = sorted(set(avoid) - present)
        if missing_avoid:
            raise ManifestStateError(
                f"avoid residues 必须位于 frozen design scope 且有坐标: {missing_avoid}"
            )
        crop = (
            None
            if variant.target_crop is None
            else (variant.target_crop.start, variant.target_crop.end)
        )
        if crop is not None and any(value < crop[0] or value > crop[1] for value in labels):
            raise ManifestStateError("target crop 未覆盖 binding residues")
        if crop is not None and any(value < crop[0] or value > crop[1] for value in avoid):
            raise ManifestStateError("target crop 未覆盖 avoid residues")
        for scaffold_id in variant.scaffold_ids:
            strategy_id = f"{variant.variant_id}-scaffold-{scaffold_id}"
            strategy_dir = artifacts_root / "strategies" / strategy_id
            variant_scaffold_path, variant_scaffold_sha = _variant_scaffold(
                artifacts_root=artifacts_root,
                strategy_dir=strategy_dir,
                scaffold_id=scaffold_id,
                variant=variant,
            )
            specification = strategy_dir / "design.yaml"
            _exclusive_text(
                yaml.safe_dump(
                    _design_specification(
                        binding_label_seq_ids=labels,
                        avoid_label_seq_ids=avoid,
                        scaffold_id=scaffold_id,
                        target_crop=crop,
                        scaffold_path="scaffold.yaml" if variant_scaffold_path else None,
                    ),
                    allow_unicode=True,
                    sort_keys=False,
                ),
                specification,
            )
            record = StrategyRecord(
                strategy_id=strategy_id,
                region_id=variant.variant_id,
                source_hotspot_set_id=variant.hotspot_set_id or "approved-subset",
                scaffold_id=scaffold_id,
                hotspot_strategy="H_subset"
                if variant.binding_label_seq_ids is not None
                else "H_set",
                crop_strategy="C_full" if crop is None else f"C_{crop[0]}_{crop[1]}",
                crop_enabled=crop is not None,
                binding_label_seq_ids=labels,
                avoid_label_seq_ids=avoid,
                candidates_per_strategy=variant.candidates_per_strategy,
                design_specification_path=specification.relative_to(artifacts_root).as_posix(),
                design_specification_sha256=sha256_file(specification),
                scaffold_template=variant.scaffold_template,
                variant_scaffold_path=variant_scaffold_path,
                variant_scaffold_sha256=variant_scaffold_sha,
                hypothesis_id=variant.hypothesis_id,
                role=variant.role,
                evidence_refs=variant.evidence_refs,
                changed_factors=variant.changed_factors,
                held_constant=variant.held_constant,
                rationale=variant.rationale,
                expected_result=variant.expected_result,
                failure_interpretation=variant.failure_interpretation,
            )
            _atomic_json(
                {
                    "schema_version": "0.3",
                    "compilation_status": "compiled",
                    "strategy_profile": STRATEGY_PROFILE_ID,
                    "scaffold_registry": SCAFFOLD_REGISTRY_ID,
                    **record.model_dump(mode="json"),
                },
                strategy_dir / "strategy-manifest.json",
            )
            records.append(record)
    for native_variant in native_variants:
        try:
            payload = yaml.safe_load(native_variant.yaml_text)
        except yaml.YAMLError as error:
            raise ManifestStateError(
                f"native strategy YAML 无法解析: {native_variant.variant_id}"
            ) from error
        if not isinstance(payload, dict):
            raise ManifestStateError("native strategy YAML 顶层必须是 mapping")
        strategy_dir = artifacts_root / "strategies" / native_variant.variant_id
        specification = strategy_dir / "design.yaml"
        _exclusive_text(native_variant.yaml_text, specification)
        record = StrategyRecord(
            strategy_id=native_variant.variant_id,
            region_id="native",
            source_hotspot_set_id="native-expert",
            scaffold_id=native_variant.scaffold_id,
            hotspot_strategy="native",
            crop_strategy="native",
            crop_enabled=False,
            binding_label_seq_ids=tuple(sorted(all_approved)),
            candidates_per_strategy=native_variant.candidates_per_strategy,
            design_specification_path=specification.relative_to(artifacts_root).as_posix(),
            design_specification_sha256=sha256_file(specification),
            native_source_sha256=native_variant.source_sha256,
            hypothesis_id=native_variant.hypothesis_id,
            role=native_variant.role,
            evidence_refs=native_variant.evidence_refs,
            changed_factors=native_variant.changed_factors,
            held_constant=native_variant.held_constant,
            rationale=native_variant.rationale,
            expected_result=native_variant.expected_result,
            failure_interpretation=native_variant.failure_interpretation,
        )
        _atomic_json(
            {
                "schema_version": "0.3",
                "compilation_status": "compiled-native",
                "strategy_profile": STRATEGY_PROFILE_ID,
                "scaffold_registry": SCAFFOLD_REGISTRY_ID,
                **record.model_dump(mode="json"),
            },
            strategy_dir / "strategy-manifest.json",
        )
        records.append(record)
    return assets, tuple(records)


def compile_basic_vhh_matrix(
    *,
    target_cif: Path,
    hotspots: HotspotsFile,
    artifacts_root: Path,
    candidates_per_strategy: int,
    scaffold_ids: tuple[str, ...] | None = None,
) -> tuple[tuple[ScaffoldAsset, ...], tuple[StrategyRecord, ...]]:
    """Compile the region × scaffold matrix with non-hotspots left neutral."""

    target_hash = sha256_file(target_cif)
    if target_hash != hotspots.target_structure_sha256:
        raise ManifestStateError("hotspots.yaml 的 target_structure_sha256 与 Target Bundle 不一致")
    _validate_hotspot_coordinate_presence(target_cif, hotspots)
    if candidates_per_strategy < 1:
        raise ManifestStateError("candidates_per_strategy 必须为正整数")
    selected_scaffolds = SCAFFOLD_IDS if scaffold_ids is None else scaffold_ids
    unknown_scaffolds = sorted(set(selected_scaffolds) - set(SCAFFOLD_IDS))
    if unknown_scaffolds:
        raise ManifestStateError(f"scaffold_ids 包含未登记的官方 scaffold: {unknown_scaffolds}")
    if not selected_scaffolds:
        raise ManifestStateError("scaffold_ids 至少包含一个官方 scaffold")
    if len(selected_scaffolds) != len(set(selected_scaffolds)):
        raise ManifestStateError("scaffold_ids 不能重复")
    if artifacts_root.exists() and any(artifacts_root.iterdir()):
        raise ManifestStateError(f"Stage 03 artifacts 目录必须为空: {artifacts_root}")

    target_asset = artifacts_root / "assets" / "target.cif"
    _exclusive_bytes(target_cif.read_bytes(), target_asset)
    raw_assets = materialize_scaffold_registry(artifacts_root / "assets" / "scaffolds")
    assets = tuple(
        asset.model_copy(
            update={
                "specification_path": Path(asset.specification_path)
                .relative_to(artifacts_root)
                .as_posix(),
                "structure_path": Path(asset.structure_path).relative_to(artifacts_root).as_posix(),
            }
        )
        for asset in raw_assets
        if asset.scaffold_id in selected_scaffolds
    )

    records: list[StrategyRecord] = []
    for hotspot_set in hotspots.hotspot_sets:
        region_id = hotspot_set.id.lower()
        labels = tuple(hotspot_set.label_seq_ids)
        for scaffold_id in selected_scaffolds:
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
                design_specification_path=specification_path.relative_to(artifacts_root).as_posix(),
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
        "avoid_label_seq_ids",
        "neutral_residue_policy",
        "candidates_per_strategy",
        "design_specification_path",
        "design_specification_sha256",
        "scaffold_template",
        "variant_scaffold_path",
        "variant_scaffold_sha256",
        "native_source_sha256",
        "hypothesis_id",
        "role",
        "evidence_refs",
        "changed_factors",
        "held_constant",
        "rationale",
        "expected_result",
        "failure_interpretation",
    )
    with tsv_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            normalized["binding_label_seq_ids"] = ",".join(
                str(value) for value in normalized["binding_label_seq_ids"]
            )
            normalized["avoid_label_seq_ids"] = ",".join(
                str(value) for value in normalized["avoid_label_seq_ids"]
            )
            for name in ("evidence_refs", "changed_factors", "held_constant"):
                normalized[name] = " | ".join(normalized[name])
            writer.writerow(normalized)
