import { afterEach, describe, expect, it, vi } from 'vitest';
import { EasyProductAdapter } from '../src/easy/EasyProductAdapter';
import { emptyInput } from '../src/easy/contracts';
import type { LabOrderView, ProductSnapshot } from '../src/easy/product-contracts';

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
    current_action: { id: 'action', stage: 'site-review', message: '', resumable: false },
    specialists: [],
    scientific_context: { structure: null, sites: [], arms: [] },
    jobs: [],
    artifacts: [],
    recent_activity: [],
    tasks: [],
    lifecycle: 'scientific_project',
    event_cursor: 12,
    candidates: { total: 0, counts: {}, url: '/api/v1/projects/native-project/candidates' },
    capabilities: { decide: true, message: true },
    requests: [],
    lab_order: null,
    connection: 'connected',
    decision: {
      id: 'native-card',
      gate: 2,
      type: 'site-hotspot',
      question: 'Choose a candidate',
      default_option_id: 'A',
      options: ['A', 'B', 'C'].map((option_id) => ({
        option_id,
        eligible: true,
        actions: ['approve', 'revise', 'reject'],
      })),
      warnings: [],
      limitations: [],
      action_summary: 'Choose one',
      revision_targets: ['site-hotspot'],
      review_status: null,
      required_fields: {},
      summary: {},
    },
  };
}

function labOrder(): LabOrderView {
  return {
    schema_version: '1',
    mode: 'simulation',
    provider: 'mock-lab-v1',
    project_id: project.id,
    handoff_sha256: 'b'.repeat(64),
    handoff_status: 'validation-only-not-authorized-for-experiment',
    ordering_status: 'not-ordered',
    revision: 'c'.repeat(64),
    candidates: [],
    draft: { reviewed: true },
    quote: null,
    receipt: null,
    capabilities: { save: true, quote: true, submit: false, real_order: false },
    disclaimer: 'Simulation only',
  };
}

const adapters: EasyProductAdapter[] = [];
it('shows a recoverable service error instead of a JSON parse crash for proxy HTML', async () => {
  const adapter = new EasyProductAdapter(
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
  adapters.forEach((adapter) => adapter.dispose());
  adapters.length = 0;
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function fixture(post: (path: string, body: Record<string, unknown>) => Promise<Response>) {
  const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url);
    if (init?.method === 'POST') return post(path, JSON.parse(String(init.body)));
    if (path.endsWith('/workbench')) return Response.json(snapshot());
    if (path.includes('/projects?'))
      return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
    return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
  });
  const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
  adapters.push(adapter);
  return { adapter, fetcher };
}

describe('Easy live adapter preserves Product API authority', () => {
  it('cancels only the selected queued request and reads the authoritative result', async () => {
    const { adapter, fetcher } = fixture(async (path, body) => {
      expect(path).toBe('/api/v1/requests/queued-id/cancel');
      expect(body).toEqual({});
      return Response.json({ id: 'queued-id', project: project.id, state: 'failed', result: { code: 'queue_cancelled' }, created: 1, updated: 2 });
    });
    let observed = await adapter.load();
    adapter.subscribe(event => { observed = event.snapshot; });
    await adapter.selectProject(project.id);
    const before = fetcher.mock.calls.length;
    await adapter.cancelRequest('queued-id');
    expect(observed.pendingRequest?.result?.code).toBe('queue_cancelled');
    expect(observed.pending).toBe(false);
    expect(fetcher.mock.calls.slice(before).some(([url]) => String(url).endsWith('/workbench'))).toBe(true);
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
    const adapter = new EasyProductAdapter(async (url) => {
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
    const adapter = new EasyProductAdapter(async (url, init) => {
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
    const adapter = new EasyProductAdapter(async (url) => {
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
    const adapter = new EasyProductAdapter(async (url) => {
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
    const adapter = new EasyProductAdapter(async (url) => {
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
  it('binds each Easy target kind as typed input, including pasted sequence bytes', async () => {
    const calls: { path: string; body: unknown }[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      calls.push({ path, body: init?.body });
      if (path.includes('/inputs?')) return Response.json({ id: 'f'.repeat(64) });
      if (init?.method === 'POST')
        return Response.json({ id: 'request', project: project.id, state: 'succeeded' });
      if (path.endsWith('/workbench')) return Response.json(snapshot());
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 5, items: [project] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.createTypedProject('UniProt design', 'Design a VHH.', {
      ...emptyInput(),
      type: 'uniprot',
      text: 'p21452',
    });
    await adapter.createTypedProject('Sequence design', 'Design a VHH.', {
      ...emptyInput(),
      type: 'sequence',
      text: 'ACDEFGHIKLMNPQRSTVWY',
    });
    const creates = calls
      .filter((call) => call.path.endsWith('/projects'))
      .map((call) => JSON.parse(String(call.body)));
    expect(creates[0].target_input).toEqual({ kind: 'uniprot', accession: 'P21452' });
    expect(creates[1].target_input).toEqual({ kind: 'sequence', artifact_id: 'f'.repeat(64) });
    const upload = calls.find((call) => call.path.includes('/inputs?'));
    expect(upload?.path).toContain('filename=easy-ui-target.fasta');
    expect(await (upload?.body as Blob).text()).toBe('>easy-ui-target\nACDEFGHIKLMNPQRSTVWY\n');
  });
  it('refreshes native job progress without requiring a new scientific revision', async () => {
    const current = snapshot();
    current.project = { ...project, phase: 'pilot', status: 'running' };
    current.decision = null;
    current.jobs = [
      {
        id: 'pilot-job',
        phase: 'pilot',
        status: 'running',
        resumable: false,
        validation_only: true,
      },
    ];
    const fetcher = vi.fn(async (url: string | URL | Request) =>
      String(url).endsWith('/workbench')
        ? Response.json(current)
        : Response.json({ total: 1, offset: 0, limit: 5, items: [current.project] }),
    );
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    let observed: ProductSnapshot | null = null;
    adapter.subscribe((event) => {
      observed = event.snapshot.snapshot;
    });
    await adapter.load();
    await adapter.selectProject(project.id);
    current.jobs[0].progress = {
      stage_id: '04-pilot-generation',
      status: 'running',
      completed: 2,
      total: 28,
      completed_tasks: 1,
      total_tasks: 14,
      running_tasks: 1,
      estimated_remaining_seconds: null,
      substage: 'boltzgen-generate',
      substage_label: 'Generate',
      substage_completed: 1,
      substage_total: 2,
      pipeline_step: 1,
      pipeline_steps: 5,
    };
    await adapter.refresh();
    expect((observed as ProductSnapshot | null)?.jobs[0].progress?.completed).toBe(2);
    expect((observed as ProductSnapshot | null)?.revision).toBe(current.revision);
    expect(fetcher.mock.calls.filter(([url]) => String(url).includes('/candidates'))).toHaveLength(
      0,
    );
  });
  it('dispatches database identifiers as native sources, not just natural-language hints', async () => {
    const bodies: Record<string, unknown>[] = [];
    const { adapter } = fixture(async (_path, body) => {
      bodies.push(body);
      return Response.json({ id: 'source-request', project: project.id, state: 'succeeded' });
    });
    await adapter.load();
    await adapter.createProject('PDB source', 'Review the exact structure.', null, {
      pdb_id: '1UBQ',
    });
    expect(bodies.at(-1)).toMatchObject({ pdb_id: '1UBQ', surface: 'easy' });
    await adapter.createProject('UniProt source', 'Review the exact accession.', null, {
      uniprot: 'P00698',
    });
    expect(bodies.at(-1)).toMatchObject({ uniprot: 'P00698', surface: 'easy' });
  });
  it('lists only Easy projects and marks every new Easy project explicitly', async () => {
    const calls: { path: string; body?: Record<string, unknown> }[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ path, body });
      if (init?.method === 'POST')
        return Response.json({ id: 'request', project: project.id, state: 'succeeded' });
      if (path.endsWith('/workbench')) return Response.json(snapshot());
      return Response.json({ total: 1, offset: 0, limit: 5, items: [project] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    expect(calls[0].path).toContain('/projects?surface=easy&offset=0&limit=5');
    await adapter.createProject('Easy design', 'Design an extracellular VHH.');
    expect(calls.find((call) => call.body?.title === 'Easy design')?.body).toMatchObject({
      title: 'Easy design',
      goal: 'Design an extracellular VHH.',
      surface: 'easy',
    });
  });

  it('submits the exact Gate card and deduplicates simultaneous approval', async () => {
    let resolve!: (response: Response) => void;
    const post = vi.fn(
      (_body: Record<string, unknown>) =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    );
    const { adapter } = fixture((_path, body) => post(body));
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

  it('uses a fresh idempotency identity for each explicit resume', async () => {
    const bodies: Record<string, unknown>[] = [];
    const current = snapshot();
    current.decision = null;
    current.capabilities = { resume: true };
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return Response.json({ id: body.request_id, project: project.id, state: 'succeeded' });
      }
      if (path.endsWith('/workbench')) return Response.json(current);
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    await adapter.resume();
    await adapter.resume();
    expect(bodies[0].request_id).not.toBe(bodies[1].request_id);
  });

  it('clears the selected historical project for a genuinely new design', async () => {
    const { adapter } = fixture(async () => Response.json({}));
    let selected: string | null = null;
    adapter.subscribe((event) => {
      selected = event.snapshot.selectedProject;
    });
    await adapter.load();
    await adapter.selectProject(project.id);
    expect(selected).toBe(project.id);
    adapter.clearProject();
    expect(selected).toBeNull();
  });

  it('loads the Easy summary candidate view without the unused metric payload', async () => {
    const current = snapshot();
    current.candidates.total = 1;
    const paths: string[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      const path = String(url);
      paths.push(path);
      if (path.endsWith('/workbench')) return Response.json(current);
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 5, items: [project] });
      return Response.json({ total: 1, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    expect(paths).toContain(
      '/api/v1/projects/native-project/candidates?offset=0&limit=20&view=summary',
    );
  });

  it('does not keep two-second polling after a project becomes complete', async () => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
    const timers = vi.spyOn(globalThis, 'setTimeout');
    try {
      const current = snapshot();
      current.project = { ...project, phase: 'handoff', status: 'complete' };
      const fetcher = vi.fn(async (url: string | URL | Request) => {
        const path = String(url);
        if (path.endsWith('/workbench')) return Response.json(current);
        if (path.includes('/projects?'))
          return Response.json({ total: 1, offset: 0, limit: 5, items: [current.project] });
        return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
      });
      const adapter = new EasyProductAdapter(fetcher as typeof fetch, 2000);
      adapters.push(adapter);
      await adapter.load();
      await adapter.selectProject(project.id);
      await adapter.refresh();
      expect(timers.mock.calls.some((call) => call[1] === 60000)).toBe(true);
      expect(timers.mock.calls.some((call) => call[1] === 2000)).toBe(false);
    } finally {
      timers.mockRestore();
    }
  });

  it('binds simulated-order commands to the current server revision', async () => {
    const bodies: Record<string, unknown>[] = [];
    const order = {
      schema_version: '1',
      project_id: project.id,
      revision: 'order-revision',
      status: 'ready',
      disclaimer: 'Simulation only',
      candidates: [],
      draft: null,
      quote: null,
      receipt: null,
    };
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === 'POST') {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return path.endsWith('/lab-order')
          ? Response.json({ order })
          : Response.json({ id: body.request_id, project: project.id, state: 'succeeded' });
      }
      if (path.endsWith('/lab-order')) return Response.json(order);
      if (path.endsWith('/workbench')) return Response.json(snapshot());
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    await adapter.quoteLabOrder();
    expect(bodies.at(-1)).toMatchObject({ action: 'quote', revision: 'order-revision' });
  });

  it('reuses the exact simulated-order identity after an uncertain transport failure', async () => {
    const bodies: Record<string, unknown>[] = [];
    const current = snapshot();
    current.lab_order = labOrder();
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const path = String(url);
      if (init?.method === 'POST' && path.endsWith('/lab-order')) {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        if (bodies.length === 1) throw new TypeError('Connection lost after quote');
        return Response.json({ order: labOrder() });
      }
      if (path.endsWith('/workbench')) return Response.json(current);
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 20, items: [project] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    await expect(adapter.quoteLabOrder()).rejects.toThrow('Connection lost');
    await adapter.quoteLabOrder();
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
    expect(bodies[1]).toMatchObject({ action: 'quote', revision: 'c'.repeat(64) });
  });
});
