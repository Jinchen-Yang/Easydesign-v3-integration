"""隔离 ScanNet epitope no-MSA GPU 后端的无 shell adapter。"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from easydesign.core import ManifestStateError
from easydesign.stages.s02_hotspot_discovery.geometry import StructureContext

SCANNET_COMMIT = "a61623cd98d243c2ff4cd03fc3619d2d22ec50e7"
SCANNET_MODEL = "ScanNet_epitope_noMSA"


class ScanNetBackendError(ManifestStateError):
    """ScanNet 环境、GPU、执行或输出不满足显式契约。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.stdout = stdout
        self.stderr = stderr


class ScanNetBackendConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backend_name: str = Field(default="scannet-epitope-no-msa", frozen=True)
    python_path: Path
    repository_root: Path
    expected_commit: str = Field(default=SCANNET_COMMIT, pattern=r"^[0-9a-f]{40}$")
    gpu_device: int = Field(default=0, ge=0)
    timeout_seconds: float = Field(default=1800, gt=0)

    @model_validator(mode="after")
    def validate_paths(self) -> "ScanNetBackendConfig":
        if not self.python_path.is_absolute() or not self.repository_root.is_absolute():
            raise ValueError("ScanNet Python 和 repository_root 必须是绝对路径")
        return self


class ScanNetGpuProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tensorflow_version: str
    keras_version: str
    gpu_available: bool
    gpu_device_name: str
    test_operation_device: str

    @model_validator(mode="after")
    def require_gpu(self) -> "ScanNetGpuProbe":
        if not self.gpu_available:
            raise ValueError("TensorFlow 未识别 GPU")
        if "GPU" not in self.gpu_device_name.upper():
            raise ValueError("TensorFlow gpu_device_name 没有 GPU 设备")
        if "GPU" not in self.test_operation_device.upper():
            raise ValueError("TensorFlow 测试计算没有放置到 GPU")
        return self


class ScanNetRawPrediction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tool_residue_index: int = Field(ge=1)
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    probability: float = Field(ge=0, le=1)


@dataclass(frozen=True, slots=True)
class PreparedScanNetInput:
    pdb_path: Path
    mapping_path: Path


@dataclass(frozen=True, slots=True)
class ScanNetPredictionProduct:
    probabilities: dict[int, float]
    raw_predictions: tuple[ScanNetRawPrediction, ...]
    raw_csv: Path
    stdout: str
    stderr: str
    runtime_seconds: float
    probe: ScanNetGpuProbe
    commit: str


GPU_PROBE = r"""
import json
import keras
import tensorflow as tf
graph = tf.Graph()
with graph.as_default():
    with tf.device('/gpu:0'):
        left = tf.constant([[1.0, 2.0]])
        right = tf.constant([[3.0], [4.0]])
        product = tf.matmul(left, right)
    config = tf.ConfigProto(log_device_placement=True)
    config.gpu_options.allow_growth = True
    with tf.Session(graph=graph, config=config) as session:
        session.run(product)
        device = product.device
payload = {
    'tensorflow_version': tf.__version__,
    'keras_version': keras.__version__,
    'gpu_available': bool(tf.test.is_gpu_available(cuda_only=True)),
    'gpu_device_name': tf.test.gpu_device_name(),
    'test_operation_device': device,
}
print('EASYDESIGN_GPU_PROBE=' + json.dumps(payload, sort_keys=True))
"""


def _write_scan_input(context: StructureContext, output_dir: Path) -> PreparedScanNetInput:
    output_dir.mkdir(parents=True, exist_ok=True)
    pdb_path = output_dir / "target.pdb"
    mapping_path = output_dir / "scannet-input-mapping.json"
    if pdb_path.exists() or mapping_path.exists():
        raise ManifestStateError("ScanNet input 不可覆盖已有文件")
    lines: list[str] = []
    mapping: list[dict[str, object]] = []
    serial = 1
    for tool_index, label in enumerate(sorted(context.residues), start=1):
        geometry = context.residues[label]
        mapping.append(
            {
                "tool_residue_index": tool_index,
                "residue": geometry.identity.model_dump(mode="json"),
            }
        )
        for atom in geometry.atoms:
            atom_name = atom.name if len(atom.name) == 4 else f" {atom.name:<3}"
            lines.append(
                f"ATOM  {serial:5d} {atom_name:4s} {geometry.residue_name:>3s} "
                f"A{tool_index:4d}    "
                f"{atom.xyz[0]:8.3f}{atom.xyz[1]:8.3f}{atom.xyz[2]:8.3f}"
                f"{atom.occupancy:6.2f}{0.0:6.2f}          {atom.element:>2s}"
            )
            serial += 1
    lines.extend(["TER", "END"])
    pdb_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    mapping_path.write_text(
        json.dumps(
            {"schema_version": "0.1", "entries": mapping},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return PreparedScanNetInput(pdb_path=pdb_path, mapping_path=mapping_path)


class ScanNetEpitopeAdapter:
    backend_name = "scannet-epitope-no-msa"
    model_name = SCANNET_MODEL

    def __init__(self, config: ScanNetBackendConfig) -> None:
        self.config = config

    def _environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = str(self.config.gpu_device)
        environment["TF_FORCE_GPU_ALLOW_GROWTH"] = "true"
        environment["TF_CPP_MIN_LOG_LEVEL"] = "0"
        return environment

    def _validate_installation(self) -> str:
        if not self.config.python_path.is_file():
            raise ScanNetBackendError(
                f"ScanNet Python 不存在: {self.config.python_path}",
                error_code="scannet-python-missing",
            )
        script = self.config.repository_root / "predict_bindingsites.py"
        if not script.is_file():
            raise ScanNetBackendError(
                f"ScanNet predict_bindingsites.py 不存在: {script}",
                error_code="scannet-repository-missing",
            )
        completed = subprocess.run(
            ["git", "-C", str(self.config.repository_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        commit = completed.stdout.strip()
        if completed.returncode != 0 or commit != self.config.expected_commit:
            raise ScanNetBackendError(
                "ScanNet commit 不匹配: "
                f"expected={self.config.expected_commit}, actual={commit or 'unknown'}",
                error_code="scannet-commit-mismatch",
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        return commit

    def probe_gpu(self) -> ScanNetGpuProbe:
        self._validate_installation()
        try:
            completed = subprocess.run(
                [str(self.config.python_path), "-c", GPU_PROBE],
                cwd=self.config.repository_root,
                env=self._environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=min(180.0, self.config.timeout_seconds),
            )
        except subprocess.TimeoutExpired as error:
            raise ScanNetBackendError(
                "ScanNet GPU probe 超时",
                error_code="scannet-gpu-probe-timeout",
                stdout=error.stdout or "",
                stderr=error.stderr or "",
            ) from error
        marker = "EASYDESIGN_GPU_PROBE="
        payload_line = next(
            (line for line in completed.stdout.splitlines() if line.startswith(marker)),
            None,
        )
        if completed.returncode != 0 or payload_line is None:
            raise ScanNetBackendError(
                "ScanNet GPU probe 失败或缺少结构化输出",
                error_code="scannet-gpu-probe-failed",
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        try:
            return ScanNetGpuProbe.model_validate_json(payload_line[len(marker) :])
        except Exception as error:
            raise ScanNetBackendError(
                f"ScanNet GPU probe 未满足 GPU 契约: {error}",
                error_code="scannet-gpu-unavailable",
                stdout=completed.stdout,
                stderr=completed.stderr,
            ) from error

    def predict(
        self,
        *,
        context: StructureContext,
        work_dir: Path,
    ) -> ScanNetPredictionProduct:
        commit = self._validate_installation()
        probe = self.probe_gpu()
        prepared = _write_scan_input(context, work_dir / "input")
        predictions_root = work_dir / "predictions"
        predictions_root.mkdir(parents=True, exist_ok=False)
        script = self.config.repository_root / "predict_bindingsites.py"
        command = [
            str(self.config.python_path),
            str(script),
            f"{prepared.pdb_path}_A",
            "--name",
            "easydesign-target",
            "--predictions_folder",
            str(predictions_root),
            "--mode",
            "epitope",
            "--noMSA",
            "--pdb",
        ]
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=self.config.repository_root,
                env=self._environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise ScanNetBackendError(
                "ScanNet epitope no-MSA 执行超时",
                error_code="scannet-timeout",
                stdout=error.stdout or "",
                stderr=error.stderr or "",
            ) from error
        runtime = time.monotonic() - started
        expected_csv = (
            predictions_root
            / "easydesign-target_(0-A)_single_ScanNet_epitope_noMSA"
            / "predictions_easydesign-target.csv"
        )
        if completed.returncode != 0:
            raise ScanNetBackendError(
                f"ScanNet 执行失败，退出码 {completed.returncode}",
                error_code="scannet-nonzero-exit",
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        if not expected_csv.is_file():
            raise ScanNetBackendError(
                f"ScanNet 缺少约定输出: {expected_csv}",
                error_code="scannet-output-missing",
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        raw, probabilities = self._parse_predictions(expected_csv, context)
        return ScanNetPredictionProduct(
            probabilities=probabilities,
            raw_predictions=raw,
            raw_csv=expected_csv,
            stdout=completed.stdout,
            stderr=completed.stderr,
            runtime_seconds=runtime,
            probe=probe,
            commit=commit,
        )

    def _parse_predictions(
        self,
        path: Path,
        context: StructureContext,
    ) -> tuple[tuple[ScanNetRawPrediction, ...], dict[int, float]]:
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error) as error:
            raise ScanNetBackendError(
                f"ScanNet CSV 无法读取: {path}",
                error_code="scannet-output-invalid",
            ) from error
        required = {
            "Model",
            "Chain",
            "Residue Index",
            "Sequence",
            "Binding site probability",
        }
        if not rows or not required <= set(rows[0]):
            raise ScanNetBackendError(
                "ScanNet CSV 缺少必需列或没有数据",
                error_code="scannet-output-invalid",
            )
        ordered_labels = sorted(context.residues)
        raw_predictions: list[ScanNetRawPrediction] = []
        probabilities: dict[int, float] = {}
        for expected_index, row in enumerate(rows, start=1):
            try:
                tool_index = int(row["Residue Index"])
                amino_acid = row["Sequence"].strip().upper()
                probability = float(row["Binding site probability"])
            except (TypeError, ValueError, KeyError) as error:
                raise ScanNetBackendError(
                    f"ScanNet CSV 行无法解析: row={expected_index}",
                    error_code="scannet-output-invalid",
                ) from error
            if tool_index != expected_index or row["Chain"].strip() != "A":
                raise ScanNetBackendError(
                    "ScanNet CSV residue index/chain 与 adapter 输入不一致",
                    error_code="scannet-numbering-mismatch",
                )
            if expected_index > len(ordered_labels):
                raise ScanNetBackendError(
                    "ScanNet CSV 比 target residue mapping 更长",
                    error_code="scannet-numbering-mismatch",
                )
            label = ordered_labels[expected_index - 1]
            expected_aa = context.residues[label].identity.amino_acid
            if amino_acid != expected_aa:
                raise ScanNetBackendError(
                    f"ScanNet sequence 不一致: tool={tool_index}, "
                    f"expected={expected_aa}, actual={amino_acid}",
                    error_code="scannet-numbering-mismatch",
                )
            prediction = ScanNetRawPrediction(
                tool_residue_index=tool_index,
                amino_acid=amino_acid,
                probability=probability,
            )
            raw_predictions.append(prediction)
            probabilities[label] = probability
        if len(raw_predictions) != len(ordered_labels):
            raise ScanNetBackendError(
                "ScanNet CSV residue 数量与 target mapping 不一致",
                error_code="scannet-numbering-mismatch",
            )
        return tuple(raw_predictions), probabilities
