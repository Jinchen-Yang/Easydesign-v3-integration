import type { ProjectResponse, Replay, Run, Stage } from "./types";

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
  preflight: (projectId: string) =>
    request<{ plan: Record<string, unknown>; diagnostic: Record<string, unknown> }>(
      "/api/v1/preflight",
      { method: "POST", body: JSON.stringify({ project_id: projectId }) },
    ),
  launch: (projectId: string, runId?: string) =>
    request<Record<string, unknown>>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, run_id: runId, confirmed: true }),
    }),
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
    request<{ upload_token: string }>("/api/v1/uploads", {
      method: "POST",
      body: JSON.stringify({ filename, content_base64: contentBase64 }),
    }),
  createProject: (body: Record<string, unknown>) =>
    request<{ project_id: string; config: string; status: string }>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
