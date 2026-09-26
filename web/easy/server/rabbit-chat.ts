import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';
import {
  CHAT_ENDPOINT,
  parseChatRequest,
  validQuestions,
  type ChatRequest,
  type ChatEvent,
} from '../src/easy/chat';

export interface ChatConfig {
  host: string;
  script: string;
  envFile: string;
}
const quote = (s: string) => "'" + s.replaceAll("'", "'\\''") + "'";
export function chatSshArgs(config: ChatConfig) {
  if (
    !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$/.test(config.host) ||
    ![config.script, config.envFile].every((p) => p.startsWith('/') && !/[\r\n\0]/.test(p))
  )
    throw new Error('Invalid server chat configuration');
  return [
    '-T',
    '-o',
    'BatchMode=yes',
    '-o',
    'ClearAllForwardings=yes',
    '-o',
    'StrictHostKeyChecking=yes',
    '-o',
    'ConnectTimeout=8',
    '-o',
    'ServerAliveInterval=10',
    '-o',
    'ServerAliveCountMax=2',
    config.host,
    'python3 -u ' + quote(config.script) + ' ' + quote(config.envFile),
  ];
}
export type ChatProvider = (request: ChatRequest, signal: AbortSignal) => AsyncIterable<ChatEvent>;
export function sshChatProvider(config: ChatConfig): ChatProvider {
  const args = chatSshArgs(config);
  return async function* (request, signal) {
    const child = spawn('ssh', args, { stdio: ['pipe', 'pipe', 'ignore'] });
    const abort = () => child.kill('SIGTERM');
    signal.addEventListener('abort', abort, { once: true });
    // Never surface raw SSH errors or server diagnostics to the browser.
    let failed = false;
    child.on('error', () => {
      failed = true;
    });
    child.stdin.on('error', () => {
      failed = true;
    });
    const closed = new Promise<number | null>((resolve) => child.on('close', resolve));
    const lines = createInterface({ input: child.stdout, crlfDelay: Infinity });
    child.stdin.end(JSON.stringify(request));
    try {
      if (signal.aborted) abort();
      let size = 0;
      for await (const line of lines) {
        size += line.length;
        if (size > 200000) throw new Error('unavailable');
        const event = JSON.parse(line) as ChatEvent;
        if (event.type === 'delta' && typeof event.text === 'string')
          yield { type: 'delta', text: event.text };
        else if (event.type === 'suggestions')
          yield { type: 'suggestions', questions: validQuestions(event.questions) };
        else if (event.type === 'error') {
          yield {
            type: 'error',
            code: ['credentials', 'rate_limit', 'timeout'].includes(event.code)
              ? event.code
              : 'unavailable',
          };
          return;
        } else if (event.type === 'done') {
          yield { type: 'done' };
          return;
        }
      }
      await closed;
      if (failed || !signal.aborted) throw new Error('interrupted');
    } finally {
      signal.removeEventListener('abort', abort);
      lines.close();
      child.kill('SIGTERM');
    }
  };
}

export function chatMiddleware(provider: ChatProvider | null) {
  let active = 0;
  let requests: number[] = [];
  return async (req: IncomingMessage, res: ServerResponse, next: () => void) => {
    if (req.url?.split('?')[0] !== CHAT_ENDPOINT) return next();
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    const json = (status: number, body: unknown) => {
      res.statusCode = status;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(body));
    };
    const host = req.headers.host ?? '';
    if (
      !/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host) ||
      (req.headers.origin && req.headers.origin !== 'http://' + host) ||
      req.headers['sec-fetch-site'] === 'cross-site'
    )
      return json(403, { error: 'forbidden' });
    if (req.url !== CHAT_ENDPOINT) return json(400, { error: 'invalid' });
    if (req.method === 'GET') return json(200, { configured: !!provider, model: 'deepseek-flash' });
    if (req.method !== 'POST') {
      res.setHeader('Allow', 'GET, POST');
      return json(405, { error: 'invalid' });
    }
    if (!provider) return json(503, { error: 'not_configured' });
    if (!req.headers['content-type']?.startsWith('application/json'))
      return json(415, { error: 'invalid' });
    requests = requests.filter((at) => Date.now() - at < 60000);
    if (active >= 2 || requests.length >= 20) return json(429, { error: 'rate_limit' });
    active++;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      abort.abort();
      req.destroy();
    }, 90000);
    const disconnected = () => abort.abort();
    res.on('close', disconnected);
    try {
      let size = 0;
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 140000) return json(413, { error: 'invalid' });
        chunks.push(Buffer.from(chunk));
      }
      let request: ChatRequest;
      try {
        request = parseChatRequest(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        return json(400, { error: 'invalid' });
      }
      requests.push(Date.now());
      res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8');
      res.flushHeaders();
      for await (const event of provider(request, abort.signal)) {
        if (abort.signal.aborted) break;
        res.write(JSON.stringify(event) + '\n');
        if (event.type === 'done' || event.type === 'error') {
          res.end();
          return;
        }
      }
      if (!abort.signal.aborted)
        res.write(JSON.stringify({ type: 'error', code: 'interrupted' }) + '\n');
      res.end();
    } catch {
      if (!res.headersSent) json(502, { error: 'unavailable' });
      else if (!res.destroyed)
        res.end(JSON.stringify({ type: 'error', code: 'unavailable' }) + '\n');
    } finally {
      clearTimeout(timer);
      res.off('close', disconnected);
      abort.abort();
      active--;
    }
  };
}

export function rabbitChatPlugin(config: ChatConfig): Plugin {
  const middleware = chatMiddleware(config.host ? sshChatProvider(config) : null);
  return {
    name: 'easydesign-rabbit-chat',
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}
