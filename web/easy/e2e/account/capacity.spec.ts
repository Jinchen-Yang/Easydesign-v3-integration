import { expect, test, type Page } from '@playwright/test';
import { emptyPage, injectAccountMode, sessionFor, workbenchSnapshot } from './fixtures';

async function install(page: Page, project = false) {
  await page.route((url) => url.pathname === '/easy/', injectAccountMode);
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname;
    const reply = (json: unknown) => route.fulfill({ json });
    if (path === '/api/v1/accounts/config')
      return reply({
        mode: 'multi-user',
        registration: 'admin-review',
        setup_required: false,
        compute_available: true,
      });
    if (path === '/api/v1/accounts/me') return reply(sessionFor('alice'));
    if (path.endsWith('/rabbit/chat')) return reply({ configured: true });
    if (path.endsWith('/projects'))
      return reply(
        project ? { ...emptyPage, total: 1, items: [workbenchSnapshot().project] } : emptyPage,
      );
    if (path.endsWith('/workbench')) return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') || path.endsWith('/drafts')) return reply(emptyPage);
    return route.fulfill({ status: 404, json: { error: { code: 'not_found' } } });
  });
}

test('capacity: unknown AI outcome retains identity, does not auto retry, and exposes status', async ({
  page,
}) => {
  await install(page);
  const ids: string[] = [];
  await page.route('**/scopes/user-a/rabbit/chat', (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { configured: true } });
    ids.push(route.request().headers()['x-request-id']);
    expect(route.request().headers()['x-csrf-token']).toBe('csrf-alice-synthetic');
    return route.fulfill({
      contentType: 'application/x-ndjson',
      body: '{"type":"error","code":"outcome_unknown"}\n',
    });
  });
  await page.route('**/scopes/user-a/rabbit/requests/*', (route) =>
    route.fulfill({
      json: { request_id: ids[0], state: 'failed', dispatched: true, code: 'outcome_unknown' },
    }),
  );
  await page.goto('/easy/?scope=user-a');
  await page.getByRole('button', { name: '和豆豆聊天', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  await panel.getByRole('textbox').fill('Synthetic capacity fixture question');
  await panel.getByRole('button', { name: '发送消息' }).click();
  await expect(panel.getByText(/结果未确认，不会自动重新调用/)).toBeVisible();
  await expect(panel.getByRole('button', { name: '重试回复' })).toHaveCount(0);
  await page.waitForTimeout(1100);
  expect(ids).toHaveLength(1);
  await panel.getByRole('button', { name: '查看请求状态' }).click();
  await expect(panel.getByText(`请求状态：failed · ${ids[0]}`)).toBeVisible();
  expect(ids).toHaveLength(1);
});

test('capacity: explicit stop cancels the same authenticated request once', async ({ page }) => {
  await install(page);
  let identity = '';
  let finish: (() => void) | undefined;
  let cancelled = 0;
  await page.route('**/scopes/user-a/rabbit/chat', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { configured: true } });
    identity = route.request().headers()['x-request-id'];
    await new Promise<void>((resolve) => {
      finish = resolve;
    });
    await route
      .fulfill({
        contentType: 'application/x-ndjson',
        body: '{"type":"error","code":"cancelled"}\n',
      })
      .catch(() => {});
  });
  await page.route('**/scopes/user-a/rabbit/requests/*/cancel', (route) => {
    expect(new URL(route.request().url()).pathname).toContain(`/requests/${identity}/cancel`);
    expect(route.request().method()).toBe('POST');
    expect(route.request().headers()['x-csrf-token']).toBe('csrf-alice-synthetic');
    cancelled++;
    finish?.();
    return route.fulfill({ json: { request_id: identity, state: 'cancelled', dispatched: false } });
  });
  await page.goto('/easy/?scope=user-a');
  await page.getByRole('button', { name: '和豆豆聊天', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  await panel.getByRole('textbox').fill('Synthetic pending question');
  await panel.getByRole('button', { name: '发送消息' }).click();
  await expect.poll(() => identity).not.toBe('');
  await panel.getByRole('button', { name: '停止回复' }).click();
  await expect.poll(() => cancelled).toBe(1);
  await expect(panel.getByRole('button', { name: '查看请求状态' })).toBeVisible();
});

test('capacity: GPU queue survives a fresh page and scoped cancellation refreshes it', async ({
  page,
}) => {
  await install(page, true);
  let cancelled = false;
  await page.route('**/workbench', (route) => {
    const value = workbenchSnapshot();
    return route.fulfill({
      json: {
        ...value,
        project: { ...value.project, status: 'running' },
        decision: null,
        requests: cancelled
          ? [
              {
                id: 'queue-1',
                project: 'proj-1',
                state: 'failed',
                result: { code: 'queue_cancelled' },
                created: 1,
                updated: 2,
              },
            ]
          : [
              {
                id: 'queue-1',
                project: 'proj-1',
                state: 'accepted',
                result: {
                  resource_waiting: true,
                  queue: {
                    state: 'queued',
                    reason: 'waiting_for_resources',
                    position: 3,
                    cancellable: true,
                  },
                },
                created: 1,
                updated: 1,
              },
            ],
      },
    });
  });
  await page.route('**/scopes/user-a/requests/queue-1/cancel', (route) => {
    expect(route.request().method()).toBe('POST');
    expect(route.request().headers()['x-csrf-token']).toBe('csrf-alice-synthetic');
    cancelled = true;
    return route.fulfill({
      json: {
        id: 'queue-1',
        project: 'proj-1',
        state: 'failed',
        result: { code: 'queue_cancelled' },
        created: 1,
        updated: 2,
      },
    });
  });
  await page.goto('/easy/?scope=user-a&project=proj-1');
  await expect(page.getByText(/排队位置：3/)).toBeVisible();
  await page.getByRole('button', { name: '取消排队', exact: true }).click();
  await expect(page.getByRole('button', { name: '取消排队', exact: true })).toHaveCount(0);
  expect(cancelled).toBe(true);
  await expect(page.getByRole('heading', { name: '排队已取消' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '排队已取消' })).toBeVisible();
  await expect(page.getByText('Agent 正在工作')).toHaveCount(0);
  await page.route('**/workbench', route => {
    const value = workbenchSnapshot();
    return route.fulfill({json: {...value, decision: null, project: {...value.project, status: 'running'}, requests: [
      {id: 'queue-1', project: 'proj-1', state: 'failed', result: {code: 'queue_cancelled'}, created: 1, updated: 2},
      {id: 'new-request', project: 'proj-1', state: 'running', result: null, created: 3, updated: 3},
    ]}});
  });
  await page.reload();
  await expect(page.getByText('Agent 正在工作')).toBeVisible();
  await expect(page.getByRole('heading', {name: '排队已取消'})).toHaveCount(0);
});
