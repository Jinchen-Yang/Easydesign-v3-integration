"""原子进度快照与 append-only task event journal。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from easydesign.core import ManifestStateError, TaskEvent, load_model


def atomic_dump_runtime_model(model: BaseModel, path: Path) -> Path:
    """运行期可替换快照；终态 artifact 仍由不可覆盖发布负责。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        model.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


class TaskEventJournal:
    """严格连续、每行一个 JSON object 的 append-only journal。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_sequence = 0
        if self.path.is_file():
            self._last_sequence = self._validate_existing()

    @property
    def next_sequence(self) -> int:
        return self._last_sequence + 1

    def _validate_existing(self) -> int:
        last = 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise ManifestStateError(f"无法读取 task event journal: {self.path}") from error
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                raise ManifestStateError(f"task event journal 含空行: line={line_number}")
            try:
                event = TaskEvent.model_validate_json(line)
            except ValueError as error:
                raise ManifestStateError(f"task event journal 损坏: line={line_number}") from error
            if event.sequence != last + 1:
                raise ManifestStateError("task event sequence 必须连续")
            last = event.sequence
        return last

    def append(self, event: TaskEvent) -> None:
        if event.sequence != self.next_sequence:
            raise ManifestStateError(f"task event sequence 应为 {self.next_sequence}")
        line = json.dumps(
            event.model_dump(mode="json", exclude_none=False),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._last_sequence = event.sequence


def load_runtime_model(path: Path, model_type: type[BaseModel]) -> BaseModel:
    """对外保持与 core load_model 相同错误语义。"""

    return load_model(path, model_type)
