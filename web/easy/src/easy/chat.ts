export const CHAT_ENDPOINT = '/api/rabbit/chat';
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}
export interface ChatContext {
  stage: string;
  status: string;
  goal: string;
}
export interface ChatRequest {
  locale: 'zh' | 'en';
  messages: ChatMessage[];
  context: ChatContext;
}
export type ChatEvent =
  | { type: 'delta'; text: string }
  | { type: 'suggestions'; questions: string[] }
  | { type: 'done' }
  | { type: 'error'; code: string };

export function validQuestions(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [
    ...new Set(
      value
        .filter((q): q is string => typeof q === 'string')
        .map((q) => q.trim())
        .filter((q) => q.length > 0 && q.length <= 120),
    ),
  ].slice(0, 3);
}

/** Only plain conversational text and a small page summary cross this boundary. */
export function parseChatRequest(value: unknown): ChatRequest {
  const v = value as Partial<ChatRequest> | null;
  if (
    !v ||
    !['zh', 'en'].includes(v.locale ?? '') ||
    !Array.isArray(v.messages) ||
    v.messages.length < 1 ||
    v.messages.length > 17
  )
    throw new Error('invalid');
  let total = 0;
  const messages = v.messages.map((m) => {
    if (
      !m ||
      !['user', 'assistant'].includes(m.role) ||
      typeof m.content !== 'string' ||
      !m.content.trim() ||
      m.content.length > 8000
    )
      throw new Error('invalid');
    total += m.content.length;
    return { role: m.role, content: m.content };
  });
  if (total > 32000 || messages.at(-1)?.role !== 'user' || messages.at(-1)!.content.length > 4000)
    throw new Error('invalid');
  const c = v.context;
  if (
    !c ||
    !['Idle', 'Target', 'Site', 'Design', 'Pilot', 'Scale', 'Candidates'].includes(c.stage) ||
    !['idle', 'draft', 'running', 'paused', 'complete'].includes(c.status) ||
    typeof c.goal !== 'string' ||
    c.goal.length > 1200
  )
    throw new Error('invalid');
  return {
    locale: v.locale!,
    messages,
    context: { stage: c.stage, status: c.status, goal: c.goal },
  };
}

export async function streamChat(
  request: ChatRequest,
  signal: AbortSignal,
  delta: (text: string) => void,
  suggestions: (questions: string[]) => void = () => {},
  transport: typeof fetch = fetch,
) {
  const response = await transport(CHAT_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': crypto.randomUUID() },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const code =
      typeof body.error === 'string'
        ? body.error
        : typeof body.error?.code === 'string'
          ? body.error.code
          : 'unavailable';
    throw new Error(code);
  }
  if (!response.body) throw new Error('unavailable');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const lines = pending.split('\n');
      pending = lines.pop()!;
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as ChatEvent;
        if (event.type === 'error') throw new Error(event.code);
        if (event.type === 'done') return;
        if (event.type === 'delta') delta(event.text);
        if (event.type === 'suggestions') suggestions(validQuestions(event.questions));
      }
      if (done) throw new Error('interrupted');
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
