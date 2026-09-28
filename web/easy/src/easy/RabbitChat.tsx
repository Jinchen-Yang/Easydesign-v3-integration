import { useContext, useEffect, useRef, useState, type CSSProperties } from 'react';
import { ArrowUp, RotateCcw, Settings2, Square, X } from 'lucide-react';
import {
  CHAT_ENDPOINT,
  streamChat,
  chatRequestStatus,
  cancelChatRequest,
  ChatStreamError,
  chatRetryAction,
  type ChatContext,
  type ChatMessage,
  type ChatRequest,
  type ChatStatus,
  type ChatRetryAction,
} from './chat';
import { translate, type Locale } from './i18n';
import { parseRabbitInlineMarkdown } from './rabbitMarkdown';
import './rabbit-chat.css';
import { AccountTransportContext } from '../accounts/AccountTransportContext';

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
  const account = useContext(AccountTransportContext);
  const transport = account?.transport || fetch;
  const readOnly = account ? !account.scope.can_edit : false;
  const t = (key: string) => translate(locale, key);
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [retryText, setRetryText] = useState('');
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [requestStatus, setRequestStatus] = useState<ChatStatus | null>(null);
  const [retryEvidence, setRetryEvidence] = useState<ChatStatus | 'not_found' | null>(null);
  const [acceptedFailure, setAcceptedFailure] = useState<boolean | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [statusFailed, setStatusFailed] = useState(false);
  const lastRequest = useRef<{ id: string; payload: ChatRequest } | null>(null);
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
    transport(CHAT_ENDPOINT, { signal: abort.signal })
      .then((r) => r.json())
      .then((v) => setConfigured(v.configured === true))
      .catch(() => {});
    return () => abort.abort();
  }, [open, transport]);
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort('unmount');
    },
    [],
  );
  // A scope or sign-in change swaps the transport identity; an in-flight reply
  // from the previous scope must never keep streaming or render here.
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort('scope-change');
      controller.current = null;
      setMessages([]);
      setSuggestions([]);
      setError('');
      setRetryText('');
      setBusy(false);
      setRequestStatus(null);
      setRetryEvidence(null);
      setAcceptedFailure(null);
      setCheckingStatus(false);
      setStatusFailed(false);
      lastRequest.current = null;
    },
    [transport],
  );
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages, suggestions, open, error]);

  const retryAction = lastRequest.current
    ? chatRetryAction(error, acceptedFailure, lastRequest.current.id, retryEvidence)
    : null;
  async function send(text = input, retrying: ChatRetryAction | false = false) {
    const content = text.trim();
    if (!content || content.length > 4000 || controller.current || readOnly) return;
    if (retrying && account && retrying !== retryAction) return;
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
    setRetryEvidence(null);
    setAcceptedFailure(null);
    setCheckingStatus(false);
    setStatusFailed(false);
    setSuggestions([]);
    setBusy(true);
    onActivity('waiting');
    const abort = new AbortController();
    controller.current = abort;
    const submitted =
      retrying && lastRequest.current
        ? {
            id: retrying === 'new_request' ? crypto.randomUUID() : lastRequest.current.id,
            payload: lastRequest.current.payload,
          }
        : { id: crypto.randomUUID(), payload: { locale, context, messages: history } };
    lastRequest.current = submitted;
    setRequestStatus({ request_id: submitted.id, state: 'submitting' });
    const cancel = () => {
      if (account) void cancelChatRequest(submitted.id, transport).catch(() => {});
    };
    abort.signal.addEventListener('abort', cancel, { once: true });
    try {
      let nextQuestions: string[] = [];
      await streamChat(
        submitted.payload,
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
        transport,
        {
          requestId: submitted.id,
          onStatus: (status) => {
            if (sequence.current === id) setRequestStatus(status);
          },
        },
      );
      if (sequence.current !== id || abort.signal.aborted) return;
      setMessages((previous) =>
        previous.map((m, i) => (i === previous.length - 1 ? { ...m, complete: true } : m)),
      );
      setSuggestions(nextQuestions);
    } catch (failure) {
      if (sequence.current !== id) return;
      const reason = abort.signal.reason;
      let code = abort.signal.aborted
        ? reason === 'user-stop'
          ? 'stopped'
          : 'paused'
        : failure instanceof Error
          ? failure.message
          : 'unavailable';
      if (account && ['timeout', 'interrupted', 'unavailable'].includes(code))
        code = 'outcome_unknown';
      setMessages((previous) => {
        const last = previous.at(-1);
        if (last?.role !== 'assistant' || last.complete) return previous;
        if (!last.content) return previous.slice(0, -1);
        return previous.map((message, index) =>
          index === previous.length - 1 ? { ...message, complete: false } : message,
        );
      });
      setRetryText(content);
      setAcceptedFailure(failure instanceof ChatStreamError ? failure.accepted : null);
      setError(
        [
          'stopped',
          'paused',
          'not_configured',
          'rate_limit',
          'credentials',
          'timeout',
          'interrupted',
          'outcome_unknown',
          'request_already_processed',
          'queue_full',
          'user_limit',
          'queue_timeout',
          'cancelled',
          'budget_exhausted',
          'authorization_revoked',
        ].includes(code)
          ? code
          : 'unavailable',
      );
    } finally {
      abort.signal.removeEventListener('abort', cancel);
      if (sequence.current === id) {
        controller.current = null;
        setBusy(false);
        onActivity('idle');
      }
    }
  }
  async function checkStatus() {
    const identity = lastRequest.current?.id;
    const id = sequence.current;
    if (!identity || checkingStatus) return;
    setCheckingStatus(true);
    setStatusFailed(false);
    setRetryEvidence(null);
    try {
      const status = await chatRequestStatus(identity, transport);
      if (sequence.current !== id || lastRequest.current?.id !== identity) return;
      setRetryEvidence(status);
      if (status !== 'not_found') setRequestStatus(status);
    } catch {
      if (sequence.current === id && lastRequest.current?.id === identity) setStatusFailed(true);
    } finally {
      if (sequence.current === id && lastRequest.current?.id === identity) setCheckingStatus(false);
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
    setRequestStatus(null);
    setRetryEvidence(null);
    setAcceptedFailure(null);
    setCheckingStatus(false);
    setStatusFailed(false);
    lastRequest.current = null;
    onActivity('idle');
    field.current?.focus();
  }
  const errors: Record<string, string> = {
    stopped: account
      ? locale === 'zh'
        ? '已申请停止，请查看请求状态确认；不会自动重新调用。'
        : 'Stop requested. Check request status to confirm; no automatic retry.'
      : 'Reply stopped.',
    paused: account
      ? locale === 'zh'
        ? '面板关闭时已申请停止，请先查看请求状态。'
        : 'Stop requested when the panel closed. Check request status first.'
      : 'Reply paused when the panel closed. Retry when ready.',
    not_configured: 'Chat is not connected yet.',
    credentials: 'The model key is unavailable. Please check the server configuration.',
    rate_limit: 'A little busy. Please try again shortly.',
    timeout: 'The reply timed out. Please try again.',
    interrupted: 'The reply was interrupted. You can ask me to continue.',
    unavailable: 'Could not connect. Please try again.',
    outcome_unknown: '结果未确认，不会自动重新调用。请先查看状态；重新提问可能再次计费。',
    request_already_processed: '该请求已受理或已处理，不会重复调用。请查看请求状态。',
    queue_full: '对话队列已满，请稍后重试。',
    user_limit: '你已有对话正在处理或等待，请先完成或取消它。',
    queue_timeout: '等待超时；本次未派发模型请求。',
    cancelled: '对话请求已取消。',
    budget_exhausted: '本次活动的对话调用额度已用完。',
    authorization_revoked: '会话或工作区权限已变化，本次没有调用模型。请重新登录并确认权限。',
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
                <button key={s} disabled={readOnly} onClick={() => void send(t(s))}>
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
              <button key={question} disabled={readOnly} onClick={() => void send(question)}>
                {question}
              </button>
            ))}
          </div>
        )}
        {configured === false && !error && (
          <p className="rabbit-chat-error">{t(errors.not_configured)}</p>
        )}
        {busy && requestStatus && (
          <p role="status" className="rabbit-chat-error">
            {requestStatus.state === 'queued'
              ? '正在排队，轮到后自动开始；等待期间不重复提交。'
              : requestStatus.state === 'cancelling'
                ? '正在确认停止…'
                : '正在准备回复…'}
          </p>
        )}
        {readOnly && (
          <p className="rabbit-chat-error">当前是只读访问，请切换到自己的工作区后使用豆豆。</p>
        )}
        {error && (
          <div className="rabbit-chat-error" role="status">
            <p>{t(errors[error])}</p>
            {retryText &&
              !account &&
              ![
                'not_configured',
                'credentials',
                'outcome_unknown',
                'request_already_processed',
                'cancelled',
                'authorization_revoked',
              ].includes(error) && (
                <button onClick={() => void send(retryText, 'same_request')}>
                  {t('Retry reply')}
                </button>
              )}
            {account && retryText && retryAction && (
              <button
                disabled={readOnly || checkingStatus}
                onClick={() => void send(retryText, retryAction)}
              >
                {retryAction === 'new_request' ? '重新排队（新请求）' : '重试提交（原请求）'}
              </button>
            )}
            {account && lastRequest.current && (
              <button disabled={checkingStatus} onClick={() => void checkStatus()}>
                查看请求状态
              </button>
            )}
            {statusFailed && <p>状态查询失败，尚不能确认是否派发；请稍后再查，不会重新调用。</p>}
            {retryEvidence === 'not_found' && <p>未找到原请求记录。</p>}
            {retryEvidence && retryEvidence !== 'not_found' && retryEvidence.dispatched && (
              <p>该请求已经派发，不会重放；再次提问可能再次计费。</p>
            )}
            {retryAction === 'new_request' && (
              <p>
                已确认原请求未派发。重新排队将使用新请求 ID 提交原问题，成功派发后会计入调用额度。
              </p>
            )}
            {requestStatus && !busy && (
              <p>
                请求状态：{requestStatus.state} · {requestStatus.request_id}
              </p>
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
          disabled={readOnly}
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
            disabled={!input.trim() || readOnly}
          >
            <ArrowUp size={20} />
          </button>
        )}
      </form>
      <footer>{t('Uses chat & page summary to prepare this reply')}</footer>
    </section>
  );
}
