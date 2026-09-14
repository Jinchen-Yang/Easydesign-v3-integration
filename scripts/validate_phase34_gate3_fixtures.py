#!/usr/bin/env python3
"""Verify Phase 3/4 upstream fixtures without mutating their source worktree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from easydesign.agent.phase34_fixtures import verify_accepted_gate3_fixtures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance-index", type=Path, required=True)
    parser.add_argument("--source-repository", type=Path)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/agent/phase34_gate3_fixtures.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_accepted_gate3_fixtures(
        fixture_path=args.fixtures,
        acceptance_index_path=args.acceptance_index,
        source_repository=args.source_repository,
    )
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
