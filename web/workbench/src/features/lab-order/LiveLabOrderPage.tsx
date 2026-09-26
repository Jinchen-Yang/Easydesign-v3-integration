import { useEffect, useState } from 'react';
import { ArrowRight, CheckCircle2, ShieldCheck } from 'lucide-react';
import type {
  ProductLabOrder,
  ProductLabOrderDraft,
  ProductLabOrderRequirements,
} from '../../live/contracts';

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
}: {
  order: ProductLabOrder;
  busy: boolean;
  error: string;
  onApply: (
    action: 'save' | 'quote' | 'submit',
    draft?: ProductLabOrderDraft,
    acknowledgement?: 'SIMULATED_ORDER_ONLY',
  ) => Promise<void>;
}) {
  const [draft, setDraft] = useState(() => draftFrom(order));
  const [acknowledged, setAcknowledged] = useState(false);
  useEffect(() => {
    setDraft(draftFrom(order));
  }, [order.revision]);
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
    <section className="lab-order live-lab-order" aria-label="Simulated lab order">
      <div className="lab-order-scroll">
        <header className="lab-title">
          <div>
            <h1>Lab Order</h1>
            <span className="lab-draft-badge">Simulation only</span>
          </div>
          <p>Validate the handoff and ordering boundary without contacting a vendor.</p>
        </header>
        <p className="lab-warning live-lab-disclaimer">
          <ShieldCheck size={17} /> {order.disclaimer}
        </p>
        {receipt ? (
          <div className="lab-layout">
            <div className="lab-form live-lab-receipt">
              <CheckCircle2 size={34} />
              <div>
                <span className="eyebrow">IMMUTABLE MOCK RECEIPT</span>
                <h2>Simulation accepted</h2>
                <p>
                  The full UI-to-API workflow completed. No experiment, payment, vendor request or
                  laboratory order was created.
                </p>
              </div>
              <dl className="lab-review-values">
                <div>
                  <dt>Receipt</dt>
                  <dd>{receipt.receipt_id}</dd>
                </div>
                <div>
                  <dt>Simulated order</dt>
                  <dd>{receipt.order_id}</dd>
                </div>
                <div>
                  <dt>Samples</dt>
                  <dd>{receipt.candidate_ids.length}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{receipt.ordering_status}</dd>
                </div>
                <div>
                  <dt>External request sent</dt>
                  <dd>{String(receipt.external_request_sent)}</dd>
                </div>
                <div>
                  <dt>Financial commitment</dt>
                  <dd>{String(receipt.financial_commitment)}</dd>
                </div>
                <div>
                  <dt>Experiment authorized</dt>
                  <dd>{String(receipt.experiment_authorized)}</dd>
                </div>
                <div>
                  <dt>Receipt SHA256</dt>
                  <dd className="lab-hash">{receipt.receipt_sha256}</dd>
                </div>
              </dl>
            </div>
            <aside className="lab-summary" aria-label="Simulation summary">
              <h2>Safety boundary</h2>
              <dl>
                <div>
                  <dt>Provider</dt>
                  <dd>{receipt.provider}</dd>
                </div>
                <div>
                  <dt>Environment</dt>
                  <dd>{receipt.environment}</dd>
                </div>
                <div>
                  <dt>Real ordering</dt>
                  <dd>Unavailable</dd>
                </div>
              </dl>
            </aside>
          </div>
        ) : (
          <div className="lab-layout">
            <div className="lab-form">
              <section className="lab-review-block">
                <header>
                  <h2>1. Gate 5 samples</h2>
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
                          {candidate.selection_class} · rank {candidate.selection_rank} ·{' '}
                          {candidate.sequence_length} aa
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              </section>
              <section className="lab-review-block live-lab-fields">
                <header>
                  <h2>2. Simulation requirements</h2>
                </header>
                <label>
                  Construct format
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
                  Amount per sample
                  <input
                    value={draft.requirements.amount}
                    disabled={busy || Boolean(order.quote)}
                    maxLength={160}
                    onChange={(event) => updateRequirement('amount', event.target.value)}
                  />
                </label>
                <label>
                  Expression host
                  <input
                    value={draft.requirements.host}
                    disabled={busy || Boolean(order.quote)}
                    maxLength={160}
                    onChange={(event) => updateRequirement('host', event.target.value)}
                  />
                </label>
                <label>
                  Buffer
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
                    <h2>3. Non-binding mock quote</h2>
                  </header>
                  <p>
                    {order.quote.sample_count} sample(s) · illustrative total{' '}
                    {order.quote.illustrative_total} {order.quote.currency} · no external request
                    sent.
                  </p>
                  <label className="lab-consent">
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      onChange={(event) => setAcknowledged(event.target.checked)}
                    />
                    <span>
                      I understand this creates only a local simulated receipt and does not
                      authorize an experiment or place a real order.
                    </span>
                  </label>
                </section>
              )}
              {error && (
                <p className="lab-warning" role="alert">
                  {error}
                </p>
              )}
            </div>
            <aside className="lab-summary" aria-label="Order summary">
              <h2>Simulation Summary</h2>
              <dl>
                <div>
                  <dt>Samples</dt>
                  <dd>{draft.candidate_ids.length} selected</dd>
                </div>
                <div>
                  <dt>Sequences</dt>
                  <dd>
                    {order.candidates.every((candidate) => candidate.sequence_ready)
                      ? 'Ready'
                      : 'Blocked'}
                  </dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>{order.provider}</dd>
                </div>
                <div>
                  <dt>Real ordering</dt>
                  <dd>Unavailable</dd>
                </div>
              </dl>
              {order.quote && (
                <div className="lab-quote">
                  <span>Mock quote</span>
                  <strong>
                    {order.quote.illustrative_total} {order.quote.currency}
                  </strong>
                  <p>Illustrative and non-binding.</p>
                </div>
              )}
            </aside>
          </div>
        )}
      </div>
      {!receipt && (
        <footer className="lab-footer">
          <p role="status">
            {order.quote
              ? 'Exact acknowledgement is required for the local mock receipt.'
              : order.draft
                ? 'Complete draft saved server-side.'
                : 'Complete the simulation-only request.'}
          </p>
          <div>
            {!order.quote && (
              <button
                className="secondary-button"
                disabled={busy || !complete || !order.capabilities.save}
                onClick={() => void onApply('save', draft)}
              >
                Save simulation draft
              </button>
            )}
            {order.draft && !order.quote && (
              <button
                className="primary-button"
                disabled={busy || !order.capabilities.quote}
                onClick={() => void onApply('quote')}
              >
                Generate mock quote <ArrowRight size={14} />
              </button>
            )}
            {order.quote && (
              <button
                className="primary-button"
                disabled={busy || !acknowledged || !order.capabilities.submit}
                onClick={() => void onApply('submit', undefined, 'SIMULATED_ORDER_ONLY')}
              >
                Create simulated receipt <ArrowRight size={14} />
              </button>
            )}
          </div>
        </footer>
      )}
    </section>
  );
}
