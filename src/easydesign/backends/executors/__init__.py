"""Local and scheduler execution adapters."""

from .local_multi_gpu import (
    DeviceResult,
    GpuResourceSnapshot,
    NvidiaSmiProbe,
    execute_on_devices,
    ui_drain_requested,
)

__all__ = [
    "DeviceResult",
    "GpuResourceSnapshot",
    "NvidiaSmiProbe",
    "execute_on_devices",
    "ui_drain_requested",
]
