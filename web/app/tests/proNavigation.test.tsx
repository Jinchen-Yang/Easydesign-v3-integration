import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { LiveWorkbenchAdapter } from '../src/adapters/LiveWorkbenchAdapter';
import { LiveWorkbench } from '../src/views/pro/LiveWorkbench';
import { I18nProvider } from '../src/shell/I18nProvider';
import type { ProductSnapshot } from '../src/data/product-contracts';

const snapshot: ProductSnapshot = {
  schema_version: '1',
  mode: 'live',
  revision: 'r1',
  project: {
    id: 'p1',
    title: 'Native project',
    goal: 'Preserve this scientific goal.',
    thread_id: null,
    phase: 'goal',
    status: 'awaiting_scientist',
    last_activity: 1,
    validation_only: true,
  },
  workflow: [],
  current_action: { id: 'goal', stage: 'goal', message: 'Native evidence.', resumable: false },
  specialists: [],
  scientific_context: { structure: null, sites: [], arms: [] },
  decision: null,
  jobs: [],
  artifacts: [],
  conversation: [],
  recent_activity: [],
  tasks: [],
  lifecycle: 'scientific_project',
  event_cursor: 1,
  candidates: { total: 0, counts: {}, url: '/projects/p1/candidates' },
  capabilities: { decide: false, message: true, resume: false },
  requests: [],
  lab_order: null,
  connection: 'connected',
};
afterEach(cleanup);
it('opens a Pro hash deep link and keeps project navigation within the scoped app route', async () => {
  localStorage.clear();
  history.replaceState({}, '', '/app/#/projects/p1?scope=s1&view=pro');
  const transport = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.method ?? 'GET').toBe('GET');
    const path = new URL(String(input), location.origin).pathname;
    const result = path.endsWith('/workbench')
      ? snapshot
      : path.endsWith('/candidates')
        ? { items: [], total: 0, offset: 0, limit: 20 }
        : { items: [snapshot.project], total: 1, offset: 0, limit: 20 };
    return new Response(JSON.stringify(result), {
      headers: { 'Content-Type': 'application/json' },
    });
  });
  const adapter = new LiveWorkbenchAdapter(transport);
  render(
    <I18nProvider>
      <LiveWorkbench
        adapter={adapter}
        access={{ id: 's1', role: 'owner', can_edit: true, can_execute: true }}
      />
    </I18nProvider>,
  );
  await screen.findByRole('heading', { name: '设计科学家' });
  expect(
    transport.mock.calls.some(([input]) => String(input).includes('/projects/p1/workbench')),
  ).toBe(true);
  expect(screen.getByLabelText('当前项目').textContent).toContain('Native project');
  fireEvent.click(screen.getByRole('button', { name: '项目' }));
  await screen.findByRole('heading', { name: '项目' });
  fireEvent.click(screen.getByRole('button', { name: '打开项目 Native project' }));
  await waitFor(() => expect(location.hash).toBe('#/projects/p1?scope=s1&view=pro'));
  expect(location.search).toBe('');
  await screen.findByRole('heading', { name: '设计科学家' });
});
