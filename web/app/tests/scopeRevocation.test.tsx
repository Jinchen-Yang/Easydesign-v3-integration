import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { Suspense } from 'react';
import { HashRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { I18nProvider, appI18n, LANGUAGE_KEY } from '../src/shell/I18nProvider';
import { SessionProvider } from '../src/shell/SessionProvider';
import { EasyWorkspace } from '../src/views/easy/EasyWorkspace';
import { LiveWorkbenchAdapter } from '../src/adapters/LiveWorkbenchAdapter';
import type { LiveProductStore } from '../src/data/LiveProductStore';
import { ProWorkspace } from '../src/views/pro/ProWorkspace';
import { EasyProductAdapter } from '../src/views/easy/EasyProductAdapter';
import type { AccountSession } from '../src/shared/account-client';
import type { ProductSnapshot } from '../src/data/product-contracts';

beforeEach(async () => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(LANGUAGE_KEY, 'en');
  await appI18n.changeLanguage('en');
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each(['easy', 'pro'] as const)(
  '%s removes a revoked team project before rebinding to the personal scope',
  async (view) => {
    const original: AccountSession = {
      user: {
        id: 'u1',
        username: 'user1',
        display_name: 'User 1',
        role: 'user',
        status: 'active',
        must_change_password: false,
      },
      csrf_token: 'csrf',
      invitations: [],
      scopes: [
        {
          id: 'u1',
          name: 'Personal',
          kind: 'personal',
          role: 'owner',
          can_edit: true,
          can_execute: true,
        },
        {
          id: 'team-1',
          name: 'Former team',
          kind: 'team',
          role: 'admin',
          can_edit: true,
          can_execute: true,
        },
      ],
    };
    const project: ProductSnapshot = {
      schema_version: '1',
      mode: 'live',
      revision: 'rev',
      project: {
        id: 'p1',
        title: 'Revoked team project',
        goal: 'Test',
        thread_id: null,
        phase: 'site',
        status: 'stopped',
        last_activity: 1,
        validation_only: true,
      },
      workflow: [],
      current_action: { id: 'stopped', stage: 'stopped', message: 'Stopped', resumable: false },
      specialists: [],
      scientific_context: { structure: null, sites: [], arms: [] },
      decision: null,
      jobs: [],
      artifacts: [],
      recent_activity: [],
      tasks: [],
      lifecycle: 'scientific_project',
      event_cursor: 1,
      candidates: { total: 0, counts: {}, url: '/candidates' },
      capabilities: {},
      requests: [],
      lab_order: null,
      connection: 'connected',
    };
    let revoked = false;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/accounts/config'))
        return Response.json({
          mode: 'multi-user',
          registration: 'open',
          setup_required: false,
          compute_available: true,
        });
      if (url.startsWith('/api/v1/scopes/team-1/')) {
        if (revoked)
          return Response.json(
            { error: { code: 'not_found', message: 'No workspace access' } },
            { status: 404 },
          );
        if (url.endsWith('/workbench')) return Response.json(project);
      }
      if (/\/scopes\/[^/]+\/projects\?/.test(url))
        return Response.json({ items: [], total: 0, offset: 0, limit: 5 });
      throw new Error(`Unexpected scoped request ${url}`);
    });
    const adapters: LiveProductStore[] = [];
    const factory = (transport: typeof fetch) => {
      const adapter = new EasyProductAdapter(transport);
      adapters.push(adapter);
      return adapter;
    };
    const proFactory = (transport: typeof fetch) => {
      const adapter = new LiveWorkbenchAdapter(transport);
      adapters.push(adapter);
      return adapter;
    };
    window.history.replaceState({}, '', `/app/#/projects/p1?scope=team-1&view=${view}`);
    render(
      <I18nProvider>
        <SessionProvider
          api={{
            probe: async () => (revoked ? { ...original, scopes: [original.scopes[0]] } : original),
            login: async () => original,
            logout: async () => {},
          }}
        >
          <HashRouter>
            <Suspense fallback="Loading">
              {view === 'easy' ? (
                <EasyWorkspace adapterFactory={factory} />
              ) : (
                <ProWorkspace adapterFactory={proFactory} />
              )}
            </Suspense>
          </HashRouter>
        </SessionProvider>
      </I18nProvider>,
    );
    await screen.findAllByText('Revoked team project', { exact: false });
    await act(async () => {
      revoked = true;
      await adapters[0].refresh();
    });
    await waitFor(() => expect(window.location.hash).toBe(`#/projects?scope=u1&view=${view}`));
    await waitFor(() =>
      expect(screen.queryAllByText('Revoked team project', { exact: false })).toHaveLength(0),
    );
    await waitFor(() =>
      expect(
        (screen.getByRole('combobox', { name: 'Switch workspace' }) as HTMLSelectElement).value,
      ).toBe('u1'),
    );
    expect(fetchMock.mock.calls.map(([url]) => String(url))).not.toContain(
      '/api/v1/scopes/u1/projects/p1/workbench',
    );
    expect(adapters).toHaveLength(2);
  },
);
