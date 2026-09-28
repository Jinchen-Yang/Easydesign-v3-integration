import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { ArrowUp, RotateCcw, Settings2, Square, X } from 'lucide-react';
import { CHAT_ENDPOINT, streamChat, type ChatContext, type ChatMessage } from './chat';
import { translate, type Locale } from './i18n';
import { parseRabbitInlineMarkdown } from './rabbitMarkdown';
import './rabbit-chat.css';

type Message = ChatMessage & { complete: boolean };
export function RabbitChat({
  open,
  locale,
  context,
  style,
  onClose,
  onSettings,
  onActivity,
}: {
  open: boolean;
  locale: Locale;
  context: ChatContext;
  style: CSSProperties;
  onClose: () => void;
  onSettings: () => void;
  onActivity: (activity: 'idle' | 'waiting' | 'replying') => void;
}) {
  const t = (key: string) => translate(locale, key);
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retryText, setRetryText] = useState('');
  const [configured, setConfigured] = useState<boolean | null>(null);
  const controller = useRef<AbortController | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const sequence = useRef(0);
  useEffect(() => {
    if (!open) {
      controller.current?.abort('panel-closed');
      return;
    }
    field.current?.focus();
    const abort = new AbortController();
    fetch(CHAT_ENDPOINT, { signal: abort.signal })
      .then((r) => r.json())
      .then((v) => setConfigured(v.configured === true))
      .catch(() => {});
    return () => abort.abort();
  }, [open]);
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort('unmount');
    },
    [],
  );
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages, suggestions, open, error]);

  async function send(text = input, retrying = false) {
    const content = text.trim();
    if (!content || content.length > 4000 || controller.current) return;
    const id = ++sequence.current;
    let history = messages
      .filter((m) => m.complete)
      .slice(-16)
      .map(({ role, content }) => ({ role, content }));
    while (history.reduce((n, m) => n + m.content.length, content.length) > 32000) history.shift();
    const user: Message = { role: 'user', content, complete: true };
    const reuseUser =
      retrying && history.at(-1)?.role === 'user' && history.at(-1)?.content === content;
    if (!reuseUser) history = [...history, user];
    setMessages((previous) => {
      const retained =
        previous.at(-1)?.role === 'assistant' && !previous.at(-1)?.complete
          ? previous.slice(0, -1)
          : previous;
      return [
        ...retained.slice(-30),
        ...(reuseUser ? [] : [user]),
        { role: 'assistant', content: '', complete: false },
      ];
    });
    setInput('');
    setError('');
    setRetryText('');
    setSuggestions([]);
    setBusy(true);
    onActivity('waiting');
    const abort = new AbortController();
    controller.current = abort;
    try {
      let nextQuestions: string[] = [];
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          await streamChat(
            { locale, context, messages: history },
            abort.signal,
            (delta) => {
              if (sequence.current !== id) return;
              onActivity('replying');
              setMessages((previous) =>
                previous.map((m, i) =>
                  i === previous.length - 1 ? { ...m, content: m.content + delta } : m,
                ),
              );
            },
            (questions) => {
              nextQuestions = questions;
            },
          );
          break;
        } catch (failure) {
          const code = failure instanceof Error ? failure.message : 'unavailable';
          if (
            attempt === 0 &&
            !abort.signal.aborted &&
            ['timeout', 'interrupted', 'unavailable'].includes(code)
          ) {
            setMessages((previous) =>
              previous.map((message, index) =>
                index === previous.length - 1 ? { ...message, content: '' } : message,
              ),
            );
            onActivity('waiting');
            await new Promise((resolve) => setTimeout(resolve, 800));
            continue;
          }
          throw failure;
        }
      }
      if (sequence.current !== id || abort.signal.aborted) return;
      setMessages((previous) =>
        previous.map((m, i) => (i === previous.length - 1 ? { ...m, complete: true } : m)),
      );
      setSuggestions(nextQuestions);
    } catch (failure) {
      if (sequence.current !== id) return;
      const reason = abort.signal.reason;
      const code = abort.signal.aborted
        ? reason === 'user-stop'
          ? 'stopped'
          : 'paused'
        : failure instanceof Error
          ? failure.message
          : 'unavailable';
      setMessages((previous) => {
        const last = previous.at(-1);
        if (last?.role !== 'assistant' || last.complete) return previous;
        if (!last.content) return previous.slice(0, -1);
        return previous.map((message, index) =>
          index === previous.length - 1 ? { ...message, complete: false } : message,
        );
      });
      setRetryText(content);
      setError(
        [
          'stopped',
          'paused',
          'not_configured',
          'rate_limit',
          'credentials',
          'timeout',
          'interrupted',
        ].includes(code)
          ? code
          : 'unavailable',
      );
    } finally {
      if (sequence.current === id) {
        controller.current = null;
        setBusy(false);
        onActivity('idle');
      }
    }
  }
  function clear() {
    controller.current?.abort('new-chat');
    controller.current = null;
    sequence.current++;
    setMessages([]);
    setSuggestions([]);
    setError('');
    setRetryText('');
    setBusy(false);
    onActivity('idle');
    field.current?.focus();
  }
  const errors: Record<string, string> = {
    stopped: 'Reply stopped.',
    paused: 'Reply paused when the panel closed. Retry when ready.',
    not_configured: 'Chat is not connected yet.',
    credentials: 'The model key is unavailable. Please check the server configuration.',
    rate_limit: 'A little busy. Please try again shortly.',
    timeout: 'The reply timed out. Please try again.',
    interrupted: 'The reply was interrupted. You can ask me to continue.',
    unavailable: 'Could not connect. Please try again.',
  };
  if (!open) return null;
  return (
    <section
      className="rabbit-chat"
      style={style}
      role="dialog"
      aria-label={t('Chat with bunny')}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <header className="rabbit-chat-header">
        <div>
          <strong>{t('Little lab companion')}</strong>
        </div>
        <button title={t('New chat')} aria-label={t('New chat')} onClick={clear}>
          <RotateCcw size={17} />
        </button>
        <button title={t('Bunny controls')} aria-label={t('Bunny controls')} onClick={onSettings}>
          <Settings2 size={17} />
        </button>
        <button title={t('Close chat')} aria-label={t('Close chat')} onClick={onClose}>
          <X size={19} />
        </button>
      </header>
      <div
        className="rabbit-chat-log"
        ref={log}
        role="log"
        aria-label={t('Conversation')}
        aria-live="polite"
        aria-relevant="additions text"
      >
        {!messages.length && (
          <div className="rabbit-chat-welcome">
            <span aria-hidden="true">✦</span>
            <p>{t('Hi! What would you like to know?')}</p>
            <div className="rabbit-chat-suggestions">
              {['What is happening in this step?', 'What is a VHH?'].map((s) => (
                <button key={s} onClick={() => void send(t(s))}>
                  {t(s)}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`rabbit-message ${m.role}`}>
            <span className="sr-only">{m.role === 'user' ? t('You') : t('Bunny')}</span>
            {m.content ? (
              m.role === 'assistant' ? (
                parseRabbitInlineMarkdown(m.content).map((token, tokenIndex) =>
                  token.type === 'strong' ? (
                    <strong key={tokenIndex}>{token.value}</strong>
                  ) : (
                    token.value
                  ),
                )
              ) : (
                m.content
              )
            ) : busy && i === messages.length - 1 ? (
                <span className="rabbit-chat-dots" aria-label={t('Preparing a reply')}>
                  ···
                </span>
              ) : (
                t('No reply')
              )}
          </div>
        ))}
        {!busy && suggestions.length > 0 && (
          <div className="rabbit-chat-suggestions" role="group" aria-label={t('Keep chatting')}>
            {suggestions.map((question) => (
              <button key={question} onClick={() => void send(question)}>
                {question}
              </button>
            ))}
          </div>
        )}
        {configured === false && !error && (
          <p className="rabbit-chat-error">{t(errors.not_configured)}</p>
        )}
        {error && (
          <div className="rabbit-chat-error" role="status">
            <p>{t(errors[error])}</p>
            {retryText && error !== 'not_configured' && (
              <button onClick={() => void send(retryText, true)}>{t('Retry reply')}</button>
            )}
          </div>
        )}
      </div>
      <form
        className="rabbit-chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          ref={field}
          value={input}
          maxLength={4000}
          rows={2}
          placeholder={t('Ask bunny…')}
          aria-label={t('Message bunny')}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
        />
        {busy ? (
          <button
            type="button"
            className="rabbit-chat-send"
            title={t('Stop reply')}
            aria-label={t('Stop reply')}
            onClick={() => controller.current?.abort('user-stop')}
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            type="submit"
            className="rabbit-chat-send"
            title={t('Send message')}
            aria-label={t('Send message')}
            disabled={!input.trim()}
          >
            <ArrowUp size={20} />
          </button>
        )}
      </form>
      <footer>{t('Uses chat & page summary to prepare this reply')}</footer>
    </section>
  );
}
