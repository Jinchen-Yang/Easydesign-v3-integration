"""从本地或远程 target 入口创建 canonical EasyDesign 用户项目。"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from easydesign.core import ConfigurationError
from easydesign.core.artifacts import ID_PATTERN

from .config import TargetInputFormat, detect_target_input_format, load_run_config


@dataclass(frozen=True, slots=True)
class InitializedProject:
    project_root: Path
    config_path: Path
    target_path: Path | None
    msa_path: Path | None
    detected_format: TargetInputFormat


def _slug(value: str, *, label: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not normalized or re.fullmatch(ID_PATTERN, normalized) is None:
        raise ConfigurationError(f"无法从 {label} 生成稳定 ID，请显式提供")
    return normalized


def _stage02_payload(method: str, *, unattended: bool) -> dict[str, object]:
    methods = {
        "both": ["sasa", "scannet"],
        "sasa": ["sasa"],
        "scannet": ["scannet"],
    }
    try:
        selected_methods = methods[method]
    except KeyError as error:
        raise ConfigurationError("--stage02-method 必须是 sasa、scannet 或 both") from error
    if unattended and len(selected_methods) != 1:
        raise ConfigurationError("unattended Stage 02 必须选择 sasa 或 scannet，不能 both")
    return {
        "mode": "automatic",
        "methods": selected_methods,
        "annotations": {"uniprot": "if_available"},
        "automatic": {
            "requested_region_count": 3,
            "minimum_region_count": 2,
            "sasa": {
                "rsasa_threshold": 0.25,
                "relaxed_threshold": 0.20,
                "probe_radius_angstrom": 1.4,
                "sphere_points": 960,
                "ensemble_consensus_fraction": 0.70,
            },
            "patch": {
                "target_member_count": 12,
                "minimum_member_count": 5,
                "heavy_atom_neighbor_angstrom": 5.0,
                "anchor_neighbor_angstrom": 12.0,
                "compactness_radius_angstrom": 14.0,
            },
            "evidence": {"scannet_mode": "epitope", "use_msa": False},
            "avoid_label_seq_ids": [],
        },
        "unattended_approval": (
            {"region_count": 3, "allow_structural_only": False}
            if unattended
            else None
        ),
    }


def _prediction_payload(
    *,
    precomputed_msa_path: str | None,
    cache_mode: str,
) -> dict[str, object]:
    msa: dict[str, object]
    if precomputed_msa_path is not None:
        msa = {
            "mode": "precomputed",
            "path": precomputed_msa_path,
        }
    else:
        msa = {
            "mode": "remote",
            "cache_mode": cache_mode,
            "providers": [
                {
                    "provider": "colabfold-public",
                    "timeout_seconds": 1800,
                    "max_attempts": 3,
                    "retry_backoff_seconds": 30,
                }
            ],
            "no_msa_fallback": False,
        }
    return {
        "backend": "protenix-v2",
        "msa": msa,
        "template_mode": "disabled",
        "parameter_profile": "model-default",
        "prediction_timeout_seconds": 7200,
        "seeds": [101],
        "sample_count": 1,
    }


def initialize_project(
    *,
    project_root: Path,
    target: Path | None = None,
    target_bundle: Path | None = None,
    source_run_root: Path | None = None,
    pdb_id: str | None = None,
    chain: str | None = None,
    chain_namespace: str = "auth",
    identity_uniprot: str | None = None,
    uniprot: str | None = None,
    uniprot_query: str | None = None,
    taxon_id: int | None = None,
    project_id: str | None = None,
    target_id: str | None = None,
    stop_after_stage: int = 1,
    stage02_method: str | None = None,
    execution_mode: str = "review-gated",
    scope_range: tuple[int, int] | None = None,
    scope_feature_type: str | None = None,
    scope_feature_name: str | None = None,
    precomputed_msa: Path | None = None,
    msa_cache_mode: str = "online",
) -> InitializedProject:
    """生成 schema 0.5；六类 Stage 01 入口全部有显式 init。"""

    if stop_after_stage not in {1, 2}:
        raise ConfigurationError("Developer Preview init 只支持 --stop-after 1 或 2")
    if execution_mode not in {"review-gated", "unattended"}:
        raise ConfigurationError("--execution-mode 必须是 review-gated 或 unattended")
    if chain_namespace not in {"auth", "label"}:
        raise ConfigurationError("--chain-namespace 必须是 auth 或 label")
    if scope_range is not None and scope_feature_type is not None:
        raise ConfigurationError("--scope-range 与 --scope-feature-type 不能同时提供")
    if scope_feature_name is not None and scope_feature_type is None:
        raise ConfigurationError("--scope-feature-name 必须配合 --scope-feature-type")
    if msa_cache_mode not in {"online", "prefer-cache", "offline"}:
        raise ConfigurationError(
            "--msa-cache-mode 必须是 online、prefer-cache 或 offline"
        )
    if precomputed_msa is not None and msa_cache_mode != "online":
        raise ConfigurationError(
            "--precomputed-msa 与 --msa-cache-mode 不能同时指定"
        )
    if target_bundle is not None and source_run_root is None:
        raise ConfigurationError("--target-bundle 必须同时提供 --source-run-root")
    if target_bundle is None and source_run_root is not None:
        raise ConfigurationError("--source-run-root 只能配合 --target-bundle")
    selected_stage02_method = stage02_method or (
        "sasa" if execution_mode == "unattended" else "both"
    )
    if sum(
        (
            target is not None,
            target_bundle is not None,
            pdb_id is not None,
            uniprot is not None,
            uniprot_query is not None,
        )
    ) != 1:
        raise ConfigurationError(
            "--target、--target-bundle、--pdb-id、--uniprot、--uniprot-query "
            "必须且只能提供一个"
        )
    if uniprot_query is not None and taxon_id is None:
        raise ConfigurationError("--uniprot-query 必须同时提供 --taxon-id")
    if identity_uniprot is not None and target is None:
        raise ConfigurationError("--identity-uniprot 只能配合本地 --target")

    source: Path | None = None
    msa_source: Path | None = None
    resolved_source_run_root: Path | None = None
    bundle_target_id: str | None = None
    selected_file = target if target is not None else target_bundle
    if selected_file is not None:
        try:
            source = selected_file.resolve(strict=True)
        except OSError as error:
            raise ConfigurationError(f"Target 文件不存在: {selected_file}") from error
        if not source.is_file():
            raise ConfigurationError(f"Target 必须是文件: {source}")
        detected = detect_target_input_format(source)
        if target_bundle is not None and detected is not TargetInputFormat.TARGET_BUNDLE:
            raise ConfigurationError(
                f"--target-bundle 不是有效 Target Bundle: {source}"
            )
        if target is not None and detected is TargetInputFormat.TARGET_BUNDLE:
            raise ConfigurationError(
                "Target Bundle 必须使用 --target-bundle 和 --source-run-root"
            )
        if target_bundle is not None:
            assert source_run_root is not None
            try:
                resolved_source_run_root = source_run_root.resolve(strict=True)
            except OSError as error:
                raise ConfigurationError(
                    f"source run root 不存在: {source_run_root}"
                ) from error
            try:
                bundle_payload = json.loads(source.read_text(encoding="utf-8"))
                bundle_target_id = str(bundle_payload["target_id"])
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as error:
                raise ConfigurationError(
                    f"Target Bundle 无法读取 target_id: {source}"
                ) from error
    elif pdb_id is not None:
        detected = TargetInputFormat.PDB_ID
    elif uniprot is not None:
        detected = TargetInputFormat.UNIPROT
    else:
        detected = TargetInputFormat.UNIPROT_SEARCH

    if precomputed_msa is not None:
        try:
            msa_source = precomputed_msa.resolve(strict=True)
        except OSError as error:
            raise ConfigurationError(
                f"预计算 A3M 不存在: {precomputed_msa}"
            ) from error
        if not msa_source.is_file():
            raise ConfigurationError(f"预计算 A3M 必须是文件: {msa_source}")

    destination = project_root.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ConfigurationError(f"项目目录非空，禁止覆盖: {destination}")
    selected_project_id = project_id or _slug(destination.name, label="项目目录名")
    source_label = (
        source.stem
        if source is not None
        else (pdb_id or uniprot or uniprot_query or "target")
    )
    selected_target_id = target_id or (
        bundle_target_id or _slug(source_label, label="target 输入")
    )
    if (
        bundle_target_id is not None
        and target_id is not None
        and target_id != bundle_target_id
    ):
        raise ConfigurationError(
            "Target Bundle target_id 禁止在 init 时静默重命名: "
            f"bundle={bundle_target_id}, requested={target_id}"
        )

    source_payload: dict[str, object]
    if target_bundle is not None:
        assert source is not None and resolved_source_run_root is not None
        source_payload = {
            "type": "target-bundle",
            "path": f"inputs/{source.name}",
            "source_run_root": str(resolved_source_run_root),
        }
    elif source is not None:
        source_payload = {
            "type": "local-file",
            "path": f"inputs/{source.name}",
            "format": str(detected),
            "chain": chain,
            "chain_namespace": chain_namespace,
            "identity": {"uniprot_accession": identity_uniprot},
        }
    elif pdb_id is not None:
        source_payload = {
            "type": "pdb-id",
            "pdb_id": pdb_id.upper(),
            "chain": chain,
            "chain_namespace": chain_namespace,
        }
    elif uniprot is not None:
        source_payload = {
            "type": "uniprot",
            "accession": uniprot.upper(),
            "organism_taxon_id": taxon_id,
            "isoform": "canonical",
            "reviewed": "required",
        }
    else:
        assert uniprot_query is not None and taxon_id is not None
        source_payload = {
            "type": "uniprot-search",
            "query": uniprot_query,
            "organism_taxon_id": taxon_id,
            "isoform": "canonical",
            "reviewed": "required",
        }

    scope_payload: dict[str, object] = {"type": "full-sequence"}
    if scope_range is not None:
        scope_payload = {
            "type": "residue-range",
            "start": scope_range[0],
            "end": scope_range[1],
        }
    elif scope_feature_type is not None:
        scope_payload = {
            "type": "uniprot-feature",
            "feature_type": scope_feature_type,
            "feature_name": scope_feature_name,
        }
    needs_prediction = detected in {
        TargetInputFormat.SEQUENCE,
        TargetInputFormat.FASTA,
        TargetInputFormat.UNIPROT,
        TargetInputFormat.UNIPROT_SEARCH,
    }
    if msa_source is not None and not needs_prediction:
        raise ConfigurationError(
            "--precomputed-msa 只适用于 FASTA/裸序列/UniProt 预测入口"
        )
    if msa_cache_mode != "online" and not needs_prediction:
        raise ConfigurationError(
            "--msa-cache-mode 只适用于 FASTA/裸序列/UniProt 预测入口"
        )
    payload: dict[str, object] = {
        "schema_version": "0.5",
        "project_id": selected_project_id,
        "design": {
            "binder_profile": "vhh",
            "intent": "exploratory",
            "required_reviews": [],
        },
        "workflow": {
            "execution_mode": execution_mode,
            "stop_after_stage": stop_after_stage,
            "cache_mode": "online",
        },
        "stage01": {
            "target": {
                "id": selected_target_id,
                "source": source_payload,
                "scope": scope_payload,
            },
            "structure_selection": {
                "policy": "experimental-first",
                "quality_profile": "experimental-strict-v1",
                "on_no_eligible_candidate": "predict",
                "on_ambiguous_candidates": "predict",
                "preserve_source_context": True,
                "keep_ligands": [],
            },
            "structure_prediction": (
                _prediction_payload(
                    precomputed_msa_path=(
                        f"inputs/{msa_source.name}"
                        if msa_source is not None
                        else None
                    ),
                    cache_mode=msa_cache_mode,
                )
                if needs_prediction
                else None
            ),
        },
        "stage02": (
            _stage02_payload(
                selected_stage02_method,
                unattended=execution_mode == "unattended",
            )
            if stop_after_stage == 2
            else None
        ),
    }
    for stage_number in range(3, 8):
        payload[f"stage{stage_number:02d}"] = None

    created_root = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    input_directory = destination / "inputs"
    config_path = destination / "easydesign.yaml"
    target_path: Path | None = None
    msa_path: Path | None = None
    try:
        if source is not None or msa_source is not None:
            input_directory.mkdir()
        if source is not None:
            target_path = input_directory / source.name
            shutil.copyfile(source, target_path)
        if msa_source is not None:
            msa_path = input_directory / msa_source.name
            if msa_path == target_path:
                raise ConfigurationError("Target 文件与预计算 A3M 文件名不能相同")
            shutil.copyfile(msa_source, msa_path)
        with config_path.open("x", encoding="utf-8", newline="\n") as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
        (destination / ".gitignore").write_text("runs/\n", encoding="utf-8")
        loaded = load_run_config(config_path)
        if loaded.detected_format is not detected:
            raise ConfigurationError("生成项目的输入格式复核不一致")
    except Exception:
        shutil.rmtree(input_directory, ignore_errors=True)
        config_path.unlink(missing_ok=True)
        (destination / ".gitignore").unlink(missing_ok=True)
        if created_root:
            destination.rmdir()
        raise
    return InitializedProject(
        project_root=destination,
        config_path=config_path,
        target_path=target_path,
        msa_path=msa_path,
        detected_format=detected,
    )
