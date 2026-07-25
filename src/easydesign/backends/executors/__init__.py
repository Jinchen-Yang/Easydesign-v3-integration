"""Local and scheduler execution adapters."""

from .local_multi_gpu import (
    DeviceResult,
    GpuResourceSnapshot,
    NvidiaSmiProbe,
    execute_on_devices,
)

__all__ = [
    "DeviceResult",
    "GpuResourceSnapshot",
    "NvidiaSmiProbe",
    "execute_on_devices",
]
