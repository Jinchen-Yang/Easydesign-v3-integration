import { afterEach, describe, expect, it, vi } from 'vitest';
import { EasyProductAdapter } from '../src/easy/EasyProductAdapter';
import type { ProductSnapshot } from '../src/easy/product-contracts';

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
});
