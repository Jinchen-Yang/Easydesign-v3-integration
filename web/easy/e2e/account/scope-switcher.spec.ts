import {expect, test} from '@playwright/test';
import {installWorkspaceRoutes} from './workspace-helpers';

/**
 * The workspace bar offers the session's own scopes and keeps account navigation
 * available without introducing another user's private workspace.
 */
test('workspace bar offers only permitted scopes plus the account surface', async ({page}) => {
  installWorkspaceRoutes(page);
  await page.goto('/easy/?scope=team-1');
  await expect(page.locator('.account-workspace-bar > strong', {hasText: 'Bob Member'})).toBeVisible();
  const switcher = page.getByLabel('切换工作区');
  await expect(switcher).toBeVisible();
  await expect(switcher.locator('option')).toHaveCount(2);
  await expect(switcher.locator('option').nth(0)).toHaveText('Bob Member 的个人工作区');
  await expect(switcher.locator('option').nth(1)).toHaveText('Antibody Crew');
  const account = page.locator('.account-workspace-bar').getByRole('link', {name: '账号、团队与资源'});
  await expect(account).toHaveAttribute('href', '/account/');
});
