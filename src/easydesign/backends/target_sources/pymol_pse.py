"""PyMOL PSE 独立环境 adapter 与文件协议。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easydesign.core import (
    BackendContractError,
    ManifestStateError,
    TargetInputError,
    dump_model,
    sha256_file,
)
from easydesign.core.artifacts import ID_PATTERN, SHA256_PATTERN

PYMOL_PYTHON_ENV = "EASYDESIGN_PYMOL_PYTHON"
PINNED_PYMOL_VERSION = "3.1.0"
WORKER_PATH = Path(__file__).with_name("pymol_pse_worker.py")


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


class PseExtractionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    target_id: str = Field(pattern=ID_PATTERN)
    source_relative_path: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)


class PseInventoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    state_count: int = Field(ge=0)
    atom_count: int = Field(ge=0)
    protein_atom_count: int = Field(ge=0)
    ignored: bool


class PseResidueAnnotation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_index: int = Field(ge=1)
    residue_name: str = Field(pattern=r"^[A-Z0-9]{3}$")
    amino_acid: str = Field(pattern=r"^[ACDEFGHIKLMNPQRSTVWY]$")
    author_chain_id: str = Field(min_length=1, max_length=16)
    author_residue_id: str = Field(min_length=1, max_length=32)
    insertion_code: str | None = Field(default=None, max_length=8)
    ca_color_index: int = Field(ge=0)
    ca_color_rgb: tuple[float, float, float]
    ca_color_hex: str = Field(pattern=r"^#[0-9A-F]{6}$")


class PseWorkerResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.1"
    status: str = Field(pattern=r"^succeeded$")
    pymol_version: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    inventory: tuple[PseInventoryEntry, ...]
    selected_object: str = Field(min_length=1)
    chain_id: str = Field(min_length=1, max_length=16)
    state: int = Field(ge=1)
    water_residue_count: int = Field(ge=0)
    ligand_heavy_atom_count: int = Field(ge=0)
    residues: tuple[PseResidueAnnotation, ...]
    raw_pdb_sha256: str = Field(pattern=SHA256_PATTERN)
    worker_runtime_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if self.pymol_version != PINNED_PYMOL_VERSION:
            raise ValueError(
                f"PyMOL 版本不匹配: expected={PINNED_PYMOL_VERSION}, "
                f"actual={self.pymol_version}"
            )
        indices = [residue.sequence_index for residue in self.residues]
        if indices != list(range(1, len(self.residues) + 1)):
            raise ValueError("PSE residue sequence_index 必须从 1 连续递增")
        if len(self.residues) < 20:
            raise ValueError("PSE worker 输出少于 20 个标准残基")
        if self.state != 1:
            raise ValueError("当前 PSE 契约只接受 state=1")
        if self.ligand_heavy_atom_count != 0:
            raise ValueError("当前 PSE 契约不接受配体或非溶剂重原子")
        if {residue.author_chain_id for residue in self.residues} != {self.chain_id}:
            raise ValueError("PSE residue annotation chain 与 session inventory 不一致")
        return self

    @property
    def sequence(self) -> str:
        return "".join(residue.amino_acid for residue in self.residues)


@dataclass(frozen=True, slots=True)
class PseWorkerInvocation:
    argv: tuple[str, ...]
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class PseExtractionProduct:
    response: PseWorkerResponse
    raw_pdb_path: Path
    response_path: Path
    stdout: str
    stderr: str
    adapter_runtime_seconds: float


class PseBackendExecutionError(BackendContractError):
    """保留失败 worker 的机器错误和日志，供 orchestration 发布失败 attempt。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        stdout: str = "",
        stderr: str = "",
        runtime_seconds: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.stdout = stdout
        self.stderr = stderr
        self.runtime_seconds = runtime_seconds


@dataclass(frozen=True, slots=True)
class PyMOLPseAdapter:
    """只通过显式 Python executable 调用固定版本 PyMOL worker。"""

    python_executable: Path
    timeout_seconds: float = 120.0
    expected_version: str = PINNED_PYMOL_VERSION
    worker_path: Path = WORKER_PATH

    backend_name = "pymol-pse"

    def __post_init__(self) -> None:
        if not self.python_executable.is_absolute():
            raise BackendContractError("PyMOL Python 必须是显式绝对路径")
        if self.timeout_seconds <= 0:
            raise BackendContractError("PyMOL worker timeout 必须大于 0")
        if self.expected_version != PINNED_PYMOL_VERSION:
            raise BackendContractError(
                f"当前 adapter 只允许固定 PyMOL {PINNED_PYMOL_VERSION}"
            )

    @classmethod
    def from_environment(cls, *, timeout_seconds: float = 120.0) -> Self:
        value = os.environ.get(PYMOL_PYTHON_ENV)
        if not value:
            raise BackendContractError(
                f"必须显式设置 {PYMOL_PYTHON_ENV}；禁止扫描 Conda 或系统 Python"
            )
        return cls(python_executable=Path(value), timeout_seconds=timeout_seconds)

    def version_probe_invocation(self) -> tuple[str, ...]:
        code = (
            "import sys, pymol; "
            "pymol.finish_launching(['pymol','-cq']); "
            "sys.stdout.write(pymol.cmd.get_version()[0]+'\\n'); "
            "sys.stdout.flush(); "
            "pymol.cmd.quit()"
        )
        return (str(self.python_executable), "-c", code)

    def validate_version_output(self, output: str) -> None:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        actual = lines[-1] if lines else ""
        if actual != self.expected_version:
            raise BackendContractError(
                f"PyMOL 版本不匹配: expected={self.expected_version}, actual={actual!r}"
            )

    def probe_version(self) -> str:
        try:
            result = subprocess.run(
                self.version_probe_invocation(),
                check=False,
                capture_output=True,
                text=True,
                timeout=min(self.timeout_seconds, 30.0),
                shell=False,
            )
        except FileNotFoundError as error:
            raise BackendContractError(
                f"显式 PyMOL Python 不存在: {self.python_executable}"
            ) from error
        except subprocess.TimeoutExpired as error:
            raise BackendContractError("PyMOL 版本探针超时") from error
        if result.returncode != 0:
            raise BackendContractError(
                f"PyMOL 版本探针失败: returncode={result.returncode}, stderr={result.stderr}"
            )
        self.validate_version_output(result.stdout)
        return self.expected_version

    def build_request(
        self,
        *,
        run_root: Path,
        source_path: Path,
        target_id: str,
    ) -> PseExtractionRequest:
        resolved_root = run_root.resolve()
        resolved_source = source_path.resolve()
        try:
            relative = resolved_source.relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise TargetInputError("PSE worker 只能读取 run snapshot 内的 source") from error
        if not resolved_source.is_file():
            raise TargetInputError(f"PSE source snapshot 不存在: {resolved_source}")
        return PseExtractionRequest(
            target_id=target_id,
            source_relative_path=relative,
            source_sha256=sha256_file(resolved_source),
        )

    def write_request(self, request: PseExtractionRequest, path: Path) -> Path:
        return dump_model(request, path)

    def extraction_invocation(
        self,
        *,
        request_path: Path,
        run_root: Path,
        output_dir: Path,
    ) -> PseWorkerInvocation:
        response = output_dir / "pse-response.json"
        raw_pdb = output_dir / "raw-protein.pdb"
        return PseWorkerInvocation(
            argv=(
                str(self.python_executable),
                str(self.worker_path),
                "--request",
                str(request_path),
                "--run-root",
                str(run_root),
                "--output-json",
                str(response),
                "--output-pdb",
                str(raw_pdb),
            ),
            timeout_seconds=self.timeout_seconds,
        )

    def extract(
        self,
        *,
        request_path: Path,
        run_root: Path,
        output_dir: Path,
    ) -> PseExtractionProduct:
        self.probe_version()
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ManifestStateError(f"PyMOL worker work 目录必须为空: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        invocation = self.extraction_invocation(
            request_path=request_path,
            run_root=run_root,
            output_dir=output_dir,
        )
        started = time.monotonic()
        try:
            result = subprocess.run(
                invocation.argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=invocation.timeout_seconds,
                shell=False,
            )
        except FileNotFoundError as error:
            raise PseBackendExecutionError(
                f"显式 PyMOL Python 不存在: {self.python_executable}",
                error_code="pymol-python-not-found",
                runtime_seconds=time.monotonic() - started,
            ) from error
        except subprocess.TimeoutExpired as error:
            raise PseBackendExecutionError(
                f"PyMOL PSE worker 超时: timeout={invocation.timeout_seconds}s",
                error_code="pymol-worker-timeout",
                stdout=_subprocess_text(error.stdout),
                stderr=_subprocess_text(error.stderr),
                runtime_seconds=time.monotonic() - started,
            ) from error
        runtime = time.monotonic() - started
        response_path = output_dir / "pse-response.json"
        raw_pdb = output_dir / "raw-protein.pdb"
        response_payload: Any = None
        if response_path.is_file():
            try:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                response_payload = None
        if (
            isinstance(response_payload, dict)
            and response_payload.get("status") == "failed"
        ):
            code = str(response_payload.get("error_code", "pymol-worker-failed"))
            message = str(response_payload.get("message", "PyMOL worker 失败"))
            raise PseBackendExecutionError(
                message,
                error_code=code,
                stdout=result.stdout,
                stderr=result.stderr,
                runtime_seconds=runtime,
            )
        if result.returncode != 0:
            code = "pymol-worker-failed"
            message = (
                f"PyMOL PSE worker 失败: returncode={result.returncode}, "
                f"stderr={result.stderr.strip()}"
            )
            if response_path.is_file():
                try:
                    failure: Any = json.loads(response_path.read_text(encoding="utf-8"))
                    if isinstance(failure, dict):
                        code = str(failure.get("error_code", code))
                        message = str(failure.get("message", message))
                except (OSError, json.JSONDecodeError):
                    pass
            raise PseBackendExecutionError(
                message,
                error_code=code,
                stdout=result.stdout,
                stderr=result.stderr,
                runtime_seconds=runtime,
            )
        if not response_path.is_file() or not raw_pdb.is_file():
            raise PseBackendExecutionError(
                "PyMOL worker 成功退出但缺少 response JSON 或 raw PDB",
                error_code="pymol-worker-output-missing",
                stdout=result.stdout,
                stderr=result.stderr,
                runtime_seconds=runtime,
            )
        try:
            if response_payload is None:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            response = PseWorkerResponse.model_validate(response_payload)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise PseBackendExecutionError(
                f"PyMOL worker response 无效: {error}",
                error_code="pymol-worker-response-invalid",
                stdout=result.stdout,
                stderr=result.stderr,
                runtime_seconds=runtime,
            ) from error
        if sha256_file(raw_pdb) != response.raw_pdb_sha256:
            raise PseBackendExecutionError(
                "PyMOL worker raw PDB SHA-256 与 response 不一致",
                error_code="pymol-worker-checksum-mismatch",
                stdout=result.stdout,
                stderr=result.stderr,
                runtime_seconds=runtime,
            )
        return PseExtractionProduct(
            response=response,
            raw_pdb_path=raw_pdb,
            response_path=response_path,
            stdout=result.stdout,
            stderr=result.stderr,
            adapter_runtime_seconds=runtime,
        )
