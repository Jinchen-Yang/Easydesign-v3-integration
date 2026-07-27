import type {
  CandidateDetail,
  CandidatePage,
  ExecutionProgress,
  FilterOverview,
  MetricPresentation,
  ProjectResponse,
  Replay,
  Run,
  Stage,
  Strategy,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  projects: () => request<ProjectResponse>("/api/v1/projects"),
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
  launch: (projectId: string, runId?: string, executorId?: string) =>
    request<Record<string, unknown>>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        run_id: runId,
        executor_id: executorId,
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
  upload: (filename: string, contentBase64: string) =>
    request<{
      upload_token: string;
      filename: string;
      size_bytes: number;
      sha256: string;
    }>("/api/v1/uploads", {
      method: "POST",
      body: JSON.stringify({ filename, content_base64: contentBase64 }),
    }),
  createProject: (body: Record<string, unknown>) =>
    request<{ project_id: string; config: string; status: string }>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
