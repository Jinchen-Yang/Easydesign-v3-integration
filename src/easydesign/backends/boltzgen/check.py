"""BoltzGen 0.3.2 capability and design-specification validation adapter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from easydesign.core import BackendContractError, sha256_file
from easydesign.stages.s03_boltzgen_configuration import (
    BOLTZGEN_COMMIT,
    BOLTZGEN_VERSION,
    StrategyRecord,
    StrategyValidationItem,
    StrategyValidationReport,
)


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_MODEL_SNAPSHOT = "c1be29e1f82ffcc72264f64b993c43fb4e0d17f0"
_DATASET_SNAPSHOT = "c3d36fd276e9caf098c75d4113c6d5eb320b1a4c"
_ARTIFACT_IDENTITY: dict[str, tuple[str, int]] = {
    "boltzgen1_diverse.ckpt": (
        "360af8bd6e59527ff6ec25dd81253967f3bd3567d200053b10680634751f8e3c",
        1_930_847_192,
    ),
    "boltzgen1_adherence.ckpt": (
        "ac7078b3dc13064c68e0c3fd542e5bc538c33558bf6607f65e499eb336ca5e5d",
        1_930_858_014,
    ),
    "boltzgen1_ifold.ckpt": (
        "dd4cf108c94471bdc3a326b7b180fa3854dc019110fae780208c30b50bd56578",
        12_582_656,
    ),
    "boltz2_conf_final.ckpt": (
        "525a51ef306da7282a54d23a4a5b91212fc60d0ff6b23b56dd6351de3b387530",
        2_087_255_089,
    ),
    "boltz2_aff.ckpt": (
        "6dc13d488015666d3c3fdffd29fab54d72e4f2597b654f996cdcf5937feab090",
        2_061_914_091,
    ),
    "mols.zip": (
        "3d4f56ac4262e745bb3d09cfaa19099b1d01be208122d501667b952e45521e53",
        391_401_102,
    ),
}


@dataclass(frozen=True, slots=True)
class BoltzGenArtifacts:
    design_diverse: Path
    design_adherence: Path
    inverse_fold: Path
    folding: Path
    affinity: Path
    molecule_dataset: Path


@lru_cache(maxsize=64)
def _sha256_for_unchanged_file(
    path: Path,
    *,
    size: int,
    modified_ns: int,
) -> str:
    del size, modified_ns
    return sha256_file(path)


def _verify_artifact(path: Path) -> str:
    expected_sha256, expected_size = _ARTIFACT_IDENTITY[path.name]
    if not path.is_file():
        raise BackendContractError(f"BoltzGen 固定资产不存在: {path}")
    stat = path.stat()
    if stat.st_size != expected_size:
        raise BackendContractError(
            "BoltzGen 固定资产大小不匹配: "
            f"path={path}, expected={expected_size}, actual={stat.st_size}"
        )
    actual_sha256 = _sha256_for_unchanged_file(
        path,
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )
    if actual_sha256 != expected_sha256:
        raise BackendContractError(
            "BoltzGen 固定资产 SHA-256 不匹配: "
            f"path={path}, expected={expected_sha256}, actual={actual_sha256}"
        )
    return actual_sha256


def _verified_source_snapshot(repository_root: Path) -> str | None:
    """Verify an immutable exported tree when no Git metadata was deployed."""

    marker = repository_root / ".easydesign-source.json"
    if not marker.is_file():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackendContractError("BoltzGen source snapshot marker 无法读取") from error
    tree = payload.get("tree")
    if (
        payload.get("schema_version") != "0.1"
        or payload.get("backend_id") != "boltzgen"
        or payload.get("commit") != BOLTZGEN_COMMIT
        or not isinstance(tree, dict)
        or not tree
    ):
        raise BackendContractError("BoltzGen source snapshot identity 不匹配")
    root = repository_root.resolve()
    for raw_relative, raw_identity in tree.items():
        if not isinstance(raw_relative, str) or not isinstance(raw_identity, dict):
            raise BackendContractError("BoltzGen source snapshot tree 无效")
        relative = Path(raw_relative)
        path = (root / relative).resolve()
        expected_sha256 = raw_identity.get("sha256")
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not path.is_relative_to(root)
            or not path.is_file()
            or not isinstance(expected_sha256, str)
            or sha256_file(path) != expected_sha256
        ):
            raise BackendContractError(
                f"BoltzGen source snapshot 文件漂移: {raw_relative}"
            )
    return BOLTZGEN_COMMIT


@dataclass(frozen=True, slots=True)
class BoltzGenCheckAdapter:
    executable: Path
    repository_root: Path
    cache_root: Path
    timeout_seconds: float = 300.0
    validation_workers: int = 4
    offline_mode: bool = True
    require_generation_assets: bool = True

    def artifact_paths(self) -> BoltzGenArtifacts:
        model_root = (
            self.cache_root
            / "models--boltzgen--boltzgen-1"
            / "snapshots"
            / _MODEL_SNAPSHOT
        )
        dataset_root = (
            self.cache_root
            / "datasets--boltzgen--inference-data"
            / "snapshots"
            / _DATASET_SNAPSHOT
        )
        return BoltzGenArtifacts(
            design_diverse=model_root / "boltzgen1_diverse.ckpt",
            design_adherence=model_root / "boltzgen1_adherence.ckpt",
            inverse_fold=model_root / "boltzgen1_ifold.ckpt",
            folding=model_root / "boltz2_conf_final.ckpt",
            affinity=model_root / "boltz2_aff.ckpt",
            molecule_dataset=dataset_root / "mols.zip",
        )

    def _run(
        self,
        argv: list[str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if self.offline_mode:
            environment["HF_HUB_OFFLINE"] = "1"
        completed = subprocess.run(
            argv,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            env=environment,
        )
        return completed

    def probe(self) -> dict[str, str]:
        if not self.executable.is_file():
            raise BackendContractError(
                f"BoltzGen executable 不存在: {self.executable}"
            )
        if not self.repository_root.is_dir():
            raise BackendContractError(
                f"BoltzGen repository_root 不存在: {self.repository_root}"
            )
        if not self.cache_root.is_dir():
            raise BackendContractError(
                f"BoltzGen cache_root 不存在: {self.cache_root}"
            )
        artifacts = self.artifact_paths()
        required_artifacts = (
            (
                artifacts.design_diverse,
                artifacts.design_adherence,
                artifacts.inverse_fold,
                artifacts.folding,
                artifacts.affinity,
                artifacts.molecule_dataset,
            )
            if self.require_generation_assets
            else (artifacts.molecule_dataset,)
        )
        artifact_hashes = {
            path.name: _verify_artifact(path) for path in required_artifacts
        }
        version = self._run([str(self.executable), "--version"])
        version_text = (version.stdout + "\n" + version.stderr).strip()
        if version.returncode != 0 or BOLTZGEN_VERSION not in version_text:
            raise BackendContractError(
                "BoltzGen 版本探针失败或版本不匹配: "
                f"expected={BOLTZGEN_VERSION}, output={version_text[:1024]}"
            )
        actual_commit = _verified_source_snapshot(self.repository_root)
        if actual_commit is None:
            commit = self._run(
                ["git", "-C", str(self.repository_root), "rev-parse", "HEAD"]
            )
            actual_commit = commit.stdout.strip()
            if commit.returncode != 0 or actual_commit != BOLTZGEN_COMMIT:
                raise BackendContractError(
                    "BoltzGen commit 不匹配: "
                    f"expected={BOLTZGEN_COMMIT}, "
                    f"actual={actual_commit or commit.stderr.strip()}"
                )
            dirty = self._run(
                [
                    "git",
                    "-C",
                    str(self.repository_root),
                    "status",
                    "--porcelain",
                    "--untracked-files=no",
                ]
            )
            if dirty.returncode != 0 or dirty.stdout.strip():
                raise BackendContractError(
                    "BoltzGen repository 必须是固定 commit 的干净 tracked tree"
                )
        result = {
            "backend": "boltzgen",
            "version": BOLTZGEN_VERSION,
            "commit": BOLTZGEN_COMMIT,
            "molecule_dataset_sha256": artifact_hashes["mols.zip"],
            "offline_mode": str(self.offline_mode).lower(),
            "random_seed_status": "unsupported-by-boltzgen-0.3.2",
            "capability": (
                "generation" if self.require_generation_assets else "yaml-validation"
            ),
        }
        if self.require_generation_assets:
            result.update(
                {
                    "design_diverse_sha256": artifact_hashes[
                        "boltzgen1_diverse.ckpt"
                    ],
                    "design_adherence_sha256": artifact_hashes[
                        "boltzgen1_adherence.ckpt"
                    ],
                    "inverse_fold_sha256": artifact_hashes[
                        "boltzgen1_ifold.ckpt"
                    ],
                    "folding_sha256": artifact_hashes["boltz2_conf_final.ckpt"],
                    "affinity_sha256": artifact_hashes["boltz2_aff.ckpt"],
                }
            )
        return result

    def validate(
        self,
        *,
        artifacts_root: Path,
        strategies: tuple[StrategyRecord, ...],
        logs_root: Path | None = None,
        checked_at: datetime | None = None,
    ) -> StrategyValidationReport:
        self.probe()
        items: list[StrategyValidationItem] = []
        if logs_root is not None:
            logs_root.mkdir(parents=True, exist_ok=False)

        def check_one(
            strategy: StrategyRecord,
        ) -> subprocess.CompletedProcess[str]:
            specification = artifacts_root / strategy.design_specification_path
            argv = [str(self.executable), "check", specification.name]
            argv.extend(
                ["--moldir", str(self.artifact_paths().molecule_dataset)]
            )
            argv.extend(["--cache", str(self.cache_root)])
            return self._run(argv, cwd=specification.parent)

        worker_count = min(max(self.validation_workers, 1), len(strategies))
        if worker_count == 1:
            completed_checks = tuple(check_one(strategy) for strategy in strategies)
        else:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="boltzgen-check",
            ) as executor:
                completed_checks = tuple(executor.map(check_one, strategies))
        for strategy, completed in zip(
            strategies,
            completed_checks,
            strict=True,
        ):
            stdout = completed.stdout
            stderr = completed.stderr
            passed = completed.returncode == 0
            stdout_path: str | None = None
            stderr_path: str | None = None
            if logs_root is not None:
                stdout_file = logs_root / f"{strategy.strategy_id}.stdout.log"
                stderr_file = logs_root / f"{strategy.strategy_id}.stderr.log"
                stdout_file.write_text(stdout, encoding="utf-8")
                stderr_file.write_text(stderr, encoding="utf-8")
                stdout_path = stdout_file.name
                stderr_path = stderr_file.name
            items.append(
                StrategyValidationItem(
                    strategy_id=strategy.strategy_id,
                    status="passed" if passed else "failed",
                    return_code=completed.returncode,
                    stdout_sha256=_text_sha256(stdout),
                    stderr_sha256=_text_sha256(stderr),
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    message=(
                        "BoltzGen check passed."
                        if passed
                        else (stderr.strip() or stdout.strip() or "BoltzGen check failed.")[
                            :4096
                        ]
                    ),
                )
            )
        report = StrategyValidationReport(
            checked_at=datetime.now(UTC) if checked_at is None else checked_at,
            status=(
                "passed"
                if all(item.status == "passed" for item in items)
                else "failed"
            ),
            items=tuple(items),
        )
        return report
