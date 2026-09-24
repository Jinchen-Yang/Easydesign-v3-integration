import { afterEach, describe, expect, it, vi } from 'vitest';
import { LiveWorkbenchAdapter } from '../src/adapters/LiveWorkbenchAdapter';
import type { ProductSnapshot } from '../src/live/contracts';
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
const adapters: LiveWorkbenchAdapter[] = [];
afterEach(() => {
  adapters.forEach((a) => a.dispose());
  adapters.length = 0;
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
});
