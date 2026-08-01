"""Local and scheduler execution adapters."""

from easydesign.managed_protocol import (
    MANAGED_WORKER_ROOT,
    ManagedBackendReadiness,
    ManagedJobRevision,
    ManagedWorkerProbe,
    RemoteJobBundle,
    RemoteJobInput,
)

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
    SshRemoteFileIdentity,
    SshRemoteJobRecord,
    SshRemoteObservation,
    SshRemoteProbe,
    SshRemoteStatus,
    SshRemoteSubmission,
    SshRemoteSyncReport,
)

__all__ = [
    "DeviceResult",
    "GpuResourceSnapshot",
    "MANAGED_WORKER_ROOT",
    "ManagedBackendReadiness",
    "ManagedJobRevision",
    "ManagedWorkerProbe",
    "NvidiaSmiProbe",
    "RemoteJobBundle",
    "RemoteJobInput",
    "SshRemoteConnection",
    "SshRemoteExecutor",
    "SshRemoteFileIdentity",
    "SshRemoteJobRecord",
    "SshRemoteObservation",
    "SshRemoteProbe",
    "SshRemoteStatus",
    "SshRemoteSubmission",
    "SshRemoteSyncReport",
    "execute_on_devices",
    "ui_drain_requested",
]
