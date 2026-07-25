"""从本地或远程 target 入口创建 canonical EasyDesign 用户项目。"""

from __future__ import annotations

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


def _prediction_payload() -> dict[str, object]:
    return {
        "backend": "protenix-v2",
        "msa": {
            "mode": "remote",
            "providers": [
                {
                    "provider": "colabfold-public",
                    "timeout_seconds": 1800,
                    "max_attempts": 3,
                    "retry_backoff_seconds": 30,
                }
            ],
            "no_msa_fallback": False,
        },
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
    pdb_id: str | None = None,
    chain: str | None = None,
    uniprot: str | None = None,
    uniprot_query: str | None = None,
    taxon_id: int | None = None,
    project_id: str | None = None,
    target_id: str | None = None,
    stop_after_stage: int = 1,
    stage02_method: str | None = None,
    execution_mode: str = "review-gated",
    scope_range: tuple[int, int] | None = None,
) -> InitializedProject:
    """生成 schema 0.4；四种 init 入口互斥，PSE/Bundle 仍通过 --target。"""

    if stop_after_stage not in {1, 2}:
        raise ConfigurationError("Developer Preview init 只支持 --stop-after 1 或 2")
    if execution_mode not in {"review-gated", "unattended"}:
        raise ConfigurationError("--execution-mode 必须是 review-gated 或 unattended")
    selected_stage02_method = stage02_method or (
        "sasa" if execution_mode == "unattended" else "both"
    )
    if sum(
        (
            target is not None,
            pdb_id is not None,
            uniprot is not None,
            uniprot_query is not None,
        )
    ) != 1:
        raise ConfigurationError(
            "--target、--pdb-id、--uniprot、--uniprot-query 必须且只能提供一个"
        )
    if uniprot_query is not None and taxon_id is None:
        raise ConfigurationError("--uniprot-query 必须同时提供 --taxon-id")

    source: Path | None = None
    if target is not None:
        try:
            source = target.resolve(strict=True)
        except OSError as error:
            raise ConfigurationError(f"Target 文件不存在: {target}") from error
        if not source.is_file():
            raise ConfigurationError(f"Target 必须是文件: {source}")
        detected = detect_target_input_format(source)
        if detected is TargetInputFormat.TARGET_BUNDLE:
            raise ConfigurationError(
                "Target Bundle init 还必须声明 source_run_root；请编辑 schema 0.4 配置"
            )
    elif pdb_id is not None:
        detected = TargetInputFormat.PDB_ID
    elif uniprot is not None:
        detected = TargetInputFormat.UNIPROT
    else:
        detected = TargetInputFormat.UNIPROT_SEARCH

    destination = project_root.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ConfigurationError(f"项目目录非空，禁止覆盖: {destination}")
    selected_project_id = project_id or _slug(destination.name, label="项目目录名")
    source_label = (
        source.stem
        if source is not None
        else (pdb_id or uniprot or uniprot_query or "target")
    )
    selected_target_id = target_id or _slug(source_label, label="target 输入")

    if source is not None:
        source_payload: dict[str, object] = {
            "type": "local-file",
            "path": f"inputs/{source.name}",
            "format": str(detected),
            "chain": chain,
            "chain_namespace": "auth",
            "identity": {"uniprot_accession": None},
        }
    elif pdb_id is not None:
        source_payload = {
            "type": "pdb-id",
            "pdb_id": pdb_id.upper(),
            "chain": chain,
            "chain_namespace": "auth",
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
    needs_prediction = detected in {
        TargetInputFormat.SEQUENCE,
        TargetInputFormat.FASTA,
        TargetInputFormat.UNIPROT,
        TargetInputFormat.UNIPROT_SEARCH,
    }
    payload: dict[str, object] = {
        "schema_version": "0.4",
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
                _prediction_payload() if needs_prediction else None
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
    try:
        if source is not None:
            input_directory.mkdir()
            target_path = input_directory / source.name
            shutil.copyfile(source, target_path)
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
        detected_format=detected,
    )
