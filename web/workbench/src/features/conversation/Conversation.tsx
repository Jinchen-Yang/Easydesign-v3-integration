import { Fragment, useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  FileSearch,
  Sparkles,
  SkipForward,
} from 'lucide-react';
import type {
  ConversationItem,
  WorkbenchSnapshot,
  WorkflowPhase,
} from '../../adapters/WorkbenchAdapter';

/** Render common answer formatting as React text, never model-supplied HTML. */
function AnswerText({ text }: { text: string }) {
  const inline = (value: string) =>
    value
      .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
      .map((part, i) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={i}>{part.slice(2, -2)}</strong>
        ) : part.startsWith('`') && part.endsWith('`') ? (
          <code key={i}>{part.slice(1, -1)}</code>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      );
  return (
    <div className="answer-text">
      {text.split(/\n\s*\n/).map((block, i) => {
        if (/^#{1,6} /.test(block)) return <h3 key={i}>{inline(block.replace(/^#{1,6} /, ''))}</h3>;
        const lines = block.split('\n');
        if (lines.every((line) => /^\s*[-*] /.test(line)))
          return (
            <ul key={i}>
              {lines.map((line, j) => (
                <li key={j}>{inline(line.replace(/^\s*[-*] /, ''))}</li>
              ))}
            </ul>
          );
        return <p key={i}>{inline(block)}</p>;
      })}
    </div>
  );
}
function ToolCard({
  item,
  mode,
  onFocus,
}: {
  mode: 'demo' | 'live';
  item: ConversationItem;
  onFocus: (phase: WorkflowPhase) => void;
}) {
  const [open, setOpen] = useState(false);
  const status = item.status || 'complete';
  const state =
    status === 'failed'
      ? { icon: <CircleAlert size={11} />, label: 'Failed' }
      : status === 'running'
        ? { icon: <span className="tiny-loader" />, label: 'Running' }
        : status === 'blocked'
          ? { icon: <Clock3 size={11} />, label: 'Awaiting review' }
          : { icon: <Check size={11} />, label: 'Completed' };
  return (
    <div className={`tool-card ${status} ${open ? 'open' : ''}`}>
      <button className="tool-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="tool-icon">
          <FileSearch size={16} />
        </span>
        <span className="tool-copy">
          <strong>{item.title}</strong>
          <span>{item.text}</span>
        </span>
        <span className={`tool-complete ${status}`}>
          {state.icon} {state.label}
        </span>
        <ChevronDown size={13} className="tool-chevron" />
      </button>
      {open && (
        <div className="tool-detail">
          <p>{item.detail}</p>
          <span className="simulated-label">
            {mode === 'demo' ? 'Demo fixture' : 'Research activity'}
          </span>
          {item.focus && (
            <button
              className="text-button"
              aria-controls="scientific-context"
              onClick={() => onFocus(item.focus!)}
            >
              View scientific context <ArrowUpRight size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
export function Conversation({
  snapshot,
  mode = 'demo',
  disabled = false,
  sending = false,
  error,
  viewedPhase,
  onFocus,
  onSend,
  onSkip,
  onRetry,
}: {
  mode?: 'demo' | 'live';
  disabled?: boolean;
  sending?: boolean;
  error?: string;
  snapshot: Pick<WorkbenchSnapshot, 'messages' | 'phase' | 'busy' | 'completed'>;
  viewedPhase: WorkflowPhase;
  onFocus: (phase: WorkflowPhase) => void;
  onSend: (text: string) => void | Promise<void>;
  onSkip: () => void;
  onRetry?: (id: string) => void;
}) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const send = async () => {
    if (!text.trim() || disabled || sending || submitting) return;
    setSubmitting(true);
    try {
      await onSend(text);
      setText('');
    } catch {
      /* Parent displays the error; preserve draft. */
    } finally {
      setSubmitting(false);
    }
  };
  const scroll = useRef<HTMLDivElement>(null);
  const messages = snapshot.messages.filter((m) => m.phase === viewedPhase);
  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [snapshot.messages.length, viewedPhase]);
  return (
    <section className="conversation" aria-label="Design Scientist conversation">
      <header className="conversation-header">
        <span className="scientist-avatar">
          <Sparkles size={18} />
        </span>
        <div>
          <h1>Design Scientist</h1>
          <span>Your research, one clear step at a time</span>
        </div>
        <span
          className="online-dot"
          title={mode === 'demo' ? 'Demo available' : 'Design Scientist'}
        />
      </header>
      <div className="conversation-scroll" ref={scroll}>
        <div className="conversation-content">
          <div className="phase-caption">
            <span>{viewedPhase.charAt(0).toUpperCase() + viewedPhase.slice(1)}</span>
            <i />
            {snapshot.completed ? 'Completed journey' : 'Research workspace'}
          </div>
          {messages.map((item) =>
            item.kind === 'user' ? (
              <div className="user-message" key={item.id}>
                <span className="message-by">YOU</span>
                <p>{item.text}</p>
              </div>
            ) : item.kind === 'tool' ? (
              <ToolCard key={item.id} item={item} mode={mode} onFocus={onFocus} />
            ) : item.kind === 'summary' ? (
              <article className="scientist-message" key={item.id}>
                <span className="message-by">
                  <Sparkles size={12} /> EASYDESIGN
                </span>
                <h2>{item.title}</h2>
                {mode === 'live' ? <AnswerText text={item.text} /> : <p>{item.text}</p>}
                {item.focus && (
                  <button
                    className="context-link"
                    aria-controls="scientific-context"
                    onClick={() => onFocus(item.focus!)}
                  >
                    Explore{' '}
                    {item.focus === 'candidates'
                      ? 'the panel'
                      : item.focus === 'goal'
                        ? 'the goal'
                        : `${item.focus} context`}{' '}
                    <ArrowUpRight size={13} />
                  </button>
                )}
              </article>
            ) : (
              <div className="conversation-note" key={item.id}>
                <Check size={13} />
                <p>{item.text}</p>
                {item.retry_request_id && onRetry && (
                  <button className="text-button" onClick={() => onRetry(item.retry_request_id!)}>
                    Retry answer
                  </button>
                )}
              </div>
            ),
          )}
          {(sending || submitting || (snapshot.busy && viewedPhase === snapshot.phase)) && (
            <div className="research-progress" role="status">
              <span className="tiny-loader" />
              <span>
                {sending || submitting ? (
                  'Design Scientist is answering…'
                ) : (
                  <>
                    Preparing your{' '}
                    {snapshot.phase === 'goal' ? 'research plan' : `${snapshot.phase} review`}
                  </>
                )}
              </span>
              {mode === 'demo' && (
                <button onClick={onSkip}>
                  <SkipForward size={12} /> Skip animation
                </button>
              )}
            </div>
          )}
          {!snapshot.busy &&
            !sending &&
            !submitting &&
            !snapshot.completed &&
            viewedPhase === snapshot.phase && (
              <p className="awaiting-copy">
                <span /> Ready for your review below
              </p>
            )}
          {viewedPhase !== snapshot.phase && (
            <button className="return-step" onClick={() => onFocus(snapshot.phase)}>
              Return to {snapshot.phase} <ArrowUpRight size={13} />
            </button>
          )}
        </div>
      </div>
      <form
        className="conversation-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <label className="sr-only" htmlFor="followup">
          Message Design Scientist
        </label>
        <textarea
          id="followup"
          value={text}
          maxLength={mode === 'demo' ? 2000 : 1500}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Ask about this step or add a note…"
          rows={2}
        />
        <div className="composer-bottom">
          <span>
            <span className="subtle-dot" />{' '}
            {mode === 'demo' ? 'Demo conversation' : 'Design Scientist'}
          </span>
          <button
            className="send-button"
            aria-label="Send message"
            disabled={disabled || sending || submitting || !text.trim()}
          >
            <ArrowUp size={17} />
          </button>
        </div>
      </form>
      <p className="conversation-footnote">
        {error ||
          (mode === 'demo'
            ? 'Research summaries and tool events · Simulated for UI development'
            : 'Research summaries and tool events · Your decisions stay yours')}
      </p>
    </section>
  );
}
