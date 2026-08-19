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
from .gpcr_site_review import (
    GpcrReviewServer,
    create_gpcr_review_server,
    export_gpcr_review_report,
)
from .gpcr_site_review import (
    ReviewReportError as GpcrReviewReportError,
)
from .gpcr_site_review import (
    generate_review_report as generate_gpcr_review_report,
)
from .gpcr_site_review import (
    resolve_latest_review_report as resolve_latest_gpcr_review_report,
)
from .gpcr_site_review import (
    validate_review_report as validate_gpcr_review_report,
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
from .review_dashboard import (
    ReviewDashboardError,
    generate_review_dashboard,
    generate_review_dashboard_nonblocking,
    resolve_latest_review_dashboard,
    verify_review_dashboard,
)
from .review_models import (
    ReviewDashboardExportManifest,
    ReviewDashboardManifest,
    ReviewDashboardOutcome,
    ReviewDashboardPresentationOverride,
    ReviewDashboardReport,
)
from .review_server import (
    ReviewDashboardHttpServer,
    create_review_dashboard_server,
    export_review_dashboard,
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
    "GpcrReviewReportError",
    "GpcrReviewServer",
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
    "create_gpcr_review_server",
    "build_evidence_bundle",
    "build_evidence_viewer_payload",
    "build_stage02_viewer_overlay",
    "generate_stage01_target_viewer",
    "generate_gpcr_review_report",
    "generate_stage01_target_viewer_nonblocking",
    "resolve_latest_target_viewer_report",
    "resolve_latest_gpcr_review_report",
    "resolve_target_viewer_argument",
    "verify_target_viewer_report",
    "verify_evidence_bundle",
    "validate_gpcr_review_report",
    "export_gpcr_review_report",
    "ReviewDashboardError",
    "ReviewDashboardExportManifest",
    "ReviewDashboardHttpServer",
    "ReviewDashboardManifest",
    "ReviewDashboardOutcome",
    "ReviewDashboardPresentationOverride",
    "ReviewDashboardReport",
    "create_review_dashboard_server",
    "export_review_dashboard",
    "generate_review_dashboard",
    "generate_review_dashboard_nonblocking",
    "resolve_latest_review_dashboard",
    "verify_review_dashboard",
]
