import { useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  ArrowUpRight,
  Check,
  ChevronDown,
  FileSearch,
  Sparkles,
  SkipForward,
} from 'lucide-react';
import type {
  ConversationItem,
  WorkbenchSnapshot,
  WorkflowPhase,
} from '../../adapters/WorkbenchAdapter';

function ToolCard({
  item,
  onFocus,
}: {
  item: ConversationItem;
  onFocus: (phase: WorkflowPhase) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`tool-card ${open ? 'open' : ''}`}>
      <button className="tool-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="tool-icon">
          <FileSearch size={16} />
        </span>
        <span className="tool-copy">
          <strong>{item.title}</strong>
          <span>{item.text}</span>
        </span>
        <span className="tool-complete">
          <Check size={11} /> Completed
        </span>
        <ChevronDown size={13} className="tool-chevron" />
      </button>
      {open && (
        <div className="tool-detail">
          <p>{item.detail}</p>
          <span className="simulated-label">Demo fixture</span>
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
  viewedPhase,
  onFocus,
  onSend,
  onSkip,
}: {
  snapshot: WorkbenchSnapshot;
  viewedPhase: WorkflowPhase;
  onFocus: (phase: WorkflowPhase) => void;
  onSend: (text: string) => void;
  onSkip: () => void;
}) {
  const [text, setText] = useState('');
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
        <span className="online-dot" title="Demo available" />
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
              <ToolCard key={item.id} item={item} onFocus={onFocus} />
            ) : item.kind === 'summary' ? (
              <article className="scientist-message" key={item.id}>
                <span className="message-by">
                  <Sparkles size={12} /> EASYDESIGN
                </span>
                <h2>{item.title}</h2>
                <p>{item.text}</p>
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
              </div>
            ),
          )}
          {snapshot.busy && viewedPhase === snapshot.phase && (
            <div className="research-progress" role="status">
              <span className="tiny-loader" />
              <span>
                Preparing your{' '}
                {snapshot.phase === 'goal' ? 'research plan' : `${snapshot.phase} review`}
              </span>
              <button onClick={onSkip}>
                <SkipForward size={12} /> Skip animation
              </button>
            </div>
          )}
          {!snapshot.busy && !snapshot.completed && viewedPhase === snapshot.phase && (
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
          if (text.trim()) {
            onSend(text);
            setText('');
          }
        }}
      >
        <label className="sr-only" htmlFor="followup">
          Message Design Scientist
        </label>
        <textarea
          id="followup"
          value={text}
          maxLength={2000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (text.trim()) {
                onSend(text);
                setText('');
              }
            }
          }}
          placeholder="Ask about this step or add a note…"
          rows={2}
        />
        <div className="composer-bottom">
          <span>
            <span className="subtle-dot" /> Demo conversation
          </span>
          <button className="send-button" aria-label="Send message" disabled={!text.trim()}>
            <ArrowUp size={17} />
          </button>
        </div>
      </form>
      <p className="conversation-footnote">
        Research summaries and tool events · Simulated for UI development
      </p>
    </section>
  );
}
