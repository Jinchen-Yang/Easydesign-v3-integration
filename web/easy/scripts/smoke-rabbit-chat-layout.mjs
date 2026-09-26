import { webkit } from '@playwright/test';
import assert from 'node:assert/strict';

const browser = await webkit.launch();
try {
  for (const [name, width, height] of [
    ['desktop', 1440, 1000],
    ['mobile', 390, 844],
  ]) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 2 });
    await page.route('**/api/rabbit/chat', (route) =>
      route.fulfill({ json: { configured: true } }),
    );
    await page.goto('http://127.0.0.1:13190/');
    const pet = page.getByRole('button', { name: '和豆豆聊天', exact: true });
    const initial = await pet.boundingBox();
    await page.mouse.move(initial.x + initial.width / 2, initial.y + initial.height / 2);
    await page.mouse.down();
    await page.mouse.move(width * 0.9, height * 0.35, { steps: 15 });
    await page.mouse.up();
    assert.ok(
      (await pet.boundingBox()).y < initial.y - 100,
      'exercise a genuinely dragged position',
    );
    await pet.click();
    const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
    await panel.getByRole('textbox').fill('你好，豆豆！');
    await page.locator('.rabbit-mesh[data-frame], .rabbit-original-fallback').waitFor();
    const a = await pet.boundingBox(),
      b = await panel.boundingBox();
    assert.ok(
      a.x + a.width <= b.x ||
        b.x + b.width <= a.x ||
        a.y + a.height <= b.y ||
        b.y + b.height <= a.y,
      'bunny is outside the chat panel',
    );
    assert.ok(a.x >= 0 && a.y >= 0 && a.x + a.width <= width && a.y + a.height <= height);
    await page.screenshot({
      path: `docs/easy/rabbit-chat-visible-webkit-${name}.png`,
      fullPage: true,
    });
    console.log(
      `PASS WebKit ${name}: full animated bunny remains visible beside the open conversation.`,
    );
    await page.close();
  }
} finally {
  await browser.close();
}
