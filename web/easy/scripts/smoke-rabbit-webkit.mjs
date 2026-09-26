import { webkit } from '@playwright/test';
import assert from 'node:assert/strict';

// Safari-engine regression: an HTML canvas inside SVG foreignObject could be painted
// at its unscaled backing size. Exercise the bounded HTML renderer at Retina density.
const browser = await webkit.launch();
try {
  for (const [name, width, height] of [
    ['desktop', 1440, 1000],
    ['mobile', 390, 844],
  ]) {
    const context = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 2,
      hasTouch: name === 'mobile',
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('http://127.0.0.1:13190/');
    await page.locator('.rabbit-mesh[data-frame], .rabbit-original-fallback').waitFor();
    await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
    await page.getByRole('button', { name: '开始设计', exact: true }).click();
    await page
      .getByRole('heading', { name: '6 个入选候选', exact: true })
      .waitFor({ timeout: 30000 });
    await page.locator('.easy-steps').getByRole('button', { name: '靶点', exact: true }).click();
    await page.locator('.bunny-magnifier').waitFor();
    await page.locator('.rabbit-mesh[data-frame], .rabbit-original-fallback').waitFor();
    const pet = page.getByRole('button', { name: '和豆豆聊天', exact: true });
    let bounds = await pet.boundingBox();
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.mouse.down();
    await page.mouse.move(width * 0.62, 220, { steps: 15 });
    await page.mouse.up();
    bounds = await pet.boundingBox();
    assert.ok(bounds.y < 220 && bounds.y >= 0, 'dragging stays bounded');
    await page.getByRole('button', { name: '豆豆设置', exact: true }).click();
    await page.getByRole('button', { name: '暂停动画', exact: true }).click();
    await page.keyboard.press('Escape');
    const box = await page.locator('.rabbit-mesh, .rabbit-original-fallback').boundingBox();
    assert.ok(box.width > 50 && box.width < 230 && box.height < 230, JSON.stringify(box));
    assert.equal(await page.locator('foreignObject .rabbit-mesh').count(), 0);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true,
    );
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `docs/easy/rabbit-webkit-${name}.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log(
      `PASS WebKit ${name} at 2x: complete demo, stage gesture, drag, pause, bounded ${Math.round(box.width)}px artwork; no page errors.`,
    );
    await context.close();
  }
} finally {
  await browser.close();
}
