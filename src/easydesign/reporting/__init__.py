"""Auditable, read-only reports derived from immutable scientific artifacts."""

from .evidence_bundle import (
    EvidenceBundleOutcome,
    build_evidence_bundle,
    verify_evidence_bundle,
)
from .evidence_viewer import (
    EvidenceStructure,
    EvidenceViewerOverlay,
    EvidenceViewerPayload,
    build_evidence_viewer_payload,
)
from .models import (
    GENERATOR_VERSION,
    MOLSTAR_VERSION,
    REPORT_ID,
    TargetViewerData,
    TargetViewerOutcome,
    TargetViewerReportManifest,
    ViewerAnnotationSummary,
    ViewerColorCount,
    ViewerDownload,
    ViewerMetric,
    ViewerResidue,
)
from .server import (
    HOST,
    TargetViewerHttpServer,
    create_target_viewer_server,
    resolve_target_viewer_argument,
)
from .stage02_overlay import Stage02ViewerOverlay, build_stage02_viewer_overlay
from .target_viewer import (
    TargetViewerReportError,
    generate_stage01_target_viewer,
    generate_stage01_target_viewer_nonblocking,
    resolve_latest_target_viewer_report,
    verify_target_viewer_report,
)

__all__ = [
    "GENERATOR_VERSION",
    "HOST",
    "MOLSTAR_VERSION",
    "REPORT_ID",
    "TargetViewerData",
    "TargetViewerHttpServer",
    "TargetViewerOutcome",
    "TargetViewerReportError",
    "TargetViewerReportManifest",
    "Stage02ViewerOverlay",
    "EvidenceBundleOutcome",
    "EvidenceStructure",
    "EvidenceViewerOverlay",
    "EvidenceViewerPayload",
    "ViewerAnnotationSummary",
    "ViewerColorCount",
    "ViewerDownload",
    "ViewerMetric",
    "ViewerResidue",
    "create_target_viewer_server",
    "build_evidence_bundle",
    "build_evidence_viewer_payload",
    "build_stage02_viewer_overlay",
    "generate_stage01_target_viewer",
    "generate_stage01_target_viewer_nonblocking",
    "resolve_latest_target_viewer_report",
    "resolve_target_viewer_argument",
    "verify_target_viewer_report",
    "verify_evidence_bundle",
]
