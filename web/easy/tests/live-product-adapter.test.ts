import { afterEach, describe, expect, it, vi } from 'vitest';
import { EasyProductAdapter } from '../src/easy/EasyProductAdapter';
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
