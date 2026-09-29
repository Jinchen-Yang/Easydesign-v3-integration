import { useTranslation } from 'react-i18next';
import { ArrowRight } from 'lucide-react';
import { useState } from 'react';
import { useInputDraft } from '../../data/useInputDraft';
import { DraftStatus } from '../../data/DraftStatus';
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
  const { t } = useTranslation('pro');
  if (value === null || value === undefined)
    return <span className="muted">{t('Not available')}</span>;
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
  return <span>{typeof value === 'boolean' ? t(value ? 'Yes' : 'No') : display(value)}</span>;
}
export function GateReview({
  decision,
  selectedOptionId,
  initialAction = 'revise',
  busy,
  onSubmit,
  onSelect,
  draftKey,
}: {
  decision: Decision;
  selectedOptionId?: string;
  initialAction?: GateAction;
  busy: boolean;
  onSubmit: (input: GateInput) => Promise<void>;
  onSelect: (id: string) => void;
  draftKey?: string;
}) {
  const { t } = useTranslation('pro');
  const input = useInputDraft(
    draftKey ?? null,
    {
      selected: selectedOptionId || decision.default_option_id,
      action: initialAction,
      instruction: '',
      reason: '',
      ack: '',
      target: decision.revision_targets[0] || '',
    },
    {
      valid: (
        value,
      ): value is {
        selected: string;
        action: GateAction;
        instruction: string;
        reason: string;
        ack: string;
        target: string;
      } => {
        if (!value || typeof value !== 'object') return false;
        const v = value as Record<string, unknown>;
        return (
          ['selected', 'action', 'instruction', 'reason', 'ack', 'target'].every(
            (key) => typeof v[key] === 'string',
          ) &&
          decision.options.some((option) => option.option_id === v.selected) &&
          ['approve', 'revise', 'reject', 'override'].includes(v.action as string)
        );
      },
    },
  );
  const { selected, action, instruction, reason, ack, target } = input.value;
  const update = (patch: Partial<typeof input.value>) =>
    input.setValue((current) => ({ ...current, ...patch }));
  const [submitting, setSubmitting] = useState(false);
  const option = decision.options.find((o) => o.option_id === selected);
  const actions = option?.actions || (['revise', 'reject'] as GateAction[]);
  const effective = actions.includes(action) ? action : actions[0];
  const fields: Record<string, string> = {
    instruction,
    reason,
    acknowledgement: ack,
  };
  const complete = (decision.required_fields[effective] || []).every((field) =>
    Boolean(fields[field]?.trim()),
  );
  return (
    <section
      className="live-gate"
      aria-label={t('Gate {{number}} decision', { number: decision.gate })}
    >
      <div className="eyebrow">
        {t('SCIENTIST DECISION · GATE')} {decision.gate}
      </div>
      <h2>
        {decision.gate === 1
          ? t('Review the automatically selected target structure')
          : decision.question}
      </h2>
      <p>
        {decision.gate === 1
          ? t('Approve the recommended structure and chain, or choose a different option.')
          : decision.action_summary}
      </p>
      <fieldset disabled={busy}>
        <legend>
          {decision.gate === 1
            ? t('Change the automatically selected structure')
            : t('Choose an option')}
        </legend>
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
                  update({ selected: o.option_id });
                  onSelect(o.option_id);
                }}
              />
              <span>
                <strong>
                  {o.priority ? `${o.priority} · ` : ''}
                  {o.label || o.option_id}
                </strong>
                <span>{o.description}</span>
                {o.design_labels && (
                  <small>
                    {t('Design residues:')} {o.design_labels.join(', ')}
                  </small>
                )}
                <small>
                  {o.eligible ? t('Selectable') : t('Blocked')}
                  {o.confidence ? ` · ${t('Confidence {{value}}', { value: o.confidence })}` : ''}
                  {decision.gate === 1 && o.option_id === decision.default_option_id
                    ? ` · ${t('Automatically recommended')}`
                    : ''}
                </small>
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {(decision.warnings.length > 0 || decision.limitations.length > 0) && (
        <details>
          <summary>
            {t('Risks & limitations ({{count}})', {
              count: decision.warnings.length + decision.limitations.length,
            })}
          </summary>
          <Facts value={[...decision.warnings, ...decision.limitations]} />
        </details>
      )}
      {option && (
        <details>
          <summary>
            {t('Option evidence & scientific review ·')}{' '}
            {decision.review_status || t('Review unavailable')}
          </summary>
          <Facts
            value={Object.fromEntries(
              Object.entries(option).filter(([k]) => !['actions', 'option_id'].includes(k)),
            )}
          />
        </details>
      )}
      <details>
        <summary>{t('Decision evidence and execution scope')}</summary>
        <Facts value={decision.summary} />
        {decision.summary_is_excerpt && (
          <p>{t('This is a display excerpt. Full details remain in the review document.')}</p>
        )}
        {decision.details_url && (
          <a href={decision.details_url} download={`gate-${decision.gate}-review.json`}>
            {t('Download complete review')}
          </a>
        )}
      </details>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (busy || submitting || !complete || !effective || !option?.eligible) return;
          setSubmitting(true);
          void onSubmit({
            action: effective,
            selected_option_id: selected,
            ...(effective === 'revise' ? { instruction, revision_target: target } : {}),
            ...(effective === 'override' ? { reason, acknowledgement: ack } : {}),
          })
            .then(() => input.complete('submitted'))
            .catch(() => {
              // The parent displays the API error. In particular, 401 recovery
              // only restores these inputs; it never retries this decision.
            })
            .finally(() => setSubmitting(false));
        }}
      >
        <label>
          {t('Decision')}
          <select
            aria-label={t('Decision action')}
            disabled={busy}
            value={effective}
            onChange={(e) => update({ action: e.target.value as GateAction })}
          >
            {actions.map((a) => (
              <option key={a} value={a}>
                {t(a[0].toUpperCase() + a.slice(1))}
              </option>
            ))}
          </select>
        </label>
        {effective === 'revise' && (
          <>
            <label>
              {t('Return to')}
              <select
                disabled={busy || submitting}
                value={target}
                onChange={(e) => update({ target: e.target.value })}
              >
                {decision.revision_targets.map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t('Scientist instruction')}
              <textarea
                required
                maxLength={1500}
                value={instruction}
                disabled={busy || submitting}
                onChange={(e) => update({ instruction: e.target.value })}
              />
            </label>
          </>
        )}
        {effective === 'override' && (
          <>
            <label>
              {t('Reason')}
              <textarea
                required
                maxLength={1500}
                value={reason}
                disabled={busy || submitting}
                onChange={(e) => update({ reason: e.target.value })}
              />
            </label>
            <label>
              {t('Acknowledgement')}
              <textarea
                required
                maxLength={1500}
                value={ack}
                disabled={busy || submitting}
                onChange={(e) => update({ ack: e.target.value })}
              />
            </label>
          </>
        )}
        <DraftStatus status={input.status} />
        <button
          className="primary-button"
          disabled={busy || submitting || !complete || !effective || !option?.eligible}
          type="submit"
        >
          {busy
            ? t('Submitting…')
            : t('Submit {{action}}', {
                action: t(effective[0].toUpperCase() + effective.slice(1)),
              })}
          <ArrowRight size={15} />
        </button>
      </form>
    </section>
  );
}
