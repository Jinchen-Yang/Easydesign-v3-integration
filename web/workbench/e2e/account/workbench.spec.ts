import {expect, test, type Route} from '@playwright/test';

/**
 * Route-stubbed browser acceptance for Professional mode under accounts. All
 * fixtures are synthetic; this never talks to the real account server.
 */
const users = {
  bob: {id: 'user-b', username: 'bob', display_name: 'Bob Member', role: 'user', status: 'active', must_change_password: false},
  root: {id: 'user-root', username: 'root', display_name: 'Platform Admin', role: 'admin', status: 'active', must_change_password: false},
} as const;

const teamScope = {id: 'team-1', kind: 'team', name: 'Antibody Crew', role: 'member', can_edit: true, can_execute: false};
const observerScope = {id: 'user-b', kind: 'personal', name: 'Bob Member 的个人工作区', role: 'observer', can_edit: false, can_execute: false};

const snapshot = () => ({
  schema_version: '1', mode: 'live', revision: 'a'.repeat(64),
  project: {
    id: 'proj-1', title: 'Synthetic pro project', goal: 'Fixture goal', thread_id: 'thread-1',
    phase: 'site', status: 'awaiting_scientist', last_activity: 5, validation_only: true,
  },
  workflow: [{id: 'site', label: 'Site', status: 'awaiting_scientist', gate: 2}],
  current_action: {id: 'action-1', stage: 'site-review', message: 'Scientist decides', resumable: false},
  specialists: [],
  scientific_context: {structure: null, sites: [], arms: []},
  decision: {
    id: 'card-1', gate: 2, type: 'site-hotspot', question: 'Choose a candidate site',
    default_option_id: 'A', warnings: [], limitations: [], action_summary: 'Review sites',
    revision_targets: ['site'], review_status: null, required_fields: {}, summary: {},
    details_url: '/api/v1/projects/proj-1/review',
    options: [
      {option_id: 'A', label: 'Site A', eligible: true, actions: ['approve', 'revise']},
      {option_id: 'B', label: 'Site B', eligible: true, actions: ['approve', 'revise']},
    ],
  },
  jobs: [], artifacts: [], recent_activity: [], tasks: [], lifecycle: 'scientific_project',
  event_cursor: 4, candidates: {total: 0, counts: {}, url: '/api/v1/projects/proj-1/candidates'},
  capabilities: {decide: true}, requests: [], lab_order: null, connection: 'connected',
});

async function injectAccountMode(route: Route): Promise<void> {
  const response = await route.fetch();
  const html = (await response.text()).replace(
    '</head>', '<meta name="easydesign-identity-mode" content="accounts" /></head>',
  );
  await route.fulfill({response, body: html});
}

function install(page: import('@playwright/test').Page, username: 'bob' | 'root', compute: boolean) {
  // Match the document regardless of query string (?scope=...).
  void page.route(url => url.pathname === '/', async route => injectAccountMode(route));
  void page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const reply = (body: unknown, status = 200) => route.fulfill({json: body, status});
    if (path === '/api/v1/accounts/config')
      return reply({mode: 'multi-user', registration: 'admin-review', setup_required: false, compute_available: compute});
    if (path === '/api/v1/accounts/me') {
      const user = users[username];
      return reply({
        user, csrf_token: `csrf-${username}-synthetic`,
        scopes: username === 'bob' ? [{id: user.id, kind: 'personal', name: `${user.display_name} 的个人工作区`, role: 'owner', can_edit: true, can_execute: true}, teamScope] : [{id: user.id, kind: 'personal', name: `${user.display_name} 的个人工作区`, role: 'owner', can_edit: true, can_execute: true}],
        invitations: [],
      });
    }
    if (path === '/api/v1/scopes/user-b/usage')
      return reply({
        scope: observerScope,
        limits: {max_active_jobs: 1, max_active_chats: 2, max_gpu_devices: 1, max_upload_bytes: 1, max_stored_upload_bytes: 1, max_candidates_per_job: 1},
        stored_upload_bytes: 0, admissions: [],
      });
    if (path.endsWith('/projects') && request.method() === 'GET')
      return reply({items: [snapshot().project], total: 1, offset: 0, limit: 20});
    if (path.endsWith('/workbench') && request.method() === 'GET')
      return reply(snapshot());
    if (path.endsWith('/candidates') && request.method() === 'GET')
      return reply({items: [], total: 0, offset: 0, limit: 20});
    return reply({error: {code: 'not_found', message: `fixture miss ${path}`}}, 404);
  });
}

test.describe('professional mode under accounts', () => {
  const incompleteTurn = 'Scientific work remains incomplete. The previous action has not produced the required verified result; inspect its status before continuing.';
  for (const [routeId, label] of [['REVISE_DESIGN', 'Revise design'], ['STOP', 'Stop campaign']]) {
    test(`Gate 4 ${routeId} labels the actual route and supersedes the old asynchronous wait`, async ({page}) => {
      install(page, 'bob', true);
      await page.route('**/workbench', route => {
        const value = snapshot();
        return route.fulfill({json: {...value,
          project: {...value.project, phase: 'pilot'},
          current_action: {...value.current_action, stage: 'scientist-gate4'},
          conversation: [{id: 'old-wait', kind: 'summary', phase: 'pilot', text: incompleteTurn}],
          decision: {...value.decision, gate: 4, type: 'pilot-promotion',
            default_option_id: routeId, options: [
              {option_id: 'PROMOTE_TO_SCALE', label: 'PROMOTE_TO_SCALE', eligible: false, actions: ['revise', 'reject']},
              {option_id: routeId, label: routeId, eligible: true, actions: ['approve', 'revise', 'reject']},
            ]},
        }});
      });
      await page.goto('/?scope=user-b&project=proj-1');
      await expect(page.getByRole('button', {name: label, exact: true})).toBeVisible();
      await expect(page.getByRole('button', {name: 'Promote pilot', exact: true})).toHaveCount(0);
      await expect(page.getByText(incompleteTurn, {exact: true})).toHaveCount(0);
      await expect(page.getByRole('region', {name: 'Gate 4 decision', exact: true})).toBeVisible();
    });
  }
  test('unresolved asynchronous work retains its incomplete message', async ({page}) => {
    install(page, 'bob', true);
    await page.route('**/workbench', route => {
      const value = snapshot();
      return route.fulfill({json: {...value, project: {...value.project, phase: 'pilot', status: 'running'},
        decision: null, capabilities: {}, current_action: {...value.current_action, stage: 'pilot-running'},
        conversation: [{id: 'current-wait', kind: 'summary', phase: 'pilot', text: incompleteTurn}],
      }});
    });
    await page.goto('/?scope=user-b&project=proj-1');
    await expect(page.getByText(incompleteTurn, {exact: true})).toBeVisible();
  });
  test('long Gate evidence stays scrollable and its real download remains reachable', async ({page}) => {
    install(page, 'bob', true);
    const evidence = {observations: Array.from({length: 100}, (_, i) => ({
      candidate: `synthetic-candidate-${i}`, finding: 'Synthetic native evidence and retained uncertainty.'.repeat(3),
    }))};
    await page.route('**/workbench', route => {
      const value = snapshot();
      return route.fulfill({json: {...value, decision: {...value.decision, summary: evidence}}});
    });
    await page.route('**/projects/proj-1/review', route => route.fulfill({json: evidence}));
    for (const width of [1440, 390]) {
      await page.setViewportSize({width, height: 900});
      await page.goto('/?scope=user-b&project=proj-1');
      await page.getByRole('button', {name: 'Edit', exact: true}).click();
      const dialog = page.getByRole('dialog', {name: 'Review your decision', exact: true});
      await dialog.getByText('Decision evidence and execution scope', {exact: true}).click();
      const bounds = await dialog.boundingBox();
      expect(bounds!.height).toBeLessThanOrEqual(860);
      expect(bounds!.y).toBeGreaterThanOrEqual(0);
      const downloadPromise = page.waitForEvent('download', {timeout: 10000});
      await dialog.getByRole('link', {name: 'Download complete review', exact: true}).click();
      const download = await downloadPromise;
      expect(await download.failure()).toBeNull();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
    }
  });
  test('running Pilot exposes native progress instead of a completed empty result', async ({page}) => {
    install(page,'bob',true);
    let completed = 0;
    await page.route('**/workbench', route => {
      const value = snapshot();
      return route.fulfill({json:{...value,project:{...value.project,phase:'pilot',status:'running'},decision:null,capabilities:{},
        jobs:[{id:'job-pilot',phase:'pilot',status:'running',resumable:false,validation_only:true,
          progress:{stage_id:'04-pilot-generation',status:'running',completed,total:28,completed_tasks:completed/2,total_tasks:14,running_tasks:1,substage_label:'Generate'}}]}});
    });
    await page.goto('/?scope=team-1&project=proj-1');
    const progress = page.getByRole('region',{name:'Native execution progress'});
    await expect(progress.getByRole('progressbar')).toHaveAttribute('aria-valuenow','0');
    await expect(page.getByText('0 of 0 pass',{exact:true})).toHaveCount(0);
    completed = 2;
    await expect(progress.getByRole('progressbar')).toHaveAttribute('aria-valuenow','2');
    await expect(progress).toContainText('2 / 28 candidates collected');
    await page.setViewportSize({width:980,height:800});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
  test('surface handoff retains a deep-linked project while its snapshot is loading', async ({page}) => {
    install(page, 'bob', true);
    let release!: () => void;
    const ready = new Promise<void>(resolve => {release = resolve;});
    await page.route('**/workbench', async route => {await ready; await route.fallback();});
    try {
      await page.goto('/?scope=team-1&project=proj-1');
      await expect(page.getByRole('link', {name: 'Easy 版', exact: true})).toHaveAttribute(
        'href', '/easy/?scope=team-1&project=proj-1',
      );
    } finally {release();}
  });

  test('team member discusses but cannot approve or launch', async ({page}) => {
    install(page, 'bob', true);
    await page.goto('/?scope=team-1');
    await expect(page.getByText('Bob Member', {exact: true})).toBeVisible();
    await expect(page.getByText('协作成员')).toBeVisible();
    // Creation affordances reflect the member right, with the reason shown.
    await expect(page.getByRole('button', {name: 'New project', exact: true})).toBeDisabled();
    await expect(page.getByText('团队成员不能启动计算；请协作编辑团队草稿，由团队管理员创建项目。')).toBeVisible();
    await page.getByTestId('design-project').getByRole('button', {name: /open/i}).click();
    await expect(page.getByRole('region', {name: /Gate 2 decision/i})).toBeVisible();
    await expect(page.getByRole('link', {name: 'Easy 版', exact: true})).toHaveAttribute(
      'href', '/easy/?scope=team-1&project=proj-1',
    );
    await expect(page.getByRole('button', {name: /Approve Site/i})).toBeDisabled();
    // Gate revise instructions are scientific submissions: members cannot send
    // them (backend execute check), so the affordance stays disabled.
    await expect(page.getByRole('button', {name: 'Edit', exact: true})).toBeDisabled();
    // Discussing the research with the agent stays available to members.
    await expect(page.getByPlaceholder('Ask about this step or add a note…')).toBeEnabled();
  });

  test('global observer admin gets no scientific affordances', async ({page}) => {
    install(page, 'root', true);
    await page.goto('/?scope=user-b');
    await expect(page.getByText('管理员只读访问 · 已审计')).toBeVisible();
    await expect(page.getByRole('button', {name: 'New project', exact: true})).toBeDisabled();
    await expect(page.getByText('管理员只读访问：不能创建项目、批准 Gate 或启动计算。')).toBeVisible();
    await page.getByTestId('design-project').getByRole('button', {name: /open/i}).click();
    await expect(page.getByRole('region', {name: /Gate 2 decision/i})).toBeVisible();
    await expect(page.getByRole('button', {name: /Approve Site/i})).toBeDisabled();
    await expect(page.getByPlaceholder('Ask about this step or add a note…')).toBeDisabled();
  });

  test('accounts-only service hides unusable execution while keeping editing', async ({page}) => {
    install(page, 'bob', false);
    await page.goto('/?scope=team-1');
    await expect(page.locator('.account-compute-off')).toBeVisible();
    await expect(page.getByText(/当前服务未连接科学执行器（账号管理模式）/)).toBeVisible();
    await expect(page.getByRole('button', {name: 'New project', exact: true})).toBeDisabled();
    await expect(page.getByText('服务未连接科学执行器（账号管理模式）：暂不能创建项目；团队草稿协作仍可用。')).toBeVisible();
    await page.getByTestId('design-project').getByRole('button', {name: /open/i}).click();
    await expect(page.getByRole('button', {name: /Approve Site/i})).toBeDisabled();
    await expect(page.getByPlaceholder('Ask about this step or add a note…')).toBeDisabled();
    // Without a launcher even the Gate edit path cannot submit science.
    await expect(page.getByRole('button', {name: 'Edit', exact: true})).toBeDisabled();
  });
});
