import { expect, test } from '@playwright/test';

const savedRun = (page: import('@playwright/test').Page) =>
  page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));

test('Chinese default, readable text and persistent language switching preserve work', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '开始设计' })).toBeVisible();
  await expect(page.getByRole('button', { name: '中文', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(page.getByLabel('输入类型').locator('option')).toHaveCount(8);
  // Readable controls and secondary text: measure actual computed styles, not declared tokens.
  const styles = await page.evaluate(() => {
    const input = getComputedStyle(document.querySelector('#easy-target-input')!);
    const note = getComputedStyle(document.querySelector('.easy-demo-note')!);
    const channels = note.color
      .match(/[\d.]+/g)!
      .slice(0, 3)
      .map(Number)
      .map((c) => c / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
    const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    return {
      inputSize: parseFloat(input.fontSize),
      noteSize: parseFloat(note.fontSize),
      contrastOnWhite: 1.05 / (luminance + 0.05),
    };
  });
  expect(styles.inputSize).toBeGreaterThanOrEqual(16);
  expect(styles.noteSize).toBeGreaterThanOrEqual(14);
  expect(styles.contrastOnWhite).toBeGreaterThanOrEqual(4.5);
  await page.screenshot({ path: `docs/easy/landing-zh-${info.project.name}.png`, fullPage: true });
  await page.getByLabel('输入类型').selectOption('uniprot');
  await page.getByLabel('UniProt 编号', { exact: true }).fill('bad');
  await expect(page.getByRole('status')).toContainText('请输入有效的 UniProt 编号');
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Enter a valid UniProt accession');
  await expect(page.getByLabel('UniProt ID', { exact: true })).toHaveValue('bad');
  await page.getByLabel('Input type').selectOption('description');
  const goal = '设计一个针对溶菌酶的 VHH，优先选择易接近的表位。';
  await page.getByLabel('Description', { exact: true }).fill(goal);
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  const draft = await savedRun(page);
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('草稿已保存到当前设备');
  await expect(page.getByLabel('自然语言', { exact: true })).toHaveValue(goal);
  expect(await savedRun(page)).toBe(draft);
  await page.getByRole('button', { name: '开始设计', exact: true }).click();
  await page.getByRole('button', { name: '暂停演示', exact: true }).click();
  const paused = await savedRun(page);
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Paused', exact: true })).toBeVisible();
  expect(await savedRun(page)).toBe(paused);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Paused', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await expect(page.getByRole('heading', { name: '6 个入选候选', exact: true })).toBeVisible({
    timeout: 20000,
  });
  await expect(page.getByRole('group', { name: '演示入选候选' }).getByRole('button')).toHaveCount(
    6,
  );
  await expect(page.getByLabel('结构链')).toBeVisible();
  await expect(page.getByRole('button', { name: '带状', exact: true })).toBeVisible();
  await page.screenshot({ path: `docs/easy/results-zh-${info.project.name}.png`, fullPage: true });
  const complete = await savedRun(page);
  await page.getByRole('button', { name: '位点', exact: true }).click();
  await expect(page.getByRole('heading', { name: '位点 B', exact: true })).toBeVisible();
  await expect(page.getByText('已高亮位点 B', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Site B', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Site', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(await savedRun(page)).toBe(complete);
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await page.getByRole('button', { name: '使用指南', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('不提交 GPU 任务');
  await page.keyboard.press('Escape');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '6 个入选候选', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
