import type { SnapshotAdapter } from "../adapters/WorkbenchAdapter";
import type {
  Candidate,
  LocalizationPassage,
  LocalizationResult,
  GateInput,
  LiveState,
  Page,
  ProductLabOrder,
  ProductLabOrderDraft,
  ProductSnapshot,
  Project,
  RequestState,
} from "./product-contracts";
import { appI18n } from "../shell/I18nProvider";
import { needsPermissionRefresh } from "../shared/sessionEvents";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
const commonT = (key: string): string => appI18n.t(key, { ns: "common" });

// Authentication recovery and uncertain server/transport failures retain identity.
// Definitively rejected commands may be corrected and sent as a fresh request.
function isDefinitiveRejection(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500 &&
    ![401, 408, 429].includes(error.status)
  );
}

export interface LiveProductPort extends SnapshotAdapter<LiveState> {
  authenticate(token: string): Promise<void>;
  refresh(): Promise<void>;
  pausePolling(): void;
  resumePolling(): void;
  selectProject(id: string): Promise<void>;
  clearProject(): void;
  projectPage(offset: number): Promise<void>;
  renameProject(id: string, title: string): Promise<void>;
  candidatePage(
    offset: number,
    phase?: "pilot" | "scale" | "candidates",
  ): Promise<void>;
  deleteProject(id: string): Promise<void>;
  artifactText(url: string): Promise<string>;
  localizeScientific(
    passages: LocalizationPassage[],
    context: { stage: string; goal: string },
  ): Promise<LocalizationResult>;
  selectCandidate(id: string): Promise<void>;
  createProject(
    title: string,
    goal: string,
    file?: File | null,
    source?: { pdb_id?: string; uniprot?: string },
  ): Promise<void>;
  decide(input: GateInput): Promise<void>;
  resume(): Promise<void>;
  sendMessage(text: string, phase?: string): Promise<void>;
  retryRequest(id: string): Promise<void>;
  cancelRequest(id: string): Promise<void>;
}
interface ProductProjection {
  surface?: "easy";
  projectLimit: number;
  candidateView?: "summary";
}

type TransitionPhase = NonNullable<LiveState["transitionPhase"]>;

export function approvedTransitionPhase(
  decision: ProductSnapshot["decision"],
  input: GateInput,
): TransitionPhase | null {
  if (!decision || !["approve", "override"].includes(input.action)) return null;
  if (decision.gate === 1) return "site";
  if (decision.gate === 2) return "design";
  if (decision.gate === 3) return "pilot";
  if (decision.gate === 4) {
    if (input.selected_option_id === "PROMOTE_TO_SCALE") return "scale";
    if (input.selected_option_id === "REVISE_DESIGN") return "design";
    if (input.selected_option_id === "REVISE_SITE") return "site";
    return "pilot";
  }
  if (decision.gate === 5) return "candidates";
  return null;
}

/** Poll serially after a response. A slow Runtime never accumulates overlapping GETs. */
const emptyPage = <T>(): Page<T> => ({
  items: [],
  total: 0,
  offset: 0,
  limit: 20,
});
/** Poll serially after a response. A slow Runtime never accumulates overlapping GETs. */
export class LiveProductStore implements LiveProductPort {
  protected state: LiveState = {
    connection: "loading",
    projects: emptyPage(),
    snapshot: null,
    candidates: emptyPage(),
    selectedCandidate: null,
    selectedProject: null,
    pending: false,
    error: null,
    pendingRequest: null,
  };
  private candidatePageKey = "";
  private candidatePages = new Map<string, Promise<void>>();
  private candidateDetails = new Map<string, Promise<Candidate | null>>();
  private listeners = new Set<
    (event: { type: "snapshot"; snapshot: LiveState }) => void
  >();
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  private started = false;
  private suspended = false;
  private readDenied = false;
  private readonly page =
    typeof document === "undefined" ? undefined : document;
  private readonly visibilityChanged = () => {
    clearTimeout(this.timer);
    if (
      this.started &&
      !this.stopped &&
      !this.suspended &&
      !this.readDenied &&
      !this.page?.hidden
    )
      void this.refresh();
  };
  private refreshing?: Promise<void>;
  private generation = 0;
  private projectsAt = 0;
  private commands = new Map<string, string>();
  private labCommands = new Map<string, string>();
  constructor(
    private transport: typeof fetch = (input, init) => fetch(input, init),
    private interval = 2000,
    private readonly projection: ProductProjection = { projectLimit: 20 },
  ) {
    this.page?.addEventListener("visibilitychange", this.visibilityChanged);
  }
  private nextRefreshDelay() {
    if (
      this.state.pending ||
      (this.state.pendingRequest &&
        ["accepted", "running"].includes(this.state.pendingRequest.state)) ||
      this.state.snapshot?.requests.some((request) =>
        ["accepted", "running"].includes(request.state),
      ) ||
      ["running", "incomplete"].includes(
        this.state.snapshot?.project.status || "",
      )
    )
      return this.interval;
    if (this.state.snapshot?.project.status === "awaiting_scientist")
      return 10000;
    // Finished projects are immutable until an explicit user action. A slow
    // heartbeat keeps multi-tab changes visible without a permanent 2 s poll.
    if (
      ["available", "complete", "blocked", "stopped"].includes(
        this.state.snapshot?.project.status || "",
      )
    )
      return 60000;
    return 30000;
  }
  private emit(update: Partial<LiveState>) {
    if (this.stopped) return;
    this.state = { ...this.state, ...update };
    for (const listener of this.listeners)
      listener({ type: "snapshot", snapshot: this.state });
  }
  async load() {
    await this.refresh();
    return this.state;
  }
  subscribe(cb: (event: { type: "snapshot"; snapshot: LiveState }) => void) {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  }
  dispose() {
    this.stopped = true;
    clearTimeout(this.timer);
    this.page?.removeEventListener("visibilitychange", this.visibilityChanged);
    this.listeners.clear();
  }
  /** 会话过期时暂停轮询：状态与请求编号表全部保留，等待恢复登录。 */
  pausePolling() {
    this.suspended = true;
    clearTimeout(this.timer);
  }
  resumePolling() {
    if (!this.suspended) return;
    this.suspended = false;
    if (this.started && !this.stopped && !this.page?.hidden)
      void this.refresh();
  }
  protected async api<T>(path: string, init?: RequestInit): Promise<T> {
    if (this.stopped)
      throw new Error(commonT("This workspace is no longer active."));
    const response = await this.transport("/api/v1" + path, {
      ...init,
      credentials: "same-origin",
      signal: AbortSignal.timeout(120000),
    });
    if (response.status === 401) {
      this.pausePolling();
      this.emit({ connection: "authentication-required" });
    }
    const value = await response.json().catch(() => {
      throw new ApiError(
        "invalid_response",
        commonT(
          "The service could not return valid data for now; refresh and try again later.",
        ),
        response.status,
      );
    });
    if (!response.ok) {
      if (
        (init?.method ?? "GET").toUpperCase() === "GET" &&
        needsPermissionRefresh(response.status, value?.error?.code)
      ) {
        // An inaccessible read must not leave former permissions/evidence on screen.
        // Stop automatic polling, while explicit Refresh/select can retry. A denied
        // mutation alone does not revoke read access or stop its ongoing heartbeat.
        this.generation++;
        this.readDenied = true;
        this.projectsAt = 0;
        clearTimeout(this.timer);
        this.emit({
          connection: "access-denied",
          error:
            value.error.message || commonT("Workspace access is unavailable."),
          projects: emptyPage(),
          snapshot: null,
          candidates: emptyPage(),
          selectedCandidate: null,
          candidatePhase: null,
          transitionPhase: null,
          selectedProject: null,
          pendingRequest: null,
        });
      }
      throw new ApiError(
        value.error?.code || "request_failed",
        value.error?.message || "Request failed",
        response.status,
      );
    }
    return value as T;
  }
  private post<T>(path: string, payload: unknown) {
    return this.api<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }
  private observeRequest(request: RequestState) {
    this.emit({
      pendingRequest: request,
      ...(request.state === "failed" ? { transitionPhase: null } : {}),
    });
    if (["succeeded", "failed"].includes(request.state)) {
      for (const [signature, id] of this.commands) {
        const { body } = JSON.parse(signature);
        // A completed turn may leave the same authorized step unfinished. A new
        // explicit Resume, message, or project with the same goal is a new command;
        // uncertain transport retries are not. Gate decisions stay deduplicated by
        // their revision/card binding.
        if (
          id === request.id &&
          (["resume", "message"].includes(body.action) ||
            body.title !== undefined)
        )
          this.commands.delete(signature);
      }
    }
  }
  async authenticate(token: string) {
    await this.post("/session", { token });
    this.resumePolling();
  }
  private scheduleRefresh() {
    clearTimeout(this.timer);
    if (
      this.started &&
      !this.stopped &&
      !this.suspended &&
      !this.readDenied &&
      !this.page?.hidden &&
      !this.refreshing
    ) {
      // Spread simultaneous visitors without polling faster than the base cadence.
      const delay = this.nextRefreshDelay() * (1 + Math.random() * 0.2);
      this.timer = setTimeout(() => void this.refresh(), delay);
    }
  }
  async refresh(): Promise<void> {
    if (this.stopped || this.suspended) return;
    this.started = true;
    clearTimeout(this.timer);
    if (this.refreshing) return this.refreshing;
    this.readDenied = false;
    this.refreshing = this.observe().finally(() => {
      this.refreshing = undefined;
      this.scheduleRefresh();
    });
    return this.refreshing;
  }
  private async observe() {
    const generation = this.generation;
    try {
      if (!this.projectsAt || Date.now() - this.projectsAt > 30000) {
        const projects = await this.api<Page<Project>>(
          this.projectsPath(this.state.projects.offset),
        );
        if (generation !== this.generation || this.stopped) return;
        this.projectsAt = Date.now();
        this.emit({ projects, connection: "connected", error: null });
      }
      if (
        this.state.pendingRequest &&
        ["accepted", "running"].includes(this.state.pendingRequest.state)
      ) {
        const pendingRequest = await this.api<RequestState>(
          "/requests/" + this.state.pendingRequest.id,
        );
        if (generation !== this.generation || this.stopped) return;
        this.observeRequest(pendingRequest);
      }
      const id = this.state.selectedProject;
      if (id) {
        const snapshot = await this.api<ProductSnapshot>(
          `/projects/${id}/workbench`,
        );
        if (generation !== this.generation || this.stopped) return;
        const previous = this.state.snapshot;
        const changed =
          this.state.snapshot?.revision !== snapshot.revision ||
          this.state.snapshot?.event_cursor !== snapshot.event_cursor;
        // Approval revisions remain fixed while workers update progress, requests,
        // conversation and permissions. Publish every server snapshot in both views.
        this.emit({
          snapshot,
          connection: "connected",
          error: null,
          ...(this.state.transitionPhase === snapshot.project.phase
            ? { transitionPhase: null }
            : {}),
        });
        const phaseChanged = previous?.project.phase !== snapshot.project.phase;
        const executionFinished =
          previous &&
          ["running", "incomplete"].includes(previous.project.status) &&
          !["running", "incomplete"].includes(snapshot.project.status);
        if (
          changed &&
          (this.projection.surface !== "easy" ||
            phaseChanged ||
            executionFinished ||
            !this.state.candidates.items.length)
        )
          void this.candidatePage(this.state.candidates.offset).catch(
            () => undefined,
          );
      }
    } catch (error) {
      if (generation !== this.generation || this.stopped) return;
      this.emit({
        connection:
          error instanceof ApiError && error.status === 401
            ? "authentication-required"
            : "reconnecting",
        error: String((error as Error).message),
      });
    }
  }
  async deleteProject(id: string) {
    await this.api<{ id: string; deleted: boolean; recoverable: boolean }>(
      `/projects/${id}`,
      {
        method: "DELETE",
      },
    );
    if (this.state.selectedProject === id) this.clearProject();
    this.projectsAt = 0;
    const projects = await this.api<Page<Project>>(
      this.projectsPath(this.state.projects.offset),
    );
    this.projectsAt = Date.now();
    this.emit({ projects, connection: "connected", error: null });
  }
  async artifactText(url: string) {
    if (
      !/^\/api\/v1\/(?:scopes\/[a-zA-Z0-9_-]+\/)?artifacts\/[0-9a-f]{64}$/.test(
        url,
      )
    )
      throw new ApiError("invalid_artifact", "Invalid artifact identity", 400);
    const response = await this.transport(url, {
      credentials: "same-origin",
      signal: AbortSignal.timeout(120000),
    });
    if (!response.ok)
      throw new ApiError(
        "artifact_unavailable",
        "Design YAML is unavailable",
        response.status,
      );
    return response.text();
  }
  async localizeScientific(
    passages: LocalizationPassage[],
    context: { stage: string; goal: string },
  ) {
    const response = await this.transport("/api/v1/rabbit/localize", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locale: "zh", passages, context }),
      signal: AbortSignal.timeout(120000),
    });
    const value = await response.json();
    if (!response.ok)
      throw new ApiError(
        value.error?.code || "localization_unavailable",
        value.error?.message || "学术中文转换暂不可用",
        response.status,
      );
    return value as LocalizationResult;
  }
  async renameProject(id: string, title: string) {
    const saved = await this.post<{ id: string; title: string }>(
      `/projects/${id}/title`,
      {
        title,
      },
    );
    this.emit({
      projects: {
        ...this.state.projects,
        items: this.state.projects.items.map((p) =>
          p.id === id ? { ...p, title: saved.title } : p,
        ),
      },
      snapshot:
        this.state.snapshot?.project.id === id
          ? {
              ...this.state.snapshot,
              project: { ...this.state.snapshot.project, title: saved.title },
            }
          : this.state.snapshot,
    });
  }
  private projectsPath(offset: number) {
    const surface = this.projection.surface
      ? `surface=${this.projection.surface}&`
      : "";
    return `/projects?${surface}offset=${offset}&limit=${this.projection.projectLimit}`;
  }
  async projectPage(offset: number) {
    const generation = this.generation;
    const projects = await this.api<Page<Project>>(this.projectsPath(offset));
    if (generation !== this.generation || this.stopped) return;
    this.emit({ projects });
    this.projectsAt = Date.now();
  }
  async selectProject(id: string) {
    this.generation++;
    this.readDenied = false;
    this.emit({
      selectedProject: id,
      snapshot: null,
      selectedCandidate: null,
      candidatePhase: null,
      transitionPhase: null,
      candidates: emptyPage(),
      error: null,
    });
    const generation = this.generation;
    const snapshot = await this.api<ProductSnapshot>(
      `/projects/${id}/workbench`,
    );
    if (generation !== this.generation || this.stopped) return;
    this.emit({ snapshot, connection: "connected", error: null });
    this.scheduleRefresh();
    if (this.projection.surface !== "easy") {
      await this.candidatePage(0);
      return;
    }
    const phase =
      snapshot.project.phase === "pilot"
        ? "pilot"
        : snapshot.project.phase === "scale"
          ? "scale"
          : ["candidates", "handoff"].includes(snapshot.project.phase)
            ? "candidates"
            : null;
    if (phase) {
      this.emit({ candidatePhase: phase });
      void this.candidatePage(0, phase).catch(() => undefined);
    }
  }
  clearProject() {
    this.generation++;
    this.emit({
      selectedProject: null,
      snapshot: null,
      selectedCandidate: null,
      candidatePhase: null,
      transitionPhase: null,
      candidates: emptyPage(),
      pendingRequest: null,
      error: null,
    });
  }
  private async legacyCandidatePage(offset: number) {
    const id = this.state.selectedProject,
      generation = this.generation;
    if (!id || !this.state.snapshot?.candidates.total) {
      this.emit({ candidates: emptyPage(), selectedCandidate: null });
      return;
    }
    const candidates = await this.api<Page<Candidate>>(
      `/projects/${id}/candidates?offset=${offset}&limit=20${this.projection.candidateView === "summary" ? "&view=summary" : ""}`,
    );
    if (generation !== this.generation || this.stopped) return;
    const prior = this.state.selectedCandidate?.id;
    this.emit({
      candidates,
      selectedCandidate:
        candidates.items.find((c) => c.id === prior) ??
        candidates.items[0] ??
        null,
    });
  }
  async candidatePage(
    offset: number,
    phase: "pilot" | "scale" | "candidates" = this.state.candidatePhase ||
      "candidates",
  ) {
    if (this.projection.surface !== "easy")
      return this.legacyCandidatePage(offset);
    const id = this.state.selectedProject,
      generation = this.generation;
    if (!id) {
      this.emit({
        candidates: emptyPage(),
        candidatePhase: phase,
        selectedCandidate: null,
      });
      return;
    }
    const key = `${generation}:${id}:${phase}:${offset}`;
    this.candidatePageKey = key;
    this.emit({ candidatePhase: phase });
    const pending = this.candidatePages.get(key);
    if (pending) return pending;
    const request = this.loadCandidatePage(
      id,
      generation,
      offset,
      phase,
    ).finally(() => {
      if (this.candidatePages.get(key) === request)
        this.candidatePages.delete(key);
    });
    this.candidatePages.set(key, request);
    return request;
  }
  private async loadCandidatePage(
    id: string,
    generation: number,
    offset: number,
    phase: "pilot" | "scale" | "candidates",
  ) {
    const candidates = await this.api<Page<Candidate>>(
      `/projects/${id}/candidates?offset=${offset}&limit=100&view=summary&phase=${phase}`,
    );
    if (generation !== this.generation || this.stopped) return;
    if (this.candidatePageKey !== `${generation}:${id}:${phase}:${offset}`)
      return;
    const prior =
      this.state.candidatePhase === phase
        ? this.state.selectedCandidate?.id
        : null;
    const chosen =
      candidates.items.find((c) => c.id === prior) ??
      candidates.items.find((c) => c.native_status === "pass") ??
      candidates.items[0] ??
      null;
    const retained =
      chosen &&
      this.state.candidatePhase === phase &&
      this.state.selectedCandidate?.id === chosen.id &&
      this.state.selectedCandidate.artifacts.length
        ? this.state.selectedCandidate
        : chosen;
    this.emit({
      candidates,
      candidatePhase: phase,
      selectedCandidate: retained,
    });
    if (chosen && !retained?.artifacts.length)
      void this.loadCandidateDetail(id, generation, chosen.id, phase);
  }
  async selectCandidate(id: string) {
    const candidate = this.state.candidates.items.find((c) => c.id === id);
    if (this.projection.surface !== "easy") {
      if (candidate) this.emit({ selectedCandidate: candidate });
      return;
    }
    if (!candidate || !this.state.selectedProject || !this.state.candidatePhase)
      return;
    this.emit({ selectedCandidate: candidate });
    await this.loadCandidateDetail(
      this.state.selectedProject,
      this.generation,
      id,
      this.state.candidatePhase,
    );
  }
  private async loadCandidateDetail(
    project: string,
    generation: number,
    candidate: string,
    phase: "pilot" | "scale" | "candidates",
  ) {
    const key = `${generation}:${project}:${phase}:${candidate}`;
    let request = this.candidateDetails.get(key);
    if (!request) {
      request = this.api<Page<Candidate>>(
        `/projects/${project}/candidates/${encodeURIComponent(candidate)}?offset=0&limit=1&view=full&phase=${phase}`,
      )
        .then((page) => page.items[0] ?? null)
        .finally(() => this.candidateDetails.delete(key));
      this.candidateDetails.set(key, request);
    }
    try {
      const detail = await request;
      if (
        detail &&
        generation === this.generation &&
        this.state.selectedProject === project &&
        this.state.candidatePhase === phase &&
        this.state.selectedCandidate?.id === candidate
      )
        this.emit({ selectedCandidate: detail });
      return detail;
    } catch {
      // Candidate detail and the 3D preview are optional secondary data. A
      // transient failure must not mark the live progress connection as lost.
      return null;
    }
  }
  protected async command(path: string, body: Record<string, unknown>) {
    if (this.state.pending) return;
    const signature = JSON.stringify({ path, body });
    const request_id = this.commands.get(signature) || crypto.randomUUID();
    this.commands.set(signature, request_id);
    this.emit({ pending: true, error: null });
    try {
      const request = await this.post<RequestState>(path, {
        ...body,
        request_id,
      });
      this.observeRequest(request);
      if (path === "/projects") {
        this.generation++;
        this.projectsAt = 0;
        this.emit({
          selectedProject: request.project,
          snapshot: null,
          candidates: emptyPage(),
          selectedCandidate: null,
          candidatePhase: null,
          transitionPhase: null,
        });
      }
    } catch (error) {
      this.emit({ error: (error as Error).message });
      // Keep the exact request identity for uncertain transport retries.
      if (isDefinitiveRejection(error)) this.commands.delete(signature);
      throw error;
    } finally {
      this.emit({ pending: false });
      // A poll started before the command may contain the old revision.
      await this.refreshing;
      if (!this.readDenied) await this.refresh();
    }
  }
  async createProject(
    title: string,
    goal: string,
    file?: File | null,
    source?: { pdb_id?: string; uniprot?: string },
  ) {
    if (this.state.pending) return;
    let input_id: string | undefined;
    if (file) {
      const input = await this.api<{ id: string }>(
        "/inputs?filename=" + encodeURIComponent(file.name),
        { method: "POST", body: file },
      );
      input_id = input.id;
    }
    await this.command("/projects", {
      title,
      goal,
      ...(this.projection.surface ? { surface: this.projection.surface } : {}),
      ...source,
      ...(input_id ? { input_id } : {}),
    });
  }
  async decide(input: GateInput) {
    const v = this.state.snapshot;
    if (!v?.decision || !v.capabilities.decide)
      throw new Error("Refresh the current Scientist Gate.");
    const transitionPhase = approvedTransitionPhase(v.decision, input);
    if (transitionPhase) this.emit({ transitionPhase });
    try {
      await this.command(`/projects/${v.project.id}/actions`, {
        ...input,
        revision: v.revision,
        card_id: v.decision.id,
      });
    } catch (error) {
      this.emit({ transitionPhase: null });
      throw error;
    }
  }
  private async act(action: "resume" | "message", instruction?: string) {
    const v = this.state.snapshot;
    if (!v || !v.capabilities[action])
      throw new Error(commonT("This action is not currently available."));
    await this.command(`/projects/${v.project.id}/actions`, {
      revision: v.revision,
      action,
      ...(instruction ? { instruction } : {}),
    });
  }
  async resume() {
    await this.act("resume");
  }
  async sendMessage(text: string, phase?: string) {
    const v = this.state.snapshot;
    if (!v || !v.capabilities.message)
      throw new Error(commonT("Please wait for the current answer."));
    await this.command(`/projects/${v.project.id}/actions`, {
      revision: v.revision,
      action: "message",
      instruction: text,
      ...(phase ? { viewed_phase: phase } : {}),
    });
  }
  async cancelRequest(id: string) {
    if (this.state.pending) return;
    this.emit({ pending: true, error: null });
    try {
      const request = await this.post<RequestState>(
        "/requests/" + id + "/cancel",
        {},
      );
      this.observeRequest(request);
    } catch (error) {
      this.emit({ error: (error as Error).message });
      throw error;
    } finally {
      this.emit({ pending: false });
      await this.refreshing;
      if (!this.readDenied) await this.refresh();
    }
  }
  async retryRequest(id: string) {
    if (this.state.pending) return;
    this.emit({ pending: true, error: null });
    try {
      const request = await this.post<RequestState>(
        "/requests/" + id + "/resume",
        {},
      );
      this.observeRequest(request);
    } catch (reason) {
      this.emit({ error: (reason as Error).message });
      throw reason;
    } finally {
      this.emit({ pending: false });
      await this.refreshing;
      if (!this.readDenied) await this.refresh();
    }
  }

  async labOrder() {
    const id = this.state.selectedProject;
    if (!id) throw new Error(commonT("Select a project first."));
    return this.api<ProductLabOrder>(`/projects/${id}/lab-order`);
  }

  protected async performLabOrder(
    action: "save" | "quote" | "submit",
    draft?: ProductLabOrderDraft,
    acknowledgement?: "SIMULATED_ORDER_ONLY",
  ): Promise<ProductLabOrder> {
    const id = this.state.selectedProject;
    if (!id) throw new Error(commonT("Select a project first."));
    if (this.state.pending)
      throw new Error(commonT("Please wait for the current request."));
    // Reserve the mutation before a possible GET, so rapid clicks cannot race.
    this.emit({ pending: true, error: null });
    let signature: string | undefined;
    try {
      const current = this.state.snapshot?.lab_order || (await this.labOrder());
      if (!current.capabilities[action])
        throw new Error(commonT("Refresh the current simulated order."));
      const body = {
        revision: current.revision,
        action,
        ...(draft ? { draft } : {}),
        ...(acknowledgement ? { acknowledgement } : {}),
      };
      signature = JSON.stringify({ project: id, body });
      const request_id = this.labCommands.get(signature) || crypto.randomUUID();
      this.labCommands.set(signature, request_id);
      const result = await this.post<{ order: ProductLabOrder }>(
        `/projects/${id}/lab-order`,
        {
          request_id,
          ...body,
        },
      );
      this.labCommands.delete(signature);
      if (this.state.snapshot?.project.id === id)
        this.emit({
          snapshot: { ...this.state.snapshot, lab_order: result.order },
          error: null,
        });
      return result.order;
    } catch (error) {
      this.emit({ error: (error as Error).message });
      if (signature && isDefinitiveRejection(error))
        this.labCommands.delete(signature);
      throw error;
    } finally {
      this.emit({ pending: false });
    }
  }
}
