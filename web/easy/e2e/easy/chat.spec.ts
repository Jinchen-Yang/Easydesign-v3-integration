import { expect, test } from '@playwright/test';

test('Doudou offers fresh clickable follow-ups every turn, keeps history and switches language', async ({
  page,
}, info) => {
  const requests: Record<string, unknown>[] = [];
  await page.route('**/api/rabbit/chat', async (route) => {
    if (route.request().method() === 'GET')
      return route.fulfill({ json: { configured: true, model: 'deepseek-flash' } });
    requests.push(route.request().postDataJSON());
    const english = requests.at(-1)!.locale === 'en';
    await route.fulfill({
      contentType: 'application/x-ndjson',
      body: [
        { type: 'delta', text: '你好，我是豆豆。' },
        { type: 'delta', text: '当前是演示页面，我可以陪你聊聊。' },
        {
          type: 'suggestions',
          questions: english
            ? ['What is a VHH?', 'How do I compare candidates?']
            : requests.length === 1
              ? ['你可以帮我做什么？', '这个演示如何开始？']
              : ['如何比较候选？', '结构图应该怎么看？'],
        },
        { type: 'done' },
      ]
        .map((e) => JSON.stringify(e) + '\n')
        .join(''),
    });
  });
  await page.goto('/easy/?mode=demo');
  await page.getByRole('button', { name: '试用溶菌酶 · VHH' }).click();
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  const research = await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'));
  await page.getByRole('button', { name: '和豆豆聊天', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  await expect(panel).toBeVisible();
  await expect(panel.locator('header strong')).toHaveText('豆豆');
  await expect(panel.getByRole('textbox')).toHaveAttribute('placeholder', '问问豆豆…');
  await panel.getByRole('textbox').fill('你好，介绍一下自己');
  await panel.getByRole('button', { name: '发送消息' }).click();
  await expect(panel.locator('.rabbit-message.assistant')).toContainText('当前是演示页面');
  await expect(panel.getByRole('group', { name: '接着聊' }).getByRole('button')).toHaveCount(2);
  await panel.getByRole('button', { name: '你可以帮我做什么？' }).click();
  await expect(panel.locator('.rabbit-message.assistant')).toHaveCount(2);
  await expect(panel.getByRole('button', { name: '如何比较候选？' })).toBeVisible();
  await expect(panel.getByRole('button', { name: '你可以帮我做什么？' })).toHaveCount(0);
  expect(requests).toHaveLength(2);
  expect(requests[1].messages as unknown[]).toHaveLength(3);
  expect((requests[1].messages as { content: string }[]).at(-1)!.content).toBe(
    '你可以帮我做什么？',
  );
  expect(requests[0].context).toMatchObject({ status: 'draft' });
  expect(requests[0]).not.toHaveProperty('key');
  expect(requests[0].context).not.toHaveProperty('file');
  await page.screenshot({ path: `docs/easy/rabbit-chat-${info.project.name}.png`, fullPage: true });
  const b = (await panel.boundingBox())!;
  expect(b.x).toBeGreaterThanOrEqual(0);
  expect(b.y).toBeGreaterThanOrEqual(0);
  expect(b.x + b.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  expect(b.y + b.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  await panel.getByRole('button', { name: '关闭聊天' }).click();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await page.getByRole('button', { name: 'Chat with Doudou', exact: true }).click();
  const englishPanel = page.getByRole('dialog', { name: 'Chat with Doudou' });
  await expect(englishPanel.locator('header strong')).toHaveText('Doudou');
  await englishPanel.getByRole('textbox').fill('Tell me more about this demo.');
  await englishPanel.getByRole('textbox').press('Enter');
  await expect(
    englishPanel
      .getByRole('group', { name: 'Keep chatting' })
      .getByRole('button', { name: 'What is a VHH?' }),
  ).toBeVisible();
  expect(requests[2].locale).toBe('en');
  expect(requests[2].messages as unknown[]).toHaveLength(5);
  await page.getByRole('button', { name: 'New chat' }).click();
  await expect(page.locator('.rabbit-message')).toHaveCount(0);
  await expect(englishPanel.getByRole('group', { name: 'Keep chatting' })).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem('easydesign-easy-preview-v1'))).toBe(
    research,
  );
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Doudou settings', exact: true })
    .click();
  await expect(page.getByRole('button', { name: 'Pause animation' })).toBeVisible();
});

test('unexpected failures retry once while explicit stops remain explicit and retryable', async ({
  page,
}) => {
  let calls = 0;
  await page.route('**/api/rabbit/chat', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { configured: true } });
    calls++;
    if (calls === 1) return route.fulfill({ status: 503, json: { error: 'unavailable' } });
    if (calls === 2)
      return route.fulfill({
        contentType: 'application/x-ndjson',
        body: '{"type":"delta","text":"自动重试成功"}\n{"type":"done"}\n',
      });
    if (calls === 3) {
      await new Promise((r) => setTimeout(r, 2000));
      return route
        .fulfill({ contentType: 'application/x-ndjson', body: '{"type":"done"}\n' })
        .catch(() => {});
    }
    return route.fulfill({
      contentType: 'application/x-ndjson',
      body: '{"type":"delta","text":"<img src=x onerror=alert(1)>"}\n{"type":"done"}\n',
    });
  });
  await page.goto('/easy/?mode=demo');
  await page.getByRole('button', { name: '和豆豆聊天', exact: true }).click();
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  async function send() {
    await panel.getByRole('textbox').fill('你好');
    await panel.getByRole('button', { name: '发送消息' }).click();
  }
  await send();
  await expect(panel.locator('.rabbit-message.assistant').last()).toContainText('自动重试成功');
  await expect(panel.getByRole('group', { name: '接着聊' })).toHaveCount(0);
  expect(calls).toBe(2);
  await send();
  await panel.getByRole('button', { name: '停止回复' }).click();
  await expect(panel.getByText('已停止回复。')).toBeVisible();
  await expect(panel.getByRole('button', { name: '重试回复' })).toBeVisible();
  await expect(panel.getByRole('group', { name: '接着聊' })).toHaveCount(0);
  await panel.getByRole('button', { name: '重试回复' }).click();
  await expect(panel.locator('.rabbit-message.assistant').last()).toContainText('<img');
  expect(await panel.locator('.rabbit-message img').count()).toBe(0);
  await panel.getByRole('textbox').focus();
  await page.keyboard.press('Escape');
  await expect(panel).not.toBeVisible();
});

test('chat never covers the whole rabbit at dragged positions or after a compact resize', async ({
  page,
}, info) => {
  await page.route('**/api/rabbit/chat', (route) => route.fulfill({ json: { configured: true } }));
  await page.goto('/easy/?mode=demo');
  const pet = page.getByRole('button', { name: '和豆豆聊天', exact: true });
  const panel = page.getByRole('dialog', { name: '和豆豆聊天' });
  async function visibleTogether() {
    await expect
      .poll(async () => {
        const a = await pet.boundingBox(),
          b = await panel.boundingBox();
        if (!a || !b) return false;
        const view = page.viewportSize()!;
        return (
          a.x >= 0 &&
          a.y >= 0 &&
          a.x + a.width <= view.width &&
          a.y + a.height <= view.height &&
          b.x >= 0 &&
          b.y >= 0 &&
          b.x + b.width <= view.width &&
          b.y + b.height <= view.height &&
          (a.x + a.width <= b.x ||
            b.x + b.width <= a.x ||
            a.y + a.height <= b.y ||
            b.y + b.height <= a.y)
        );
      })
      .toBe(true);
    expect(
      await pet.evaluate((el) => {
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
      }),
    ).toBe(true);
  }
  for (const [x, y] of [
    [0.9, 0.35],
    [0.5, 0.5],
    [0.05, 0.05],
    [0.5, 0.95],
  ]) {
    const b = (await pet.boundingBox())!;
    const v = page.viewportSize()!;
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.mouse.down();
    await page.mouse.move(v.width * x, v.height * y, { steps: 10 });
    await page.mouse.up();
    const before = await page.evaluate(() => localStorage.getItem('easydesign-rabbit-v1'));
    const original = (await pet.boundingBox())!;
    await pet.click();
    await visibleTogether();
    if (y === 0.35)
      await page.screenshot({
        path: `docs/easy/rabbit-chat-visible-${info.project.name}.png`,
        fullPage: true,
      });
    expect(await page.evaluate(() => localStorage.getItem('easydesign-rabbit-v1'))).toBe(before);
    await panel.getByRole('button', { name: '关闭聊天' }).click();
    expect((await pet.boundingBox())!.x).toBeCloseTo(original.x, 0);
    expect((await pet.boundingBox())!.y).toBeCloseTo(original.y, 0);
  }
  await pet.click();
  for (const [width, height] of [
    [320, 500],
    [390, 360],
    [650, 360],
  ]) {
    await page.setViewportSize({ width, height });
    await visibleTogether();
    await expect(panel.getByRole('textbox')).toBeVisible();
    await panel.getByRole('textbox').fill('豆豆还在！');
  }
});
