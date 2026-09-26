import { expect, test } from '@playwright/test';

test('bunny controls, original album and saved preferences preserve research data', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  const companion = page.getByRole('complementary', { name: 'EasyDesign 豆豆' });
  await expect(companion).toHaveAttribute('data-motion', 'playing');
  // Check real transparency, not a white or checkerboard rectangle.
  const alpha = await page.evaluate(async () => {
    const img = new Image();
    img.src = '/mascot/rabbit/rabbit-mascot.png';
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(img, 0, 0);
    return [
      ctx.getImageData(0, 0, 1, 1).data[3],
      ctx.getImageData(canvas.width / 2, canvas.height / 2, 1, 1).data[3],
    ];
  });
  expect(alpha[0]).toBe(0);
  expect(alpha[1]).toBeGreaterThanOrEqual(240);
  await page.screenshot({ path: `docs/easy/bunny-${info.project.name}.png`, fullPage: true });
  await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  const research = await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await page.getByRole('button', { name: '暂停动画', exact: true }).click();
  await expect(companion).toHaveAttribute('data-motion', 'paused');
  expect(
    await page.locator('.bunny-body').evaluate((el) => getComputedStyle(el).animationPlayState),
  ).toBe('paused');
  await page.getByRole('button', { name: '换到另一侧' }).click();
  await expect(companion).toHaveClass(/left/);
  await page.getByRole('button', { name: '豆豆相册', exact: true }).click();
  const album = page.getByRole('dialog', { name: '豆豆相册' });
  await expect(album).toBeVisible();
  await expect(album.getByRole('group').getByRole('button')).toHaveCount(7);
  await album.getByRole('button', { name: '引导', exact: true }).click();
  await expect(album.locator('.rabbit-album-main')).toHaveAttribute('src', /07-guide.jpg$/);
  await expect(album.getByRole('link', { name: '下载原图' })).toHaveAttribute('download', '');
  await page.screenshot({ path: `docs/easy/bunny-album-${info.project.name}.png`, fullPage: true });
  await page.keyboard.press('Escape');
  await expect(album).not.toBeVisible();
  await page.getByRole('button', { name: '收起豆豆', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('button', { name: '显示豆豆' })).toBeVisible();
  await expect(companion).toHaveClass(/left/);
  await page.getByRole('button', { name: '显示豆豆' }).click();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await page.getByRole('button', { name: 'Doudou settings', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Resume animation' })).toBeVisible();
  await page.getByRole('button', { name: 'Resume animation' }).click();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'playing');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Chat with Doudou', exact: true })).toBeFocused();
  expect(await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'))).toBe(
    research,
  );
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('system reduced motion pauses by default and responds to preference changes', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'paused');
  expect(
    await page.locator('.bunny-body').evaluate((el) => getComputedStyle(el).animationPlayState),
  ).toBe('paused');
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await expect(page.getByRole('button', { name: '播放豆豆动画' })).toBeEnabled();
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'playing');
  await expect(page.getByRole('button', { name: '暂停动画' })).toBeEnabled();
});

test('missing mascot image leaves a usable companion and design form', async ({ page }) => {
  await page.route('**/mascot/rabbit/rabbit-mascot.png', (route) => route.abort());
  await page.goto('/');
  await expect(page.locator('.rabbit-fallback')).toBeVisible();
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await page.getByRole('button', { name: '关闭豆豆设置' }).click();
  await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
  await expect(page.getByRole('button', { name: '开始设计', exact: true })).toBeEnabled();
});

test('drag, keyboard positioning, reload, viewport boundaries and click separation', async ({
  page,
}, info) => {
  await page.goto('/');
  const pet = page.getByRole('button', { name: '和豆豆聊天', exact: true });
  const root = page.locator('.rabbit-companion');
  const initial = (await pet.boundingBox())!;
  const target = { x: page.viewportSize()!.width * 0.38, y: 210 };
  await page.mouse.move(initial.x + initial.width / 2, initial.y + initial.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y, { steps: 15 });
  await page.mouse.up();
  await expect(page.locator('.rabbit-popover')).not.toBeVisible();
  await expect(root).toHaveAttribute('data-dragging', 'false');
  const moved = (await root.boundingBox())!;
  expect(moved.y).toBeLessThan(initial.y - 100);
  const saved = await page.evaluate(
    () => JSON.parse(localStorage.getItem('easydesign-rabbit-v1')!).position,
  );
  await page.reload();
  expect(
    await page.evaluate(() => JSON.parse(localStorage.getItem('easydesign-rabbit-v1')!).position),
  ).toEqual(saved);
  expect((await root.boundingBox())!.y).toBeCloseTo(moved.y, 0);
  await pet.focus();
  await page.keyboard.press('ArrowDown');
  expect((await root.boundingBox())!.y).toBeCloseTo(moved.y + 20, 0);
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  const menu = page.locator('.rabbit-popover');
  await expect(menu).toBeVisible();
  const menuBounds = (await menu.boundingBox())!;
  expect(menuBounds.x).toBeGreaterThanOrEqual(0);
  expect(menuBounds.y).toBeGreaterThanOrEqual(0);
  expect(menuBounds.x + menuBounds.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  await page.keyboard.press('Escape');
  if (info.project.name === 'mobile') {
    const client = await page.context().newCDPSession(page);
    const bounds = (await pet.boundingBox())!;
    const x = bounds.x + bounds.width / 2,
      y = bounds.y + bounds.height / 2;
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: x + 45, y: y + 80 }],
    });
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    expect((await pet.boundingBox())!.y).toBeGreaterThan(bounds.y + 60);
    await expect(menu).not.toBeVisible();
    await client.detach();
  }
  await page.setViewportSize({ width: 320, height: 500 });
  await expect
    .poll(async () => {
      const box = (await root.boundingBox())!;
      return box.x + box.width;
    })
    .toBeLessThanOrEqual(320);
  const small = (await root.boundingBox())!;
  expect(small.x).toBeGreaterThanOrEqual(0);
  expect(small.y).toBeGreaterThanOrEqual(0);
  expect(small.x + small.width).toBeLessThanOrEqual(320);
  expect(small.y + small.height).toBeLessThanOrEqual(500);
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await page.getByRole('button', { name: '回到右下角' }).click();
  const reset = (await root.boundingBox())!;
  expect(reset.x + reset.width).toBeCloseTo(308, 0);
  expect(reset.y + reset.height).toBeCloseTo(488, 0);
});

test('live six-stage gestures, continuous rendering and completed-stage review preserve results', async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/');
  await expect(page.locator('.rabbit-mesh')).toHaveAttribute('data-frame', /\d+/);
  const first = Number(await page.locator('.rabbit-mesh').getAttribute('data-frame'));
  await expect
    .poll(async () => Number(await page.locator('.rabbit-mesh').getAttribute('data-frame')))
    .toBeGreaterThan(first + 100);
  await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
  await page.evaluate(() => {
    const root = document.querySelector('.rabbit-companion')!;
    const observed: string[] = [];
    const observer = new MutationObserver(() => {
      const stage = root.getAttribute('data-stage');
      const animation = getComputedStyle(root.querySelector('.bunny-body')!).animationName;
      observed.push(stage + ':' + animation);
      document.documentElement.dataset.rabbitTrace = JSON.stringify(observed);
    });
    observer.observe(root, { attributes: true, attributeFilter: ['data-stage'] });
  });
  await page.getByRole('button', { name: '开始设计', exact: true }).click();
  const steps = [
    ['Target', '靶点', 'bunny-search'],
    ['Site', '位点', 'bunny-point'],
    ['Design', '设计', 'bunny-work'],
    ['Pilot', '试运行', 'bunny-work'],
    ['Scale', '扩展', 'bunny-batch'],
    ['Candidates', '候选', 'bunny-cheer'],
  ];
  await expect(page.getByRole('heading', { name: '6 个入选候选', exact: true })).toBeVisible({
    timeout: 25000,
  });
  const trace = await page.evaluate(() =>
    JSON.parse(document.documentElement.dataset.rabbitTrace || '[]'),
  );
  expect(trace).toEqual(steps.map(([stage, , animation]) => stage + ':' + animation));
  const research = await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));
  // Move out of the workflow hit targets before using the finished-stage controls.
  const pet = page.getByRole('button', { name: '和豆豆聊天', exact: true });
  await pet.focus();
  await page.keyboard.press('ArrowUp');
  for (const [stage, label] of steps) {
    await page.locator('.easy-steps').getByRole('button', { name: label, exact: true }).click();
    await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-stage', stage);
    await expect(page.locator('.rabbit-mesh')).toHaveAttribute('data-frame', /\d+/);
    await page.mouse.move(0, 0);
    await page
      .locator('.rabbit-companion')
      .screenshot({ path: `docs/easy/rabbit-${stage.toLowerCase()}-${info.project.name}.png` });
  }
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await page.getByRole('button', { name: '暂停动画', exact: true }).click();
  const frozen = await page.locator('.rabbit-mesh').getAttribute('data-frame');
  await page.waitForTimeout(160);
  expect(await page.locator('.rabbit-mesh').getAttribute('data-frame')).toBe(frozen);
  expect(
    await page.locator('.bunny-body').evaluate((el) => getComputedStyle(el).animationPlayState),
  ).toBe('paused');
  expect(await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'))).toBe(
    research,
  );
  expect(errors).toEqual([]);
});

test('reduced-motion playback is explicit and the artwork has a WebGL fallback', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'paused');
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await page.getByRole('button', { name: '播放豆豆动画' }).click();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'playing');
  expect(
    await page.locator('.bunny-body').evaluate((el) => getComputedStyle(el).animationName),
  ).toBe('bunny-bounce');
  await page.reload();
  await expect(page.locator('.rabbit-companion')).toHaveAttribute('data-motion', 'playing');
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...args: unknown[]
    ) {
      if (type === 'webgl') return null;
      return Reflect.apply(original, this, [type, ...args]);
    } as typeof original;
  });
  await page.reload();
  await expect(page.locator('.rabbit-original-fallback')).toBeVisible();
  await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
  await expect(page.getByRole('button', { name: '豆豆相册', exact: true })).toBeVisible();
});
