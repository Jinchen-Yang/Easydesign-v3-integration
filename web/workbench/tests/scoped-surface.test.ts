import { describe, expect, it, vi } from 'vitest';
import { LiveWorkbenchAdapter } from '../src/adapters/LiveWorkbenchAdapter';
import {scopedTransport, scopeDecisionLinks, type AccountSession} from '../../shared/account-client';

const session: AccountSession = {
  user: {
    id: 'user-b', username: 'bob', display_name: 'Bob', role: 'user',
    status: 'active', must_change_password: false,
  },
  csrf_token: 'csrf-b',
  scopes: [{
    id: 'team-7', kind: 'team', name: 'Reagents', role: 'member', can_edit: true, can_execute: false,
  }],
  invitations: [],
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {status, headers: {'Content-Type': 'application/json'}});
}

describe('professional mode scoped transport', () => {
  it('sends every product call through the team scope with the session CSRF token', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith('/api/v1/scopes/team-7/projects?'))
        return jsonResponse({items: [], total: 0, offset: 0, limit: 20});
      return jsonResponse({error: {code: 'not_found', message: 'unscoped'}}, 404);
    });
    vi.stubGlobal('fetch', fetch);
    const adapter = new LiveWorkbenchAdapter(scopedTransport(session, session.scopes[0]!), 1_000_000);
    const state = await adapter.load();
    adapter.dispose();
    expect(state.connection).toBe('connected');
    const call = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(call[0]).toContain('/api/v1/scopes/team-7/projects?');
    expect(new Headers(call[1]!.headers).get('X-CSRF-Token')).toBe('csrf-b');
    vi.unstubAllGlobals();
  });
  it('keeps Gate review links inside the scope instead of the unscoped API', () => {
    const scoped = scopeDecisionLinks(
      {decision: {details_url: '/api/v1/projects/native-project/decision-card'}},
      'team-7',
    );
    expect(scoped.decision?.details_url).toBe(
      '/api/v1/scopes/team-7/projects/native-project/decision-card',
    );
  });
});
