"""从七个 Stage status 生成统一路线图摘要，并在 CI 中检查是否同步。"""

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
WORKSTREAM_PREFIXES = {
    "ENG",
    "UX",
    "REP",
    "UI",
    "VAL",
    "DATA",
    "REL",
    "PAPER",
    "BIZ",
}
ACTIVE_ID_PATTERN = re.compile(r"\[([A-Z]+-\d{3}|S0[1-7])\]")


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
    path = ROOT / "docs" / "workflow" / f"{stage}-status.md"
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
        link = f"workflow/{row.stage}-status.md"
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


def _validate_workstream_index(roadmap: str) -> None:
    for prefix in sorted(WORKSTREAM_PREFIXES):
        if f"| `{prefix}` |" not in roadmap:
            raise ValueError(f"docs/ROADMAP.md 缺少工作板块索引: {prefix}")
    for task_id in ACTIVE_ID_PATTERN.findall(roadmap):
        if task_id.startswith("S0"):
            continue
        prefix = task_id.split("-", maxsplit=1)[0]
        if prefix not in WORKSTREAM_PREFIXES:
            raise ValueError(f"ROADMAP 使用未登记的板块前缀: {task_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查 ROADMAP 摘要是否与 Stage status 一致，不写文件。",
    )
    args = parser.parse_args()
    try:
        rows = [_read_rollup(stage) for stage in STAGES]
        generated = _render(rows)
        path = ROOT / "docs" / "ROADMAP.md"
        current = path.read_text(encoding="utf-8")
        expected = _replace_generated_block(current, generated, path)
        stale = current != expected
        _validate_workstream_index(expected)
        if args.check:
            if stale:
                print(
                    "ERROR: ROADMAP Stage 摘要过期；运行 "
                    "`python scripts/sync_status_rollup.py`",
                    file=sys.stderr,
                )
                return 1
            print("ROADMAP 摘要与七个 Stage status 一致。")
            return 0
        if stale:
            path.write_text(expected, encoding="utf-8")
        print(f"已同步 {1 if stale else 0} 个路线图状态文档。")
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
