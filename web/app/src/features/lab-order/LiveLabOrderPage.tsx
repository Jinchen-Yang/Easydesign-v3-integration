import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { useInputDraft } from '../../data/useInputDraft';
import { DraftStatus } from '../../data/DraftStatus';
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import type {
  ProductLabOrder,
  ProductLabOrderDraft,
  ProductLabOrderRequirements,
} from '../../views/pro/contracts';

const emptyRequirements = (): ProductLabOrderRequirements => ({
  format: 'VHH',
  amount: '1 mg per sample',
  host: 'E. coli',
  buffer: 'PBS',
  profile: 'simulation-lab',
  preferred_date: '',
  purchase_order: '',
  sds_purity: '',
  sec_purity: '',
  endotoxin: '',
  concentration: '',
  notes: 'Simulation-only packaging review.',
});

function draftFrom(order: ProductLabOrder): ProductLabOrderDraft {
  return (
    order.draft ?? {
      schema_version: '1',
      candidate_ids: order.candidates.map((candidate) => candidate.id),
      requirements: emptyRequirements(),
      reviewed: true,
    }
  );
}

export function LiveLabOrderPage({
  order,
  busy,
  error,
  onApply,
  draftKey,
}: {
  order: ProductLabOrder;
  busy: boolean;
  error: string;
  draftKey?: string;
  onApply: (
    action: 'save' | 'quote' | 'submit',
    draft?: ProductLabOrderDraft,
    acknowledgement?: 'SIMULATED_ORDER_ONLY',
  ) => Promise<void>;
}) {
  const { t } = useTranslation('pro');
  const input = useInputDraft(
    draftKey ? `${draftKey}:${encodeURIComponent(order.revision)}` : null,
    () => ({ draft: draftFrom(order), acknowledged: false }),
    {
      valid: (value): value is { draft: ProductLabOrderDraft; acknowledged: boolean } => {
        if (!value || typeof value !== 'object') return false;
        const v = value as {
          draft?: ProductLabOrderDraft;
          acknowledged?: unknown;
        };
        return (
          typeof v.acknowledged === 'boolean' &&
          v.draft?.schema_version === '1' &&
          Array.isArray(v.draft.candidate_ids) &&
          v.draft.candidate_ids.every((id) => order.candidates.some((c) => c.id === id)) &&
          !!v.draft.requirements &&
          Object.values(v.draft.requirements).every((field) => typeof field === 'string')
        );
      },
    },
  );
  const { draft, acknowledged } = input.value;
  const setDraft = (update: (current: ProductLabOrderDraft) => ProductLabOrderDraft) =>
    input.setValue((current) => ({ ...current, draft: update(current.draft) }));
  const setAcknowledged = (value: boolean) =>
    input.setValue((current) => ({ ...current, acknowledged: value }));
  const [submitting, setSubmitting] = useState(false);
  const [applyError, setApplyError] = useState('');
  const apply = async (action: 'save' | 'quote' | 'submit') => {
    if (busy || submitting) return;
    setSubmitting(true);
    setApplyError('');
    try {
      await onApply(
        action,
        action === 'save' ? draft : undefined,
        action === 'submit' ? 'SIMULATED_ORDER_ONLY' : undefined,
      );
      input.complete(action === 'submit' ? 'submitted' : 'saved');
    } catch (reason) {
      setApplyError((reason as Error).message);
    } finally {
      setSubmitting(false);
    }
  };
  const updateRequirement = (key: keyof ProductLabOrderRequirements, value: string) =>
    setDraft((current) => ({
      ...current,
      requirements: { ...current.requirements, [key]: value },
    }));
  const complete =
    draft.candidate_ids.length > 0 &&
    Boolean(draft.requirements.format && draft.requirements.amount.trim());
  const receipt = order.receipt;
  return (
    <section className="lab-order live-lab-order" aria-label={t('Simulated lab order')}>
      <div className="lab-order-scroll">
        <header className="lab-title">
          <div>
            <h1>{t('Lab Order')}</h1>
            <span className="lab-draft-badge">{t('Simulation only')}</span>
          </div>
          <p>{t('Validate the handoff and ordering boundary without contacting a vendor.')}</p>
        </header>
        <p className="lab-warning live-lab-disclaimer">
          <ShieldCheck size={17} /> {order.disclaimer}
        </p>
        {receipt ? (
          <div className="lab-layout">
            <div className="lab-form live-lab-receipt">
              <CheckCircle2 size={34} />
              <div>
                <span className="eyebrow">{t('IMMUTABLE MOCK RECEIPT')}</span>
                <h2>{t('Simulation accepted')}</h2>
                <p>
                  {t(
                    'The full UI-to-API workflow completed. No experiment, payment, vendor request or laboratory order was created.',
                  )}
                </p>
              </div>
              <dl className="lab-review-values">
                <div>
                  <dt>{t('Receipt')}</dt>
                  <dd>{receipt.receipt_id}</dd>
                </div>
                <div>
                  <dt>{t('Simulated order')}</dt>
                  <dd>{receipt.order_id}</dd>
                </div>
                <div>
                  <dt>{t('Samples')}</dt>
                  <dd>{receipt.candidate_ids.length}</dd>
                </div>
                <div>
                  <dt>{t('Status')}</dt>
                  <dd>{receipt.ordering_status}</dd>
                </div>
                <div>
                  <dt>{t('External request sent')}</dt>
                  <dd>{String(receipt.external_request_sent)}</dd>
                </div>
                <div>
                  <dt>{t('Financial commitment')}</dt>
                  <dd>{String(receipt.financial_commitment)}</dd>
                </div>
                <div>
                  <dt>{t('Experiment authorized')}</dt>
                  <dd>{String(receipt.experiment_authorized)}</dd>
                </div>
                <div>
                  <dt>{t('Receipt SHA256')}</dt>
                  <dd className="lab-hash">{receipt.receipt_sha256}</dd>
                </div>
              </dl>
            </div>
            <aside className="lab-summary" aria-label={t('Simulation summary')}>
              <h2>{t('Safety boundary')}</h2>
              <dl>
                <div>
                  <dt>{t('Provider')}</dt>
                  <dd>{receipt.provider}</dd>
                </div>
                <div>
                  <dt>{t('Environment')}</dt>
                  <dd>{receipt.environment}</dd>
                </div>
                <div>
                  <dt>{t('Real ordering')}</dt>
                  <dd>{t('Unavailable')}</dd>
                </div>
              </dl>
            </aside>
          </div>
        ) : (
          <div className="lab-layout">
            <div className="lab-form">
              <section className="lab-review-block">
                <header>
                  <h2>{t('1. Gate 5 samples')}</h2>
                </header>
                <div className="lab-samples">
                  {order.candidates.map((candidate) => (
                    <label className="lab-sample" key={candidate.id}>
                      <input
                        type="checkbox"
                        checked={draft.candidate_ids.includes(candidate.id)}
                        disabled={busy || Boolean(order.quote)}
                        onChange={(event) =>
                          setDraft((current) => ({
                            ...current,
                            candidate_ids: event.target.checked
                              ? [...current.candidate_ids, candidate.id]
                              : current.candidate_ids.filter((id) => id !== candidate.id),
                          }))
                        }
                      />
                      <span>
                        <strong>{candidate.id}</strong>
                        <small>
                          {candidate.selection_class} {t('· rank')} {candidate.selection_rank} ·{' '}
                          {candidate.sequence_length} aa
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              </section>
              <section className="lab-review-block live-lab-fields">
                <header>
                  <h2>{t('2. Simulation requirements')}</h2>
                </header>
                <label>
                  {t('Construct format')}
                  <select
                    value={draft.requirements.format}
                    disabled={busy || Boolean(order.quote)}
                    onChange={(event) => updateRequirement('format', event.target.value)}
                  >
                    <option value="VHH">VHH</option>
                    <option value="VHH-Fc">VHH-Fc</option>
                  </select>
                </label>
                <label>
                  {t('Amount per sample')}
                  <input
                    value={draft.requirements.amount}
                    disabled={busy || Boolean(order.quote)}
                    maxLength={160}
                    onChange={(event) => updateRequirement('amount', event.target.value)}
                  />
                </label>
                <label>
                  {t('Expression host')}
                  <input
                    value={draft.requirements.host}
                    disabled={busy || Boolean(order.quote)}
                    maxLength={160}
                    onChange={(event) => updateRequirement('host', event.target.value)}
                  />
                </label>
                <label>
                  {t('Buffer')}
                  <input
                    value={draft.requirements.buffer}
                    disabled={busy || Boolean(order.quote)}
                    maxLength={160}
                    onChange={(event) => updateRequirement('buffer', event.target.value)}
                  />
                </label>
              </section>
              {order.quote && (
                <section className="lab-review-block">
                  <header>
                    <h2>{t('3. Non-binding mock quote')}</h2>
                  </header>
                  <p>
                    {order.quote.sample_count} {t('sample(s) · illustrative total')}{' '}
                    {order.quote.illustrative_total} {order.quote.currency}{' '}
                    {t('· no external request sent.')}
                  </p>
                  <label className="lab-consent">
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      onChange={(event) => setAcknowledged(event.target.checked)}
                    />
                    <span>
                      {t(
                        'I understand this creates only a local simulated receipt and does not authorize an experiment or place a real order.',
                      )}
                    </span>
                  </label>
                </section>
              )}
              {(error || applyError) && (
                <p className="lab-warning" role="alert">
                  {error || applyError}
                </p>
              )}
            </div>
            <aside className="lab-summary" aria-label={t('Order summary')}>
              <h2>{t('Simulation Summary')}</h2>
              <dl>
                <div>
                  <dt>{t('Samples')}</dt>
                  <dd>
                    {draft.candidate_ids.length} {t('selected')}
                  </dd>
                </div>
                <div>
                  <dt>{t('Sequences')}</dt>
                  <dd>
                    {order.candidates.every((candidate) => candidate.sequence_ready)
                      ? t('Ready')
                      : t('Blocked')}
                  </dd>
                </div>
                <div>
                  <dt>{t('Provider')}</dt>
                  <dd>{order.provider}</dd>
                </div>
                <div>
                  <dt>{t('Real ordering')}</dt>
                  <dd>{t('Unavailable')}</dd>
                </div>
              </dl>
              {order.quote && (
                <div className="lab-quote">
                  <span>{t('Mock quote')}</span>
                  <strong>
                    {order.quote.illustrative_total} {order.quote.currency}
                  </strong>
                  <p>{t('Illustrative and non-binding.')}</p>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
      {!receipt && (
        <footer className="lab-footer">
          <DraftStatus status={input.status} />
          <p role="status">
            {order.quote
              ? t('Exact acknowledgement is required for the local mock receipt.')
              : input.status === 'local'
                ? t('Input kept in this browser tab; not saved to the server or submitted.')
                : order.draft
                  ? t('Complete draft saved server-side.')
                  : t('Complete the simulation-only request.')}
          </p>
          <div>
            {!order.quote && (
              <button
                className="secondary-button"
                disabled={busy || submitting || !complete || !order.capabilities.save}
                onClick={() => void apply('save')}
              >
                {t('Save simulation draft')}
              </button>
            )}
            {order.draft && !order.quote && (
              <button
                className="primary-button"
                disabled={
                  busy || submitting || input.status === 'local' || !order.capabilities.quote
                }
                onClick={() => void apply('quote')}
              >
                {t('Generate mock quote')}
                <ArrowRight size={14} />
              </button>
            )}
            {order.quote && (
              <button
                className="primary-button"
                disabled={busy || submitting || !acknowledged || !order.capabilities.submit}
                onClick={() => void apply('submit')}
              >
                {t('Create simulated receipt')}
                <ArrowRight size={14} />
              </button>
            )}
          </div>
        </footer>
      )}
    </section>
  );
}
