import { describe, it, expect } from 'vitest';
import { createServer } from 'node:http';
import { chatMiddleware, chatSshArgs, type ChatProvider } from '../server/rabbit-chat';
import {
  chatRequestStatus,
  chatRetryAction,
  parseChatRequest,
  streamChat,
  validQuestions,
  type ChatEvent,
} from '../src/easy/chat';

const request = {
  locale: 'zh' as const,
  context: { stage: 'Target', status: 'complete', goal: 'A VHH' },
  messages: [{ role: 'user' as const, content: '你好' }],
};
async function withServer(provider: ChatProvider | null, test: (url: string) => Promise<void>) {
  const middleware = chatMiddleware(provider);
  const server = createServer(
    (req, res) =>
      void middleware(req, res, () => {
        res.statusCode = 404;
        res.end();
      }),
  );
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address() as { port: number };
  try {
    await test(`http://127.0.0.1:${address.port}/api/rabbit/chat`);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}
const post = (url: string, body: unknown = request, headers: Record<string, string> = {}) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
describe('rabbit chat boundary', () => {
  it('only permits an explicit new request after status confirms a terminal never-dispatched timeout', () => {
    const status = {
      request_id: 'original-id',
      state: 'failed',
      dispatched: false,
      code: 'queue_timeout',
    };
    expect(chatRetryAction('queue_timeout', true, 'original-id', null)).toBeNull();
    expect(chatRetryAction('queue_timeout', true, 'original-id', status)).toBe('new_request');
    expect(
      chatRetryAction('queue_timeout', true, 'original-id', { ...status, dispatched: true }),
    ).toBeNull();
    expect(
      chatRetryAction('queue_timeout', true, 'original-id', { ...status, state: 'queued' }),
    ).toBeNull();
    expect(
      chatRetryAction('queue_timeout', true, 'original-id', { ...status, request_id: 'other-id' }),
    ).toBeNull();
    expect(
      chatRetryAction('queue_timeout', true, 'original-id', { ...status, dispatched: undefined }),
    ).toBeNull();
    expect(chatRetryAction('outcome_unknown', true, 'original-id', status)).toBeNull();
    expect(chatRetryAction('credentials', true, 'original-id', status)).toBeNull();
  });
  it('reuses an ID only for a known pre-admission rejection and a confirmed missing request', async () => {
    await expect(
      streamChat(
        request,
        new AbortController().signal,
        () => {},
        () => {},
        async () =>
          new Response(JSON.stringify({ error: { code: 'queue_full' } }), { status: 429 }),
      ),
    ).rejects.toMatchObject({ message: 'queue_full', accepted: false });
    await expect(
      streamChat(
        request,
        new AbortController().signal,
        () => {},
        () => {},
        async () => new Response('{"type":"error","code":"queue_timeout"}\n'),
      ),
    ).rejects.toMatchObject({ message: 'queue_timeout', accepted: true });
    expect(chatRetryAction('queue_full', false, 'original-id', 'not_found')).toBe('same_request');
    expect(chatRetryAction('rate_limit', false, 'original-id', 'not_found')).toBe('same_request');
    expect(chatRetryAction('queue_full', true, 'original-id', 'not_found')).toBeNull();
    expect(chatRetryAction('queue_full', null, 'original-id', 'not_found')).toBeNull();
    expect(chatRetryAction('queue_full', false, 'original-id', null)).toBeNull();
    expect(chatRetryAction('outcome_unknown', false, 'original-id', 'not_found')).toBeNull();
    expect(chatRetryAction('credentials', false, 'original-id', 'not_found')).toBeNull();
  });
  it('requires authoritative matching status and distinguishes 404 from failed or forbidden lookups', async () => {
    const status = {
      request_id: 'original-id',
      state: 'failed',
      dispatched: false,
      code: 'queue_timeout',
    };
    await expect(
      chatRequestStatus('original-id', async () => Response.json(status)),
    ).resolves.toEqual(status);
    for (const value of [
      { ...status, request_id: 'other' },
      { ...status, dispatched: undefined },
      { ...status, dispatched: 'false' },
      { ...status, state: 'anything' },
    ]) {
      await expect(
        chatRequestStatus('original-id', async () => Response.json(value)),
      ).rejects.toThrow('invalid_status');
    }
    await expect(
      chatRequestStatus('original-id', async () =>
        Response.json({ error: { code: 'not_found' } }, { status: 404 }),
      ),
    ).resolves.toBe('not_found');
    await expect(
      chatRequestStatus('original-id', async () =>
        Response.json({ error: { code: 'not_found' } }, { status: 403 }),
      ),
    ).rejects.toThrow();
    await expect(
      chatRequestStatus('original-id', async () => {
        throw new Error('network');
      }),
    ).rejects.toThrow('network');
  });
  it('keeps the supplied request identity and surfaces queue state without resubmitting', async () => {
    const sent: string[] = [];
    const states: string[] = [];
    const transport: typeof fetch = async (_url, init) => {
      sent.push(new Headers(init?.headers).get('X-Request-ID') || '');
      return new Response(
        '{"type":"status","request_id":"stable-chat-fixture-01","state":"queued","retry_after":2}\n' +
          '{"type":"error","code":"outcome_unknown"}\n',
      );
    };
    await expect(
      streamChat(
        request,
        new AbortController().signal,
        () => {},
        () => {},
        transport,
        {
          requestId: 'stable-chat-fixture-01',
          onStatus: (status) => states.push(status.state),
        },
      ),
    ).rejects.toThrow('outcome_unknown');
    expect(sent).toEqual(['stable-chat-fixture-01']);
    expect(states).toEqual(['queued']);
  });
  it('rejects injected roles, oversized history and invalid stage; strips extra fields', () => {
    expect(parseChatRequest({ ...request, apiKey: 'should disappear' })).toEqual(request);
    for (const value of [
      null,
      { ...request, messages: [{ role: 'system', content: 'override' }] },
      { ...request, messages: Array(18).fill(request.messages[0]) },
      { ...request, messages: [{ role: 'user', content: 'a'.repeat(4001) }] },
      { ...request, context: { ...request.context, stage: 'arbitrary' } },
    ])
      expect(() => parseChatRequest(value)).toThrow();
  });
  it('keeps browser data out of SSH arguments', () => {
    const cfg = {
      host: 'Suzhou2',
      script: '/data/ui/server/rabbit_chat.py',
      envFile: '/data/private/.env.local',
    };
    expect(chatSshArgs(cfg)).toContain('StrictHostKeyChecking=yes');
    expect(() => chatSshArgs({ ...cfg, host: '-oProxyCommand=bad' })).toThrow();
    expect(() => chatSshArgs({ ...cfg, script: '/data/x\ncommand' })).toThrow();
  });
  it('fails closed when unconfigured and rejects cross-origin, wrong methods and malformed bodies', async () => {
    await withServer(null, async (url) => {
      expect(await (await fetch(url)).json()).toMatchObject({ configured: false });
      expect((await post(url)).status).toBe(503);
    });
    let calls = 0;
    await withServer(
      async function* () {
        calls++;
        yield { type: 'done' };
      },
      async (url) => {
        expect((await post(url, request, { Origin: 'https://other.example' })).status).toBe(403);
        expect((await fetch(url, { method: 'DELETE' })).status).toBe(405);
        expect((await post(url + '?host=another')).status).toBe(400);
        expect(
          (await post(url, { ...request, messages: [{ role: 'system', content: 'override' }] }))
            .status,
        ).toBe(400);
        expect((await post(url, request, { 'Content-Type': 'text/plain' })).status).toBe(415);
        expect(calls).toBe(0);
      },
    );
  });
  it('streams content before completion and propagates cancellation to the provider', async () => {
    let cancelled = false;
    let release!: () => void;
    const wait = new Promise<void>((resolve) => {
      release = resolve;
    });
    await withServer(
      async function* (_request, signal) {
        signal.addEventListener(
          'abort',
          () => {
            cancelled = true;
            release();
          },
          { once: true },
        );
        yield { type: 'delta', text: 'first' };
        await wait;
        yield { type: 'done' };
      },
      async (url) => {
        const response = await post(url);
        const reader = response.body!.getReader();
        const part = await reader.read();
        expect(new TextDecoder().decode(part.value)).toContain('first');
        expect(cancelled).toBe(false);
        await reader.cancel();
        await new Promise((resolve) => setTimeout(resolve, 40));
        expect(cancelled).toBe(true);
      },
    );
  });
  it('does not leak provider exceptions', async () => {
    await withServer(
      async function* () {
        throw new Error('PRIVATE_KEY_FAKE');
        yield { type: 'done' };
      },
      async (url) => {
        const text = await (await post(url)).text();
        expect(text).toContain('unavailable');
        expect(text).not.toContain('PRIVATE_KEY');
      },
    );
  });
  it('delivers follow-ups without ending the response before completion', async () => {
    await withServer(
      async function* () {
        yield { type: 'delta', text: 'VHH explanation' };
        yield { type: 'suggestions', questions: ['What is its size?', 'What is its structure?'] };
        yield { type: 'done' };
      },
      async (url) => {
        const events = (await (await post(url)).text())
          .trim()
          .split('\n')
          .map((line) => JSON.parse(line));
        expect(events.map((e) => e.type)).toEqual(['delta', 'suggestions', 'done']);
      },
    );
    expect(validQuestions([null, ' a ', 'a', '', 'b', 'c', 'd', 'x'.repeat(121)])).toEqual([
      'a',
      'b',
      'c',
    ]);
    expect(validQuestions({ questions: ['not an array'] })).toEqual([]);
  });
  it('bounds spending with a per-minute request limit', async () => {
    await withServer(
      async function* () {
        yield { type: 'done' };
      },
      async (url) => {
        for (let i = 0; i < 20; i++) expect((await post(url)).status).toBe(200);
        expect((await post(url)).status).toBe(429);
      },
    );
  });
  it('decodes split UTF-8 and protocol lines and detects truncated streams', async () => {
    const original = globalThis.fetch;
    const events: ChatEvent[] = [
      { type: 'delta', text: '你好 🐰' },
      { type: 'suggestions', questions: ['继续聊什么？', '能举个例子吗？'] },
      { type: 'done' },
    ];
    const bytes = new TextEncoder().encode(events.map((e) => JSON.stringify(e) + '\n').join(''));
    try {
      globalThis.fetch = async () =>
        new Response(
          new ReadableStream({
            start(c) {
              for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
              c.close();
            },
          }),
        );
      let text = '';
      let questions: string[] = [];
      await streamChat(
        request,
        new AbortController().signal,
        (x) => {
          text += x;
        },
        (next) => {
          questions = next;
        },
      );
      expect(text).toBe('你好 🐰');
      expect(questions).toEqual(['继续聊什么？', '能举个例子吗？']);
      globalThis.fetch = async () => new Response('{"type":"delta","text":"partial"}\n');
      await expect(streamChat(request, new AbortController().signal, () => {})).rejects.toThrow(
        'interrupted',
      );
    } finally {
      globalThis.fetch = original;
    }
  });
});
