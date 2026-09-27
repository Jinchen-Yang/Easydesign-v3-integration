import { expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';

test('live project open and Site switching stay within the interactive budget', async ({
  page,
}) => {
  const pdb = await readFile('public/structures/1MEL.pdb');
  const sha256 = createHash('sha256').update(pdb).digest('hex');
  let artifactRequests = 0;
  const artifact = {
    id: sha256,
    label: 'Verified target',
    url: `/api/v1/artifacts/${sha256}`,
    format: 'pdb',
    sha256,
    size_bytes: pdb.byteLength,
    role: 'structure',
    candidate_id: null,
  };
  const project = {
    id: 'performance-project',
    title: 'Performance regression',
    goal: 'Design an extracellular VHH.',
    thread_id: 'thread',
    phase: 'candidates',
    status: 'complete',
    last_activity: 42,
    validation_only: true,
  };
  const sites = ['A', 'B', 'C'].map((rank, index) => ({
    id: `site-${rank}`,
    rank,
    name: `Site ${rank}`,
    selectable: true,
    design_labels: [index + 1],
    why_ranked: 'Verified fixture',
    risks: [],
    uncertainty: [],
    confidence: 'medium',
    coordinates: [
      { author_chain_id: 'A', author_residue_id: String(index + 1), insertion_code: '' },
    ],
  }));
  const snapshot = {
    schema_version: '1',
    mode: 'live',
    revision: 'a'.repeat(64),
    project,
    workflow: ['target', 'site', 'design', 'pilot', 'scale', 'candidates'].map((id) => ({
      id,
      label: id,
      status: 'complete',
      gate: null,
      subtasks: [{ label: 'Verified', status: 'complete' }],
    })),
    current_action: {
      id: 'complete',
      stage: 'handoff-complete',
      message: 'Complete',
      resumable: false,
    },
    specialists: [],
    scientific_context: {
      target_id: 'TACR2',
      sequence_length: 398,
      chains: ['A'],
      structure: artifact,
      sites,
      approved_site: { selected_candidate_id: 'site-A', selected_rank: 'A', hotspots: {} },
      arms: [{ arm_id: 'arm-1' }],
      design_approved: true,
    },
    decision: null,
    jobs: [],
    artifacts: [],
    recent_activity: [],
    tasks: [],
    lifecycle: 'scientific_project',
    event_cursor: 42,
    candidates: { total: 1, counts: { pass: 1 }, url: '/candidates' },
    capabilities: {},
    requests: [],
    lab_order: null,
    connection: 'connected',
  };
  await page.route('**/api/v1/projects?**', (route) =>
    route.fulfill({ json: { items: [project], total: 1, offset: 0, limit: 5 } }),
  );
  await page.route('**/api/v1/projects/performance-project/workbench', (route) =>
    route.fulfill({ json: snapshot }),
  );
  await page.route('**/api/v1/projects/performance-project/candidates?**', async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('view')).toBe('summary');
    expect(url.searchParams.get('limit')).toBe('100');
    const phase = url.searchParams.get('phase') || 'candidates';
    const rows =
      phase === 'pilot'
        ? [
            { id: 'pilot-pass', status: 'pass', scaffold: '7xl0' },
            { id: 'pilot-fail', status: 'fail', scaffold: '8z8v' },
          ]
        : phase === 'scale'
          ? [
              { id: 'scale-pass-1', status: 'pass', scaffold: '7eow' },
              { id: 'scale-pass-2', status: 'pass', scaffold: '8coh' },
            ]
          : [{ id: 'candidate-1', status: 'pass', scaffold: '7eow' }];
    await route.fulfill({
      json: {
        items: rows.map((row, index) => ({
          id: row.id,
          arm: `arm-1-scaffold-${row.scaffold}`,
          backend_id: null,
          scaffold: row.scaffold,
          native_status: row.status,
          evaluable: true,
          competition_eligible: row.status === 'pass',
          independent_prediction: 'complete',
          sequence: 'AAA',
          sequence_sha256: 'b'.repeat(64),
          metrics: [],
          artifacts: [{ ...artifact, candidate_id: row.id }],
          panel_role: phase === 'candidates' && index === 0 ? 'primary' : null,
          failure_reason: null,
          lineage: {},
          structure_roles: { A: 'target', B: 'binder' },
        })),
        total: rows.length,
        offset: 0,
        limit: 100,
      },
    });
  });
  await page.route(`**/api/v1/artifacts/${sha256}`, async (route) => {
    artifactRequests++;
    await route.fulfill({ body: pdb, contentType: 'chemical/x-pdb' });
  });

  await page.goto('/easy/');
  const started = Date.now();
  await page.getByRole('button', { name: '打开', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Candidates', exact: true })).toBeVisible();
  expect(Date.now() - started).toBeLessThan(1500);
  await expect(page.locator('.molecule[data-status="ready"]')).toBeVisible();
  // Software WebGL in CI is slower than a user's GPU-backed browser, but a cold
  // viewer must still become interactive within a tight bounded interval.
  expect(Date.now() - started).toBeLessThan(3000);
  expect(artifactRequests).toBe(1);

  const switched = Date.now();
  await page.getByRole('button', { name: 'Site B', exact: true }).click();
  await expect(page.getByText('Site B highlighted')).toBeVisible();
  expect(Date.now() - switched).toBeLessThan(500);
  expect(artifactRequests).toBe(1);
  await expect(page.getByText('Loading verified coordinates…')).toHaveCount(0);

  await expect(page.locator('.pdb-label')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Top 1/ })).toContainText('主候选');
  await expect(page.getByText('primary', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: 'Pilot', exact: true }).click();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-stage', 'Pilot');
  await expect(page.getByRole('region', { name: '真实执行进度' })).toContainText('2 / 2 条');
  await expect(page.getByText('Scaffold 7XL0')).toBeVisible();
  await expect(page.getByText('查看未通过或未完成的候选（1）')).toBeVisible();

  await page.getByRole('button', { name: 'Scale', exact: true }).click();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-stage', 'Scale');
  await expect(page.getByRole('region', { name: '真实执行进度' })).toContainText('2 / 2 条');
  await expect(page.getByText('Scaffold 8COH')).toBeVisible();

  await page.getByRole('button', { name: 'Candidates', exact: true }).click();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-stage', 'Candidates');
  await expect(page.getByRole('region', { name: '真实执行进度' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Top 1/ })).toContainText('主候选');

  await page.getByRole('button', { name: 'Target', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Target history' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Target 阶段记录' })).toBeVisible();
});
