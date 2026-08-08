"""不接管外部进程的本地多 GPU 资源探针和有界调度器。"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from easydesign.core import BackendContractError

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class GpuResourceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    device: int = Field(ge=0)
    name: str
    uuid: str
    memory_total_mib: int = Field(ge=0)
    memory_used_mib: int = Field(ge=0)
    utilization_percent: int = Field(ge=0, le=100)
    compute_process_pids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class NvidiaSmiProbe:
    executable: Path = Path("/usr/bin/nvidia-smi")
    timeout_seconds: float = 15.0

    def snapshots(self) -> tuple[GpuResourceSnapshot, ...]:
        command = [
            str(self.executable),
            "--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackendContractError(f"nvidia-smi GPU 探针失败: {error}") from error
        if completed.returncode != 0:
            raise BackendContractError(
                "nvidia-smi GPU 探针失败: "
                + (completed.stderr.strip() or completed.stdout.strip())[:2048]
            )
        processes = self._compute_processes()
        snapshots: list[GpuResourceSnapshot] = []
        for row in csv.reader(io.StringIO(completed.stdout), skipinitialspace=True):
            if len(row) != 6:
                raise BackendContractError("nvidia-smi GPU 输出列数不符合契约")
            uuid = row[2].strip()
            snapshots.append(
                GpuResourceSnapshot(
                    device=int(row[0].strip()),
                    name=row[1].strip(),
                    uuid=uuid,
                    memory_total_mib=int(row[3].strip()),
                    memory_used_mib=int(row[4].strip()),
                    utilization_percent=int(row[5].strip()),
                    compute_process_pids=tuple(sorted(processes.get(uuid, set()))),
                )
            )
        if not snapshots:
            raise BackendContractError("nvidia-smi 没有返回 GPU")
        return tuple(snapshots)

    def _compute_processes(self) -> dict[str, set[int]]:
        command = [
            str(self.executable),
            "--query-compute-apps=gpu_uuid,pid",
            "--format=csv,noheader,nounits",
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            lowered = (completed.stderr + completed.stdout).lower()
            if "no running processes" in lowered:
                return {}
            raise BackendContractError(
                "nvidia-smi process 探针失败: "
                + (completed.stderr.strip() or completed.stdout.strip())[:2048]
            )
        by_uuid: dict[str, set[int]] = {}
        for row in csv.reader(io.StringIO(completed.stdout), skipinitialspace=True):
            if not row or not row[0].strip():
                continue
            if len(row) != 2:
                raise BackendContractError("nvidia-smi process 输出列数不符合契约")
            try:
                pid = int(row[1].strip())
            except ValueError:
                continue
            by_uuid.setdefault(row[0].strip(), set()).add(pid)
        return by_uuid

    def wait_until_idle(
        self,
        devices: tuple[int, ...],
        *,
        max_memory_used_mib: int,
        max_utilization_percent: int,
        timeout_seconds: float,
        poll_seconds: float,
        on_wait: Callable[[tuple[GpuResourceSnapshot, ...]], None] | None = None,
    ) -> tuple[GpuResourceSnapshot, ...]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            all_snapshots = self.snapshots()
            by_device = {snapshot.device: snapshot for snapshot in all_snapshots}
            missing = [device for device in devices if device not in by_device]
            if missing:
                raise BackendContractError(f"请求的 GPU device 不存在: {missing}")
            selected = tuple(by_device[device] for device in devices)
            busy = tuple(
                item
                for item in selected
                if item.compute_process_pids
                or item.memory_used_mib > max_memory_used_mib
                or item.utilization_percent > max_utilization_percent
            )
            if not busy:
                return selected
            if time.monotonic() >= deadline:
                details = "; ".join(
                    f"gpu={item.device},memory={item.memory_used_mib}MiB,"
                    f"util={item.utilization_percent}%,pids={item.compute_process_pids}"
                    for item in busy
                )
                raise BackendContractError(f"GPU 在有界等待后仍不满足空闲门槛: {details}")
            if on_wait is not None:
                on_wait(busy)
            time.sleep(poll_seconds)


@dataclass(frozen=True, slots=True)
class DeviceResult(Generic[OutputT]):
    input_index: int
    device: int
    result: OutputT


def execute_on_devices(
    items: tuple[InputT, ...],
    *,
    devices: tuple[int, ...],
    worker: Callable[[InputT, int], OutputT],
    should_stop: Callable[[], bool] | None = None,
) -> tuple[DeviceResult[OutputT], ...]:
    """每个 device 一个串行 worker；可在当前 item 完成后停止继续调度。"""

    if not devices:
        raise ValueError("execute_on_devices 至少需要一个 device")
    if len(devices) != len(set(devices)):
        raise ValueError("execute_on_devices device 不能重复")
    buckets: list[list[tuple[int, InputT]]] = [[] for _ in devices]
    for index, item in enumerate(items):
        buckets[index % len(devices)].append((index, item))

    def run_bucket(
        device: int,
        bucket: list[tuple[int, InputT]],
    ) -> list[DeviceResult[OutputT]]:
        results: list[DeviceResult[OutputT]] = []
        for index, item in bucket:
            if should_stop is not None and should_stop():
                break
            results.append(
                DeviceResult(
                    input_index=index,
                    device=device,
                    result=worker(item, device),
                )
            )
        return results

    results: list[DeviceResult[OutputT]] = []
    with ThreadPoolExecutor(
        max_workers=len(devices),
        thread_name_prefix="easydesign-gpu",
    ) as executor:
        futures: list[Future[list[DeviceResult[OutputT]]]] = [
            executor.submit(run_bucket, device, bucket)
            for device, bucket in zip(devices, buckets, strict=True)
        ]
        for future in futures:
            results.extend(future.result())
    return tuple(sorted(results, key=lambda item: item.input_index))


def local_drain_requested() -> bool:
    """读取可选调度停止标记；不终止已经启动的 backend。"""

    value = os.environ.get("EASYDESIGN_LOCAL_DRAIN_FILE")
    return False if value is None else Path(value).is_file()
