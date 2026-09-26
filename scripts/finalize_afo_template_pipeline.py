#!/usr/bin/env python3
"""Publish and activate one fully downloaded AFO local template component."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration.runtime_components import (
    AfoTemplatePipelineComponentReceipt,
    activate_afo_template_pipeline_component,
    verify_afo_template_pipeline_component,
)
from easydesign.workspace_context import WorkspaceContext

DATABASE_VERSION = "pdb-2022-09-28"
SEQRES_VERSION = "pdb-seqres-2022-09-28"
MAX_TEMPLATE_DATE = date(2022, 9, 28)
SEQRES_URL = (
    "https://storage.googleapis.com/alphafold-databases/v3.0/"
    "pdb_seqres_2022_09_28.fasta.zst"
)
MMCIF_URL = (
    "https://storage.googleapis.com/alphafold-databases/v3.0/"
    "pdb_2022_09_28_mmcif_files.tar.zst"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument(
        "--profile",
        type=Path,
        help="Activate only this clone-local profile (defaults to runtime/profile.yaml)",
    )
    return parser.parse_args()


def _hmmer_version(executable: Path) -> str:
    completed = subprocess.run(
        [str(executable), "-h"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = completed.stdout + "\n" + completed.stderr
    if completed.returncode != 0 or "HMMER 3.4" not in output:
        raise ConfigurationError("AFO template component 必须使用 HMMER 3.4")
    return "3.4"


def _mmcif_manifest(root: Path, destination: Path) -> tuple[int, str]:
    paths = tuple(
        sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in {".cif", ".mmcif"}
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )
    if not paths:
        raise ConfigurationError("AFO template mmCIF snapshot 为空")
    files = [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]
    payload = {
        "schema_version": "0.1",
        "database_version": DATABASE_VERSION,
        "file_count": len(files),
        "files": files,
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        with destination.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        if destination.read_bytes() != encoded:
            raise ConfigurationError(
                "AFO template mmCIF manifest 已存在但内容不一致"
            ) from error
    return len(files), hashlib.sha256(encoded).hexdigest()


def main() -> int:
    arguments = _arguments()
    context = WorkspaceContext.from_root(arguments.workspace_root.resolve())
    staging = arguments.staging.resolve()
    staging_root = context.runtime_root / "staging"
    if not staging.is_relative_to(staging_root.resolve()):
        raise ConfigurationError("AFO template staging 必须位于当前 clone runtime/staging")
    if (staging / "STATUS").read_text(encoding="utf-8").strip() != "extracted":
        raise ConfigurationError("AFO template download/extraction 尚未完成")
    source_component = staging / "component"
    final_component = (
        context.runtime_root
        / "models/afo-template-pipeline-v1/pdb-2022-09-28"
    )
    receipt_path = final_component / "component.json"
    if final_component.exists():
        verify_afo_template_pipeline_component(receipt_path, context=context)
        profile = activate_afo_template_pipeline_component(
            receipt_path,
            context=context,
            profile_path=arguments.profile,
        )
        print(profile)
        return 0
    hmmbuild = source_component / "tools/hmmbuild"
    hmmsearch = source_component / "tools/hmmsearch"
    hmmalign = source_component / "tools/hmmalign"
    disabled_search = source_component / "tools/disabled-msa-search"
    unused_database = source_component / "databases/unused-msa-database.sentinel"
    seqres = source_component / "databases/pdb_seqres_2022_09_28.fasta"
    mmcif = source_component / "databases/mmcif_files"
    for path in (
        hmmbuild,
        hmmsearch,
        hmmalign,
        disabled_search,
        unused_database,
        seqres,
    ):
        if not path.is_file():
            raise ConfigurationError(f"AFO template component 缺少文件: {path}")
    if not mmcif.is_dir():
        raise ConfigurationError(f"AFO template component 缺少 mmCIF 目录: {mmcif}")
    version = _hmmer_version(hmmsearch)
    manifest = source_component / "mmcif-manifest.json"
    file_count, manifest_sha = _mmcif_manifest(mmcif, manifest)
    final_component.parent.mkdir(parents=True, exist_ok=True)
    final_paths = {
        "hmmbuild": final_component / "tools/hmmbuild",
        "hmmsearch": final_component / "tools/hmmsearch",
        "hmmalign": final_component / "tools/hmmalign",
        "disabled_search": final_component / "tools/disabled-msa-search",
        "unused_database": (
            final_component / "databases/unused-msa-database.sentinel"
        ),
        "seqres": final_component / "databases/pdb_seqres_2022_09_28.fasta",
        "mmcif": final_component / "databases/mmcif_files",
        "manifest": final_component / "mmcif-manifest.json",
    }
    receipt = AfoTemplatePipelineComponentReceipt(
        installed_at=datetime.now(UTC),
        hmmbuild=final_paths["hmmbuild"],
        hmmbuild_sha256=sha256_file(hmmbuild),
        hmmsearch=final_paths["hmmsearch"],
        hmmsearch_sha256=sha256_file(hmmsearch),
        hmmalign=final_paths["hmmalign"],
        hmmalign_sha256=sha256_file(hmmalign),
        hmmer_version=version,
        disabled_msa_search_executable=final_paths["disabled_search"],
        disabled_msa_search_executable_sha256=sha256_file(disabled_search),
        unused_msa_database_sentinel=final_paths["unused_database"],
        unused_msa_database_sentinel_sha256=sha256_file(unused_database),
        seqres_database=final_paths["seqres"],
        seqres_database_sha256=sha256_file(seqres),
        seqres_database_version=SEQRES_VERSION,
        mmcif_database=final_paths["mmcif"],
        mmcif_manifest=final_paths["manifest"],
        mmcif_manifest_sha256=manifest_sha,
        mmcif_database_version=DATABASE_VERSION,
        mmcif_file_count=file_count,
        max_template_date=MAX_TEMPLATE_DATE,
        source_urls=(SEQRES_URL, MMCIF_URL),
    )
    component_receipt = source_component / "component.json"
    with component_receipt.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(receipt.model_dump_json(indent=2))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    source_component.rename(final_component)
    verify_afo_template_pipeline_component(receipt_path, context=context)
    profile = activate_afo_template_pipeline_component(
        receipt_path,
        context=context,
        profile_path=arguments.profile,
    )
    print(profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
