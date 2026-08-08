"""Local execution adapters only."""

from .local_multi_gpu import (
    DeviceResult,
    GpuResourceSnapshot,
    NvidiaSmiProbe,
    execute_on_devices,
    local_drain_requested,
)

__all__ = [
    "DeviceResult",
    "GpuResourceSnapshot",
    "NvidiaSmiProbe",
    "execute_on_devices",
    "local_drain_requested",
]
