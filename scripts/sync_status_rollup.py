"""从七个 Stage STATUS 生成顶层实时摘要，并在 CI 中检查是否同步。"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "01-target-preparation",
    "02-hotspot-discovery",
    "03-boltzgen-configuration",
    "04-pilot-generation",
    "05-pilot-filtering",
    "06-scale-generation-and-refolding",
    "07-final-filtering-and-selection",
)
STATUS_VALUES = {
    "planned",
    "implemented",
    "smoke-validated",
    "scientifically-validated",
    "production-ready",
}
START_MARKER = "<!-- BEGIN AUTO-GENERATED STAGE ROLLUP -->"
END_MARKER = "<!-- END AUTO-GENERATED STAGE ROLLUP -->"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class StageRollup:
    stage: str
    overall_status: str
    summary: str
    focus: str
    blocker: str
    updated: str


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _read_rollup(stage: str) -> StageRollup:
    path = ROOT / "workflow" / stage / "STATUS.md"
    text = path.read_text(encoding="utf-8")
    heading = "## 顶层摘要"
    if heading not in text:
        raise ValueError(f"{path.relative_to(ROOT)} 缺少 {heading}")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [
        _table_cells(line)
        for line in section.splitlines()
        if line.startswith("|") and "---" not in line
    ]
    if len(rows) != 2 or len(rows[1]) != 5:
        raise ValueError(
            f"{path.relative_to(ROOT)} 顶层摘要必须是一行五列数据"
        )
    overall_status, summary, focus, blocker, updated = rows[1]
    if overall_status.strip("`") not in STATUS_VALUES:
        raise ValueError(
            f"{path.relative_to(ROOT)} 顶层状态非法: {overall_status}"
        )
    if not all((summary, focus, blocker)):
        raise ValueError(f"{path.relative_to(ROOT)} 顶层摘要存在空字段")
    if DATE_PATTERN.fullmatch(updated) is None:
        raise ValueError(
            f"{path.relative_to(ROOT)} 更新时间必须是 YYYY-MM-DD: {updated}"
        )
    return StageRollup(
        stage=stage,
        overall_status=overall_status,
        summary=summary,
        focus=focus,
        blocker=blocker,
        updated=updated,
    )


def _render(rows: list[StageRollup]) -> str:
    lines = [
        START_MARKER,
        "| Stage | 总体状态 | 一句话进展 | 当前重心 | 主要阻塞 | 更新 | 详情 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        label = f"Stage {row.stage[:2]}"
        link = f"workflow/{row.stage}/STATUS.md"
        lines.append(
            f"| {label} | {row.overall_status} | {row.summary} | {row.focus} | "
            f"{row.blocker} | {row.updated} | [STATUS]({link}) |"
        )
    lines.append(END_MARKER)
    return "\n".join(lines)


def _replace_generated_block(text: str, generated: str, path: Path) -> str:
    if text.count(START_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise ValueError(
            f"{path.relative_to(ROOT)} 必须且只能包含一对 Stage rollup 标记"
        )
    start = text.index(START_MARKER)
    end = text.index(END_MARKER, start) + len(END_MARKER)
    return text[:start] + generated + text[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查顶层摘要是否与 Stage STATUS 一致，不写文件。",
    )
    args = parser.parse_args()
    try:
        rows = [_read_rollup(stage) for stage in STAGES]
        generated = _render(rows)
        stale: list[Path] = []
        updates: list[tuple[Path, str]] = []
        for filename in ("TODO.md", "TODO_NOW.md"):
            path = ROOT / filename
            current = path.read_text(encoding="utf-8")
            expected = _replace_generated_block(current, generated, path)
            if current != expected:
                stale.append(path)
                updates.append((path, expected))
        if args.check:
            if stale:
                names = ", ".join(path.name for path in stale)
                print(
                    "ERROR: 顶层 Stage 摘要过期；运行 "
                    f"`python scripts/sync_status_rollup.py`: {names}",
                    file=sys.stderr,
                )
                return 1
            print("顶层 Stage 摘要与七个 STATUS 一致。")
            return 0
        for path, expected in updates:
            path.write_text(expected, encoding="utf-8")
        print(f"已同步 {len(updates)} 个顶层状态文档。")
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
