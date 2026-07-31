import type {
  CandidateDetail,
  CandidatePage,
  DesignSession,
  ExecutionProgress,
  FilterOverview,
  InstallStatus,
  MetricPresentation,
  ProjectResponse,
  ProjectCatalogEntry,
  ReferenceStructure,
  RegionEditorProjection,
  Replay,
  Run,
  AssistantServiceStatus,
  SelfTestRecord,
  Stage,
  StageFormDefinition,
  Strategy,
  StructureInteractionSession,
  UiJobRecord,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = payload.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object"
        ? String(detail.reason || detail.message || detail.code || `HTTP ${response.status}`)
        : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  installStatus: () => request<InstallStatus>("/api/v1/install/status"),
  launchSetup: (
    minimal: boolean,
    component: string | undefined,
    acceptedLicenseIds: string[],
  ) =>
    request<{ job_id: string; status: string; pid?: number }>("/api/v1/install/setup", {
      method: "POST",
      body: JSON.stringify({
        minimal,
        component,
        accepted_license_ids: acceptedLicenseIds,
        confirmed: true,
      }),
    }),
  projects: () => request<ProjectResponse>("/api/v1/projects"),
  projectPreflight: (projectId: string) =>
    request<{
      available: boolean;
      project_id: string;
      reason: string;
      existing_project?: string;
      suggested_project_id?: string;
    }>(`/api/v1/project-preflight?project_id=${encodeURIComponent(projectId)}`),
  projectCatalog: () =>
    request<{ entries: ProjectCatalogEntry[] }>(
      "/api/v1/project-catalog?include_archived=true&include_developer_smoke=true",
    ),
  archiveProject: (projectId: string) =>
    request<Record<string, unknown>>(
      `/api/v1/project-catalog/${encodeURIComponent(projectId)}/archive`,
      { method: "POST", body: JSON.stringify({ confirmed: true }) },
    ),
  restoreProject: (projectId: string) =>
    request<Record<string, unknown>>(
      `/api/v1/project-catalog/${encodeURIComponent(projectId)}/restore`,
      { method: "POST", body: JSON.stringify({ confirmed: true }) },
    ),
  designSessions: () => request<DesignSession[]>("/api/v1/design-sessions"),
  selfTests: () => request<SelfTestRecord[]>("/api/v1/self-tests"),
  runSelfTest: (mode: SelfTestRecord["mode"]) =>
    request<SelfTestRecord>("/api/v1/self-tests", {
      method: "POST",
      body: JSON.stringify({ mode, confirmed: true }),
    }),
  runSelfTestStage: (selfTestId: string, stage: number) =>
    request<{ record: SelfTestRecord; job: UiJobRecord | null }>(
      `/api/v1/self-tests/${encodeURIComponent(selfTestId)}/stages/${stage}/run`,
      {
        method: "POST",
        body: JSON.stringify({ stage_number: stage, confirmed: true }),
      },
    ),
  createDesignSession: (
    projectId: string,
    designMode: DesignSession["design_mode"],
    executionMode: DesignSession["execution_mode"],
  ) =>
    request<DesignSession>("/api/v1/design-sessions", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        design_mode: designMode,
        execution_mode: executionMode,
      }),
    }),
  configForm: (stage: number) =>
    request<StageFormDefinition>(`/api/v1/config/forms/${stage}`),
  run: (key: string) => request<Run>(`/api/v1/runs/${key}`),
  stage: (key: string, stage: number) =>
    request<Stage>(`/api/v1/runs/${key}/stages/${stage}`),
  execution: (key: string, stage: 4 | 6) =>
    request<ExecutionProgress>(`/api/v1/runs/${key}/stages/${stage}/execution`),
  filterOverview: (key: string) =>
    request<FilterOverview>(`/api/v1/runs/${key}/stages/5/overview`),
  filterStrategies: (key: string) =>
    request<Strategy[]>(`/api/v1/runs/${key}/stages/5/strategies`),
  filterMetrics: (key: string) =>
    request<MetricPresentation[]>(`/api/v1/runs/${key}/stages/5/metrics`),
  filterCandidates: (
    key: string,
    parameters: {
      phase: string;
      page?: number;
      pageSize?: number;
      strategyId?: string;
      gateStatus?: string;
      failedRule?: string;
      sortKey?: string;
      sortOrder?: string;
    },
  ) => {
    const query = new URLSearchParams({
      phase: parameters.phase,
      page: String(parameters.page || 1),
      page_size: String(parameters.pageSize || 50),
      sort_key: parameters.sortKey || "candidate_id",
      sort_order: parameters.sortOrder || "asc",
    });
    if (parameters.strategyId) query.set("strategy_id", parameters.strategyId);
    if (parameters.gateStatus) query.set("gate_status", parameters.gateStatus);
    if (parameters.failedRule) query.set("failed_rule", parameters.failedRule);
    return request<CandidatePage>(
      `/api/v1/runs/${key}/stages/5/candidates?${query.toString()}`,
    );
  },
  filterCandidate: (key: string, candidateId: string, phase: string) =>
    request<CandidateDetail>(
      `/api/v1/runs/${key}/stages/5/candidates/${encodeURIComponent(candidateId)}?phase=${encodeURIComponent(phase)}`,
    ),
  replay: (key: string) => request<Replay>(`/api/v1/runs/${key}/replay`),
  decision: (key: string) =>
    request<{ request: Record<string, unknown>; request_sha256: string }>(
      `/api/v1/runs/${key}/decision`,
    ),
  approveDecision: (
    key: string,
    selectedOptionIds: string[],
    approvedBy: string,
    acknowledgement?: string,
  ) =>
    request<Record<string, unknown>>(`/api/v1/runs/${key}/decision`, {
      method: "POST",
      body: JSON.stringify({
        selected_option_ids: selectedOptionIds,
        approved_by: approvedBy,
        acknowledgement,
        confirmed: true,
      }),
    }),
  hotspotReview: (key: string, method?: "sasa" | "scannet") =>
    request<{ run_key: string; yaml: string }>(
      `/api/v1/runs/${key}/hotspots/review${method ? `?method=${method}` : ""}`,
    ),
  approveHotspots: (key: string, yamlText: string) =>
    request<{ status: string; run_key: string; next_action: string }>(
      `/api/v1/runs/${key}/hotspots/approve`,
      {
        method: "POST",
        body: JSON.stringify({ yaml_text: yamlText, confirmed: true }),
      },
    ),
  regionEditor: (key: string) =>
    request<RegionEditorProjection>(`/api/v1/runs/${key}/regions/editor`),
  reviseRegions: (
    key: string,
    body: {
      session_id: string;
      execution_mode: "unattended" | "review-gated";
      regions: Array<{ id: string; label_seq_ids: number[] }>;
      approved_by: string;
      acknowledge_user_provided_regions: boolean;
      acknowledge_evidence_limitations: boolean;
    },
  ) =>
    request<{ job: Record<string, unknown>; session: DesignSession }>(
      `/api/v1/runs/${key}/regions/revise`,
      {
        method: "POST",
        body: JSON.stringify({ ...body, confirmed: true }),
      },
    ),
  continueRun: (
    key: string,
    stage: number,
    body: {
      session_id: string;
      execution_mode: "unattended" | "review-gated";
      options?: Record<string, unknown>;
    },
  ) =>
    request<{ job: UiJobRecord; session: DesignSession }>(
      `/api/v1/runs/${key}/continue/${stage}`,
      {
        method: "POST",
        body: JSON.stringify({
          ...body,
          stage_number: stage,
          confirmed: true,
        }),
      },
    ),
  resume: (key: string) =>
    request<Record<string, unknown>>(`/api/v1/runs/${key}/resume`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true }),
    }),
  clone: (key: string, projectId: string) =>
    request<{ project_id: string; config: string; status: string }>(
      `/api/v1/runs/${key}/clone`,
      { method: "POST", body: JSON.stringify({ project_id: projectId }) },
    ),
  config: (projectId: string) =>
    request<{ project_id: string; yaml: string }>(
      `/api/v1/projects/${projectId}/config`,
    ),
  updateConfig: (projectId: string, yamlText: string) =>
    request<{ status: string; plan: Record<string, unknown> }>(
      `/api/v1/projects/${projectId}/config`,
      { method: "PUT", body: JSON.stringify({ yaml_text: yamlText }) },
    ),
  preflight: (projectId: string, executorId?: string) =>
    request<{ plan: Record<string, unknown>; diagnostic: Record<string, unknown> }>(
      "/api/v1/preflight",
      {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          executor_id: executorId,
        }),
      },
    ),
  launch: (
    projectId: string,
    runId?: string,
    executorId?: string,
    sessionId?: string,
    stageNumber?: number,
  ) =>
    request<Record<string, unknown>>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        run_id: runId,
        executor_id: executorId,
        session_id: sessionId,
        stage_number: stageNumber,
        confirmed: true,
      }),
    }),
  remoteExecutors: () =>
    request<{ executors: Array<{ executor_id: string; label: string }> }>(
      "/api/v1/remote-executors",
    ),
  remoteJobs: () =>
    request<{ jobs: Array<Record<string, unknown>> }>("/api/v1/remote-jobs"),
  remoteJob: (executorId: string, jobId: string) =>
    request<Record<string, unknown>>(
      `/api/v1/remote-jobs/${executorId}/${jobId}`,
    ),
  syncRemoteJob: (
    executorId: string,
    jobId: string,
    mode: "metadata" | "complete" = "metadata",
  ) =>
    request<Record<string, unknown>>(
      `/api/v1/remote-jobs/${executorId}/${jobId}/sync`,
      {
        method: "POST",
        body: JSON.stringify({ mode, confirmed: true }),
      },
    ),
  resumeRemoteJob: (executorId: string, jobId: string) =>
    request<Record<string, unknown>>(
      `/api/v1/remote-jobs/${executorId}/${jobId}/resume`,
      {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      },
    ),
  jobs: () => request<Array<Record<string, unknown>>>("/api/v1/jobs"),
  drain: (jobId: string) =>
    request<Record<string, unknown>>(`/api/v1/jobs/${jobId}/drain`, {
      method: "POST",
    }),
  draftOrder: (key: string) =>
    request<Record<string, unknown>>(`/api/v1/runs/${key}/draft-order-package`, {
      method: "POST",
    }),
  browserPymolStatus: () =>
    request<{
      available: boolean;
      renderer: string;
      pymol_version: string;
      pyodide_version: string;
      offline_assets: boolean;
    }>("/api/v1/browser-pymol/status"),
  assistantStatus: () =>
    request<AssistantServiceStatus>("/api/v1/structure-assistant/status"),
  createStructureSession: (key: string, stageNumber: 1 | 2) =>
    request<StructureInteractionSession>(
      `/api/v1/runs/${key}/structure-sessions`,
      {
        method: "POST",
        body: JSON.stringify({ stage_number: stageNumber }),
      },
    ),
  structureSession: (sessionId: string) =>
    request<StructureInteractionSession>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}`,
    ),
  assistantMessage: (
    sessionId: string,
    message: string,
  ) =>
    request<StructureInteractionSession>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ message }),
      },
    ),
  appendStructurePml: (
    sessionId: string,
    pml: string,
    source: "viewer" | "expert-console" = "expert-console",
  ) =>
    request<StructureInteractionSession>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/pml`,
      {
        method: "POST",
        body: JSON.stringify({ pml, source }),
      },
    ),
  saveScenePml: (
    sessionId: string,
    pml: string,
    source: "viewer" | "expert-console" = "expert-console",
  ) =>
    request<{
      session: StructureInteractionSession;
      result: string;
      version: { version_id: string; revision: number; pml: string };
    }>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/scene-pml`,
      {
        method: "PUT",
        body: JSON.stringify({ pml, source }),
      },
    ),
  applyAssistantProposal: (sessionId: string, proposalId: string) =>
    request<{
      session: StructureInteractionSession;
      result: string;
      analysis_plan?: {
        methods: Array<"sasa" | "scannet">;
        requires_confirmation: true;
        reason: string;
      };
      version?: {
        version_id: string;
        revision: number;
        pml: string;
      };
    }>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/proposals/${encodeURIComponent(proposalId)}/apply`,
      {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      },
    ),
  restoreSceneVersion: (sessionId: string, versionId: string, baseVersionId?: string) =>
    request<{
      session: StructureInteractionSession;
      result: string;
      version: { version_id: string; revision: number; pml: string };
    }>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/scene-versions/${encodeURIComponent(versionId)}/restore`,
      {
        method: "POST",
        body: JSON.stringify({ base_version_id: baseVersionId, confirmed: true }),
      },
    ),

  addUploadedStructureReference: (
    sessionId: string,
    uploadToken: string,
    objectName?: string,
  ) =>
    request<{
      session: StructureInteractionSession;
      result: string;
      reference: ReferenceStructure;
      version: { version_id: string; revision: number; pml: string };
    }>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/references/uploads`,
      {
        method: "POST",
        body: JSON.stringify({ upload_token: uploadToken, object_name: objectName, confirmed: true }),
      },
    ),
  addRcsbStructureReference: (
    sessionId: string,
    rcsbId: string,
    objectName?: string,
  ) =>
    request<{
      session: StructureInteractionSession;
      result: string;
      reference: ReferenceStructure;
      version: { version_id: string; revision: number; pml: string };
    }>(
      `/api/v1/structure-sessions/${encodeURIComponent(sessionId)}/references/rcsb`,
      {
        method: "POST",
        body: JSON.stringify({ rcsb_id: rcsbId, object_name: objectName, confirmed: true }),
      },
    ),
  upload: async (file: File) => {
    const bytes = await file.arrayBuffer();
    const hash = await crypto.subtle.digest("SHA-256", bytes);
    const sha256 = [...new Uint8Array(hash)]
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 120_000);
    try {
      const response = await fetch(
        `/api/v1/uploads/raw?filename=${encodeURIComponent(file.name)}&sha256=${sha256}`,
        {
          method: "POST",
          body: file,
          cache: "no-store",
          headers: { "Content-Type": "application/octet-stream" },
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(payload.detail || `HTTP ${response.status}`);
      }
      return await response.json() as {
        schema_version: "0.2";
        upload_token: string;
        filename: string;
        size_bytes: number;
        sha256: string;
        status: string;
        relative_path: string;
      };
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new Error("文件接收超时，请检查连接后重试");
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  },
  job: (jobId: string) =>
    request<UiJobRecord>(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
  createProject: (body: Record<string, unknown>) =>
    request<{
      project_id: string;
      config: string;
      status: string;
      session: DesignSession;
    }>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
