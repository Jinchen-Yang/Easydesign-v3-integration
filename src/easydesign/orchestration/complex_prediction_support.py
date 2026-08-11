"""Shared file-protocol helpers for Stage 05/07 complex prediction."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from easydesign.backends.structure_prediction import (
    BackendInvocation,
    StructurePredictionProduct,
)
from easydesign.core import ManifestStateError

AFO_RELEASE_IDENTITY_KEYS = (
    "release_id",
    "backend_id",
    "backend_version",
    "model_id",
    "adapter_contract_version",
    "release_manifest_sha256",
    "conversion_receipt_sha256",
    "raw_checkpoint_sha256",
    "converted_weight_sha256",
    "wheel_sha256",
    "environment_lock_sha256",
    "runner_commit",
    "runner_tree_sha256",
)


def prediction_release_identity(product: StructurePredictionProduct) -> dict[str, str]:
    """Extract the complete immutable AFO identity; Protenix returns an empty mapping."""

    values = {
        key: str(product.native_metrics[key])
        for key in AFO_RELEASE_IDENTITY_KEYS
        if isinstance(product.native_metrics.get(key), str)
    }
    if product.backend_name == "openfold3-af3-jax" and set(values) != set(
        AFO_RELEASE_IDENTITY_KEYS
    ):
        missing = sorted(set(AFO_RELEASE_IDENTITY_KEYS) - set(values))
        raise ManifestStateError(f"AFO prediction 缺少完整 release identity: {missing}")
    return values


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
