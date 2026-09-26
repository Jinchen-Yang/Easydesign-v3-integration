import { webkit } from '@playwright/test';
import assert from 'node:assert/strict';

// Explicit, opt-in paid API smoke: three calls. Ordinary regression tests mock chat.
const browser = await webkit.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('http://127.0.0.1:13190/');
  await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  const before = await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));
  await page.getByRole('button', { name: '和豆豆聊天', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  await panel.getByRole('textbox').fill('你好，请介绍一下你自己，再用一句话解释什么是 VHH。');
  const started = Date.now();
  await panel.getByRole('button', { name: '发送消息' }).click();
  await page.waitForFunction(
    () => {
      const el = document.querySelector('.rabbit-message.assistant');
      return (
        el &&
        Array.from(el.childNodes).some(
          (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim().length > 0,
        )
      );
    },
    null,
    { timeout: 90000 },
  );
  const firstTextSeconds = (Date.now() - started) / 1000;
  await panel.getByRole('button', { name: '发送消息' }).waitFor({ timeout: 90000 });
  assert.equal(await panel.locator('.rabbit-chat-error').count(), 0);
  const answerText = () =>
    page
      .locator('.rabbit-message.assistant')
      .last()
      .evaluate((el) =>
        Array.from(el.childNodes)
          .filter((n) => n.nodeType === Node.TEXT_NODE)
          .map((n) => n.textContent)
          .join(''),
      );
  const firstReply = await answerText();
  assert.ok(firstReply.includes('豆豆'));
  const followups = panel.getByRole('group', { name: '接着聊' });
  const firstQuestions = await followups.getByRole('button').allTextContents();
  assert.ok(firstQuestions.length >= 2 && firstQuestions.length <= 3);
  assert.match(firstQuestions.join(' '), /VHH|抗体/i);
  await followups.getByRole('button').first().click();
  await panel.getByRole('button', { name: '发送消息' }).waitFor({ timeout: 90000 });
  const secondReply = await answerText();
  const secondQuestions = await followups.getByRole('button').allTextContents();
  assert.ok(secondQuestions.length >= 2 && secondQuestions.length <= 3);
  assert.notDeepEqual(firstQuestions, secondQuestions);
  assert.equal(
    await panel.locator('.rabbit-message.user').last().innerText(),
    '你' + firstQuestions[0],
  );
  assert.ok(!(await panel.innerText()).includes('<doudou_questions>'));
  assert.equal(await panel.locator('.rabbit-chat-error').count(), 0);
  assert.equal(
    await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1')),
    before,
  );
  assert.deepEqual(errors, []);
  await page.screenshot({ path: 'docs/easy/rabbit-chat-live-webkit-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const box = await panel.boundingBox();
  assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= 390 && box.y + box.height <= 844);
  await page.screenshot({ path: 'docs/easy/rabbit-chat-live-webkit-mobile.png', fullPage: true });
  await panel.getByRole('button', { name: '关闭聊天' }).click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await page.getByRole('button', { name: 'Chat with Doudou', exact: true }).click();
  const englishPanel = page.getByRole('dialog', { name: 'Chat with Doudou' });
  await englishPanel.getByRole('button', { name: 'New chat' }).click();
  await englishPanel
    .getByRole('textbox')
    .fill('I like growing basil on my balcony. Give me one easy watering tip.');
  await englishPanel.getByRole('button', { name: 'Send message' }).click();
  await englishPanel.getByRole('button', { name: 'Send message' }).waitFor({ timeout: 90000 });
  assert.equal(await englishPanel.locator('.rabbit-chat-error').count(), 0);
  const englishQuestions = await englishPanel
    .getByRole('group', { name: 'Keep chatting' })
    .getByRole('button')
    .allTextContents();
  assert.ok(englishQuestions.length >= 2 && englishQuestions.length <= 3);
  assert.match(englishQuestions.join(' '), /basil|water|soil|herb|plant/i);
  assert.ok(!/[\u4e00-\u9fff]/u.test(englishQuestions.join('')));
  assert.ok(!(await englishPanel.innerText()).includes('<doudou_questions>'));
  assert.deepEqual(errors, []);
  await page.screenshot({ path: 'docs/easy/doudou-followups-english.png', fullPage: true });
  console.log(
    JSON.stringify(
      {
        passed: true,
        firstTextSeconds,
        firstReply,
        secondReply,
        firstQuestions,
        secondQuestions,
        englishQuestions,
        engine: 'WebKit',
        researchUnchanged: true,
      },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
}
