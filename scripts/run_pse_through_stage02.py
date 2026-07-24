"""兼容薄入口：委托统一 orchestration API 运行 PSE Stage 01/02。"""

from __future__ import annotations

import argparse
from pathlib import Path

from easydesign.orchestration import execute_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a single-target PSE through EasyDesign Stage 01 and Stage 02."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()

    completed = execute_pipeline(
        args.config,
        profile_path=args.profile,
        runs_root=args.runs_root,
        run_id=args.run_id,
    )
    print(completed.run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
