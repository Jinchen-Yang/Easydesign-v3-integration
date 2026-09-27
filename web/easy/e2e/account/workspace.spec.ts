import {expect, test, type Page} from '@playwright/test';
import {
  emptyPage, injectAccountMode, jsonResponse, observerScope, sessionFor, usage, users,
  workbenchSnapshot,
} from './fixtures';

/**
 * Account-mode Easy workspace gating with synthetic fixtures: members discuss and
 * co-edit but cannot start or approve; admin observation is read-only and audited;
 * Gate review links stay inside the scope.
 */
function installWorkspaceRoutes(page: Page, username: string, scopeId: string, compute = true) {
  // Match the document regardless of query string (?scope=...).
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: compute});
    if (path === '/api/v1/accounts/me')
      return reply(username ? sessionFor(username) : {error: {code: 'session_required', message: '请先登录'}}, username ? 200 : 401);
    if (path === '/api/v1/scopes/team-1/usage' || path === `/api/v1/scopes/${users.bob.id}/usage`)
      return reply({...usage(scopeId), scope: scopeId === 'team-1' ? sessionFor('bob').scopes[1] : observerScope(users.bob.id, 'Bob Member 的个人工作区')});
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [workbenchSnapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET')
      return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET')
      return reply(emptyPage);
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'GET')
      return reply({configured: false});
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
}

/** A step the backend marked resumable and auto-continuable (no open Gate). */
function resumableSnapshot(status = 'available') {
  const base = workbenchSnapshot();
  return {
    ...base,
    project: {...base.project, phase: 'pilot', status},
    workflow: [{id: 'pilot', label: 'Pilot', status: 'available', gate: 4}],
    current_action: {id: 'action-resume-1', stage: 'pilot-card', message: 'Pilot 结果已就绪', resumable: true},
    capabilities: {resume: true, auto_continue: true},
    decision: null,
  };
}

interface RecordedAction {
  body: Record<string, unknown>;
  csrf: string | undefined;
}

function installResumableRoutes(page: Page, username: string, compute = true, status = 'available', bootstrap = false): RecordedAction[] {
  const actions: RecordedAction[] = [];
  const snapshot = () => {
    const value = resumableSnapshot(status);
    return bootstrap ? {...value,capabilities:{resume:false,auto_continue:false},requests:[{kind:'create',id:'req-create-failed',project:'proj-1',state:'failed',result:null,created:1,updated:1}]} : value;
  };
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: compute});
    if (path === '/api/v1/accounts/me') return reply(sessionFor(username));
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [snapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET') return reply(snapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET') return reply(emptyPage);
    if (path.endsWith('/projects') && request.method() === 'POST') {
      actions.push({body: request.postDataJSON() as Record<string, unknown>, csrf: request.headers()['x-csrf-token']});
      return reply({kind:'action', id:'req-create-1', project:'proj-1', state:'succeeded', result:null, created:1, updated:1});
    }
    if (path === '/api/v1/scopes/team-1/requests/req-create-failed/resume' && request.method() === 'POST') {
      actions.push({body:request.postDataJSON() as Record<string,unknown>,csrf:request.headers()['x-csrf-token']});
      return reply({kind:'create',id:'req-create-failed',project:'proj-1',state:'accepted',result:null,created:1,updated:2});
    }
    if (path === '/api/v1/scopes/team-1/projects/proj-1/actions' && request.method() === 'POST') {
      actions.push({body: request.postDataJSON() as Record<string, unknown>, csrf: request.headers()['x-csrf-token']});
      return reply({
        kind: 'action', id: 'req-resume-1', project: 'proj-1', state: 'succeeded',
        result: null, created: 1, updated: 1,
      });
    }
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
  return actions;
}

interface RecordedChatPost {
  csrf: string | undefined;
  requestId: string | undefined;
}

function installChatRoutes(page: Page, behavior: 'transient' | 'forbidden'): RecordedChatPost[] {
  const posts: RecordedChatPost[] = [];
  let calls = 0;
  void page.route(url => url.pathname === '/easy/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => jsonResponse(route, body, status);
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: true});
    if (path === '/api/v1/accounts/me') return reply(sessionFor('bob'));
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [workbenchSnapshot().project], total: 1, offset: 0, limit: 5});
    if (path.endsWith('/workbench') && request.method() === 'GET') return reply(workbenchSnapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET') return reply(emptyPage);
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'GET')
      return reply({configured: true});
    if (path === '/api/v1/scopes/team-1/rabbit/chat' && request.method() === 'POST') {
      calls++;
      const headers = request.headers();
      posts.push({csrf: headers['x-csrf-token'], requestId: headers['x-request-id']});
      if (behavior === 'forbidden')
        return reply({error: {code: 'read_only_scope', message: '管理员查看权限不允许修改或推进他人的科学项目'}}, 403);
      if (calls === 1) return reply({error: 'unavailable'}, 503);
      return route.fulfill({
        contentType: 'application/x-ndjson',
        body: '{"type":"delta","text":"自动重试成功"}\n{"type":"done"}\n',
      });
    }
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
  return posts;
}

test.describe('account-mode Easy workspace', () => {
  test('team member cannot start or approve but keeps read and co-edit surfaces', async ({page}) => {
    installWorkspaceRoutes(page, 'bob', 'team-1');
    // A stale single-user workspace token is dropped silently, never authenticated.
    await page.goto('/easy/?scope=team-1&token=stale-legacy-token-fixture&project=proj-1');
    await expect(page).toHaveURL(/scope=team-1&project=proj-1$/);
    await expect(page.getByText('Bob Member', {exact: true})).toBeVisible();
    await expect(page.locator('.account-workspace-bar > span', {hasText: 'Antibody Crew'})).toBeVisible();
    await expect(page.locator('.account-workspace-bar > span', {hasText: '团队协作成员'})).toBeVisible();
    await expect(page.getByText('团队协作成员：可以查看和讨论，科学审批及计算启动由团队管理员负责。')).toBeVisible();
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('region', {name: 'Gate 2'})).toBeVisible();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
    await expect(page.getByRole('button', {name: '修改', exact: true})).toBeDisabled();
    // The Gate provenance link is scope-projected, never the unscoped API.
    await page.getByText('查看技术详情').click();
    await expect(page.getByRole('link', {name: '查看当前 Gate 的审查与 provenance'}))
      .toHaveAttribute('href', '/api/v1/scopes/team-1/projects/proj-1/review');
    // The dropped legacy token never surfaces anywhere in the document.
    expect(await page.locator('body').innerText()).not.toContain('stale-legacy-token-fixture');
  });

  test('system admin observation is explicitly read-only', async ({page}) => {
    installWorkspaceRoutes(page, 'root', users.bob.id);
    await page.goto(`/easy/?scope=${users.bob.id}&project=proj-1`);
    await expect(page.getByText('管理员只读访问 · 已审计')).toBeVisible();
    await expect(page.getByText('管理员只读查看：不能修改他人项目、批准 Gate 或启动计算。')).toBeVisible();
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
  });

  test('accounts-only service keeps browsing and co-editing but removes execution', async ({page}) => {
    installWorkspaceRoutes(page, 'alice', 'team-1', false);
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await expect(page.getByText('未连接科学执行器')).toBeVisible();
    await expect(page.getByText(/当前服务未连接科学执行器（账号管理模式）/)).toBeVisible();
    // Even the team admin loses launch/approval affordances without a launcher.
    await expect(page.getByRole('button', {name: /开始设计/})).toBeDisabled();
    await expect(page.getByRole('button', {name: /批准并继续/})).toBeDisabled();
    await expect(page.getByRole('region', {name: 'Gate 2'})).toBeVisible();
  });
});

test.describe('account-mode automatic continuation', () => {
  test('a failed bootstrap retries the original scoped request instead of leaving a dead end', async ({page}) => {
    const actions = installResumableRoutes(page,'alice',true,'blocked',true);
    await page.goto('/easy/?scope=team-1&project=proj-1');
    const retry=page.getByRole('button',{name:/重试目标解析/});
    await expect(retry).toBeEnabled();
    await retry.click();
    await expect.poll(()=>actions.length).toBe(1);
    expect(actions[0]!.csrf).toBe('csrf-alice-synthetic');
    await expect(retry).toBeDisabled();
    await expect(page.getByText('正在自动继续')).toHaveCount(0);
  });
  test('typed target identifiers reach the scoped API without a prose-only source', async ({page}) => {
    const actions = installResumableRoutes(page, 'alice', true, 'blocked');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await page.getByRole('combobox', {name:'输入类型'}).selectOption('pdb-id');
    await page.getByPlaceholder('目标名称或数据库 ID').fill('1UBQ');
    await page.getByRole('button', {name:/开始设计/}).click();
    await expect.poll(()=>actions.length).toBe(1);
    expect(actions[0]!.body).toMatchObject({pdb_id:'1UBQ',surface:'easy'});
    expect(actions[0]!.csrf).toBe('csrf-alice-synthetic');
    await page.getByRole('button', {name:/开始设计/}).waitFor();
    await page.getByRole('combobox', {name:'输入类型'}).selectOption('uniprot');
    await page.getByPlaceholder('目标名称或数据库 ID').fill('p00698');
    await page.getByRole('button', {name:/开始设计/}).click();
    await expect.poll(()=>actions.length).toBe(2);
    expect(actions[1]!.body).toMatchObject({uniprot:'P00698',surface:'easy'});
  });

  test('unsupported live sequences are explicit and cannot be submitted', async ({page}) => {
    const actions = installResumableRoutes(page, 'alice', true, 'blocked');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    const choice = page.getByRole('combobox', {name:'输入类型'}).locator('option[value="sequence"]');
    await expect(choice).toHaveAttribute('disabled','');
    await expect(choice).toHaveText('Sequence / FASTA · LIVE 暂未接入');
    expect(actions).toHaveLength(0);
  });
  test('a blocked execution reports its state and requires an explicit recovery action', async ({page}) => {
    const actions = installResumableRoutes(page, 'alice', true, 'blocked');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await expect(page.getByText('当前执行已阻塞', {exact: true})).toBeVisible();
    await expect(page.getByText('正在自动继续')).toHaveCount(0);
    await expect(page.getByText('科学 Agent 正在处理当前阶段。')).toHaveCount(0);
    const resume = page.getByRole('button', {name: /继续研究/});
    await expect(resume).toBeEnabled();
    await page.waitForTimeout(600);
    expect(actions).toHaveLength(0);
    await resume.click();
    await expect.poll(() => actions.length).toBe(1);
    expect(actions[0]!.csrf).toBe('csrf-alice-synthetic');
    await page.waitForTimeout(600);
    expect(actions).toHaveLength(1);
  });
  test('an ordinary team member never auto-continues and keeps the explicit disabled control', async ({page}) => {
    const actions = installResumableRoutes(page, 'bob');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await expect(page.getByText('当前步骤可以继续')).toBeVisible();
    // capabilities.auto_continue must not claim automatic progress for a member.
    await expect(page.getByText('正在自动继续')).toHaveCount(0);
    const resume = page.getByRole('button', {name: /继续研究/});
    await expect(resume).toBeVisible();
    await expect(resume).toBeDisabled();
    await page.waitForTimeout(600);
    expect(actions).toHaveLength(0);
  });

  test('compute-off surfaces never auto-continue even for the team admin', async ({page}) => {
    const actions = installResumableRoutes(page, 'alice', false);
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await expect(page.getByText(/当前服务未连接科学执行器（账号管理模式）/)).toBeVisible();
    await expect(page.getByText('当前步骤可以继续')).toBeVisible();
    const resume = page.getByRole('button', {name: /继续研究/});
    await expect(resume).toBeVisible();
    await expect(resume).toBeDisabled();
    await page.waitForTimeout(600);
    expect(actions).toHaveLength(0);
  });

  test('an authorized team admin still auto-continues once via the scoped transport', async ({page}) => {
    const actions = installResumableRoutes(page, 'alice');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await expect(page.getByText('正在自动继续')).toBeVisible();
    // While auto-continuation owns the step, the manual control stays hidden.
    await expect(page.getByRole('button', {name: /继续研究/})).toHaveCount(0);
    await expect.poll(() => actions.length).toBe(1);
    expect(actions[0]!.body).toMatchObject({action: 'resume'});
    expect(actions[0]!.csrf).toBe('csrf-alice-synthetic');
    await page.waitForTimeout(600);
    expect(actions).toHaveLength(1);
  });
});

test.describe('account-mode Doudou chat retry boundary', () => {
  test('a transient failure retries once through the scoped transport with fresh identities', async ({page}) => {
    const posts = installChatRoutes(page, 'transient');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await page.getByRole('button', {name: '和豆豆聊天', exact: true}).click();
    const panel = page.getByRole('dialog', {name: '和豆豆聊天'});
    await expect(panel).toBeVisible();
    await panel.getByRole('textbox').fill('你好豆豆');
    await panel.getByRole('button', {name: '发送消息'}).click();
    await expect(panel.locator('.rabbit-message.assistant').last()).toContainText('自动重试成功');
    expect(posts).toHaveLength(2);
    for (const post of posts) expect(post.csrf).toBe('csrf-bob-synthetic');
    // Every attempt is a new request identity, never a replayed one.
    expect(posts[0]!.requestId).not.toBe(posts[1]!.requestId);
  });

  test('an authorization failure is never retried automatically', async ({page}) => {
    const posts = installChatRoutes(page, 'forbidden');
    await page.goto('/easy/?scope=team-1&project=proj-1');
    await page.getByRole('button', {name: '和豆豆聊天', exact: true}).click();
    const panel = page.getByRole('dialog', {name: '和豆豆聊天'});
    await expect(panel).toBeVisible();
    await panel.getByRole('textbox').fill('你好豆豆');
    await panel.getByRole('button', {name: '发送消息'}).click();
    await expect(panel.getByRole('status')).toContainText('暂时连接不上，请重试。');
    // Outlive the 800 ms automatic-retry window: a 403 stays a single request.
    await page.waitForTimeout(1500);
    expect(posts).toHaveLength(1);
    expect(posts[0]!.csrf).toBe('csrf-bob-synthetic');
    // An explicit human retry is still allowed and stays scoped.
    await panel.getByRole('button', {name: '重试回复'}).click();
    await expect.poll(() => posts.length).toBe(2);
    expect(posts[1]!.csrf).toBe('csrf-bob-synthetic');
  });
});
