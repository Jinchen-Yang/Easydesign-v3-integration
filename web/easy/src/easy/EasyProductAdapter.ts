import type {
  Candidate,
  GateInput,
  LabOrderDraftInput,
  LabOrderView,
  LiveState,
  Page,
  ProductSnapshot,
  Project,
  RequestState,
} from './product-contracts';
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export interface EasyProductPort {
  load(): Promise<LiveState>;
  subscribe(cb: (event: { type: 'snapshot'; snapshot: LiveState }) => void): () => void;
  dispose(): void;
  authenticate(token: string): Promise<void>;
  refresh(): Promise<void>;
  selectProject(id: string): Promise<void>;
  projectPage(offset: number): Promise<void>;
  renameProject(id: string, title: string): Promise<void>;
  candidatePage(offset: number): Promise<void>;
  selectCandidate(id: string): Promise<void>;
  createProject(title: string, goal: string, file?: File | null): Promise<void>;
  decide(input: GateInput): Promise<void>;
  resume(): Promise<void>;
  sendMessage(text: string, phase?: string): Promise<void>;
  retryRequest(id: string): Promise<void>;
  labOrder(): Promise<LabOrderView>;
  saveLabOrder(draft: LabOrderDraftInput): Promise<LabOrderView>;
  quoteLabOrder(): Promise<LabOrderView>;
  submitLabOrder(): Promise<LabOrderView>;
}
const emptyPage = <T>(): Page<T> => ({ items: [], total: 0, offset: 0, limit: 20 });
/** Poll serially after a response. A slow Runtime never accumulates overlapping GETs. */
export class EasyProductAdapter implements EasyProductPort {
  private state: LiveState = {
    connection: 'loading',
    projects: emptyPage(),
    snapshot: null,
    candidates: emptyPage(),
    selectedCandidate: null,
    selectedProject: null,
    pending: false,
    error: null,
    pendingRequest: null,
  };
  private listeners = new Set<(event: { type: 'snapshot'; snapshot: LiveState }) => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  private refreshing?: Promise<void>;
  private generation = 0;
  private projectsAt = 0;
  private commands = new Map<string, string>();
  private labCommands = new Map<string, string>();
  constructor(
    private transport: typeof fetch = (input, init) => fetch(input, init),
    private interval = 2000,
  ) {}
  private emit(update: Partial<LiveState>) {
    this.state = { ...this.state, ...update };
    for (const listener of this.listeners) listener({ type: 'snapshot', snapshot: this.state });
  }
  async load() {
    await this.refresh();
    return this.state;
  }
  subscribe(cb: (event: { type: 'snapshot'; snapshot: LiveState }) => void) {
    this.listeners.add(cb);
    return () => {
      this.listeners.delete(cb);
    };
  }
  dispose() {
    this.stopped = true;
    clearTimeout(this.timer);
    this.listeners.clear();
  }
  private async api<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.transport('/api/v1' + path, {
      ...init,
      credentials: 'same-origin',
      signal: AbortSignal.timeout(120000),
    });
    const value = await response.json();
    if (!response.ok)
      throw new ApiError(
        value.error?.code || 'request_failed',
        value.error?.message || 'Request failed',
        response.status,
      );
    return value as T;
  }
  private post<T>(path: string, payload: unknown) {
    return this.api<T>(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }
  private observeRequest(request: RequestState) {
    this.emit({ pendingRequest: request });
    if (['succeeded', 'failed'].includes(request.state)) {
      for (const [signature, id] of this.commands) {
        const { body } = JSON.parse(signature);
        // A completed turn may leave the same authorized step unfinished. A new
        // explicit Resume, message, or project with the same goal is a new command;
        // uncertain transport retries are not. Gate decisions stay deduplicated by
        // their revision/card binding.
        if (
          id === request.id &&
          (['resume', 'message'].includes(body.action) || body.title !== undefined)
        )
          this.commands.delete(signature);
      }
    }
  }
  async authenticate(token: string) {
    await this.post('/session', { token });
  }
  async refresh(): Promise<void> {
    if (this.refreshing) return this.refreshing;
    this.refreshing = this.observe().finally(() => {
      this.refreshing = undefined;
      clearTimeout(this.timer);
      if (!this.stopped) this.timer = setTimeout(() => void this.refresh(), this.interval);
    });
    return this.refreshing;
  }
  private async observe() {
    const generation = this.generation;
    try {
      if (!this.projectsAt || Date.now() - this.projectsAt > 30000) {
        const projects = await this.api<Page<Project>>(
          `/projects?surface=easy&offset=${this.state.projects.offset}&limit=5`,
        );
        if (generation !== this.generation) return;
        this.projectsAt = Date.now();
        this.emit({ projects, connection: 'connected', error: null });
      }
      if (
        this.state.pendingRequest &&
        ['accepted', 'running'].includes(this.state.pendingRequest.state)
      ) {
        const pendingRequest = await this.api<RequestState>(
          '/requests/' + this.state.pendingRequest.id,
        );
        this.observeRequest(pendingRequest);
      }
      const id = this.state.selectedProject;
      if (id) {
        const snapshot = await this.api<ProductSnapshot>(`/projects/${id}/workbench`);
        if (generation !== this.generation) return;
        const changed =
          this.state.snapshot?.revision !== snapshot.revision ||
          this.state.snapshot?.event_cursor !== snapshot.event_cursor;
        this.emit({ snapshot, connection: 'connected', error: null });
        if (changed) await this.candidatePage(this.state.candidates.offset);
      }
    } catch (error) {
      this.emit({
        connection:
          error instanceof ApiError && error.status === 401
            ? 'authentication-required'
            : 'reconnecting',
        error: String((error as Error).message),
      });
    }
  }
  async renameProject(id: string, title: string) {
    const saved = await this.post<{ id: string; title: string }>(`/projects/${id}/title`, {
      title,
    });
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
  async projectPage(offset: number) {
    this.emit({
      projects: await this.api<Page<Project>>(`/projects?surface=easy&offset=${offset}&limit=5`),
    });
  }
  async selectProject(id: string) {
    this.generation++;
    this.emit({
      selectedProject: id,
      snapshot: null,
      selectedCandidate: null,
      candidates: emptyPage(),
      error: null,
    });
    const generation = this.generation;
    const snapshot = await this.api<ProductSnapshot>(`/projects/${id}/workbench`);
    if (generation !== this.generation) return;
    this.emit({ snapshot, connection: 'connected', error: null });
    await this.candidatePage(0);
  }
  async candidatePage(offset: number) {
    const id = this.state.selectedProject,
      generation = this.generation;
    if (!id || !this.state.snapshot?.candidates.total) {
      this.emit({ candidates: emptyPage(), selectedCandidate: null });
      return;
    }
    const candidates = await this.api<Page<Candidate>>(
      `/projects/${id}/candidates?offset=${offset}&limit=20`,
    );
    if (generation !== this.generation) return;
    const prior = this.state.selectedCandidate?.id;
    this.emit({
      candidates,
      selectedCandidate:
        candidates.items.find((c) => c.id === prior) ?? candidates.items[0] ?? null,
    });
  }
  async selectCandidate(id: string) {
    const candidate = this.state.candidates.items.find((c) => c.id === id);
    if (candidate) this.emit({ selectedCandidate: candidate });
  }
  private async command(path: string, body: Record<string, unknown>) {
    if (this.state.pending) return;
    const signature = JSON.stringify({ path, body });
    const request_id = this.commands.get(signature) || crypto.randomUUID();
    this.commands.set(signature, request_id);
    this.emit({ pending: true, error: null });
    try {
      const request = await this.post<RequestState>(path, { ...body, request_id });
      this.observeRequest(request);
      if (path === '/projects') {
        this.generation++;
        this.projectsAt = 0;
        this.emit({
          selectedProject: request.project,
          snapshot: null,
          candidates: emptyPage(),
          selectedCandidate: null,
        });
      }
    } catch (error) {
      this.emit({ error: (error as Error).message });
      // Keep the exact request identity for uncertain transport retries.
      if (error instanceof ApiError && error.status < 500) this.commands.delete(signature);
      throw error;
    } finally {
      this.emit({ pending: false });
      await this.refresh();
    }
  }
  async createProject(title: string, goal: string, file?: File | null) {
    if (this.state.pending) return;
    let input_id: string | undefined;
    if (file) {
      const input = await this.api<{ id: string }>(
        '/inputs?filename=' + encodeURIComponent(file.name),
        { method: 'POST', body: file },
      );
      input_id = input.id;
    }
    await this.command('/projects', {
      title,
      goal,
      surface: 'easy',
      ...(input_id ? { input_id } : {}),
    });
  }
  async decide(input: GateInput) {
    const v = this.state.snapshot;
    if (!v?.decision || !v.capabilities.decide)
      throw new Error('Refresh the current Scientist Gate.');
    await this.command(`/projects/${v.project.id}/actions`, {
      ...input,
      revision: v.revision,
      card_id: v.decision.id,
    });
  }
  private async act(action: 'resume' | 'message', instruction?: string) {
    const v = this.state.snapshot;
    if (!v || !v.capabilities[action]) throw new Error('This action is not currently available.');
    await this.command(`/projects/${v.project.id}/actions`, {
      revision: v.revision,
      action,
      ...(instruction ? { instruction } : {}),
    });
  }
  async resume() {
    await this.act('resume');
  }
  async sendMessage(text: string, phase?: string) {
    const v = this.state.snapshot;
    if (!v || !v.capabilities.message) throw new Error('Please wait for the current answer.');
    await this.command(`/projects/${v.project.id}/actions`, {
      revision: v.revision,
      action: 'message',
      instruction: text,
      ...(phase ? { viewed_phase: phase } : {}),
    });
  }
  async retryRequest(id: string) {
    await this.post('/requests/' + id + '/resume', {});
    await this.refresh();
  }

  async labOrder() {
    const id = this.state.selectedProject;
    if (!id) throw new Error('Select a project first.');
    return this.api<LabOrderView>(`/projects/${id}/lab-order`);
  }

  private async applyLabOrder(action: 'save' | 'quote' | 'submit', draft?: LabOrderDraftInput) {
    const id = this.state.selectedProject;
    if (!id) throw new Error('Select a project first.');
    const current = this.state.snapshot?.lab_order || (await this.labOrder());
    const body = {
      revision: current.revision,
      action,
      ...(draft ? { draft } : {}),
      ...(action === 'submit' ? { acknowledgement: 'SIMULATED_ORDER_ONLY' as const } : {}),
    };
    const signature = JSON.stringify({ project: id, body });
    const request_id = this.labCommands.get(signature) || crypto.randomUUID();
    this.labCommands.set(signature, request_id);
    this.emit({ pending: true, error: null });
    try {
      const result = await this.post<{ order: LabOrderView }>(`/projects/${id}/lab-order`, {
        request_id,
        ...body,
      });
      this.labCommands.delete(signature);
      if (this.state.snapshot?.project.id === id)
        this.emit({ snapshot: { ...this.state.snapshot, lab_order: result.order }, error: null });
      return result.order;
    } catch (error) {
      this.emit({ error: (error as Error).message });
      if (error instanceof ApiError && error.status < 500) this.labCommands.delete(signature);
      throw error;
    } finally {
      this.emit({ pending: false });
    }
  }

  saveLabOrder(draft: LabOrderDraftInput) {
    return this.applyLabOrder('save', draft);
  }
  quoteLabOrder() {
    return this.applyLabOrder('quote');
  }
  submitLabOrder() {
    return this.applyLabOrder('submit');
  }
}
