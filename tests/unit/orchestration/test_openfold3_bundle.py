from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from easydesign.core import ConfigurationError, sha256_file
from easydesign.orchestration.git_sources import directory_content_sha256
from easydesign.orchestration.openfold3_bundle import (
    _export_runner_source,
    _verify_conversion_receipt,
)
from easydesign.orchestration.runtime_components import (
    load_openfold3_validation_receipt,
)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _runner_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "runner-repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    _git(repository, "config", "user.name", "Fixture")
    (repository / "run_alphafold.py").write_text("OFFICIAL = True\n", encoding="utf-8")
    (repository / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (repository / "WEIGHTS_TERMS_OF_USE.md").write_text("terms\n", encoding="utf-8")
    (repository / "WEIGHTS_PROHIBITED_USE_POLICY.md").write_text(
        "policy\n", encoding="utf-8"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "fixture")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_runner_export_rejects_head_mismatch(tmp_path: Path) -> None:
    repository, _ = _runner_repository(tmp_path)
    workspace = tmp_path / "export"
    workspace.mkdir()

    with pytest.raises(ConfigurationError, match="HEAD"):
        _export_runner_source(
            repository,
            runner_commit="0" * 40,
            workspace=workspace,
        )


def test_runner_export_rejects_tracked_dirty_worktree(tmp_path: Path) -> None:
    repository, commit = _runner_repository(tmp_path)
    (repository / "run_alphafold.py").write_text("PATCHED = True\n", encoding="utf-8")
    workspace = tmp_path / "export"
    workspace.mkdir()

    with pytest.raises(ConfigurationError, match="本地修改"):
        _export_runner_source(repository, runner_commit=commit, workspace=workspace)


def test_runner_export_reads_commit_object_not_hidden_worktree_patch(tmp_path: Path) -> None:
    repository, commit = _runner_repository(tmp_path)
    _git(repository, "update-index", "--assume-unchanged", "run_alphafold.py")
    (repository / "run_alphafold.py").write_text("PATCHED = True\n", encoding="utf-8")
    workspace = tmp_path / "export"
    workspace.mkdir()

    exported, _ = _export_runner_source(
        repository,
        runner_commit=commit,
        workspace=workspace,
    )

    assert (exported / "run_alphafold.py").read_text(encoding="utf-8") == (
        "OFFICIAL = True\n"
    )


@pytest.mark.skipif(shutil.which("zstd") is None, reason="zstd is required")
def test_conversion_receipt_is_cross_checked_against_actual_weights(tmp_path: Path) -> None:
    plain = tmp_path / "weights.bin"
    plain.write_bytes(b"833-dimensional-converted-weights")
    first = tmp_path / "first.bin.zst"
    second = tmp_path / "second.bin.zst"
    subprocess.run(["zstd", "-q", "-f", str(plain), "-o", str(first)], check=True)
    shutil.copyfile(first, second)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    def evidence(name: str) -> dict[str, object]:
        path = evidence_root / f"{name}.log"
        path.write_text(f"{name}: ok\n", encoding="utf-8")
        return {
            "relative_path": f"evidence/{name}.log",
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    runner = tmp_path / "runner"
    runner.mkdir()
    (runner / "run_alphafold.py").write_text("official\n", encoding="utf-8")
    runner_tree = directory_content_sha256(runner)
    wrong_compressed_sha = "0" * 64
    conversions = [
        {
            "conversion_id": identity,
            "compressed_size_bytes": first.stat().st_size,
            "compressed_sha256": wrong_compressed_sha,
            "uncompressed_size_bytes": plain.stat().st_size,
            "uncompressed_sha256": sha256_file(plain),
            "log": evidence(identity),
        }
        for identity in ("conversion-a", "conversion-b")
    ]
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "backend_version": "3.1.4",
                "runner_commit": "1" * 40,
                "runner_tree_sha256": runner_tree,
                "raw_checkpoint_sha256": "2" * 64,
                "conversions": conversions,
                "converter_tests": {
                    "command": ["pytest", "converter"],
                    "collected": 43,
                    "passed": 43,
                    "return_code": 0,
                    "log": evidence("converter-tests"),
                },
                "verification_harnesses": [
                    {
                        "harness_id": "pytorch-jax-parity",
                        "command": ["python", "verify.py"],
                        "return_code": 0,
                        "tolerance": 0.001,
                        "maximum_relative_error": 0.0001,
                        "log": evidence("harness"),
                    }
                ],
                "python_version": "3.12.11",
                "pytorch_version": "2.7.1",
                "environment_inventory": evidence("inventory"),
                "generated_at": "2026-08-11T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    receipt = load_openfold3_validation_receipt(receipt_path)

    with pytest.raises(ConfigurationError, match="实际文件"):
        _verify_conversion_receipt(
            receipt_path,
            receipt=receipt,
            backend_version="3.1.4",
            runner_commit="1" * 40,
            runner_tree_sha256=runner_tree,
            raw_checkpoint_sha256="2" * 64,
            first_conversion=first,
            second_conversion=second,
        )
