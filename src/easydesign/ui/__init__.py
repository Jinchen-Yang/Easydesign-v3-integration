"""EasyDesign 本地科研工作台的公共 API。"""

from .app import create_ui_app, serve_ui
from .execution import get_execution_progress
from .jobs import (
    UiJobController,
    clone_run_configuration,
    launch_pipeline_job,
    request_pipeline_drain,
    resume_pipeline_job,
)
from .models import (
    ArtifactProjection,
    DraftOrderOutcome,
    ProjectProjection,
    ReplayTimeline,
    RunProjection,
    StageProjection,
    UiJobRecord,
    UiStageState,
)
from .projections import (
    UiRunRegistry,
    create_demo_replay,
    create_draft_order_package,
    get_project_projection,
    get_run_projection,
    get_stage_projection,
    stream_run_events,
)

__all__ = [
    "ArtifactProjection",
    "DraftOrderOutcome",
    "ProjectProjection",
    "ReplayTimeline",
    "RunProjection",
    "StageProjection",
    "UiJobController",
    "UiJobRecord",
    "UiRunRegistry",
    "UiStageState",
    "clone_run_configuration",
    "create_demo_replay",
    "create_draft_order_package",
    "create_ui_app",
    "get_project_projection",
    "get_execution_progress",
    "get_run_projection",
    "get_stage_projection",
    "launch_pipeline_job",
    "request_pipeline_drain",
    "resume_pipeline_job",
    "serve_ui",
    "stream_run_events",
]
