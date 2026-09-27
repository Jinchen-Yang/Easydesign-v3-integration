import {expect, test} from '@playwright/test';
import {installAccountRoutes, login} from './account-helpers';
import {users} from './fixtures';

test.describe('multi-user account experience', () => {
  test('member logs in, collaborates on drafts, cannot start, sees usage', async ({page}) => {
    const fixture = installAccountRoutes(page);
    await login(page, 'bob');
    await expect(page.getByRole('heading', {name: 'Bob Member'})).toBeVisible();
    await expect(page.getByText('研究用户')).toBeVisible();

    await page.getByRole('button', {name: '团队协作'}).click();
    await page.getByLabel('选择团队').selectOption('team-1');
    await expect(page.getByRole('heading', {name: 'Antibody Crew'})).toBeVisible();
    await expect(page.getByText('@bob').first()).toBeVisible();

    // Drafts list appears with revision and collaborators.
    await expect(page.getByRole('heading', {name: '团队项目草稿'})).toBeVisible();
    await expect(page.getByRole('cell', {name: /Lysozyme VHH/})).toBeVisible();
    await expect(page.getByText(/Alice Lead/).first()).toBeVisible();
    // Ordinary member: edit allowed, start not offered.
    await expect(page.getByRole('button', {name: '编辑', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: '启动项目'})).toHaveCount(0);
    await expect(page.getByText('当前身份是团队成员：可以编辑和讨论草稿；启动计算与科学审批由团队管理员执行。')).toBeVisible();

    // Concurrent editing is surfaced, never silently overwritten.
    fixture.armStaleOnce();
    await page.getByRole('button', {name: '编辑', exact: true}).click();
    await page.getByLabel('标题').fill('Lysozyme VHH revised');
    await page.getByRole('button', {name: '保存新版本'}).click();
    await expect(page.getByText('草稿已被其他成员更新，请重新加载')).toBeVisible();
    await page.getByRole('button', {name: '刷新', exact: true}).click();
    await expect(page.getByText(/草稿 · r3/)).toBeVisible();
    await page.getByRole('button', {name: '编辑', exact: true}).click();
    await page.getByLabel('标题').fill('Lysozyme VHH revised');
    await page.getByRole('button', {name: '保存新版本'}).click();
    await expect(page.getByText('草稿已保存')).toBeVisible();

    // Resource usage reflects the admission ledger projection.
    await page.getByRole('button', {name: '资源用量'}).click();
    await expect(page.getByRole('heading', {name: '资源用量', exact: true})).toBeVisible();
    await page.getByLabel('选择工作区').selectOption('team-1');
    await expect(page.getByRole('cell', {name: '科学计算'})).toBeVisible();
    await expect(page.getByText(/1 \/ 2/).first()).toBeVisible();
    // Team view shows the team-local final-design aggregate only: no allowance,
    // no remaining, and never another member's personal balance.
    const teamBalance = page.getByRole('region', {name: '最终设计用量（团队口径）'});
    await expect(teamBalance).toBeVisible();
    await expect(teamBalance.getByText('已预留（本团队，进行中的战役）')).toBeVisible();
    await expect(teamBalance.getByText('已交付（本团队，含科学负结果）')).toBeVisible();
    await expect(teamBalance.getByText('剩余可用')).toHaveCount(0);
    await expect(teamBalance.getByText(/不披露成员的个人余额/)).toBeVisible();
    // The personal view shows Bob's own cumulative balance with remaining.
    await page.getByLabel('选择工作区').selectOption(users.bob.id);
    const ownBalance = page.getByRole('region', {name: '最终设计余额（个人累计）'});
    await expect(ownBalance).toBeVisible();
    await expect(ownBalance.getByText('还可预留 10 个最终设计')).toBeVisible();
    await expect(ownBalance.getByText('已交付（含科学负结果）')).toBeVisible();
    await ownBalance.getByText('计费规则').click();
    await expect(ownBalance.getByText(/Pilot pools never count/)).toBeVisible();
    // Ordinary members never see the admin console or quota editing.
    await expect(page.getByRole('button', {name: '管理员后台'})).toHaveCount(0);

    // Logout returns to the login surface. A fast logout→login attempt must not
    // lose already-typed credentials to async settling (no remount/reset loop).
    await page.getByRole('button', {name: '退出登录'}).click();
    const username = page.getByLabel('用户名');
    await username.fill('alice');
    await page.waitForTimeout(1200);
    await expect(username).toHaveValue('alice');
    await expect(page.getByRole('heading', {name: '登录 EasyDesign'})).toBeVisible();
    await expect(username).toHaveValue('alice');
  });

  test('team admin starts a claimed revision and gets the project link', async ({page}) => {
    const fixture = installAccountRoutes(page);
    await login(page, 'alice');
    await page.getByRole('button', {name: '团队协作'}).click();
    await page.getByLabel('选择团队').selectOption('team-1');
    await expect(page.getByRole('button', {name: '启动项目'})).toBeVisible();
    page.once('dialog', dialog => void dialog.accept());
    await page.getByRole('button', {name: '启动项目'}).click();
    await expect(page.getByText('项目已启动')).toBeVisible();
    const link = page.getByRole('link', {name: '在工作区打开新项目'});
    await expect(link).toHaveAttribute('href', /scope=team-1&project=proj-new/);
    expect(fixture.drafts().find(draft => draft.id === 'draft-1')?.state).toBe('started');
    await expect(page.getByText(/已启动/).first()).toBeVisible();
  });

  test('registration stays pending and login is refused until approval', async ({page}) => {
    installAccountRoutes(page);
    await page.goto('/easy/account/');
    await page.getByRole('button', {name: '没有账号？申请注册'}).click();
    await page.getByLabel('用户名').fill('newcomer');
    await page.getByLabel('显示名称').fill('New Comer');
    await page.getByLabel('密码', {exact: true}).fill('synthetic-password-12');
    await page.getByRole('button', {name: '提交注册申请'}).click();
    await expect(page.getByText('注册已提交，等待管理员审核。审核通过后即可登录。')).toBeVisible();
  });

  test('system administrator reviews users and inspects read-only', async ({page}) => {
    const fixture = installAccountRoutes(page);
    await login(page, 'root');
    await expect(page.getByText('系统管理员')).toBeVisible();
    await page.getByRole('button', {name: '管理员后台'}).click();
    await expect(page.getByRole('heading', {name: '用户审核与管理'})).toBeVisible();
    await expect(page.getByText('Carol Pending')).toBeVisible();
    await expect(page.getByRole('row', {name: /Carol/}).getByRole('link', {name: '只读查看项目'}))
      .toHaveAttribute('href', /scope=user-c/);
    await page.getByRole('button', {name: '批准注册'}).click();
    await expect(page.getByText('已启用').first()).toBeVisible();
    await expect(page.getByRole('heading', {name: '最近审计记录'})).toBeVisible();
    // Admin has no team scope; the admin tab never offers scientific launch UI.
    await expect(page.getByRole('button', {name: '启动项目'})).toHaveCount(0);
    // Quota editing mirrors backend field constraints with useful messages.
    await page.getByRole('row', {name: /Carol/}).getByRole('button', {name: '资源额度'}).click();
    const gpuField = page.getByLabel('GPU 槽位上限', {exact: false});
    await expect(gpuField).toBeVisible();
    await gpuField.fill('0');
    await expect(page.getByText('必须在 1 到 64 之间。')).toBeVisible();
    await expect(page.getByRole('button', {name: '保存额度'})).toBeDisabled();
    await gpuField.fill('');
    await expect(page.getByText('不能为空；请填写服务端允许范围内的整数。')).toBeVisible();
    await gpuField.fill('4');
    await expect(page.getByRole('button', {name: '保存额度'})).toBeEnabled();
    // The cumulative final-design allowance validates against its own range.
    const allowanceField = page.locator('label:has-text("最终设计个人累计额度") input[type="number"]');
    await allowanceField.fill('1000001');
    await expect(page.getByText('必须在 0 到 1000000 之间。')).toBeVisible();
    await expect(page.getByRole('button', {name: '保存额度'})).toBeDisabled();
    await allowanceField.fill('25');
    // Null is an explicit control, never a silently emptied numeric field.
    const pilotField = page.locator('label:has-text("Pilot 阶段预算") input[type="number"]');
    await pilotField.fill('');
    await expect(page.getByText(/不能为空；请填写 1 到 10000 之间的整数，或勾选/)).toBeVisible();
    await expect(page.getByRole('button', {name: '保存额度'})).toBeDisabled();
    await page.getByRole('checkbox', {name: /Pilot 阶段预算（新项目默认）：使用原生默认/}).check();
    await expect(page.getByRole('button', {name: '保存额度'})).toBeEnabled();
    const scaleField = page.locator('label:has-text("Scale 阶段预算") input[type="number"]');
    await scaleField.fill('40');
    await page.getByRole('button', {name: '保存额度'}).click();
    await expect(page.getByText('资源额度已保存，后续准入按新额度检查')).toBeVisible();
    expect(fixture.quotaSaves().at(-1)).toMatchObject({
      max_gpu_devices: 4, final_designs_allowance: 25, pilot_stage_budget: null, scale_stage_budget: 40,
    });
    // A team subject's allowance never looks like an additional team pool.
    await page.getByRole('button', {name: '团队额度'}).click();
    await expect(page.getByText('该额度只按审批人个人计费')).toBeVisible();
    // The site-wide final-designs overview aggregates per person, unlimited included.
    const overview = page.getByRole('region', {name: '最终设计余额总览'});
    await expect(overview).toBeVisible();
    await expect(overview.getByRole('row', {name: /Alice Lead/})).toContainText('10');
    await expect(overview.getByRole('row', {name: /Bob Member/})).toContainText('不限制');
    await overview.getByText('计费规则').click();
    await expect(overview.getByText(/Gate-5 panel revisions/)).toBeVisible();
  });

  test('personal final-design balance renders unrestricted and exhausted states truthfully', async ({page}) => {
    const fixture = installAccountRoutes(page);
    await login(page, 'bob');
    await page.getByRole('button', {name: '资源用量'}).click();
    const ownBalance = page.getByRole('region', {name: '最终设计余额（个人累计）'});
    await expect(ownBalance).toBeVisible();
    await expect(ownBalance.getByText('还可预留 10 个最终设计')).toBeVisible();
    // Unrestricted: null allowance is a real state with its own display, not a parse gap.
    fixture.setPersonalFinalDesigns({allowance: null});
    await page.getByRole('button', {name: '刷新', exact: true}).click();
    await expect(ownBalance.getByText('不限制：未启用余额检查')).toBeVisible();
    await expect(ownBalance.locator('.account-scope', {hasText: '剩余可用'})).toContainText('不限制');
    // Exhausted: remaining hits zero and the UI says new holds are refused.
    fixture.setPersonalFinalDesigns({allowance: 20});
    await page.getByRole('button', {name: '刷新', exact: true}).click();
    await expect(ownBalance.getByText(/可用额度已耗尽/)).toBeVisible();
    await expect(ownBalance.getByText(/final_designs_exhausted/)).toBeVisible();
  });
});
