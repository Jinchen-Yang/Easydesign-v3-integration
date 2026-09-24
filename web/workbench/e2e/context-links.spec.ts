import { expect, test } from '@playwright/test';

test('scientific context links reveal, focus and scroll the panel on desktop and narrow screens', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/?mode=demo#workspace');
  await page.getByRole('button', { name: 'Start design', exact: true }).click();
  await page.getByRole('button', { name: 'Approve target', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve Site B', exact: true })).toBeVisible();
  const panel = page.getByRole('complementary', { name: 'Scientific Context', exact: true });
  const heading = panel.getByRole('heading', { name: 'Choose a binding site' });
  const scroll = panel.locator('.context-scroll');
  const card = page.locator('.tool-card').filter({ hasText: 'Surface context prepared' });
  await card.getByRole('button', { name: /Surface context prepared/ }).click();
  const link = card.getByRole('button', { name: 'View scientific context', exact: true });
  const saved = await page.evaluate(() => localStorage.getItem('easydesign-workbench-projects-v1'));

  // The panel is already open on desktop. A repeated same-phase click must still do useful work.
  for (let attempt = 0; attempt < 2; attempt++) {
    const canScroll = await scroll.evaluate((node) => node.scrollHeight > node.clientHeight);
    await scroll.evaluate((node) => (node.scrollTop = node.scrollHeight));
    if (canScroll) expect(await scroll.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);
    await link.click();
    await expect(panel).toBeFocused();
    await expect(heading).toBeInViewport();
    expect(await scroll.evaluate((node) => node.scrollTop)).toBe(0);
  }
  await page.screenshot({ path: `docs/screenshots/context-link-${info.project.name}.png` });

  // Tablet and small in-app windows use the drawer, not the desktop column.
  await page.getByRole('button', { name: 'Collapse project sidebar', exact: true }).click();
  for (const width of [1180, 642]) {
    await page.setViewportSize({ width, height: 900 });
    const close = page.getByRole('button', { name: 'Close scientific context', exact: true });
    await close.click();
    await expect(panel).toBeHidden();
    await expect(link).toBeFocused();
    await link.press('Enter');
    await expect(panel).toBeVisible();
    await expect(panel).toBeFocused();
    await expect(heading).toBeInViewport();
    await expect(panel.getByRole('region', { name: 'Molecular structure' })).toHaveAttribute(
      'data-status',
      'ready',
    );
    await page.screenshot({
      path: `docs/screenshots/context-link-${width}-${info.project.name}.png`,
    });
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await expect(link).toBeFocused();
    await page.getByRole('button', { name: 'Open scientific context', exact: true }).click();
    await expect(panel).toBeVisible();
    await expect(panel).toBeFocused();
    await close.click();
    await expect(
      page.getByRole('button', { name: 'Open scientific context', exact: true }),
    ).toBeFocused();
    await link.click();
  }
  expect(await page.evaluate(() => localStorage.getItem('easydesign-workbench-projects-v1'))).toBe(
    saved,
  );
  expect(errors).toEqual([]);
});
