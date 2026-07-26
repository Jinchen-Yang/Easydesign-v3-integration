"""Auditable, read-only reports derived from immutable scientific artifacts."""

from .evidence_bundle import (
    UiEvidenceBundleOutcome,
    build_ui_evidence_bundle,
    verify_ui_evidence_bundle,
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
    "UiEvidenceBundleOutcome",
    "ViewerAnnotationSummary",
    "ViewerColorCount",
    "ViewerDownload",
    "ViewerMetric",
    "ViewerResidue",
    "create_target_viewer_server",
    "build_ui_evidence_bundle",
    "generate_stage01_target_viewer",
    "generate_stage01_target_viewer_nonblocking",
    "resolve_latest_target_viewer_report",
    "resolve_target_viewer_argument",
    "verify_target_viewer_report",
    "verify_ui_evidence_bundle",
]
