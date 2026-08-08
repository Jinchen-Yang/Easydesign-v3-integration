"""Build a compact, manifest-faithful run bundle for read-only review."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from easydesign.core import ArtifactRef, RunManifest, StageManifest, load_model
from easydesign.core.hashing import sha256_file
from easydesign.safe_writes import read_last_text_line

_PRUNED_RUNTIME_DIRECTORIES = frozenset({"logs", "runtime", "tasks", "work"})


@dataclass(frozen=True)
class EvidenceBundleOutcome:
    """Result of a compact read-only evidence export."""

    bundle_root: Path
    run_root: Path
    manifest_path: Path
    file_count: int
    size_bytes: int


def _safe_relative(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Evidence bundle 路径不是安全相对路径: {value}")
    return relative


def _copy_relative(source_root: Path, target_root: Path, relative: str) -> None:
    selected = _safe_relative(relative)
    source = source_root / selected
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Evidence bundle 缺少普通文件: {selected.as_posix()}")
    target = target_root / selected
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_non_runtime_tree(source_root: Path, target_root: Path) -> None:
    for source in sorted(source_root.rglob("*")):
        relative = source.relative_to(source_root)
        if any(part in _PRUNED_RUNTIME_DIRECTORIES for part in relative.parts):
            continue
        if source.is_symlink():
            raise ValueError(f"Evidence bundle 禁止 symlink: {relative.as_posix()}")
        if source.is_dir():
            (target_root / relative).mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _iter_stage_artifacts(stage: StageManifest) -> Iterable[ArtifactRef]:
    yield from stage.input_artifacts
    yield from stage.output_artifacts
    for attempt in stage.attempts:
        yield from attempt.log_artifacts


def _load_json_reference(run_root: Path, reference: ArtifactRef) -> dict[str, Any]:
    path = reference.verify(run_root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Evidence bundle JSON 必须是 object: {reference.relative_path}")
    return payload


def _copy_stage05_review_structures(
    source_root: Path,
    target_root: Path,
    stage: StageManifest,
) -> tuple[int, int]:
    by_id = {item.artifact_id: item for item in stage.output_artifacts}
    validation_ref = by_id.get("expansion-validation-report")
    index_ref = by_id.get("expansion-candidate-index")
    if validation_ref is None or index_ref is None:
        return 0, 0

    validation = _load_json_reference(source_root, validation_ref)
    candidate_index = _load_json_reference(source_root, index_ref)
    local_pass_ids = {
        str(item.get("candidate_id"))
        for item in validation.get("candidates") or []
        if isinstance(item, dict) and item.get("local_gate_pass") is True
    }
    copied_structures = 0
    for item in candidate_index.get("candidates") or []:
        if not isinstance(item, dict) or str(item.get("candidate_id")) not in local_pass_ids:
            continue
        for key in ("original_structure", "refolded_structure"):
            value = item.get(key)
            if not isinstance(value, dict):
                continue
            reference = ArtifactRef.model_validate(value)
            reference.verify(source_root)
            _copy_relative(source_root, target_root, reference.relative_path)
            copied_structures += 1

    prediction_count = 0
    for item in validation.get("predictions") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("predicted_structure")
        if not isinstance(value, dict):
            continue
        reference = ArtifactRef.model_validate(value)
        reference.verify(source_root)
        _copy_relative(source_root, target_root, reference.relative_path)
        prediction_count += 1
    return copied_structures, prediction_count


def _verify_manifest_closure(
    run_root: Path,
    manifest: RunManifest,
) -> tuple[StageManifest, ...]:
    manifest.config_snapshot.verify(run_root)
    stages: list[StageManifest] = []
    for reference in manifest.stage_manifest_refs:
        stage = load_model(reference.verify(run_root), StageManifest)
        for artifact in _iter_stage_artifacts(stage):
            artifact.verify(run_root)
        stages.append(stage)
    return tuple(stages)


def build_evidence_bundle(
    source_run_root: Path,
    output_root: Path,
    *,
    generated_at: datetime | None = None,
) -> EvidenceBundleOutcome:
    """Export one immutable run for review without backend intermediate trees."""

    source = source_run_root.expanduser().resolve()
    output = output_root.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"source run 不存在: {source}")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Evidence bundle 输出目录必须为空: {output}")

    pointer = source / "manifests" / "LATEST"
    latest_name = read_last_text_line(pointer)
    latest_path = source / "manifests" / latest_name
    manifest = load_model(latest_path, RunManifest)
    stages = _verify_manifest_closure(source, manifest)

    target = output / "evidence-runs" / manifest.project_id / manifest.run_id
    target.mkdir(parents=True, exist_ok=False)
    _copy_non_runtime_tree(source, target)

    _copy_relative(source, target, manifest.config_snapshot.relative_path)
    stage05_structures = 0
    protenix_structures = 0
    for reference, stage in zip(manifest.stage_manifest_refs, stages, strict=True):
        _copy_relative(source, target, reference.relative_path)
        for artifact in _iter_stage_artifacts(stage):
            artifact.verify(source)
            _copy_relative(source, target, artifact.relative_path)
        if str(stage.stage_id) == "05-pilot-filtering":
            stage05_structures, protenix_structures = _copy_stage05_review_structures(
                source,
                target,
                stage,
            )

    _verify_manifest_closure(target, manifest)
    generated = (generated_at or datetime.now(tz=UTC)).astimezone(UTC)
    run_index_path = output / "evidence-runs" / "run-index.json"
    run_index_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "generated_at": generated.isoformat(),
                "entries": [
                    {
                        "category": "project-run",
                        "path": f"{manifest.project_id}/{manifest.run_id}",
                        "layout_version": "1",
                        "status": str(manifest.status),
                        "project_id": manifest.project_id,
                        "run_id": manifest.run_id,
                        "notes": ["Repository-shared read-only evidence bundle."],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files: list[dict[str, Any]] = []
    size_bytes = 0
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        relative = path.relative_to(output).as_posix()
        size = path.stat().st_size
        size_bytes += size
        files.append(
            {
                "path": relative,
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )
    bundle_manifest = {
        "schema_version": "0.1",
        "bundle_type": "easydesign-local-evidence",
        "generated_at": generated.isoformat().replace("+00:00", "Z"),
        "project_id": manifest.project_id,
        "run_id": manifest.run_id,
        "run_manifest": (
            target / "manifests" / latest_name
        ).relative_to(output).as_posix(),
        "source_run_manifest_sha256": sha256_file(latest_path),
        "scientific_status": manifest.status,
        "evidence_status": manifest.evidence_status,
        "coverage": {
            "stage_count": len(stages),
            "stage05_local_pass_structure_files": stage05_structures,
            "stage05_protenix_structure_files": protenix_structures,
            "backend_intermediate_directories_included": False,
        },
        "file_count": len(files),
        "size_bytes": size_bytes,
        "files": files,
    }
    manifest_path = output / "bundle-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(bundle_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return EvidenceBundleOutcome(
        bundle_root=output,
        run_root=target,
        manifest_path=manifest_path,
        file_count=len(files),
        size_bytes=size_bytes,
    )


def verify_evidence_bundle(bundle_root: Path) -> EvidenceBundleOutcome:
    """Verify bundle file hashes and the enclosed Run/Stage manifest closure."""

    root = bundle_root.expanduser().resolve()
    manifest_path = root / "bundle-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("bundle_type") not in {
        "easydesign-local-evidence",
        "easydesign-ui-evidence",
    }:
        raise ValueError("不是 EasyDesign evidence bundle")
    files = payload.get("files")
    if not isinstance(files, list):
        raise ValueError("Evidence bundle files 字段无效")
    size_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Evidence bundle file entry 无效")
        relative = _safe_relative(str(item["path"]))
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Evidence bundle 文件缺失: {relative.as_posix()}")
        size = path.stat().st_size
        if size != int(item["size_bytes"]):
            raise ValueError(f"Evidence bundle 文件大小不一致: {relative.as_posix()}")
        if sha256_file(path) != str(item["sha256"]):
            raise ValueError(f"Evidence bundle SHA-256 不一致: {relative.as_posix()}")
        size_bytes += size
    run_manifest_path = root / _safe_relative(str(payload["run_manifest"]))
    manifest = load_model(run_manifest_path, RunManifest)
    run_root = run_manifest_path.parent.parent
    _verify_manifest_closure(run_root, manifest)
    run_index_path = root / "evidence-runs" / "run-index.json"
    run_index = json.loads(run_index_path.read_text(encoding="utf-8"))
    expected_path = f"{manifest.project_id}/{manifest.run_id}"
    entries = run_index.get("entries") if isinstance(run_index, dict) else None
    if not isinstance(entries, list) or not any(
        isinstance(entry, dict)
        and entry.get("category") == "project-run"
        and entry.get("path") == expected_path
        for entry in entries
    ):
        raise ValueError("Evidence bundle run-index 未声明所含 run")
    if size_bytes != int(payload["size_bytes"]):
        raise ValueError("Evidence bundle 总大小不一致")
    return EvidenceBundleOutcome(
        bundle_root=root,
        run_root=run_root,
        manifest_path=manifest_path,
        file_count=len(files),
        size_bytes=size_bytes,
    )


__all__ = [
    "EvidenceBundleOutcome",
    "build_evidence_bundle",
    "verify_evidence_bundle",
]
