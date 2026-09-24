import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DemoAdapter, STORAGE_KEY, LEGACY_STORAGE_KEY } from '../src/adapters/DemoAdapter';
import { DshAdapter, DSH_PHASE_MAPPING } from '../src/adapters/DshAdapter';
import type { WorkbenchSnapshot } from '../src/adapters/WorkbenchAdapter';
import { createLabOrderDraft, labProgress } from '../src/domain/labOrder';

class MemoryStorage {
  data = new Map<string, string>();
  getItem(k: string) {
    return this.data.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.data.set(k, v);
  }
  removeItem(k: string) {
    this.data.delete(k);
  }
}
let adapters: DemoAdapter[];
beforeEach(() => {
  vi.useFakeTimers();
  adapters = [];
});
afterEach(() => {
  adapters.forEach((a) => a.dispose());
  vi.useRealTimers();
  vi.restoreAllMocks();
});
function create(storage = new MemoryStorage()) {
  const a = new DemoAdapter({ storage, tickMs: 480 });
  adapters.push(a);
  return a;
}
async function begin(a: DemoAdapter) {
  await a.load();
  await a.sendMessage('Design my lysozyme VHH binder.');
  await a.skipAnimation();
  return a.load();
}
async function next(a: DemoAdapter) {
  const s = await a.load();
  await a.approve(s.decision!.id);
  await a.skipAnimation();
  return a.load();
}
async function to(a: DemoAdapter, phase: WorkbenchSnapshot['phase']) {
  let s = await begin(a);
  while (s.phase !== phase) s = await next(a);
  return s;
}

describe('deterministic workbench contract', () => {
  it('keeps lab preparation behind finalization and rejects unknown or duplicate samples', async () => {
    const a = create();
    let s = await to(a, 'candidates');
    const ids = s.context.finalists.map((candidate) => candidate.id);
    const draft = createLabOrderDraft(ids, ['P-01', ids[2]]);
    expect(draft.candidateIds).toEqual([ids[2]]);
    await expect(a.saveLabOrder(draft)).rejects.toThrow('Finalize');
    await a.approve(s.decision!.id);
    await expect(a.saveLabOrder({ ...draft, candidateIds: ['P-01'] })).rejects.toThrow('invalid');
    await expect(a.saveLabOrder({ ...draft, candidateIds: [ids[2], ids[2]] })).rejects.toThrow(
      'invalid',
    );
    await a.saveLabOrder(draft);
    s = await a.load();
    expect(s.labOrder).toEqual(draft);
    expect(s.phase).toBe('candidates');
    expect(s.completed).toBe(true);
    expect(s.compute.runs).toHaveLength(2);
    s.labOrder!.candidateIds.length = 0;
    expect((await a.load()).labOrder!.candidateIds).toEqual([ids[2]]);
    expect(labProgress({ ...draft, reviewed: true }).review).toBe(false);
  });

  it('persists independent lab drafts through project switching and reload, and clears only the replayed project', async () => {
    const storage = new MemoryStorage();
    const a = create(storage);
    let s = await to(a, 'candidates');
    await a.approve(s.decision!.id);
    const firstId = s.project.id!;
    const first = createLabOrderDraft(s.context.finalists.map((c) => c.id));
    first.requirements.amount = '2 mg';
    first.requirements.notes = 'First-project packaging';
    first.step = 'requirements';
    await a.saveLabOrder(first);
    await a.createProject('Second lab project');
    await a.skipAnimation();
    s = await a.load();
    while (!s.completed) s = await next(a);
    const secondId = s.project.id!;
    const second = createLabOrderDraft(
      s.context.finalists.map((c) => c.id),
      ['ED-003'],
    );
    second.requirements.amount = '5 mg';
    await a.saveLabOrder(second);
    await a.selectProject(firstId);
    expect((await a.load()).labOrder).toEqual(first);
    const restored = create(storage);
    expect((await restored.load()).labOrder).toEqual(first);
    await restored.replayDemo();
    expect((await restored.load()).labOrder).toBeNull();
    await restored.selectProject(secondId);
    expect((await restored.load()).labOrder).toEqual(second);
  });

  it('loads older projects and contains damaged lab drafts without discarding the scientific panel', async () => {
    const storage = new MemoryStorage();
    const a = create(storage);
    const s = await to(a, 'candidates');
    await a.approve(s.decision!.id);
    expect((await create(storage).load()).labOrder).toBeNull();
    const workspace = JSON.parse(storage.getItem(STORAGE_KEY)!);
    workspace.projects[0].state.labOrder = {
      version: 1,
      candidateIds: ['made-up'],
      requirements: null,
    };
    storage.setItem(STORAGE_KEY, JSON.stringify(workspace));
    const restored = await create(storage).load();
    expect(restored.completed).toBe(true);
    expect(restored.context.finalists).toHaveLength(6);
    expect(restored.labOrder).toBeNull();
    expect(restored.notice).toBeUndefined();
  });
  it('projects compute activity only after design approval and preserves paused runs across projects', async () => {
    const storage = new MemoryStorage();
    const a = create(storage);
    let s = await to(a, 'design');
    expect(s.compute).toEqual({ connection: 'demo-only', runs: [] });
    await a.approve(s.decision!.id);
    s = await a.load();
    const firstId = s.project.id!;
    expect(s.compute.runs).toHaveLength(1);
    expect(s.compute.runs[0]).toMatchObject({
      projectId: firstId,
      phase: 'pilot',
      status: 'running',
      prepared: 0,
      total: 8,
    });
    await vi.advanceTimersByTimeAsync(960);
    expect((await a.load()).compute.runs[0]).toMatchObject({ status: 'running', prepared: 8 });
    await a.createProject('A separate project');
    expect((await a.load()).compute.runs[0]).toMatchObject({
      projectId: firstId,
      status: 'paused',
    });
    await a.renameProject(firstId, 'First pilot');
    expect((await a.load()).compute.runs[0].projectTitle).toBe('First pilot');
    await a.selectProject(firstId);
    await a.skipAnimation();
    s = await a.load();
    expect(s.compute.runs[0]).toMatchObject({ status: 'complete', prepared: 8 });
    await a.approve(s.decision!.id);
    await vi.advanceTimersByTimeAsync(960);
    expect((await a.load()).compute.runs[1]).toMatchObject({
      phase: 'scale',
      status: 'running',
      prepared: 8,
      total: 24,
    });
    await a.skipAnimation();
    const saved = storage.getItem(STORAGE_KEY);
    s = await a.load();
    expect(s.compute.runs[1]).toMatchObject({ status: 'complete', prepared: 24 });
    expect(storage.getItem(STORAGE_KEY)).toBe(saved);
    a.dispose();
    expect((await create(storage).load()).compute).toEqual(s.compute);
  });

  it('replay and reset remove only the selected project’s current demo activity', async () => {
    const a = create();
    let s = await to(a, 'scale');
    const firstId = s.project.id!;
    await a.createProject('Second pilot');
    await a.skipAnimation();
    for (let i = 0; i < 3; i++) s = await next(a);
    expect(s.phase).toBe('pilot');
    expect(s.compute.runs).toHaveLength(3);
    await a.replayDemo();
    s = await a.load();
    expect(s.compute.runs).toHaveLength(2);
    expect(s.compute.runs.every((run) => run.projectId === firstId)).toBe(true);
    await a.selectProject(firstId);
    await a.resetDemo();
    s = await a.load();
    expect(s.projects).toHaveLength(2);
    expect(s.compute.runs).toEqual([]);
  });

  it('completes all seven phases with exactly 8 / 24 / 6 and explicit decisions', async () => {
    const a = create();
    let s = await begin(a);
    expect(s.phase).toBe('target');
    expect(s.decision?.label).toBe('Approve target');
    expect(s.tasks.map((t) => t.label)).toEqual([
      'Goal',
      'Target',
      'Site',
      'Design',
      'Pilot',
      'Scale',
      'Candidates',
    ]);
    s = await next(a);
    expect(s.phase).toBe('site');
    expect(s.context.selectedSite).toBe('B');
    s = await next(a);
    expect(s.phase).toBe('design');
    expect(s.context.approvedSite).toBe('B');
    expect(s.context.arms.map((x) => x.count)).toEqual([4, 4]);
    s = await next(a);
    expect(s.context.pilotCandidates).toHaveLength(8);
    expect(s.context.pilotCandidates.filter((x) => x.status === 'pass')).toHaveLength(6);
    s = await next(a);
    expect(s.phase).toBe('scale');
    expect(s.context.scale).toMatchObject({
      total: 24,
      completedBatches: 3,
      passed: 18,
      filtered: 6,
    });
    s = await next(a);
    expect(s.phase).toBe('candidates');
    expect(s.context.finalists).toHaveLength(6);
    expect(s.completed).toBe(false);
    await a.approve(s.decision!.id);
    s = await a.load();
    expect(s.completed).toBe(true);
    expect(s.decision).toBeUndefined();
    expect(s.tasks.every((t) => t.status === 'complete')).toBe(true);
  });
  it('will not advance without approval or accept duplicate/stale decisions', async () => {
    const a = create();
    const s = await begin(a);
    await vi.advanceTimersByTimeAsync(20000);
    expect((await a.load()).phase).toBe('target');
    await a.approve(s.decision!.id);
    await expect(a.approve(s.decision!.id)).rejects.toThrow('no longer active');
    await expect(a.approve('invented')).rejects.toThrow();
  });
  it('emits timed specialist/tool progress then pauses within three seconds', async () => {
    const a = create();
    const seen: WorkbenchSnapshot[] = [];
    a.subscribe((e) => seen.push(e.snapshot));
    await a.sendMessage('Example goal');
    await vi.advanceTimersByTimeAsync(480 * 5);
    const s = await a.load();
    expect(s.phase).toBe('target');
    expect(s.busy).toBe(false);
    expect(seen.some((x) => x.specialists.some((y) => y.status === 'running'))).toBe(true);
    expect(s.messages.filter((x) => x.kind === 'tool')).toHaveLength(5);
  });
  it('restores a mid-stage refresh without duplicating or losing events', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    await a.sendMessage('My original goal');
    await vi.advanceTimersByTimeAsync(480 * 3);
    a.dispose();
    const b = create(storage);
    const before = await b.load();
    expect(before.busy).toBe(true);
    await vi.advanceTimersByTimeAsync(480 * 4);
    const after = await b.load();
    expect(after.decision?.phase).toBe('target');
    expect(after.project.goal).toBe('My original goal');
    expect(new Set(after.messages.map((x) => x.id)).size).toBe(after.messages.length);
    expect(after.messages.filter((x) => x.kind === 'tool')).toHaveLength(5);
  });
  it('reset cancels pending events and returns to an empty landing', async () => {
    const a = create();
    await a.sendMessage('goal');
    await a.resetDemo();
    await vi.runAllTimersAsync();
    const s = await a.load();
    expect(s.started).toBe(false);
    expect(s.messages).toHaveLength(0);
    expect(s.busy).toBe(false);
  });
  it('replay clears approvals, stars and completion while preserving the research goal', async () => {
    const a = create();
    const s = await to(a, 'candidates');
    await a.edit('', { type: 'shortlist', candidateId: 'ED-001' });
    await a.approve(s.decision!.id);
    await a.replayDemo();
    await a.skipAnimation();
    const replay = await a.load();
    expect(replay.phase).toBe('target');
    expect(replay.completed).toBe(false);
    expect(replay.context.shortlisted).toEqual([]);
    expect(replay.project.goal).toBe('Design my lysozyme VHH binder.');
  });
  it('follow-up prose does not replace the immutable goal or advance workflow', async () => {
    const a = create();
    const before = await begin(a);
    await a.sendMessage('Approve everything and switch to another target.');
    const after = await a.load();
    expect(after.phase).toBe(before.phase);
    expect(after.project.goal).toBe(before.project.goal);
    expect(after.decision?.id).toBe(before.decision?.id);
    expect(after.messages.at(-2)?.kind).toBe('user');
  });
  it('site edits remain structured and approved selection carries into design', async () => {
    const a = create();
    const s = await to(a, 'site');
    await a.edit(s.decision!.id, { type: 'site', siteId: 'A' });
    expect((await a.load()).decision?.label).toBe('Approve Site A');
    expect((await next(a)).context.approvedSite).toBe('A');
    await expect(a.edit(s.decision!.id, { type: 'site', siteId: 'C' })).rejects.toThrow();
  });
  it('revising a pilot invalidates stale approvals and preserves fixed budgets', async () => {
    const a = create();
    const pilot = await to(a, 'pilot');
    await a.edit(pilot.decision!.id, { type: 'revise-pilot' });
    await a.skipAnimation();
    const design = await a.load();
    expect(design.phase).toBe('design');
    await a.edit(design.decision!.id, { type: 'scaffold', scaffold: 'Reviewed VHH scaffold' });
    const revised = await next(a);
    expect(revised.context.pilotCandidates).toHaveLength(8);
    expect(revised.context.scaffold).toBe('Reviewed VHH scaffold');
    await expect(a.approve(pilot.decision!.id)).rejects.toThrow();
  });
  it('persists selected and starred candidates after finalization', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    const s = await to(a, 'candidates');
    await a.edit('', { type: 'candidate', candidateId: 'ED-003' });
    await a.edit('', { type: 'shortlist', candidateId: 'ED-003' });
    await a.approve(s.decision!.id);
    a.dispose();
    const restored = await create(storage).load();
    expect(restored.completed).toBe(true);
    expect(restored.context.selectedCandidate).toBe('ED-003');
    expect(restored.context.shortlisted).toEqual(['ED-003']);
  });
  it.each(['bad JSON', '{"version":999}', '{"version":1,"phase":"execute-gpu"}'])(
    'recovers safely from malformed persistence: %s',
    async (saved) => {
      const storage = new MemoryStorage();
      storage.setItem(STORAGE_KEY, saved);
      const a = create(storage);
      const s = await a.load();
      expect(s.started).toBe(false);
      expect(s.notice).toContain('fresh');
      await begin(a);
      expect((await a.load()).phase).toBe('target');
    },
  );
  it('works when browser storage is unavailable', async () => {
    const a = new DemoAdapter({
      storage: {
        getItem() {
          throw Error('denied');
        },
        setItem() {
          throw Error('denied');
        },
        removeItem() {},
      },
    });
    adapters.push(a);
    const s = await to(a, 'candidates');
    await a.approve(s.decision!.id);
    expect((await a.load()).completed).toBe(true);
  });
  it('never calls a network endpoint to complete the demo', async () => {
    const network = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new Error('No network allowed'));
    const a = create();
    const s = await to(a, 'candidates');
    await a.approve(s.decision!.id);
    expect(network).not.toHaveBeenCalled();
  });
  it('DSH boundary fails explicitly and retains all product phase mappings', async () => {
    const dsh = new DshAdapter();
    await expect(dsh.load()).rejects.toThrow('not configured');
    await expect(dsh.approve('fake')).rejects.toThrow('not configured');
    expect(Object.keys(DSH_PHASE_MAPPING)).toHaveLength(7);
  });
});

describe('independent demo projects', () => {
  it('deletes only the selected project and its runs/lab draft while retaining the other project through reload', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    let first = await to(a, 'candidates');
    first = await next(a);
    await a.saveLabOrder(
      createLabOrderDraft(
        first.context.finalists.map((c) => c.id),
        [],
      ),
    );
    await a.createProject('Keep this original goal');
    await a.skipAnimation();
    const second = await a.load();
    await a.deleteProject(first.project.id!);
    const after = await create(storage).load();
    expect(after.projects.map((p) => p.id)).toEqual([second.project.id]);
    expect(after.messages).toEqual(second.messages);
    expect(after.compute.runs).toEqual([]);
    expect(after.labOrder).toBeNull();
    expect(after.project.goal).toBe('Keep this original goal');
    await expect(a.selectProject(first.project.id!)).rejects.toThrow();
  });
  it('deletes an active animation and the final project without resurrecting legacy data or reusing ids', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    const first = await begin(a);
    const legacy = JSON.stringify(JSON.parse(storage.getItem(STORAGE_KEY)!).projects[0].state);
    storage.setItem(LEGACY_STORAGE_KEY, legacy);
    await a.createProject('Active animation');
    const second = await a.load();
    await a.deleteProject(second.project.id!);
    await vi.advanceTimersByTimeAsync(5000);
    expect((await a.load()).messages).toEqual(first.messages);
    await a.deleteProject(first.project.id!);
    await vi.advanceTimersByTimeAsync(5000);
    a.dispose();
    const restored = create(storage);
    expect((await restored.load()).projects).toEqual([]);
    expect((await restored.load()).started).toBe(false);
    await restored.createProject('Fresh project');
    expect((await restored.load()).project.id).toBe('demo-3');
    expect(storage.getItem(LEGACY_STORAGE_KEY)).toBe(legacy);
  });
  it('retains project data when deletion cannot be saved', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    const before = await begin(a);
    vi.spyOn(storage, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    await expect(a.deleteProject(before.project.id!)).rejects.toThrow('has been kept');
    expect((await a.load()).projects).toEqual(before.projects);
    await expect(a.deleteProject('missing')).rejects.toThrow();
  });
  it('keeps goals, notes, approvals and choices independent across projects and refresh', async () => {
    const storage = new MemoryStorage(),
      a = create(storage);
    const first = await to(a, 'site');
    const firstId = first.project.id!;
    await a.edit(first.decision!.id, { type: 'site', siteId: 'C' });
    await a.sendMessage('Only the first project has this note.');
    await a.renameProject(firstId, 'Compact epitope');
    const firstSaved = await a.load();
    await a.createProject('Explore an independent VHH design.');
    await a.skipAnimation();
    const second = await a.load();
    expect(second.projects).toHaveLength(2);
    expect(second.project.id).not.toBe(firstId);
    expect(second.phase).toBe('target');
    expect(second.context.selectedSite).toBe('B');
    expect(second.messages.some((m) => m.text.includes('Only the first'))).toBe(false);
    await a.renameProject(second.project.id!, 'VHH exploration');
    await a.selectProject(firstId);
    const restored = await a.load();
    expect(restored.project.title).toBe('Compact epitope');
    expect(restored.project.goal).toBe(firstSaved.project.goal);
    expect(restored.context.selectedSite).toBe('C');
    expect(restored.messages).toEqual(firstSaved.messages);
    expect(restored.decision?.label).toBe('Approve Site C');
    a.dispose();
    const refreshed = create(storage);
    expect((await refreshed.load()).project.id).toBe(firstId);
    await refreshed.selectProject(second.project.id!);
    expect((await refreshed.load()).project).toMatchObject({
      title: 'VHH exploration',
      goal: 'Explore an independent VHH design.',
    });
  });
  it('binds decisions to a project even when two projects are at the same phase and run', async () => {
    const a = create();
    const first = await begin(a);
    await a.createProject('Another target review');
    await a.skipAnimation();
    const second = await a.load();
    expect(first.decision?.id).not.toBe(second.decision?.id);
    await expect(a.approve(first.decision!.id)).rejects.toThrow('no longer active');
    await a.selectProject(first.project.id!);
    await expect(a.approve(second.decision!.id)).rejects.toThrow('no longer active');
    await a.approve(first.decision!.id);
    expect((await a.load()).phase).toBe('site');
  });
  it('pauses the inactive animation and resumes without cross-project events or duplicates', async () => {
    const a = create();
    await a.createProject('First animated project');
    await vi.advanceTimersByTimeAsync(480);
    const first = await a.load();
    await a.createProject('Second animated project');
    await vi.advanceTimersByTimeAsync(480 * 8);
    const second = await a.load();
    expect(second.projects.find((p) => p.id === first.project.id)?.status).toBe('paused');
    await a.selectProject(first.project.id!);
    expect((await a.load()).messages).toEqual(first.messages);
    await vi.advanceTimersByTimeAsync(480 * 8);
    const resumed = await a.load();
    expect(resumed.phase).toBe('target');
    expect(resumed.messages.filter((m) => m.kind === 'tool')).toHaveLength(5);
    expect(new Set(resumed.messages.map((m) => m.id)).size).toBe(resumed.messages.length);
    expect(resumed.messages.some((m) => m.text === 'Second animated project')).toBe(false);
  });
  it('replays and resets only the selected project, retaining another finalized panel', async () => {
    const a = create();
    const first = await to(a, 'candidates');
    await a.edit('', { type: 'shortlist', candidateId: 'ED-002' });
    await a.approve(first.decision!.id);
    await a.createProject('Second project to reset');
    await a.skipAnimation();
    const secondId = (await a.load()).project.id!;
    await a.replayDemo();
    await a.skipAnimation();
    expect((await a.load()).project.id).toBe(secondId);
    await a.resetDemo();
    expect((await a.load()).started).toBe(false);
    await a.selectProject(first.project.id!);
    const restored = await a.load();
    expect(restored.completed).toBe(true);
    expect(restored.context.shortlisted).toEqual(['ED-002']);
    expect(restored.projects).toHaveLength(2);
  });
  it('imports the legacy single demo once without changing its original stored bytes', async () => {
    const source = new MemoryStorage(),
      seed = create(source);
    const snapshot = await to(seed, 'site');
    await seed.edit(snapshot.decision!.id, { type: 'site', siteId: 'A' });
    const legacy = JSON.stringify(JSON.parse(source.getItem(STORAGE_KEY)!).projects[0].state);
    const storage = new MemoryStorage();
    storage.setItem(LEGACY_STORAGE_KEY, legacy);
    const a = create(storage);
    expect((await a.load()).context.selectedSite).toBe('A');
    expect((await a.load()).projects).toHaveLength(1);
    await a.createProject('New independent project');
    expect(storage.getItem(LEGACY_STORAGE_KEY)).toBe(legacy);
    a.dispose();
    const restored = await create(storage).load();
    expect(restored.projects).toHaveLength(2);
    expect(restored.project.goal).toBe('New independent project');
  });
  it('rejects invalid project operations without disturbing the active project', async () => {
    const a = create();
    const before = await begin(a);
    await expect(a.createProject('  ')).rejects.toThrow();
    await expect(a.selectProject('missing')).rejects.toThrow();
    await expect(a.renameProject(before.project.id!, '  ')).rejects.toThrow();
    expect((await a.load()).project).toEqual(before.project);
    expect((await a.load()).decision).toEqual(before.decision);
  });
});
