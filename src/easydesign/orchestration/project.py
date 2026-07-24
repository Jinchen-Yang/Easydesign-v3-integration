"""从真实 target 文件创建最小、可验证的 EasyDesign 用户项目。"""

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
    target_path: Path
    detected_format: TargetInputFormat


def _slug(value: str, *, label: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not normalized or re.fullmatch(ID_PATTERN, normalized) is None:
        raise ConfigurationError(f"无法从 {label} 生成稳定 ID，请显式提供")
    return normalized


def _stage02_payload() -> dict[str, object]:
    return {
        "mode": "automatic",
        "automatic": {
            "region_count": 3,
            "sasa": {
                "rsasa_threshold": 0.25,
                "relaxed_threshold": 0.20,
                "probe_radius_angstrom": 1.4,
                "sphere_points": 960,
            },
            "patch": {
                "target_member_count": 12,
                "minimum_member_count": 6,
                "heavy_atom_neighbor_angstrom": 5.0,
                "anchor_neighbor_angstrom": 12.0,
                "compactness_radius_angstrom": 14.0,
            },
            "evidence": {"scannet_mode": "epitope", "use_msa": False},
            "avoid_label_seq_ids": [],
        },
    }


def initialize_project(
    *,
    project_root: Path,
    target: Path,
    project_id: str | None = None,
    target_id: str | None = None,
    stop_after_stage: int = 1,
) -> InitializedProject:
    """复制 target 并生成显式 YAML；目标目录必须不存在或为空。"""

    if stop_after_stage not in {1, 2}:
        raise ConfigurationError("Developer Preview init 只支持 --stop-after 1 或 2")
    try:
        source = target.resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(f"Target 文件不存在: {target}") from error
    if not source.is_file():
        raise ConfigurationError(f"Target 必须是文件: {source}")
    detected = detect_target_input_format(source)
    if detected not in {
        TargetInputFormat.SEQUENCE,
        TargetInputFormat.FASTA,
        TargetInputFormat.PSE,
    }:
        raise ConfigurationError(
            f"已识别 target format={detected}，但 Developer Preview 尚未实现该入口"
        )

    destination = project_root.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ConfigurationError(f"项目目录非空，禁止覆盖: {destination}")
    selected_project_id = project_id or _slug(destination.name, label="项目目录名")
    selected_target_id = target_id or _slug(source.stem, label="target 文件名")
    payload: dict[str, object] = {
        "schema_version": "0.2",
        "project_id": selected_project_id,
        "target": {
            "id": selected_target_id,
            "source": f"inputs/{source.name}",
            "format": "auto",
        },
    }
    if detected in {TargetInputFormat.SEQUENCE, TargetInputFormat.FASTA}:
        payload["structure_prediction"] = {
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
    if stop_after_stage == 2:
        payload["stage02"] = _stage02_payload()
    payload["workflow"] = {"stop_after_stage": stop_after_stage}

    created_root = not destination.exists()
    destination.mkdir(parents=True, exist_ok=True)
    input_directory = destination / "inputs"
    input_directory.mkdir()
    target_path = input_directory / source.name
    config_path = destination / "easydesign.yaml"
    try:
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
