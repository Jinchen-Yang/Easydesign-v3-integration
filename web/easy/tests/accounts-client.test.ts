import { describe, expect, it, vi } from 'vitest';
import {
  AccountApiError, accountApi, draftsApi, fetchFinalDesignsOverview, scopedProductPath,
  scopeDecisionLinks, scopeProductUrl, scopedTransport, type AccountScope, type AccountSession,
  type ProjectDraft,
} from '../../shared/account-client';

const session: AccountSession = {
  user: {
    id: 'user-a', username: 'alice', display_name: 'Alice', role: 'user',
    status: 'active', must_change_password: false,
  },
  csrf_token: 'csrf-1',
  scopes: [{
    id: 'team-1', kind: 'team', name: 'Antibodies', role: 'member', can_edit: true, can_execute: false,
  }],
  invitations: [],
};

describe('scoped product paths', () => {
  it('rewrites product API paths and the rabbit chat endpoint into the scope', () => {
    expect(scopedProductPath('team-1', '/api/v1/projects?surface=easy')).toBe(
      '/api/v1/scopes/team-1/projects?surface=easy',
    );
    expect(scopedProductPath('team-1', '/api/rabbit/chat')).toBe('/api/v1/scopes/team-1/rabbit/chat');
  });
  it('never double-scopes or rewrites foreign paths', () => {
    expect(scopedProductPath('team-1', '/api/v1/scopes/team-2/projects')).toBe(
      '/api/v1/scopes/team-2/projects',
    );
    expect(scopedProductPath('team-1', '/easy/')).toBe('/easy/');
    expect(scopedProductPath('team-1', '/api/compute/resources')).toBe('/api/compute/resources');
  });
  it('scopes declared link fields like decision.details_url but leaves other URLs intact', () => {
    expect(scopeProductUrl('team-1', '/api/v1/projects/p1/decisions/d1')).toBe(
      '/api/v1/scopes/team-1/projects/p1/decisions/d1',
    );
    expect(scopeProductUrl('team-1', 'https://example.org/external')).toBe('https://example.org/external');
    expect(scopeProductUrl('team-1', undefined)).toBeUndefined();
    const snapshot = scopeDecisionLinks(
      {revision: 3, decision: {gate: 2, details_url: '/api/v1/projects/p1/review'}},
      'team-1',
    );
    expect(snapshot.decision?.details_url).toBe('/api/v1/scopes/team-1/projects/p1/review');
    expect(snapshot.revision).toBe(3);
    // No copy when there is nothing to project.
    const untouched = {decision: {gate: 1, details_url: 'https://pubs.example/x'}};
    expect(scopeDecisionLinks(untouched, 'team-1')).toBe(untouched);
  });
});

describe('scoped transport', () => {
  it('adds the CSRF token and scopes product paths', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ok: true}), {status: 200}));
    vi.stubGlobal('fetch', fetch);
    const scope: AccountScope = session.scopes[0]!;
    const transport = scopedTransport(session, scope);
    const response = await transport('/api/v1/projects', {method: 'POST', body: '{}'});
    expect(response.status).toBe(200);
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/scopes/team-1/projects',
      expect.objectContaining({credentials: 'same-origin', body: '{}'}),
    );
    const call = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(call[1]!.headers).get('X-CSRF-Token')).toBe('csrf-1');
    vi.unstubAllGlobals();
  });
});

describe('accountApi error handling', () => {
  it('maps backend error bodies and survives non-JSON responses', async () => {
    const fetch = vi.fn(async () => new Response('proxy html', {status: 502}));
    vi.stubGlobal('fetch', fetch);
    await expect(accountApi('/accounts/me')).rejects.toMatchObject({
      code: 'request_failed', status: 502,
    });
    fetch.mockImplementation(async () =>
      new Response(JSON.stringify({error: {code: 'csrf_failed', message: '校验失败'}}), {status: 403}),
    );
    await expect(accountApi('/teams', session, {name: 'x'})).rejects.toMatchObject({
      code: 'csrf_failed', status: 403,
    });
    fetch.mockImplementation(async () => new Response(JSON.stringify({value: 7}), {status: 200}));
    await expect(accountApi<{value: number}>('/health')).resolves.toEqual({value: 7});
    vi.unstubAllGlobals();
  });
  it('reports network failures as account errors, not parser crashes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline'); }));
    await expect(accountApi('/accounts/config')).rejects.toBeInstanceOf(AccountApiError);
    vi.unstubAllGlobals();
  });
});

const draft: ProjectDraft = {
  id: 'draft-1', revision: 4, payload: {title: 'T', goal: 'G'}, state: 'draft',
  created_by: 'user-a', updated_by: 'user-b', created_at: 1, updated_at: 2,
  start_request_id: null, project_id: null,
};

describe('draftsApi', () => {
  it('lists, saves with revision and starts with a fresh request id', async () => {
    const calls: Array<{path: string; init: RequestInit}> = [];
    const transport: typeof fetch = async (input, init) => {
      const path = String(input);
      const method = init?.method || 'GET';
      calls.push({path, init: init || {}});
      if (path === '/api/v1/drafts' && method === 'GET')
        return new Response(JSON.stringify({drafts: [draft]}), {status: 200});
      if (path === '/api/v1/drafts/draft-1' && method === 'POST')
        return new Response(JSON.stringify({draft: {...draft, revision: 5}}), {status: 200});
      if (path === '/api/v1/drafts' && method === 'POST')
        return new Response(JSON.stringify({draft}), {status: 200});
      return new Response(JSON.stringify({project: {id: 'proj-9'}}), {status: 202});
    };
    await expect(draftsApi.list(transport)).resolves.toEqual({drafts: [draft]});
    await expect(draftsApi.save(transport, {title: 'T2', goal: 'G2'}, 'draft-1', 4)).resolves.toEqual({
      draft: {...draft, revision: 5},
    });
    const started = await draftsApi.start(transport, 'draft-1', 5);
    expect(started.project?.id).toBe('proj-9');
    const saveCall = calls[1]!;
    expect(saveCall.init.method).toBe('POST');
    expect(JSON.parse(String(saveCall.init.body))).toEqual({title: 'T2', goal: 'G2', revision: 4});
    const startCall = calls[2]!;
    expect(startCall.path).toBe('/api/v1/drafts/draft-1/start');
    const body = JSON.parse(String(startCall.init.body)) as {revision: number; request_id: string};
    expect(body.revision).toBe(5);
    expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
    const create = await draftsApi.save(transport, {title: 'New', goal: 'G'});
    expect(calls[3]!.init.method).toBe('POST');
    expect(JSON.parse(String(calls[3]!.init.body))).toEqual({title: 'New', goal: 'G'});
    expect(create).toEqual({draft});
  });
  it('surfaces concurrent-edit conflicts as actionable errors', async () => {
    const transport: typeof fetch = async () =>
      new Response(JSON.stringify({error: {code: 'stale_draft', message: '草稿已被其他成员更新，请重新加载'}}), {status: 409});
    await expect(draftsApi.save(transport, {title: 'T', goal: 'G'}, 'draft-1', 1)).rejects.toMatchObject({
      code: 'stale_draft', status: 409,
    });
  });
});

describe('final-designs admin overview', () => {
  it('reads the audited admin aggregate with session credentials', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({
      rule: 'Per-person cumulative final-design allowance.',
      entries: [],
      subjects: [{subject_id: 'user-a', username: 'alice', display_name: 'Alice',
        allowance: 30, reserved: 12, delivered: 8, remaining: 10}],
    }), {status: 200}));
    vi.stubGlobal('fetch', fetch);
    const overview = await fetchFinalDesignsOverview(session);
    expect(overview.subjects[0]).toMatchObject({username: 'alice', remaining: 10});
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe('/api/v1/admin/final-designs');
    expect(new Headers(init.headers).get('X-CSRF-Token')).toBe('csrf-1');
    fetch.mockImplementation(async () =>
      new Response(JSON.stringify({error: {code: 'admin_required', message: '需要系统管理员'}}), {status: 403}));
    await expect(fetchFinalDesignsOverview(session)).rejects.toMatchObject({
      code: 'admin_required', status: 403,
    });
    vi.unstubAllGlobals();
  });
});
