"""Publish a staged Workbench build without deleting prior bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "easydesign" / "ui" / "static"
STAGING_ROOT = ROOT / "runtime" / "tmp"
QUARANTINE_ROOT = ROOT / "runtime" / "quarantine"


def _tree_identity(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("staging", type=Path)
    arguments = parser.parse_args()
    staging = arguments.staging.resolve()
    if not staging.is_dir() or not staging.is_relative_to(STAGING_ROOT.resolve()):
        raise SystemExit("UI staging 必须是 runtime/tmp 下的新目录")
    if not (staging / "index.html").is_file():
        raise SystemExit("UI staging 缺少 index.html")

    if TARGET.exists() and _tree_identity(TARGET) == _tree_identity(staging):
        print(f"UI 构建与已发布字节一致；staging 保留在 {staging.relative_to(ROOT)}")
        return 0

    if TARGET.exists():
        operation_id = (
            datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
            + "-ui-build-"
            + uuid4().hex[:10]
        )
        quarantine = QUARANTINE_ROOT / operation_id
        quarantine.mkdir(parents=True, exist_ok=False)
        previous = quarantine / "previous-static"
        os.rename(TARGET, previous)
        (quarantine / "quarantine.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "operation_id": operation_id,
                    "reason": "Workbench build replaced by a newly staged revision",
                    "source_path": str(TARGET.relative_to(ROOT)),
                    "quarantined_at": datetime.now(tz=UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging, TARGET)
    print(f"UI 构建已从 staging 发布到 {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
