import type {
  Candidate,
  GateInput,
  LabOrderDraftInput,
  LabOrderView,
  LiveState,
  LocalizationPassage,
  LocalizationResult,
  Page,
  ProductSnapshot,
  Project,
  RequestState,
} from './product-contracts';
import type { EasyInput } from './contracts';
import { sequence } from './inputs';
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
  clearProject(): void;
  projectPage(offset: number): Promise<void>;
  renameProject(id: string, title: string): Promise<void>;
  deleteProject(id: string): Promise<void>;
  candidatePage(offset: number, phase?: 'pilot' | 'scale' | 'candidates'): Promise<void>;
  selectCandidate(id: string): Promise<void>;
  artifactText(url: string): Promise<string>;
  localizeScientific(
    passages: LocalizationPassage[],
    context: { stage: string; goal: string },
  ): Promise<LocalizationResult>;
  createProject(title: string, goal: string, input: EasyInput, file?: File | null): Promise<void>;
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

type TransitionPhase = NonNullable<LiveState['transitionPhase']>;

export function approvedTransitionPhase(
  decision: ProductSnapshot['decision'],
  input: GateInput,
): TransitionPhase | null {
  if (!decision || !['approve', 'override'].includes(input.action)) return null;
  if (decision.gate === 1) return 'site';
  if (decision.gate === 2) return 'design';
  if (decision.gate === 3) return 'pilot';
  if (decision.gate === 4) {
    if (input.selected_option_id === 'PROMOTE_TO_SCALE') return 'scale';
    if (input.selected_option_id === 'REVISE_DESIGN') return 'design';
    if (input.selected_option_id === 'REVISE_SITE') return 'site';
    return 'pilot';
  }
  if (decision.gate === 5) return 'candidates';
  return null;
}

/** Poll serially after a response. A slow Runtime never accumulates overlapping GETs. */
export class EasyProductAdapter implements EasyProductPort {
  private state: LiveState = {
    connection: 'loading',
    projects: emptyPage(),
    snapshot: null,
    candidates: emptyPage(),
    candidatePhase: null,
    selectedCandidate: null,
    selectedProject: null,
    pending: false,
    error: null,
    pendingRequest: null,
    transitionPhase: null,
  };
  private listeners = new Set<(event: { type: 'snapshot'; snapshot: LiveState }) => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private stopped = false;
  private refreshing?: Promise<void>;
  private generation = 0;
  private projectsAt = 0;
  private commands = new Map<string, string>();
  private labCommands = new Map<string, string>();
  private candidatePages = new Map<string, Promise<void>>();
  private candidateDetails = new Map<string, Promise<Candidate | null>>();
  constructor(
    private transport: typeof fetch = (input, init) => fetch(input, init),
    private interval = 2000,
  ) {}
  private nextRefreshDelay() {
    if (
      this.state.pending ||
      (this.state.pendingRequest &&
        ['accepted', 'running'].includes(this.state.pendingRequest.state)) ||
      ['running', 'incomplete'].includes(this.state.snapshot?.project.status || '')
    )
      return this.interval;
    if (this.state.snapshot?.project.status === 'awaiting_scientist') return 10000;
    // Finished projects are immutable until an explicit user action. A slow
    // heartbeat keeps multi-tab changes visible without a permanent 2 s poll.
    if (
      ['available', 'complete', 'blocked', 'stopped'].includes(
        this.state.snapshot?.project.status || '',
      )
    )
      return 60000;
    return 30000;
  }
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
    this.emit({
      pendingRequest: request,
      ...(['failed'].includes(request.state) ? { transitionPhase: null } : {}),
    });
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
      this.scheduleRefresh();
    });
    return this.refreshing;
  }
  private scheduleRefresh() {
    clearTimeout(this.timer);
    if (!this.stopped)
      this.timer = setTimeout(() => void this.refresh(), this.nextRefreshDelay());
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
        const previous = this.state.snapshot;
        const snapshot = await this.api<ProductSnapshot>(`/projects/${id}/workbench`);
        if (generation !== this.generation) return;
        const changed =
          previous?.revision !== snapshot.revision ||
          previous?.event_cursor !== snapshot.event_cursor ||
          previous?.project.phase !== snapshot.project.phase;
        const transitionFinished = Boolean(
          this.state.transitionPhase && snapshot.project.phase === this.state.transitionPhase,
        );
        if (
          changed ||
          transitionFinished ||
          this.state.snapshot?.project.status !== snapshot.project.status
        )
          this.emit({
            snapshot,
            connection: 'connected',
            error: null,
            ...(transitionFinished ? { transitionPhase: null } : {}),
          });
        else if (this.state.connection !== 'connected' || this.state.error !== null)
          // A successful manual/automatic refresh is itself authoritative
          // connection evidence, even when the scientific snapshot is
          // byte-for-byte unchanged.  Do not leave a stale transport error in
          // front of an otherwise healthy project.
          this.emit({ connection: 'connected', error: null });
        const phaseChanged = previous?.project.phase !== snapshot.project.phase;
        const executionFinished =
          previous != null &&
          ['running', 'incomplete'].includes(previous.project.status) &&
          !['running', 'incomplete'].includes(snapshot.project.status);
        // Candidate projection is the heaviest read in the Easy surface. It is
        // deliberately not part of the progress-poll critical path: every
        // BoltzGen event must be able to repaint the progress card immediately.
        // Refresh the list only when its population can have changed, and do so
        // in the background. Per-candidate structures are hydrated separately.
        if (
          changed &&
          (phaseChanged || executionFinished || this.state.candidates.items.length === 0)
        )
          void this.candidatePage(this.state.candidates.offset).catch(() => undefined);
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
  async deleteProject(id: string) {
    await this.api<{ id: string; deleted: boolean; recoverable: boolean }>(`/projects/${id}`, {
      method: 'DELETE',
    });
    if (this.state.selectedProject === id) this.clearProject();
    this.projectsAt = 0;
    const projects = await this.api<Page<Project>>(
      `/projects?surface=easy&offset=${this.state.projects.offset}&limit=5`,
    );
    this.projectsAt = Date.now();
    this.emit({ projects, connection: 'connected', error: null });
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
      candidatePhase: null,
      transitionPhase: null,
      error: null,
    });
    const generation = this.generation;
    const snapshot = await this.api<ProductSnapshot>(`/projects/${id}/workbench`);
    if (generation !== this.generation) return;
    this.emit({ snapshot, connection: 'connected', error: null });
    // load() may have scheduled its first idle heartbeat before a deep-linked
    // project was selected. Recalculate now so a running project starts its
    // normal live-progress cadence immediately rather than waiting 30 seconds.
    this.scheduleRefresh();
    const phase =
      snapshot.project.phase === 'pilot'
        ? 'pilot'
        : snapshot.project.phase === 'scale'
          ? 'scale'
          : ['candidates', 'handoff'].includes(snapshot.project.phase)
            ? 'candidates'
            : null;
    if (!phase) return;
    // Reserve the phase before the deferred compact read. EasyLiveApp uses this
    // marker to avoid launching a duplicate request while the shell is already
    // visible and the candidate page is still loading.
    this.emit({ candidatePhase: phase });
    // The scientific shell is useful before the candidate page and 3D viewer
    // finish loading. Do not batch the user's Open click behind that heavier read.
    setTimeout(() => {
      // Candidate rows and the 3D preview are secondary data. A transient
      // compact-page failure must not replace a healthy workbench connection
      // with a red global error; the next phase change/manual refresh retries it.
      void this.candidatePage(0, phase).catch(() => undefined);
    }, 0);
  }
  clearProject() {
    this.generation++;
    this.emit({
      selectedProject: null,
      snapshot: null,
      selectedCandidate: null,
      candidates: emptyPage(),
      candidatePhase: null,
      pendingRequest: null,
      transitionPhase: null,
      error: null,
    });
  }
  async candidatePage(offset: number, phase = this.state.candidatePhase || 'candidates') {
    const id = this.state.selectedProject,
      generation = this.generation;
    if (!id) {
      this.emit({ candidates: emptyPage(), candidatePhase: phase, selectedCandidate: null });
      return;
    }
    const key = `${generation}:${id}:${phase}:${offset}`;
    const pending = this.candidatePages.get(key);
    if (pending) return pending;
    const request = this.loadCandidatePage(id, generation, offset, phase).finally(() => {
      if (this.candidatePages.get(key) === request) this.candidatePages.delete(key);
    });
    this.candidatePages.set(key, request);
    return request;
  }
  private async loadCandidatePage(
    id: string,
    generation: number,
    offset: number,
    phase: 'pilot' | 'scale' | 'candidates',
  ) {
    const candidates = await this.api<Page<Candidate>>(
      `/projects/${id}/candidates?offset=${offset}&limit=100&view=summary&phase=${phase}`,
    );
    if (generation !== this.generation) return;
    const prior = this.state.candidatePhase === phase ? this.state.selectedCandidate?.id : null;
    const chosen =
      candidates.items.find((c) => c.id === prior) ??
      candidates.items.find((c) => c.native_status === 'pass') ??
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
    if (!candidate || !this.state.selectedProject || !this.state.candidatePhase) return;
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
    phase: 'pilot' | 'scale' | 'candidates',
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
  async artifactText(url: string) {
    if (!/^\/api\/v1\/artifacts\/[0-9a-f]{64}$/.test(url))
      throw new ApiError('invalid_artifact', 'Invalid artifact identity', 400);
    const response = await this.transport(url, {
      credentials: 'same-origin',
      signal: AbortSignal.timeout(120000),
    });
    if (!response.ok)
      throw new ApiError('artifact_unavailable', 'Design YAML is unavailable', response.status);
    return response.text();
  }
  async localizeScientific(
    passages: LocalizationPassage[],
    context: { stage: string; goal: string },
  ) {
    const response = await this.transport('/api/rabbit/localize', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locale: 'zh', passages, context }),
      signal: AbortSignal.timeout(120000),
    });
    const value = await response.json();
    if (!response.ok)
      throw new ApiError(
        value.error?.code || 'localization_unavailable',
        value.error?.message || '学术中文转换暂不可用',
        response.status,
      );
    return value as LocalizationResult;
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
          candidatePhase: null,
          selectedCandidate: null,
          transitionPhase: null,
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
  async createProject(title: string, goal: string, input: EasyInput, file?: File | null) {
    if (this.state.pending) return;
    let target_input: Record<string, unknown>;
    if (input.type === 'description') {
      target_input = { kind: 'description', description: input.text.trim() };
    } else if (input.type === 'protein-name') {
      target_input = {
        kind: 'protein-name',
        name: input.text.trim(),
        organism: input.species.trim(),
      };
    } else if (input.type === 'uniprot') {
      target_input = { kind: 'uniprot', accession: input.text.trim().toUpperCase() };
    } else if (input.type === 'pdb-id') {
      target_input = { kind: 'pdb-id', pdb_id: input.text.trim().toUpperCase() };
    } else if (input.type === 'structure' || input.type === 'sequence') {
      const upload =
        input.type === 'structure'
          ? file
          : file ||
            new Blob([`>easy-ui-target\n${sequence(input.text)}\n`], {
              type: 'text/plain;charset=utf-8',
            });
      if (!upload) throw new Error('Choose a target structure before starting the design.');
      const filename =
        input.type === 'structure' ? file!.name : file?.name || 'easy-ui-target.fasta';
      const artifact = await this.api<{ id: string }>(
        '/inputs?filename=' + encodeURIComponent(filename),
        { method: 'POST', body: upload },
      );
      target_input = { kind: input.type, artifact_id: artifact.id };
    } else {
      throw new Error('This input type is not supported by the live backend.');
    }
    await this.command('/projects', {
      title,
      goal,
      surface: 'easy',
      target_input,
    });
  }
  async decide(input: GateInput) {
    const v = this.state.snapshot;
    if (!v?.decision || !v.capabilities.decide)
      throw new Error('Refresh the current Scientist Gate.');
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
