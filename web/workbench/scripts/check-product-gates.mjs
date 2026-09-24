import { chromium, expect } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const base = process.env.PRODUCT_URL || 'http://127.0.0.1:14381';
const out = process.env.PRODUCT_RESULTS;
const token = (await fs.readFile(process.env.PRODUCT_TOKEN_FILE, 'utf8')).trim();
const browser = await chromium.launch({
  headless: true,
  args: [
    '--enable-webgl',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
  ],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(120000);
const errors = [],
  gates = [];
page.on('pageerror', (e) => errors.push(e.message));
await fs.mkdir(out, { recursive: true });
let questionPreserved = false;
const snapshot = async () => {
  const id = new URL(page.url()).searchParams.get('project');
  return (await page.request.get(`${base}/api/v1/projects/${id}/workbench`)).json();
};
try {
  await page.request.post(base + '/api/v1/session', { data: { token } });
  await page.goto(
    base +
      (process.env.PRODUCT_PROJECT_ID
        ? '/?project=' + process.env.PRODUCT_PROJECT_ID + '#workspace'
        : '/#projects'),
  );
  if (!process.env.PRODUCT_PROJECT_ID) {
    await page.getByRole('button', { name: 'New project', exact: true }).click();
    await page
      .getByLabel('Your research goal', { exact: true })
      .fill(
        'SYNTHETIC PRODUCT E2E: exploratory VHH design; no biological result, production GPU work, experiments or ordering.',
      );
    await page
      .getByLabel('Target structure · PDB / mmCIF', { exact: true })
      .setInputFiles(process.env.PRODUCT_INPUT_FILE);
    await page.getByRole('button', { name: 'Start design', exact: true }).click();
  }
  for (let gate = Number(process.env.PRODUCT_START_GATE || 1); gate <= 5; gate++) {
    const decision = page.getByRole('region', { name: `Gate ${gate} decision`, exact: true });
    await expect
      .poll(
        async () => {
          if (await decision.isVisible()) return true;
          const resume = page.getByRole('button', { name: 'Continue research', exact: true });
          if ((await resume.isVisible()) && (await resume.isEnabled())) await resume.click();
          return false;
        },
        { timeout: 240000, intervals: [2000, 3000] },
      )
      .toBe(true);
    await expect(decision.locator('.primary-button')).toBeEnabled({ timeout: 240000 });
    if (gate === 2) {
      await page.reload();
      await decision.waitFor({ timeout: 240000 });
      await page.getByRole('button', { name: 'Site B', exact: true }).click();
      await expect(decision.locator('.primary-button')).toHaveText(/Approve Site B/);
      const before = await snapshot();
      const composer = page.getByLabel('Message Design Scientist', { exact: true });
      await expect(composer).toBeEnabled();
      await composer.fill(
        'Why is Site B an alternative? Explain its residues and uncertainties; do not approve.',
      );
      await composer.press('Enter');
      await expect(
        page.locator('.scientist-message').filter({ hasText: 'Its hotspot residues are 3 and 4' }),
      ).toBeVisible({ timeout: 180000 });
      const after = await snapshot();
      expect(after.revision).toBe(before.revision);
      expect(after.decision.id).toBe(before.decision.id);
      expect(after.event_cursor).toBe(before.event_cursor);
      questionPreserved = true;
      await page.reload();
      await expect(
        page.locator('.scientist-message').filter({ hasText: 'Its hotspot residues are 3 and 4' }),
      ).toBeVisible({ timeout: 180000 });
      await page.getByRole('button', { name: 'Site B', exact: true }).click();
      await page.locator('.live-molecule[data-status="ready"]').waitFor();
      const layout = await page.evaluate(() =>
        Object.fromEntries(
          [
            '.project-rail',
            '.workflow',
            '.conversation',
            '.scientific-context',
            '.decision-bar',
            '.conversation-composer',
          ].map((s) => [s, document.querySelector(s).getBoundingClientRect().toJSON()]),
        ),
      );
      expect(layout['.decision-bar'].y).toBeGreaterThan(layout['.conversation-composer'].y);
      expect(layout['.scientific-context'].x).toBeGreaterThan(layout['.conversation'].x);
      expect(layout['.conversation'].x).toBeGreaterThan(layout['.workflow'].x);
      expect(layout['.project-rail'].width).toBeGreaterThan(200);
      await fs.writeFile(path.join(out, 'prototype-layout.json'), JSON.stringify(layout, null, 2));
    }
    await page.screenshot({ path: path.join(out, `product-gate-${gate}.png`), fullPage: true });
    const state = await snapshot();
    gates.push({ gate, card: state.decision.id, project: state.project.id });
    console.log(JSON.stringify({ gate, ready: true }));
    await decision.locator('.primary-button').click();
  }
  await expect(
    page
      .getByRole('region', { name: 'Research status', exact: true })
      .locator('.decision-copy strong'),
  ).toHaveText('Panel finalized', { timeout: 240000 });
  await page.reload();
  await expect(page.locator('.live-candidate-select')).toHaveCount(6, { timeout: 180000 });
  await page.locator('.live-molecule[data-status="ready"]').waitFor({ timeout: 120000 });
  const final = await snapshot();
  if (process.env.PRODUCT_PROJECT_ID) {
    questionPreserved = final.conversation.some(
      (m) => m.kind === 'user' && m.text.startsWith('Why is Site B an alternative?'),
    );
    expect(questionPreserved).toBe(true);
  }
  expect(final.scientific_context.approved_site.selected_rank).toBe('B');
  expect(final.scientific_context.approved_site.hotspots.hotspot_sets[0].label_seq_ids).toEqual([
    3, 4,
  ]);
  expect(final.candidates.counts).toEqual({ pass: 3, fail: 3 });
  expect(final.scientific_context.campaign.production_intent.requested_scale_candidates).toBe(30);
  expect(final.scientific_context.campaign.execution.execution_candidates).toBe(6);
  expect(final.scientific_context.campaign.production_intent.authorizes_production_compute).toBe(
    false,
  );
  expect(final.project.validation_only).toBe(true);
  await page.getByLabel('Reset structure view', { exact: true }).click();
  await page.screenshot({ path: path.join(out, 'product-handoff.png'), fullPage: true });
  await page.getByTestId('phase-site').click();
  await page.getByRole('button', { name: 'Site B', exact: true }).click();
  await expect
    .poll(
      async () =>
        page.evaluate(() =>
          document
            .querySelector('.live-canvas canvas')
            ?._3dmol_viewer?.selectedAtoms({ chain: 'A', atom: 'CA' })
            .map((a) => ({ residue: a.resi, color: a.style.sphere?.color })),
        ),
      { timeout: 120000 },
    )
    .toEqual([
      { residue: 1, color: '#d5d1ea' },
      { residue: 2, color: '#d5d1ea' },
      { residue: 3, color: '#8270d4' },
      { residue: 4, color: '#8270d4' },
      { residue: 5, color: '#d5d1ea' },
      { residue: 6, color: '#d5d1ea' },
    ]);
  await page.screenshot({ path: path.join(out, 'product-target-hotspots.png'), fullPage: true });
  await page.getByTestId('phase-candidates').click();
  await page.locator('.live-molecule[data-status="ready"]').waitFor();
  expect(errors).toEqual([]);
  const result = {
    gates,
    completed: true,
    reload: true,
    project: final.project.id,
    selectedRank: final.scientific_context.approved_site.selected_rank,
    candidates: final.candidates.counts,
    validationOnly: true,
    productionIntent: 30,
    validationExecution: 6,
    questionPreserved,
    errors,
  };
  await fs.writeFile(path.join(out, 'product-gates-browser.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} catch (error) {
  await page.screenshot({ path: path.join(out, 'product-gates-failure.png'), fullPage: true });
  console.log((await page.locator('body').innerText()).slice(-5000));
  console.error(String(error).replaceAll(token, '[redacted]'));
  process.exitCode = 1;
} finally {
  await browser.close();
}
