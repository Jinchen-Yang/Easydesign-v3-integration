"""Local and scheduler execution adapters."""

from .local_multi_gpu import (
    DeviceResult,
    GpuResourceSnapshot,
    NvidiaSmiProbe,
    execute_on_devices,
    ui_drain_requested,
)
from .managed_worker import (
    MANAGED_WORKER_ROOT,
    ManagedJobRevision,
    ManagedQueue,
    ManagedWorker,
    ManagedWorkerLayout,
    ManagedWorkerProbe,
    RemoteJobBundle,
    RemoteJobInput,
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
    "ManagedJobRevision",
    "ManagedQueue",
    "ManagedWorker",
    "ManagedWorkerLayout",
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
