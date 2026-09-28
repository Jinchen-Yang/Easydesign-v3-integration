import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiveWorkbenchAdapter } from '../src/adapters/LiveWorkbenchAdapter';
import type { ProductLabOrder, ProductLabOrderDraft, ProductSnapshot } from '../src/live/contracts';
const project = {
  id: 'native-project',
  title: 'Native project',
  goal: 'Synthetic validation',
  phase: 'site',
  status: 'awaiting_scientist',
  thread_id: 'native-thread',
  last_activity: 12,
  validation_only: true,
};
function snapshot(): ProductSnapshot {
  return {
    schema_version: '1',
    mode: 'live',
    revision: 'a'.repeat(64),
    project,
    workflow: [{ id: 'site', label: 'Site', status: 'awaiting_scientist', gate: 2 }],
    current_action: {
      id: 'runtime-action',
      stage: 'site-review',
      message: 'Scientist decides',
      resumable: false,
    },
    specialists: [],
    scientific_context: { structure: null, sites: [], arms: [] },
    jobs: [],
    artifacts: [],
    recent_activity: [],
    tasks: [],
    lifecycle: 'scientific_project',
    event_cursor: 12,
    candidates: { total: 0, counts: {}, url: '/api/v1/projects/native-project/candidates' },
    capabilities: { decide: true },
    requests: [],
    connection: 'connected',
    decision: {
      id: 'native-card',
      gate: 2,
      type: 'site-hotspot',
      question: 'Choose a candidate',
      default_option_id: 'A',
      options: ['A', 'B', 'C'].map((id) => ({
        option_id: id,
        eligible: true,
        actions: ['approve', 'revise', 'reject'],
      })),
      warnings: ['High uncertainty'],
      limitations: [],
      action_summary: 'Choose one',
      revision_targets: ['site-hotspot'],
      review_status: 'DISCOURAGED',
      required_fields: { revise: ['instruction'] },
      summary: {},
    },
  };
}
function labOrder(): ProductLabOrder {
  return {
    schema_version: '1',
    mode: 'simulation',
    provider: 'mock-lab-v1',
    project_id: project.id,
    handoff_sha256: 'b'.repeat(64),
    handoff_status: 'validation-only-not-authorized-for-experiment',
    ordering_status: 'not-ordered',
    revision: 'c'.repeat(64),
    candidates: [
      {
        id: 'candidate-1',
        selection_class: 'primary',
        selection_rank: 1,
        sequence_length: 120,
        sequence_sha256: 'd'.repeat(64),
        sequence_ready: true,
      },
    ],
    draft: null,
    quote: null,
    receipt: null,
    capabilities: { save: true, quote: false, submit: false, real_order: false },
    disclaimer: 'Simulation only.',
  };
}
const adapters: LiveWorkbenchAdapter[] = [];
it('shows a recoverable service error instead of a JSON parse crash for proxy HTML', async () => {
  const adapter = new LiveWorkbenchAdapter(
    async () => new Response('<html>unavailable</html>', { status: 503 }),
    1_000_000,
  );
  adapters.push(adapter);
  const state = await adapter.load();
  expect(state.connection).toBe('reconnecting');
  expect(state.error).toContain('服务暂时无法返回有效数据');
  expect(state.error).not.toContain('Unexpected token');
});
afterEach(() => {
  adapters.forEach((a) => a.dispose());
  adapters.length = 0;
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function fixture(post: (body: Record<string, unknown>) => Promise<Response>) {
  let current = snapshot();
  const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const route = String(url);
    if (init?.method === 'POST') return post(JSON.parse(String(init.body)));
    if (route.endsWith('/workbench')) return Response.json(current);
    if (route.includes('/projects?'))
      return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
    return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
  });
  const adapter = new LiveWorkbenchAdapter(fetcher as typeof fetch, 1000000);
  adapters.push(adapter);
  return {
    adapter,
    fetcher,
    setCurrent: (value: ProductSnapshot) => {
      current = value;
    },
  };
}
describe('Live adapter preserves Runtime authority', () => {
  it('cancels only the selected queued request and refreshes its authoritative snapshot', async () => {
    const calls: string[] = [];
    const adapter = new LiveWorkbenchAdapter(async (url, init) => {
      calls.push(String(url));
      if (init?.method === 'POST') {
        expect(String(url)).toBe('/api/v1/requests/queued-id/cancel');
        expect(JSON.parse(String(init.body))).toEqual({});
        return Response.json({id: 'queued-id', project: 'native-project', state: 'failed', result: {code: 'queue_cancelled'}, created: 1, updated: 2});
      }
      if (String(url).endsWith('/workbench')) return Response.json(snapshot());
      return Response.json({items: [snapshot().project], total: 1, offset: 0, limit: 20});
    }, 1_000_000);
    adapters.push(adapter);
    let observed = await adapter.load();
    adapter.subscribe(event => { observed = event.snapshot; });
    await adapter.selectProject(snapshot().project.id);
    const before = calls.length;
    await adapter.cancelRequest('queued-id');
    expect(observed.pendingRequest?.result?.code).toBe('queue_cancelled');
    expect(observed.pending).toBe(false);
    expect(calls.slice(before).some(url => url.endsWith('/workbench'))).toBe(true);
  });
  it('keeps a request started in another tab on the active cadence', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const current = snapshot();
    current.requests = [
      {
        id: 'other-tab',
        project: project.id,
        state: 'accepted',
        result: null,
        created: 1,
        updated: 1,
      },
    ];
    let workbenchReads = 0;
    const adapter = new LiveWorkbenchAdapter(async (url) => {
      if (String(url).endsWith('/workbench')) {
        workbenchReads++;
        return Response.json(current);
      }
      return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
    });
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    expect(workbenchReads).toBe(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(workbenchReads).toBe(2);
  });
  it('reads the result of an explicit action even when an older poll is still in flight', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    let current = snapshot();
    current.capabilities.message = true;
    let slow = false;
    let release: ((response: Response) => void) | undefined;
    const adapter = new LiveWorkbenchAdapter(async (url, init) => {
      if (init?.method === 'POST') {
        current = { ...current, revision: 'b'.repeat(64) };
        return Response.json({ id: 'message', project: project.id, state: 'succeeded' });
      }
      if (String(url).endsWith('/workbench')) {
        if (slow) {
          slow = false;
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        }
        return Response.json(current);
      }
      return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
    });
    adapters.push(adapter);
    let observed = await adapter.load();
    adapter.subscribe((event) => {
      observed = event.snapshot;
    });
    await adapter.selectProject(project.id);
    const prior = current;
    slow = true;
    const poll = adapter.refresh();
    const action = adapter.sendMessage('Explain the uncertainty', 'site');
    await vi.advanceTimersByTimeAsync(0);
    release!(Response.json(prior));
    await Promise.all([poll, action]);
    expect(observed.snapshot?.revision).toBe('b'.repeat(64));
  });
  it('finishes a slow poll before another refresh and never rearms after disposal', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-09-29T00:00:00Z'));
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const page = Object.assign(new EventTarget(), { hidden: false });
    vi.stubGlobal('document', page);
    const current = snapshot();
    current.project = { ...project, status: 'running' };
    const fetched: string[] = [];
    let release: ((response: Response) => void) | undefined;
    let slow = false;
    const adapter = new LiveWorkbenchAdapter(async (url) => {
      fetched.push(String(url));
      if (slow)
        return new Promise<Response>((resolve) => {
          release = resolve;
        });
      return Response.json(
        String(url).endsWith('/workbench')
          ? current
          : { total: 1, offset: 0, limit: 20, items: [current.project] },
      );
    });
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    slow = true;
    const initial = fetched.length;
    await vi.advanceTimersByTimeAsync(2000);
    const refresh = adapter.refresh();
    page.hidden = true;
    page.dispatchEvent(new Event('visibilitychange'));
    page.hidden = false;
    page.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetched).toHaveLength(initial + 1);
    adapter.dispose();
    release!(Response.json(current));
    await refresh;
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetched).toHaveLength(initial + 1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each([
    ['running', 2000, 0],
    ['running', 2200, 0.5],
    ['incomplete', 2000, 0],
    ['awaiting_scientist', 10000, 0],
    ['complete', 60000, 0],
  ])('uses the %s cadence (%i ms) immediately after selection', async (status, delay, random) => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-09-29T00:00:00Z'));
    vi.spyOn(Math, 'random').mockReturnValue(Number(random));
    const current = snapshot();
    current.project = { ...project, status: String(status) };
    const fetched: string[] = [];
    const adapter = new LiveWorkbenchAdapter(async (url) => {
      fetched.push(String(url));
      return Response.json(
        String(url).endsWith('/workbench')
          ? current
          : { total: 1, offset: 0, limit: 20, items: [current.project] },
      );
    });
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    const initial = fetched.length;
    await vi.advanceTimersByTimeAsync(Number(delay) - 1);
    expect(fetched).toHaveLength(initial);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetched.at(-1)).toBe('/api/v1/projects/native-project/workbench');
    expect(fetched.length).toBeGreaterThan(initial);
  });
  it('pauses automatic polling while hidden and refreshes immediately on return', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-09-29T00:00:00Z'));
    const page = Object.assign(new EventTarget(), { hidden: false });
    vi.stubGlobal('document', page);
    const fetched: string[] = [];
    const adapter = new LiveWorkbenchAdapter(async (url) => {
      fetched.push(String(url));
      return Response.json(
        String(url).endsWith('/workbench')
          ? snapshot()
          : { total: 1, offset: 0, limit: 20, items: [project] },
      );
    });
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    const initial = fetched.length;
    page.hidden = true;
    page.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetched).toHaveLength(initial);
    page.hidden = false;
    page.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetched.at(-1)).toBe('/api/v1/projects/native-project/workbench');
    expect(fetched.length).toBeGreaterThan(initial);
    adapter.dispose();
    const disposed = fetched.length;
    page.dispatchEvent(new Event('visibilitychange'));
    await adapter.refresh();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetched).toHaveLength(disposed);
  });
  it('keeps a completed project current without polling it every two seconds', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-09-29T00:00:00Z'));
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const current = snapshot();
    current.project = { ...project, status: 'complete' };
    const fetched: string[] = [];
    const adapter = new LiveWorkbenchAdapter(async (url) => {
      fetched.push(String(url));
      return Response.json(
        String(url).endsWith('/workbench')
          ? current
          : { total: 1, offset: 0, limit: 20, items: [current.project] },
      );
    });
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    await adapter.refresh();
    const initial = fetched.length;
    await vi.advanceTimersByTimeAsync(59_999);
    expect(fetched).toHaveLength(initial);
    await vi.advanceTimersByTimeAsync(1);
    expect(fetched.at(-1)).toBe('/api/v1/projects/native-project/workbench');
    expect(fetched.length).toBeGreaterThan(initial);
  });
  it('keeps a Gate question separate from approval and preserves identity on transport retry', async () => {
    const bodies: Record<string, unknown>[] = [];
    const { adapter, setCurrent } = fixture(async (body) => {
      bodies.push(body);
      if (bodies.length === 1) throw new TypeError('Connection lost after submission');
      return Response.json({
        id: body.request_id,
        project: project.id,
        kind: 'conversation',
        state: 'succeeded',
      });
    });
    const current = snapshot();
    current.capabilities.message = true;
    setCurrent(current);
    await adapter.load();
    await adapter.selectProject(project.id);
    await expect(adapter.sendMessage('Why Site B?', 'site')).rejects.toThrow('Connection lost');
    await adapter.sendMessage('Why Site B?', 'site');
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
    expect(bodies[1]).toMatchObject({
      action: 'message',
      instruction: 'Why Site B?',
      viewed_phase: 'site',
    });
    expect(bodies[1]).not.toHaveProperty('card_id');
    expect(bodies[1]).not.toHaveProperty('selected_option_id');
    const state = await adapter.load();
    expect(state.snapshot?.decision?.id).toBe('native-card');
    expect(state.snapshot?.revision).toBe(current.revision);
    await adapter.sendMessage('What are the uncertainties?', 'site');
    expect(bodies[2].request_id).not.toBe(bodies[1].request_id);
  });
  it('forwards B without override and deduplicates simultaneous UI submission', async () => {
    let resolve!: (response: Response) => void;
    const post = vi.fn(
      (_body: Record<string, unknown>) =>
        new Promise<Response>((r) => {
          resolve = r;
        }),
    );
    const { adapter } = fixture(post);
    await adapter.load();
    await adapter.selectProject(project.id);
    const first = adapter.decide({ action: 'approve', selected_option_id: 'B' });
    await adapter.decide({ action: 'approve', selected_option_id: 'B' });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatchObject({
      action: 'approve',
      selected_option_id: 'B',
      revision: 'a'.repeat(64),
      card_id: 'native-card',
    });
    resolve(Response.json({ id: 'accepted', project: project.id, state: 'succeeded' }));
    await first;
  });
  it('reuses request identity after uncertain transport failure', async () => {
    const bodies: Record<string, unknown>[] = [];
    const { adapter } = fixture(async (body) => {
      bodies.push(body);
      if (bodies.length === 1) throw new TypeError('Connection lost');
      return Response.json({ id: body.request_id, project: project.id, state: 'succeeded' });
    });
    await adapter.load();
    await adapter.selectProject(project.id);
    await expect(adapter.decide({ action: 'approve', selected_option_id: 'C' })).rejects.toThrow(
      'Connection lost',
    );
    await adapter.decide({ action: 'approve', selected_option_id: 'C' });
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
  });
  it('refreshes a stale card without optimistically advancing workflow', async () => {
    const { adapter, setCurrent } = fixture(async () => {
      const current = snapshot();
      current.revision = 'b'.repeat(64);
      current.decision!.id = 'new-card';
      setCurrent(current);
      return Response.json(
        { error: { code: 'stale_state', message: 'Refresh this card' } },
        { status: 409 },
      );
    });
    await adapter.load();
    await adapter.selectProject(project.id);
    await expect(adapter.decide({ action: 'approve', selected_option_id: 'B' })).rejects.toThrow(
      'Refresh this card',
    );
    const state = await adapter.load();
    expect(state.snapshot?.decision?.id).toBe('new-card');
    expect(state.snapshot?.workflow[0].status).toBe('awaiting_scientist');
  });
  it('marks a lost backend as reconnecting and keeps the last honest view', async () => {
    const { adapter, fetcher } = fixture(async () => Response.json({}));
    await adapter.load();
    await adapter.selectProject(project.id);
    fetcher.mockRejectedValue(new TypeError('Offline'));
    const state = await adapter.load();
    expect(state.connection).toBe('reconnecting');
    expect(state.snapshot?.project.id).toBe(project.id);
  });
  it('allows a new explicit resume after a finished turn leaves the same Runtime step', async () => {
    const bodies: Record<string, unknown>[] = [];
    const { adapter, setCurrent } = fixture(async (body) => {
      bodies.push(body);
      return Response.json({ id: body.request_id, project: project.id, state: 'succeeded' });
    });
    const current = snapshot();
    current.decision = null;
    current.capabilities = { resume: true };
    setCurrent(current);
    await adapter.load();
    await adapter.selectProject(project.id);
    await adapter.resume();
    await adapter.resume();
    expect(bodies).toHaveLength(2);
    expect(bodies[0].request_id).not.toBe(bodies[1].request_id);
    expect(bodies[0].revision).toBe(bodies[1].revision);
  });
  it('creates a persistent project without uploading a target structure', async () => {
    const bodies: Record<string, unknown>[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const route = String(url);
      if (init?.method === 'POST' && route.endsWith('/projects')) {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return Response.json({
          id: body.request_id,
          project: 'workbench-goal-only',
          state: 'accepted',
          kind: 'create',
        });
      }
      if (route.endsWith('/workbench')) return Response.json(snapshot());
      if (route.includes('/projects?'))
        return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
      if (route.includes('/requests/'))
        return Response.json({
          id: bodies[0].request_id,
          project: 'workbench-goal-only',
          state: 'running',
          kind: 'create',
        });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new LiveWorkbenchAdapter(fetcher as typeof fetch, 1000000);
    adapters.push(adapter);
    await adapter.createProject(
      'NK2R inhibitory nanobody',
      'Please design an inhibitory nanobody against NK2R.',
    );
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).not.toHaveProperty('input_id');
    expect(bodies[0]).toMatchObject({
      title: 'NK2R inhibitory nanobody',
      goal: 'Please design an inhibitory nanobody against NK2R.',
    });
  });
  it('creates a new project when the scientist repeats the same goal', async () => {
    const bodies: Record<string, unknown>[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const route = String(url);
      if (init?.method === 'POST' && route.endsWith('/projects')) {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return Response.json({
          id: body.request_id,
          project: `workbench-goal-${bodies.length}`,
          state: 'succeeded',
          kind: 'create',
        });
      }
      if (route.endsWith('/workbench')) return Response.json(snapshot());
      if (route.includes('/projects?'))
        return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new LiveWorkbenchAdapter(fetcher as typeof fetch, 1000000);
    adapters.push(adapter);
    const title = 'NK2R inhibitory nanobody';
    const goal = 'Please design an inhibitory nanobody against NK2R.';
    await adapter.createProject(title, goal);
    await adapter.createProject(title, goal);
    expect(bodies).toHaveLength(2);
    expect(bodies[0].request_id).not.toBe(bodies[1].request_id);
  });
  it('connects the live UI to the server-owned simulated order with retry identity', async () => {
    const bodies: Record<string, unknown>[] = [];
    const { adapter, setCurrent } = fixture(async (body) => {
      bodies.push(body);
      if (bodies.length === 1) throw new TypeError('Connection lost after simulated save');
      const order = labOrder();
      order.draft = body.draft as ProductLabOrderDraft;
      order.capabilities = { save: true, quote: true, submit: false, real_order: false };
      order.revision = 'e'.repeat(64);
      return Response.json({ order });
    });
    const current = snapshot();
    current.current_action.stage = 'handoff-complete';
    current.lab_order = labOrder();
    setCurrent(current);
    await adapter.load();
    await adapter.selectProject(project.id);
    let observed = await adapter.load();
    adapter.subscribe((event) => {
      observed = event.snapshot;
    });
    const draft: ProductLabOrderDraft = {
      schema_version: '1',
      candidate_ids: ['candidate-1'],
      requirements: {
        format: 'VHH',
        amount: '1 mg',
        host: 'E. coli',
        buffer: 'PBS',
        profile: 'simulation-lab',
        preferred_date: '',
        purchase_order: '',
        sds_purity: '',
        sec_purity: '',
        endotoxin: '',
        concentration: '',
        notes: 'Simulation only.',
      },
      reviewed: true,
    };
    await expect(adapter.applyLabOrder('save', draft)).rejects.toThrow('Connection lost');
    await adapter.applyLabOrder('save', draft);
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
    expect(bodies[1]).toMatchObject({
      action: 'save',
      revision: 'c'.repeat(64),
      draft,
    });
    expect(observed.snapshot?.lab_order?.draft?.candidate_ids).toEqual(['candidate-1']);
    expect(observed.snapshot?.lab_order?.capabilities.real_order).toBe(false);
  });
});
