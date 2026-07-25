"""Shared file-protocol helpers for Stage 05/07 complex prediction."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from easydesign.backends.structure_prediction import BackendInvocation
from easydesign.core import ManifestStateError


def read_fasta_sequence(path: Path) -> str:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(">")
    ]
    sequence = "".join(lines).upper()
    if not sequence:
        raise ManifestStateError("target sequence artifact 为空")
    return sequence


def prepare_query_only_a3m(sequence: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    expected = f">query\n{sequence}\n"
    if path.exists():
        if path.read_text(encoding="ascii") != expected:
            raise ManifestStateError(f"query-only MSA 已存在但 sequence 不一致: {path}")
    else:
        path.write_text(expected, encoding="ascii")
    return path.resolve()


def run_checked_backend_invocation(
    invocation: BackendInvocation,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(dict(invocation.environment))
    try:
        completed = subprocess.run(
            list(invocation.argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=invocation.timeout_seconds,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise ManifestStateError(
            f"backend invocation timeout: {invocation.backend_name}"
        ) from error
    if completed.returncode != 0:
        raise ManifestStateError(
            f"backend invocation failed: {invocation.backend_name}, "
            f"returncode={completed.returncode}, stderr={completed.stderr[-2048:]}"
        )
    return completed
