"""Local and scheduler execution adapters."""

from .local_multi_gpu import (
    DeviceResult,
    GpuResourceSnapshot,
    NvidiaSmiProbe,
    execute_on_devices,
    ui_drain_requested,
)
from .ssh_remote import (
    SshRemoteConnection,
    SshRemoteExecutor,
    SshRemoteProbe,
    SshRemoteStatus,
    SshRemoteSubmission,
)

__all__ = [
    "DeviceResult",
    "GpuResourceSnapshot",
    "NvidiaSmiProbe",
    "SshRemoteConnection",
    "SshRemoteExecutor",
    "SshRemoteProbe",
    "SshRemoteStatus",
    "SshRemoteSubmission",
    "execute_on_devices",
    "ui_drain_requested",
]
