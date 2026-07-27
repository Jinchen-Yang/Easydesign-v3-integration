"""BoltzGen 0.3.2 full-pipeline generation adapter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from easydesign.core import BackendContractError

from .check import BoltzGenCheckAdapter


@dataclass(frozen=True, slots=True)
class BoltzGenGenerationRequest:
    design_specification: Path
    output_directory: Path
    requested_candidates: int
    physical_device: int
    stdout_path: Path
    stderr_path: Path


@dataclass(frozen=True, slots=True)
class BoltzGenGenerationResult:
    command: tuple[str, ...]
    command_sha256: str
    started_at: datetime
    ended_at: datetime
    return_code: int
    stdout_path: Path
    stderr_path: Path
    output_directory: Path


@dataclass(frozen=True, slots=True)
class BoltzGenGenerationHeartbeat:
    """后端进程存活心跳；不宣称中间文件已成为完整候选。"""

    observed_at: datetime
    elapsed_seconds: float
    phase: str = "boltzgen-running"
    message: str = "BoltzGen process is still running."


BoltzGenHeartbeatCallback = Callable[[BoltzGenGenerationHeartbeat], None]


@dataclass(frozen=True, slots=True)
class BoltzGenGenerationAdapter:
    check_adapter: BoltzGenCheckAdapter
    generation_timeout_seconds: float = 172_800.0
    data_loader_workers: int = 4
    heartbeat_interval_seconds: float = 30.0

    def probe(self) -> dict[str, str]:
        return self.check_adapter.probe()

    def build_command(self, request: BoltzGenGenerationRequest) -> tuple[str, ...]:
        if request.requested_candidates < 1:
            raise BackendContractError("BoltzGen requested_candidates 必须为正整数")
        return (
            str(self.check_adapter.executable),
            "run",
            str(request.design_specification),
            "--protocol",
            "nanobody-anything",
            "--output",
            str(request.output_directory),
            "--devices",
            "1",
            "--num_workers",
            str(self.data_loader_workers),
            "--num_designs",
            str(request.requested_candidates),
            "--inverse_fold_num_sequences",
            "1",
            "--budget",
            "30",
            "--alpha",
            "0.001",
            "--filter_biased",
            "true",
            "--cache",
            str(self.check_adapter.cache_root),
        )

    def execute(
        self,
        request: BoltzGenGenerationRequest,
        *,
        heartbeat_callback: BoltzGenHeartbeatCallback | None = None,
    ) -> BoltzGenGenerationResult:
        self.probe()
        if not request.design_specification.is_file():
            raise BackendContractError(
                f"BoltzGen design specification 不存在: {request.design_specification}"
            )
        if request.output_directory.exists():
            raise BackendContractError(
                f"BoltzGen task attempt output 禁止覆盖: {request.output_directory}"
            )
        request.output_directory.parent.mkdir(parents=True, exist_ok=True)
        request.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        request.stderr_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(request)
        command_sha256 = hashlib.sha256(
            json.dumps(command, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = str(request.physical_device)
        if self.check_adapter.offline_mode:
            environment["HF_HUB_OFFLINE"] = "1"
        started = datetime.now(UTC)
        heartbeat_stop = threading.Event()
        heartbeat_errors: list[Exception] = []

        def emit_heartbeats() -> None:
            while not heartbeat_stop.wait(self.heartbeat_interval_seconds):
                if heartbeat_callback is None:
                    continue
                observed = datetime.now(UTC)
                try:
                    heartbeat_callback(
                        BoltzGenGenerationHeartbeat(
                            observed_at=observed,
                            elapsed_seconds=max(
                                0.0,
                                (observed - started).total_seconds(),
                            ),
                        )
                    )
                except Exception as error:  # pragma: no cover - defensive thread boundary
                    heartbeat_errors.append(error)
                    return

        heartbeat_thread: threading.Thread | None = None
        if heartbeat_callback is not None:
            if self.heartbeat_interval_seconds <= 0:
                raise BackendContractError("BoltzGen heartbeat interval 必须为正数")
            heartbeat_thread = threading.Thread(
                target=emit_heartbeats,
                name="easydesign-boltzgen-heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()
        try:
            with (
                request.stdout_path.open("x", encoding="utf-8") as stdout_handle,
                request.stderr_path.open("x", encoding="utf-8") as stderr_handle,
            ):
                completed = subprocess.run(
                    list(command),
                    cwd=request.design_specification.parent,
                    check=False,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    timeout=self.generation_timeout_seconds,
                    env=environment,
                )
            return_code = completed.returncode
        except subprocess.TimeoutExpired:
            return_code = 124
            with request.stderr_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "\nEasyDesign operational timeout after "
                    f"{self.generation_timeout_seconds} seconds.\n"
                )
        finally:
            heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=max(1.0, self.heartbeat_interval_seconds))
        if heartbeat_errors:
            raise BackendContractError(
                f"BoltzGen heartbeat 写入失败: {heartbeat_errors[0]}"
            ) from heartbeat_errors[0]
        ended = datetime.now(UTC)
        return BoltzGenGenerationResult(
            command=command,
            command_sha256=command_sha256,
            started_at=started,
            ended_at=ended,
            return_code=return_code,
            stdout_path=request.stdout_path,
            stderr_path=request.stderr_path,
            output_directory=request.output_directory,
        )
