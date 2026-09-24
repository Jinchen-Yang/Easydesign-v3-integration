import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const project = process.env.EASYDESIGN_LIVE_PROJECT;
const token = process.env.EASYDESIGN_LIVE_TOKEN;

test('live goal-first workspace projects durable target activity and Gate 1', async ({ page }) => {
  test.skip(!project || !token, 'Set EASYDESIGN_LIVE_PROJECT and EASYDESIGN_LIVE_TOKEN');
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });

  await page.goto(`/?project=${project}#access=${token}`);
  await expect(page.getByRole('complementary', { name: 'Workflow' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Design Scientist conversation' })).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'Scientific Context' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  await expect(page.getByText('Structure candidates', { exact: true })).toBeVisible();
  await expect(page.getByText('7XWO chain B', { exact: true })).toBeVisible();
  await expect(page.getByText('Target Intelligence', { exact: true }).first()).toBeVisible();

  const before = await page.evaluate(async (projectID) => {
    const response = await fetch(`/api/v1/projects/${projectID}/workbench`);
    return response.json();
  }, project);
  expect(before.lifecycle).toBe('gate1_awaiting_scientist');
  expect(before.scientific_context.target.decision_kind).toBe('structure-selection');
  expect(before.tasks.length).toBeGreaterThan(5);
  expect(before.recent_activity.length).toBeGreaterThan(5);

  await mkdir('docs/screenshots', { recursive: true });
  await page.screenshot({
    path: 'docs/screenshots/goal-first-live-workbench.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'View all tasks', exact: true }).click();
  const inspector = page.getByRole('complementary', { name: 'Agent Tasks' });
  await expect(inspector).toBeVisible();
  await expect(inspector).toContainText('Target Intelligence');
  await expect(inspector).toContainText('Scientist structure decision');
  await page.screenshot({
    path: 'docs/screenshots/goal-first-live-task-inspector.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: 'Close Agent Tasks' }).click();

  await page.reload();
  await expect(page.getByRole('button', { name: 'Approve target', exact: true })).toBeVisible();
  const after = await page.evaluate(async (projectID) => {
    const response = await fetch(`/api/v1/projects/${projectID}/workbench`);
    return response.json();
  }, project);
  expect(after.revision).toBe(before.revision);
  expect(after.event_cursor).toBe(before.event_cursor);
  expect(after.decision.id).toBe(before.decision.id);
  expect(errors).toEqual([]);
});
