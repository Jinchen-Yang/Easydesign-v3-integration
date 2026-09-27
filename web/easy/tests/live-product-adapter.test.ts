import { afterEach, describe, expect, it, vi } from 'vitest';
import { EasyProductAdapter } from '../src/easy/EasyProductAdapter';
import { emptyInput, type EasyInput } from '../src/easy/contracts';
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
    await adapter.createProject('Easy design', 'Design an extracellular VHH.', {
      ...emptyInput(),
      text: 'Design an extracellular VHH.',
    });
    expect(calls.find((call) => call.body?.title === 'Easy design')?.body).toMatchObject({
      title: 'Easy design',
      goal: 'Design an extracellular VHH.',
      surface: 'easy',
      target_input: {
        kind: 'description',
        description: 'Design an extracellular VHH.',
      },
    });
  });

  it.each([
    [
      'description',
      { text: 'Design an extracellular VHH binder.' },
      { kind: 'description', description: 'Design an extracellular VHH binder.' },
    ],
    [
      'protein-name',
      { text: 'TACR2', species: 'Homo sapiens' },
      { kind: 'protein-name', name: 'TACR2', organism: 'Homo sapiens' },
    ],
    ['uniprot', { text: 'p21452' }, { kind: 'uniprot', accession: 'P21452' }],
    ['pdb-id', { text: '9w1j' }, { kind: 'pdb-id', pdb_id: '9W1J' }],
  ] as const)(
    'binds the %s intake to the canonical typed target input',
    async (type, changes, expected) => {
      const bodies: Record<string, unknown>[] = [];
      const { adapter } = fixture(async (_path, body) => {
        bodies.push(body);
        return Response.json({ id: 'request', project: project.id, state: 'succeeded' });
      });
      await adapter.load();
      await adapter.createProject(`${type} design`, 'Design an extracellular VHH.', {
        ...emptyInput(),
        type,
        ...changes,
      } as EasyInput);
      expect(bodies.find((body) => body.title === `${type} design`)?.target_input).toEqual(
        expected,
      );
    },
  );

  it.each([
    [
      'structure',
      new File(['ATOM      1  N   ALA A   1'], 'target.pdb'),
      { kind: 'structure', artifact_id: 'f'.repeat(64) },
    ],
    ['sequence', null, { kind: 'sequence', artifact_id: 'f'.repeat(64) }],
  ] as const)(
    'uploads and binds the %s intake by immutable artifact id',
    async (type, file, expected) => {
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
      await adapter.createProject(
        `${type} design`,
        'Design an extracellular VHH.',
        {
          ...emptyInput(),
          type,
          text: type === 'sequence' ? 'ACDEFGHIKLMNPQRSTVWY' : '',
          file: file ? { name: file.name, size: file.size } : null,
        },
        file,
      );
      const create = calls.find((call) => call.path.endsWith('/projects'));
      expect(create?.body && JSON.parse(String(create.body))).toMatchObject({
        target_input: expected,
      });
      const upload = calls.find((call) => call.path.includes('/inputs?'));
      expect(upload?.path).toContain(
        type === 'structure' ? 'filename=target.pdb' : 'filename=easy-ui-target.fasta',
      );
      expect(upload?.body).toBeInstanceOf(Blob);
    },
  );

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
    await vi.waitFor(() =>
      expect(paths).toContain(
        '/api/v1/projects/native-project/candidates?offset=0&limit=100&view=summary&phase=candidates',
      ),
    );
  });

  it('loads a phase-specific candidate population for historical Pilot and Scale views', async () => {
    const current = snapshot();
    current.project = { ...project, phase: 'handoff', status: 'complete' };
    current.candidates.total = 30;
    const paths: string[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      const path = String(url);
      paths.push(path);
      if (path.endsWith('/workbench')) return Response.json(current);
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 5, items: [current.project] });
      return Response.json({ total: 0, offset: 0, limit: 100, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await adapter.load();
    await adapter.selectProject(project.id);
    await adapter.candidatePage(0, 'pilot');
    await adapter.candidatePage(0, 'scale');
    expect(paths).toContain(
      '/api/v1/projects/native-project/candidates?offset=0&limit=100&view=summary&phase=pilot',
    );
    expect(paths).toContain(
      '/api/v1/projects/native-project/candidates?offset=0&limit=100&view=summary&phase=scale',
    );
  });

  it('reads only declared immutable artifact URLs for the detailed Design YAML', async () => {
    const token = 'd'.repeat(64);
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      if (String(url) === `/api/v1/artifacts/${token}`)
        return new Response('schema_version: 1\narms: []\n', {
          headers: { 'Content-Type': 'text/plain' },
        });
      return Response.json({ total: 0, offset: 0, limit: 5, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    await expect(adapter.artifactText(`/api/v1/artifacts/${token}`)).resolves.toContain(
      'schema_version: 1',
    );
    await expect(adapter.artifactText('https://example.com/design.yaml')).rejects.toMatchObject({
      code: 'invalid_artifact',
    });
  });

  it('requests bounded academic Chinese without changing scientific source text', async () => {
    const calls: { path: string; body: Record<string, unknown> }[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      calls.push({ path: String(url), body: JSON.parse(String(init?.body)) });
      return Response.json({
        locale: 'zh-CN',
        source_sha256: 'e'.repeat(64),
        items: { 'site.why': 'ECL2 邻近残基 273。' },
      });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    const passages = [{ id: 'site.why', text: 'ECL2 is near residue 273.' }];
    const result = await adapter.localizeScientific(passages, {
      stage: 'Site',
      goal: 'NK2R VHH',
    });
    expect(result.items['site.why']).toContain('273');
    expect(calls[0]).toEqual({
      path: '/api/rabbit/localize',
      body: {
        locale: 'zh',
        passages,
        context: { stage: 'Site', goal: 'NK2R VHH' },
      },
    });
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

  it('clears a stale transport error after an unchanged snapshot refresh succeeds', async () => {
    let failWorkbench = false;
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      const path = String(url);
      if (path.endsWith('/workbench')) {
        if (failWorkbench) throw new TypeError('Temporary connection failure');
        return Response.json(snapshot());
      }
      if (path.includes('/projects?'))
        return Response.json({ total: 1, offset: 0, limit: 5, items: [project] });
      return Response.json({ total: 0, offset: 0, limit: 20, items: [] });
    });
    const adapter = new EasyProductAdapter(fetcher as typeof fetch, 1_000_000);
    adapters.push(adapter);
    let current = await adapter.load();
    adapter.subscribe((event) => {
      current = event.snapshot;
    });
    await adapter.selectProject(project.id);
    failWorkbench = true;
    await adapter.refresh();
    expect(current.connection).toBe('reconnecting');
    expect(current.error).toContain('Temporary connection failure');

    failWorkbench = false;
    await adapter.refresh();
    expect(current.connection).toBe('connected');
    expect(current.error).toBeNull();
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
