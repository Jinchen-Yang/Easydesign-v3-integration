import fixture from '../demo/demo-fixture.json';
import reference from '../demo/structure-reference.json';
import { stages } from '../demo/stages';
import { PHASES } from './WorkbenchAdapter';
import { isLabOrderDraft, type LabOrderDraft } from '../domain/labOrder';
import type {
  Candidate,
  ConversationItem,
  DecisionState,
  WorkbenchAdapter,
  WorkbenchEdit,
  WorkbenchEvent,
  WorkbenchSnapshot,
  WorkflowPhase,
} from './WorkbenchAdapter';

export const LEGACY_STORAGE_KEY = 'easydesign-workbench-demo-v1';
export const STORAGE_KEY = 'easydesign-workbench-projects-v1';
type Persistence = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
interface DemoState {
  version: 1;
  run: number;
  started: boolean;
  completed: boolean;
  phase: WorkflowPhase;
  eventIndex: number;
  goal: string;
  selectedSite: string;
  approvedSite?: string;
  scaffold: string;
  selectedCandidate: string;
  shortlisted: string[];
  messages: ConversationItem[];
  labOrder?: LabOrderDraft;
}
interface SavedProject {
  id: string;
  title: string;
  state: DemoState;
}
interface SavedWorkspace {
  version: 1;
  nextProjectNumber: number;
  activeProjectId: string | null;
  projects: SavedProject[];
}
const initial = (run = 1): DemoState => ({
  version: 1,
  run,
  started: false,
  completed: false,
  phase: 'goal',
  eventIndex: 0,
  goal: fixture.project.goal,
  selectedSite: 'B',
  scaffold: fixture.design.scaffold,
  selectedCandidate: 'P-01',
  shortlisted: [],
  messages: [],
});

/** Deterministic, UI-only state machine. No network, LLM, CLI or compute dependencies. */
export class DemoAdapter implements WorkbenchAdapter {
  private state = initial();
  private projects: SavedProject[] = [];
  private activeProjectId: string | null = null;
  private nextProjectNumber = 1;
  private loaded = false;
  private timer?: ReturnType<typeof setTimeout>;
  private listeners = new Set<(event: WorkbenchEvent) => void>();
  private notice?: string;
  constructor(private options: { storage?: Persistence; tickMs?: number } = {}) {}

  private readSaved(): void {
    if (this.loaded) return;
    this.loaded = true;
    try {
      const saved = this.options.storage?.getItem(STORAGE_KEY);
      if (saved) {
        const workspace: unknown = JSON.parse(saved);
        if (!isValidWorkspace(workspace)) throw new Error('Invalid saved workspace');
        this.projects = workspace.projects;
        this.activeProjectId = workspace.activeProjectId;
        this.nextProjectNumber = workspace.nextProjectNumber;
        this.state = this.projects.find((p) => p.id === this.activeProjectId)?.state ?? initial();
      } else {
        // Preserve the earlier single-demo state as the first local project. Never delete it.
        const legacy = this.options.storage?.getItem(LEGACY_STORAGE_KEY);
        if (!legacy) return;
        const s: unknown = JSON.parse(legacy);
        if (!isValidState(s)) throw new Error('Invalid saved demo');
        if (s.started) {
          this.state = s;
          this.allocateProject();
        }
      }
    } catch {
      this.state = initial();
      this.projects = [];
      this.activeProjectId = null;
      this.nextProjectNumber = 1;
      this.notice = 'The saved demo could not be restored. A fresh workspace is ready.';
    }
  }
  async load(): Promise<WorkbenchSnapshot> {
    this.readSaved();
    this.schedule();
    return this.snapshot();
  }
  subscribe(cb: (event: WorkbenchEvent) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private publish(): void {
    this.saveActiveState();
    try {
      const workspace: SavedWorkspace = {
        version: 1,
        nextProjectNumber: this.nextProjectNumber,
        activeProjectId: this.activeProjectId,
        projects: this.projects,
      };
      this.options.storage?.setItem(STORAGE_KEY, JSON.stringify(workspace));
    } catch {
      this.notice = 'This browser cannot save the demo. You can still complete it in this tab.';
    }
    const event: WorkbenchEvent = { type: 'snapshot', snapshot: this.snapshot() };
    for (const listener of this.listeners) listener(event);
  }
  private saveActiveState(): void {
    const active = this.projects.find((p) => p.id === this.activeProjectId);
    if (active) active.state = this.state;
  }
  private allocateProject(): void {
    const number = this.nextProjectNumber++;
    this.activeProjectId = `demo-${number}`;
    this.projects.push({
      id: this.activeProjectId,
      title: number === 1 ? fixture.project.title : `${fixture.project.title} ${number}`,
      state: this.state,
    });
  }
  private cancel(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }
  private busy(): boolean {
    return (
      this.state.started &&
      !this.state.completed &&
      this.state.eventIndex < stages[this.state.phase].events.length
    );
  }
  private schedule(): void {
    if (!this.busy() || this.timer !== undefined) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.tick();
      this.schedule();
    }, this.options.tickMs ?? 480);
  }
  private append(item: Omit<ConversationItem, 'id' | 'phase'>): void {
    this.state.messages.push({
      ...item,
      id: `${this.activeProjectId}:${this.state.run}:${this.state.messages.length}`,
      phase: this.state.phase,
    });
  }
  private enter(phase: WorkflowPhase): void {
    this.cancel();
    this.state.phase = phase;
    this.state.eventIndex = 0;
    if (phase === 'candidates') this.state.selectedCandidate = fixture.finalists[0].id;
    if (phase === 'pilot') this.state.selectedCandidate = fixture.pilot.candidates[0].id;
    this.append({
      kind: 'summary',
      title: stages[phase].title,
      text: stages[phase].summary,
      focus: phase,
    });
  }
  private tick(): void {
    if (!this.busy()) return;
    const event = stages[this.state.phase].events[this.state.eventIndex];
    this.append({
      kind: 'tool',
      title: event.title,
      text: event.text,
      detail: event.detail,
      focus: this.state.phase,
    });
    this.state.eventIndex += 1;
    if (this.state.phase === 'goal' && !this.busy()) this.enter('target');
    this.publish();
  }
  private decision(): DecisionState | undefined {
    const s = this.state;
    if (!s.started || s.completed || this.busy() || s.phase === 'goal') return;
    const content: Partial<Record<WorkflowPhase, [string, string, string]>> = {
      target: [
        'Ready to confirm your target?',
        'Review lysozyme and the 1MEL reference before continuing.',
        'Approve target',
      ],
      site: [
        `Continue with Site ${s.selectedSite}?`,
        'Your selected demo site will anchor both design arms.',
        `Approve Site ${s.selectedSite}`,
      ],
      design: [
        'Start with a small pilot',
        'Two design arms · 4 candidates each · simulated results.',
        'Approve design',
      ],
      pilot: [
        'The pilot produced 6/8 passing candidates',
        'Promote the six passing candidates to a 24-candidate demo.',
        'Promote 6 candidates',
      ],
      scale: [
        'All 24 demo candidates reviewed',
        '18 pass · 6 filtered · 6 finalists ready to compare.',
        'Review candidates',
      ],
      candidates: [
        'Your panel is ready',
        `${fixture.finalists.length} finalists${s.shortlisted.length ? ` · ${s.shortlisted.length} starred` : ''} · simulated for UI development.`,
        'Finalize panel',
      ],
    };
    const [title, description, label] = content[s.phase]!;
    return {
      id: `${this.activeProjectId}:${s.run}:${s.phase}`,
      phase: s.phase,
      title,
      description,
      label,
    };
  }
  private snapshot(): WorkbenchSnapshot {
    const s = this.state,
      busy = this.busy(),
      phaseIndex = PHASES.indexOf(s.phase);
    const pilot: Candidate[] = fixture.pilot.candidates.map((c) => ({
      ...c,
      status: c.status as Candidate['status'],
      sequencePreview: 'QVQLV…WGQGTQVTVSS',
      length: 132,
    }));
    const finalists: Candidate[] = fixture.finalists.map(({ sequence_preview, ...c }) => ({
      ...c,
      status: 'pass',
      sequencePreview: sequence_preview,
      length: 132,
    }));
    const finishedEvents = s.eventIndex;
    return {
      version: 1,
      mode: 'demo',
      labOrder:
        s.completed &&
        isLabOrderDraft(
          s.labOrder,
          fixture.finalists.map((c) => c.id),
        )
          ? structuredClone(s.labOrder)
          : null,
      started: s.started,
      completed: s.completed,
      busy,
      phase: s.phase,
      project: {
        id: this.activeProjectId,
        title:
          this.projects.find((p) => p.id === this.activeProjectId)?.title ?? fixture.project.title,
        goal: s.goal,
        exampleGoal: fixture.project.goal,
        badge: fixture.project.badge,
      },
      projects: [...this.projects].reverse().map((p) => ({
        id: p.id,
        title: p.title,
        goal: p.state.goal,
        phase: p.state.phase,
        status: !p.state.started
          ? 'not-started'
          : p.state.completed
            ? 'complete'
            : p.state.eventIndex < stages[p.state.phase].events.length
              ? p.id === this.activeProjectId
                ? 'running'
                : 'paused'
              : 'review',
      })),
      // Read-only projection of existing demo events, not a job store or scheduler.
      compute: {
        connection: 'demo-only',
        runs: [...this.projects].reverse().flatMap((project) => {
          const state = project.id === this.activeProjectId ? s : project.state;
          return (['pilot', 'scale'] as const).flatMap((phase) => {
            if (!state.started || PHASES.indexOf(state.phase) < PHASES.indexOf(phase)) return [];
            const complete =
              PHASES.indexOf(state.phase) > PHASES.indexOf(phase) ||
              state.eventIndex >= stages[phase].events.length;
            const total = phase === 'pilot' ? fixture.pilot.candidates.length : fixture.scale.total;
            return [
              {
                id: `${project.id}:${state.run}:${phase}`,
                projectId: project.id,
                projectTitle: project.title,
                phase,
                status: complete
                  ? ('complete' as const)
                  : project.id === this.activeProjectId
                    ? ('running' as const)
                    : ('paused' as const),
                total,
                prepared: complete
                  ? total
                  : phase === 'pilot'
                    ? state.eventIndex >= 2
                      ? total
                      : 0
                    : Math.max(0, Math.min(3, state.eventIndex - 1)) * fixture.scale.batch_size,
              },
            ];
          });
        }),
      },
      tasks: PHASES.map((id, i) => ({
        id,
        label: fixture.phases[i].label,
        status:
          s.completed || i < phaseIndex
            ? 'complete'
            : i > phaseIndex
              ? 'locked'
              : this.decision()
                ? 'approval'
                : 'current',
        subtasks: stages[id].subtasks.map((label, j) => ({
          label,
          status:
            s.completed || i < phaseIndex || (i === phaseIndex && (!busy || j < finishedEvents))
              ? 'complete'
              : i === phaseIndex && j === Math.min(finishedEvents, stages[id].subtasks.length - 1)
                ? 'running'
                : 'waiting',
        })),
      })),
      messages: structuredClone(s.messages),
      specialists: stages[s.phase].specialists.map(([name, role], i) => ({
        name,
        role,
        status:
          !busy || i < finishedEvents ? 'complete' : i === finishedEvents ? 'running' : 'waiting',
      })),
      context: {
        phase: s.phase,
        structure: reference,
        sites: fixture.site_options,
        selectedSite: s.selectedSite,
        approvedSite: s.approvedSite,
        scaffold: s.scaffold,
        arms: fixture.design.arms.map((a) => ({
          id: a.id,
          label: a.label,
          count: a.pilot_candidates,
        })),
        pilotCandidates: pilot,
        finalists,
        selectedCandidate: s.selectedCandidate,
        shortlisted: [...s.shortlisted],
        scale: {
          total: fixture.scale.total,
          batches: fixture.scale.batches,
          batchSize: fixture.scale.batch_size,
          completedBatches:
            phaseIndex > PHASES.indexOf('scale')
              ? 3
              : s.phase === 'scale'
                ? Math.max(0, Math.min(3, finishedEvents - 1))
                : 0,
          passed: fixture.scale.passed,
          filtered: fixture.scale.filtered,
        },
      },
      decision: this.decision(),
      notice: this.notice,
    };
  }
  async sendMessage(text: string): Promise<void> {
    this.readSaved();
    const value = text.trim().slice(0, 2000);
    if (!value) return;
    if (!this.state.started) {
      if (!this.activeProjectId) this.allocateProject();
      this.state.started = true;
      this.state.goal = value;
      this.append({ kind: 'user', text: value });
      this.enter('goal');
    } else {
      this.append({ kind: 'user', text: value });
      this.append({
        kind: 'note',
        title: 'Design Scientist',
        text: 'Your note is recorded. This demo keeps the lysozyme/VHH target and fixed candidate budgets. You can inspect the context or use the decision bar to continue; your original research goal is preserved.',
      });
    }
    this.publish();
    this.schedule();
  }
  async createProject(goal: string): Promise<void> {
    this.readSaved();
    if (!goal.trim()) throw new Error('Add a research goal before creating a project.');
    this.cancel();
    this.saveActiveState();
    this.state = initial();
    this.allocateProject();
    this.notice = undefined;
    await this.sendMessage(goal);
  }
  async selectProject(projectId: string): Promise<void> {
    this.readSaved();
    const project = this.projects.find((p) => p.id === projectId);
    if (!project) throw new Error('This project is unavailable.');
    if (projectId === this.activeProjectId) return;
    // Only the selected demo animates. Switching cancels its timer, never schedules jobs.
    this.cancel();
    this.saveActiveState();
    this.activeProjectId = project.id;
    this.state = project.state;
    this.publish();
    this.schedule();
  }
  async renameProject(projectId: string, title: string): Promise<void> {
    this.readSaved();
    const project = this.projects.find((p) => p.id === projectId);
    if (!project || !title.trim()) throw new Error('Enter a project name.');
    project.title = title.trim().slice(0, 80);
    this.publish();
  }
  async deleteProject(projectId: string): Promise<void> {
    this.readSaved();
    if (!this.projects.some((p) => p.id === projectId))
      throw new Error('This project is unavailable.');
    this.saveActiveState();
    const projects = this.projects.filter((p) => p.id !== projectId);
    const activeId =
      projectId === this.activeProjectId ? (projects.at(-1)?.id ?? null) : this.activeProjectId;
    // Persist first so a storage failure cannot falsely report a durable deletion.
    try {
      this.options.storage?.setItem(
        STORAGE_KEY,
        JSON.stringify({
          version: 1,
          nextProjectNumber: this.nextProjectNumber,
          activeProjectId: activeId,
          projects,
        } satisfies SavedWorkspace),
      );
    } catch {
      throw new Error('Could not save the deletion. The project has been kept.');
    }
    if (projectId === this.activeProjectId) {
      this.cancel();
      this.activeProjectId = activeId;
      this.state = projects.find((p) => p.id === activeId)?.state ?? initial();
    }
    this.projects = projects;
    this.notice = undefined;
    // Do not rewrite storage twice. The retained empty collection prevents legacy re-import.
    const event: WorkbenchEvent = { type: 'snapshot', snapshot: this.snapshot() };
    for (const listener of this.listeners) listener(event);
    this.schedule();
  }
  async approve(decisionId: string): Promise<void> {
    if (this.decision()?.id !== decisionId)
      throw new Error('This decision is no longer active. Review the current step.');
    const s = this.state;
    this.append({ kind: 'note', text: `${this.decision()!.label} · confirmed by you` });
    if (s.phase === 'site') s.approvedSite = s.selectedSite;
    if (s.phase === 'candidates') {
      s.completed = true;
      this.append({
        kind: 'summary',
        title: 'A complete panel. A clear next step.',
        text: 'Your six-candidate demo panel is finalized. The entire journey remains available to review. All candidate scores and outcomes are simulated; the displayed complex is the shared 1MEL reference.',
      });
    } else this.enter(PHASES[PHASES.indexOf(s.phase) + 1]);
    this.publish();
    this.schedule();
  }
  async edit(decisionId: string, payload: WorkbenchEdit): Promise<void> {
    const s = this.state;
    if (payload.type === 'candidate' || payload.type === 'shortlist') {
      const candidates = [...fixture.pilot.candidates, ...fixture.finalists];
      if (!candidates.some((c) => c.id === payload.candidateId))
        throw new Error('Unknown candidate');
      if (payload.type === 'candidate') s.selectedCandidate = payload.candidateId;
      else
        s.shortlisted = s.shortlisted.includes(payload.candidateId)
          ? s.shortlisted.filter((id) => id !== payload.candidateId)
          : [...s.shortlisted, payload.candidateId];
    } else {
      if (this.decision()?.id !== decisionId || s.completed)
        throw new Error('This decision is no longer active.');
      if (payload.type === 'site') {
        if (s.phase !== 'site' || !fixture.site_options.some((site) => site.id === payload.siteId))
          throw new Error('Invalid site selection');
        s.selectedSite = payload.siteId;
      } else if (payload.type === 'scaffold') {
        if (s.phase !== 'design' || !payload.scaffold.trim()) throw new Error('Invalid scaffold');
        s.scaffold = payload.scaffold.trim().slice(0, 100);
      } else if (payload.type === 'revise-pilot') {
        if (s.phase !== 'pilot') throw new Error('Pilot review is not active');
        // Invalidate the old decision even if a revision returns to the same phase later.
        s.run += 1;
        this.enter('design');
      }
    }
    this.publish();
    this.schedule();
  }
  async skipAnimation(): Promise<void> {
    this.cancel();
    let guard = 0;
    while (this.busy() && guard++ < 20) this.tick();
    this.publish();
  }
  async saveLabOrder(draft: LabOrderDraft): Promise<void> {
    this.readSaved();
    if (!this.state.completed)
      throw new Error('Finalize the candidate panel before preparing a lab order.');
    if (
      !isLabOrderDraft(
        draft,
        fixture.finalists.map((c) => c.id),
      )
    )
      throw new Error('This lab draft contains invalid samples or requirements.');
    // Request preparation belongs to this project/run; it never starts a lab or compute job.
    this.state.labOrder = structuredClone(draft);
    this.publish();
  }
  async resetDemo(): Promise<void> {
    this.cancel();
    this.state = initial(this.state.run + 1);
    this.notice = undefined;
    this.loaded = true;
    this.publish();
  }
  async replayDemo(): Promise<void> {
    const goal = this.state.goal;
    await this.resetDemo();
    await this.sendMessage(goal);
  }
  dispose(): void {
    this.cancel();
    this.listeners.clear();
  }
}

function isValidState(value: unknown): value is DemoState {
  if (!value || typeof value !== 'object') return false;
  const s = value as DemoState;
  if (
    s.version !== 1 ||
    !PHASES.includes(s.phase) ||
    !Number.isInteger(s.run) ||
    s.run < 1 ||
    typeof s.started !== 'boolean' ||
    typeof s.completed !== 'boolean'
  )
    return false;
  if (
    !Number.isInteger(s.eventIndex) ||
    s.eventIndex < 0 ||
    s.eventIndex > stages[s.phase].events.length ||
    (s.completed && (s.phase !== 'candidates' || s.eventIndex !== stages.candidates.events.length))
  )
    return false;
  if (
    typeof s.goal !== 'string' ||
    s.goal.length > 2000 ||
    typeof s.scaffold !== 'string' ||
    typeof s.selectedCandidate !== 'string' ||
    !fixture.site_options.some((x) => x.id === s.selectedSite)
  )
    return false;
  if (s.approvedSite !== undefined && !fixture.site_options.some((x) => x.id === s.approvedSite))
    return false;
  if (
    !Array.isArray(s.shortlisted) ||
    !s.shortlisted.every((x) => typeof x === 'string') ||
    !Array.isArray(s.messages)
  )
    return false;
  return s.messages.every(
    (m) =>
      m &&
      typeof m.id === 'string' &&
      PHASES.includes(m.phase) &&
      ['user', 'summary', 'tool', 'note'].includes(m.kind) &&
      typeof m.text === 'string' &&
      (m.title === undefined || typeof m.title === 'string') &&
      (m.detail === undefined || typeof m.detail === 'string'),
  );
}

function isValidWorkspace(value: unknown): value is SavedWorkspace {
  if (!value || typeof value !== 'object') return false;
  const w = value as SavedWorkspace;
  if (
    w.version !== 1 ||
    !Number.isInteger(w.nextProjectNumber) ||
    w.nextProjectNumber < 1 ||
    !Array.isArray(w.projects)
  )
    return false;
  const ids = new Set<string>();
  for (const p of w.projects) {
    if (
      !p ||
      typeof p.id !== 'string' ||
      !/^demo-[1-9]\d*$/.test(p.id) ||
      Number(p.id.slice(5)) >= w.nextProjectNumber ||
      ids.has(p.id) ||
      typeof p.title !== 'string' ||
      !p.title.trim() ||
      p.title.length > 80 ||
      !isValidState(p.state)
    )
      return false;
    ids.add(p.id);
  }
  return w.activeProjectId === null ? w.projects.length === 0 : ids.has(w.activeProjectId);
}
