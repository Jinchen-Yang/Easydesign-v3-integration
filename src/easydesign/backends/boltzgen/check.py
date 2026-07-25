"""BoltzGen 0.3.2 capability and design-specification validation adapter."""

from __future__ import annotations

import hashlib
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
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


@dataclass(frozen=True, slots=True)
class BoltzGenCheckAdapter:
    executable: Path
    repository_root: Path
    cache_root: Path
    timeout_seconds: float = 300.0
    validation_workers: int = 4
    offline_mode: bool = True

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
        molecule_archives = tuple(
            self.cache_root.glob(
                "datasets--boltzgen--inference-data/snapshots/*/mols.zip"
            )
        )
        if len(molecule_archives) != 1 or not molecule_archives[0].is_file():
            raise BackendContractError(
                "BoltzGen cache 必须包含唯一固定 inference-data mols.zip snapshot"
            )
        version = self._run([str(self.executable), "--version"])
        version_text = (version.stdout + "\n" + version.stderr).strip()
        if version.returncode != 0 or BOLTZGEN_VERSION not in version_text:
            raise BackendContractError(
                "BoltzGen 版本探针失败或版本不匹配: "
                f"expected={BOLTZGEN_VERSION}, output={version_text[:1024]}"
            )
        commit = self._run(
            ["git", "-C", str(self.repository_root), "rev-parse", "HEAD"]
        )
        actual_commit = commit.stdout.strip()
        if commit.returncode != 0 or actual_commit != BOLTZGEN_COMMIT:
            raise BackendContractError(
                "BoltzGen commit 不匹配: "
                f"expected={BOLTZGEN_COMMIT}, actual={actual_commit or commit.stderr.strip()}"
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
        return {
            "backend": "boltzgen",
            "version": BOLTZGEN_VERSION,
            "commit": BOLTZGEN_COMMIT,
            "molecule_dataset_sha256": sha256_file(molecule_archives[0]),
            "offline_mode": str(self.offline_mode).lower(),
            "random_seed_status": "unsupported-by-boltzgen-0.3.2",
        }

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
