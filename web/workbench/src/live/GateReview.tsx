import { ArrowRight } from 'lucide-react';
import { useState } from 'react';
import type { Decision, GateAction, GateInput } from './contracts';
const display = (value: unknown): string =>
  value === null || value === undefined
    ? 'Not available'
    : typeof value === 'boolean'
      ? value
        ? 'Yes'
        : 'No'
      : String(value);
const label = (key: string) => key.replaceAll('_', ' ').replaceAll('-', ' ').replaceAll('.', ' ');
function Facts({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="muted">Not available</span>;
  if (Array.isArray(value))
    return (
      <ul className="live-facts">
        {value.map((v, i) => (
          <li key={i}>
            <Facts value={v} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === 'object')
    return (
      <dl className="live-facts">
        {Object.entries(value).map(([key, v]) => (
          <div key={key}>
            <dt>{label(key)}</dt>
            <dd>
              <Facts value={v} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>{display(value)}</span>;
}
export function GateReview({
  decision,
  selectedOptionId,
  initialAction = 'revise',
  busy,
  onSubmit,
  onSelect,
}: {
  decision: Decision;
  selectedOptionId?: string;
  initialAction?: GateAction;
  busy: boolean;
  onSubmit: (input: GateInput) => void;
  onSelect: (id: string) => void;
}) {
  const [selected, setSelected] = useState(selectedOptionId || decision.default_option_id),
    [action, setAction] = useState<GateAction>(initialAction);
  const [instruction, setInstruction] = useState(''),
    [reason, setReason] = useState(''),
    [ack, setAck] = useState('');
  const [target, setTarget] = useState(decision.revision_targets[0]);
  const option = decision.options.find((o) => o.option_id === selected);
  const actions = option?.actions || (['revise', 'reject'] as GateAction[]);
  const effective = actions.includes(action) ? action : actions[0];
  const fields: Record<string, string> = { instruction, reason, acknowledgement: ack };
  const complete = (decision.required_fields[effective] || []).every((field) =>
    Boolean(fields[field]?.trim()),
  );
  return (
    <section className="live-gate" aria-label={`Gate ${decision.gate} decision`}>
      <div className="eyebrow">SCIENTIST DECISION · GATE {decision.gate}</div>
      <h2>{decision.question}</h2>
      <p>{decision.action_summary}</p>
      <fieldset disabled={busy}>
        <legend>Choose an option</legend>
        <div className="live-options">
          {decision.options.map((o) => (
            <label
              key={o.option_id}
              className={`live-option ${selected === o.option_id ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="gate-option"
                value={o.option_id}
                checked={selected === o.option_id}
                onChange={() => {
                  setSelected(o.option_id);
                  onSelect(o.option_id);
                }}
              />
              <span>
                <strong>
                  {o.priority ? `${o.priority} · ` : ''}
                  {o.label || o.option_id}
                </strong>
                <span>{o.description}</span>
                {o.design_labels && <small>Design residues: {o.design_labels.join(', ')}</small>}
                <small>
                  {o.eligible ? 'Selectable' : 'Blocked'}
                  {o.confidence ? ` · Confidence ${o.confidence}` : ''}
                </small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {(decision.warnings.length > 0 || decision.limitations.length > 0) && (
        <details>
          <summary>
            Risks & limitations ({decision.warnings.length + decision.limitations.length})
          </summary>
          <Facts value={[...decision.warnings, ...decision.limitations]} />
        </details>
      )}
      {option && (
        <details>
          <summary>
            Option evidence & scientific review · {decision.review_status || 'Review unavailable'}
          </summary>
          <Facts
            value={Object.fromEntries(
              Object.entries(option).filter(([k]) => !['actions', 'option_id'].includes(k)),
            )}
          />
        </details>
      )}
      <details>
        <summary>Decision evidence and execution scope</summary>
        <Facts value={decision.summary} />
        {decision.summary_is_excerpt && (
          <p>This is a display excerpt. Full details remain in the review document.</p>
        )}
        {decision.details_url && (
          <a href={decision.details_url} download={`gate-${decision.gate}-review.json`}>
            Download complete review
          </a>
        )}
      </details>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit({
            action: effective,
            selected_option_id: selected,
            ...(effective === 'revise' ? { instruction, revision_target: target } : {}),
            ...(effective === 'override' ? { reason, acknowledgement: ack } : {}),
          });
        }}
      >
        <label>
          Decision
          <select
            aria-label="Decision action"
            disabled={busy}
            value={effective}
            onChange={(e) => setAction(e.target.value as GateAction)}
          >
            {actions.map((a) => (
              <option key={a} value={a}>
                {a.toUpperCase()}
              </option>
            ))}
          </select>
        </label>
        {effective === 'revise' && (
          <>
            <label>
              Return to
              <select value={target} onChange={(e) => setTarget(e.target.value)}>
                {decision.revision_targets.map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Scientist instruction
              <textarea
                required
                maxLength={1500}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              />
            </label>
          </>
        )}
        {effective === 'override' && (
          <>
            <label>
              Reason
              <textarea
                required
                maxLength={1500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <label>
              Acknowledgement
              <textarea
                required
                maxLength={1500}
                value={ack}
                onChange={(e) => setAck(e.target.value)}
              />
            </label>
          </>
        )}
        <button className="primary-button" disabled={busy || !complete || !effective} type="submit">
          {busy ? 'Submitting…' : `Submit ${effective?.toUpperCase()}`}
          <ArrowRight size={15} />
        </button>
      </form>
    </section>
  );
}
