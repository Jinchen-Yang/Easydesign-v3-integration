"""开发期薄入口：一次命令运行 PSE Stage 01 和 Stage 02 对比。"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

import easydesign
from easydesign.backends.hotspot import ScanNetBackendConfig, ScanNetEpitopeAdapter
from easydesign.backends.target_sources import PyMOLPseAdapter
from easydesign.core import ConfigurationError
from easydesign.orchestration import (
    execute_pse_import,
    execute_stage02_comparison,
    initialize_pse_run,
)


def _required_path(environment_variable: str) -> Path:
    value = os.environ.get(environment_variable)
    if not value:
        raise ConfigurationError(f"必须显式设置 {environment_variable}")
    return Path(value)


def _code_commit(repository: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a single-target PSE through EasyDesign Stage 01 and Stage 02."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--execution-device",
        choices=("cpu", "gpu"),
        default="cpu",
        help="ScanNet execution device; CPU is the validated default.",
    )
    parser.add_argument("--gpu-device", type=int, default=0)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    pymol_adapter = PyMOLPseAdapter(
        python_executable=_required_path("EASYDESIGN_PYMOL_PYTHON")
    )
    scannet_adapter = ScanNetEpitopeAdapter(
        ScanNetBackendConfig(
            python_path=_required_path("EASYDESIGN_SCANNET_PYTHON"),
            repository_root=_required_path("EASYDESIGN_SCANNET_ROOT"),
            execution_device=args.execution_device,
            gpu_device=args.gpu_device,
        )
    )
    prepared = initialize_pse_run(
        config_path=args.config,
        runs_root=args.runs_root,
        request_writer=pymol_adapter,
        code_commit=_code_commit(repository),
        easydesign_version=easydesign.__version__,
        run_id=args.run_id,
    )
    completed_stage01 = execute_pse_import(
        prepared=prepared,
        adapter=pymol_adapter,
    )
    completed_stage02 = execute_stage02_comparison(
        run_root=completed_stage01.prepared.workspace.run_root,
        adapter=scannet_adapter,
    )
    print(completed_stage02.run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
