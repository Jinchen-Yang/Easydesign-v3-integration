import { useEffect, useRef, useState } from 'react';
import { ArrowRight, X } from 'lucide-react';
import type { Candidate } from '../../adapters/WorkbenchAdapter';
import {
  LAB_STEPS,
  labProgress,
  type LabOrderDraft,
  type LabOrderStep,
  type LabRequirements,
} from '../../domain/labOrder';

const requirementLabels: Record<keyof LabRequirements, string> = {
  format: 'Construct format',
  amount: 'Amount per sample',
  host: 'Expression host',
  buffer: 'Buffer',
  profile: 'Delivery & billing profile',
  preferredDate: 'Preferred delivery date',
  purchaseOrder: 'PO reference',
  sdsPurity: 'SDS-PAGE purity (%)',
  secPurity: 'SEC-HPLC purity (%)',
  endotoxin: 'Endotoxin requirement',
  concentration: 'Concentration (mg/mL)',
  notes: 'Additional requirements',
};

type TextKey = Exclude<keyof LabRequirements, 'format' | 'profile' | 'notes'>;
function RequirementField({
  name,
  value,
  onChange,
  placeholder,
}: {
  name: TextKey;
  value: string;
  onChange: (key: TextKey, value: string) => void;
  placeholder?: string;
}) {
  return (
    <label>
      {requirementLabels[name]}
      <input
        aria-label={requirementLabels[name]}
        type={name === 'preferredDate' ? 'date' : 'text'}
        value={value}
        maxLength={160}
        placeholder={placeholder}
        onChange={(e) => onChange(name, e.target.value)}
      />
    </label>
  );
}

export function LabOrderPage({
  draft,
  candidates,
  onChange,
}: {
  draft: LabOrderDraft;
  candidates: Candidate[];
  onChange: (draft: LabOrderDraft) => void;
}) {
  const [saved, setSaved] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const previewButton = useRef<HTMLButtonElement>(null);
  const r = draft.requirements;
  const progress = labProgress(draft);
  const selected = candidates.filter((candidate) => draft.candidateIds.includes(candidate.id));
  const stepIndex = LAB_STEPS.indexOf(draft.step);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
    stepHeading.current?.focus({ preventScroll: true });
  }, [draft.step]);
  const update = (next: LabOrderDraft) => {
    setSaved(false);
    onChange(next);
  };
  const changeRequirement = (key: keyof LabRequirements, value: string) =>
    update({ ...draft, requirements: { ...r, [key]: value }, reviewed: false });
  const changeStep = (step: LabOrderStep) => update({ ...draft, step });
  const footerMessage = !progress.samples
    ? 'Select at least one sample.'
    : !progress.requirements && draft.step !== 'samples'
      ? 'Choose a format, amount and delivery profile.'
      : draft.step === 'review' && !draft.reviewed
        ? 'Review the request and confirm below.'
        : 'Demo only · No data is sent to the lab.';
  return (
    <section className="lab-order" aria-label="Lab order preparation">
      <div className="lab-order-scroll" ref={scroll}>
        <header className="lab-title">
          <div>
            <h1>Lab Order</h1>
            <span className="lab-draft-badge">Draft</span>
          </div>
          <p>Turn your selected candidates into a lab request.</p>
        </header>
        <div className="lab-layout">
          <div className="lab-form">
            <details className="lab-scientist">
              <summary>Design Scientist · Request preparation</summary>
              <p>
                Choose your samples, then confirm their expression requirements. Full expression
                sequences are required before submission. Binding assays are not included in this
                request.
              </p>
            </details>
            <nav className="lab-tabs" aria-label="Request preparation">
              {LAB_STEPS.map((step, index) => (
                <button
                  key={step}
                  type="button"
                  aria-current={step === draft.step ? 'step' : undefined}
                  onClick={() => changeStep(step)}
                >
                  {index + 1} {['Samples', 'Requirements', 'Review'][index]}
                </button>
              ))}
            </nav>
            <div className="lab-panel" key={draft.step}>
              <h2 ref={stepHeading} tabIndex={-1}>
                {
                  ['Choose samples to send', 'Expression requirements', 'Review your lab request'][
                    stepIndex
                  ]
                }
              </h2>
              <p className="lab-caption">
                {
                  [
                    'Selected candidates from your finalized panel.',
                    'Shared settings for selected samples. Final scope is confirmed by the lab.',
                    'A final check before sharing your design with the lab.',
                  ][stepIndex]
                }
              </p>
              {draft.step === 'samples' && (
                <>
                  <div className="lab-samples">
                    {candidates.map((candidate) => (
                      <label className="lab-sample" key={candidate.id}>
                        <input
                          type="checkbox"
                          checked={draft.candidateIds.includes(candidate.id)}
                          aria-label={`Send ${candidate.id}`}
                          onChange={(e) =>
                            update({
                              ...draft,
                              candidateIds: e.target.checked
                                ? [...draft.candidateIds, candidate.id]
                                : draft.candidateIds.filter((id) => id !== candidate.id),
                              reviewed: false,
                            })
                          }
                        />
                        <span>
                          <strong>{candidate.id}</strong>
                          <small>Lysozyme / VHH · Demo candidate</small>
                        </span>
                        <span className="lab-sequence-needed">Full sequence required</span>
                      </label>
                    ))}
                  </div>
                  <details className="lab-sequence-previews">
                    <summary>View sequence previews</summary>
                    <p>Truncated previews cannot be used as expression sequences.</p>
                    {candidates
                      .filter((c) => draft.candidateIds.includes(c.id))
                      .map((candidate) => (
                        <p key={candidate.id}>
                          <strong>{candidate.id}</strong> <code>{candidate.sequencePreview}</code>
                        </p>
                      ))}
                  </details>
                </>
              )}
              {draft.step === 'requirements' && (
                <>
                  <div className="lab-fields">
                    <label>
                      Construct format
                      <select
                        aria-label="Construct format"
                        value={r.format}
                        onChange={(e) => changeRequirement('format', e.target.value)}
                      >
                        <option value="">Select a format</option>
                        <option>VHH</option>
                        <option>VHH-Fc</option>
                      </select>
                    </label>
                    <RequirementField
                      name="amount"
                      value={r.amount}
                      onChange={changeRequirement}
                      placeholder="Specify amount and unit"
                    />
                    <RequirementField
                      name="host"
                      value={r.host}
                      onChange={changeRequirement}
                      placeholder="To be agreed with the lab"
                    />
                    <RequirementField
                      name="buffer"
                      value={r.buffer}
                      onChange={changeRequirement}
                      placeholder="Specify buffer requirements"
                    />
                    <label className="lab-full">
                      Delivery & billing profile
                      <select
                        aria-label="Delivery & billing profile"
                        value={r.profile}
                        onChange={(e) => changeRequirement('profile', e.target.value)}
                      >
                        <option value="">Select saved details</option>
                        <option value="demo-lab">Research lab · Example profile</option>
                      </select>
                    </label>
                    <RequirementField
                      name="preferredDate"
                      value={r.preferredDate}
                      onChange={changeRequirement}
                    />
                    <RequirementField
                      name="purchaseOrder"
                      value={r.purchaseOrder}
                      onChange={changeRequirement}
                      placeholder="Optional"
                    />
                  </div>
                  <details className="lab-advanced">
                    <summary>Quality & delivery details</summary>
                    <div className="lab-fields">
                      <RequirementField
                        name="sdsPurity"
                        value={r.sdsPurity}
                        onChange={changeRequirement}
                        placeholder="Lab to confirm"
                      />
                      <RequirementField
                        name="secPurity"
                        value={r.secPurity}
                        onChange={changeRequirement}
                        placeholder="Lab to confirm"
                      />
                      <RequirementField
                        name="endotoxin"
                        value={r.endotoxin}
                        onChange={changeRequirement}
                        placeholder="Include units"
                      />
                      <RequirementField
                        name="concentration"
                        value={r.concentration}
                        onChange={changeRequirement}
                        placeholder="Lab to confirm"
                      />
                      <label className="lab-full">
                        Additional requirements
                        <textarea
                          aria-label="Additional requirements"
                          rows={3}
                          value={r.notes}
                          maxLength={2000}
                          onChange={(e) => changeRequirement('notes', e.target.value)}
                          placeholder="Special packaging or other requirements"
                        />
                      </label>
                    </div>
                  </details>
                </>
              )}
              {draft.step === 'review' && (
                <>
                  <section className="lab-review-block">
                    <header>
                      <h3>Selected samples</h3>
                      <button className="text-button" onClick={() => changeStep('samples')}>
                        Edit samples
                      </button>
                    </header>
                    <p>
                      {selected.map((candidate) => candidate.id).join(', ') ||
                        'No samples selected'}
                    </p>
                    <p className="lab-warning">
                      Full expression sequences required. Demo previews cannot be ordered.
                    </p>
                  </section>
                  <section className="lab-review-block">
                    <header>
                      <h3>Service & requirements</h3>
                      <button className="text-button" onClick={() => changeStep('requirements')}>
                        Edit requirements
                      </button>
                    </header>
                    <dl className="lab-review-values">
                      <div>
                        <dt>Service</dt>
                        <dd>VHH expression</dd>
                      </div>
                      <div>
                        <dt>Construct</dt>
                        <dd>{r.format || 'Not selected'}</dd>
                      </div>
                      <div>
                        <dt>Amount per sample</dt>
                        <dd>{r.amount || 'To be specified'}</dd>
                      </div>
                      {(Object.keys(r) as (keyof LabRequirements)[])
                        .filter(
                          (key) => !['format', 'amount', 'profile'].includes(key) && r[key].trim(),
                        )
                        .map((key) => (
                          <div key={key}>
                            <dt>{requirementLabels[key]}</dt>
                            <dd>{r[key]}</dd>
                          </div>
                        ))}
                    </dl>
                    <p>Binding assays are not included in this request.</p>
                  </section>
                  <section className="lab-review-block">
                    <header>
                      <h3>Delivery & billing</h3>
                      <button className="text-button" onClick={() => changeStep('requirements')}>
                        Edit profile
                      </button>
                    </header>
                    <p>
                      {r.profile
                        ? 'Research lab · Example profile (not a live account)'
                        : 'Choose a saved delivery, pickup and invoice profile.'}
                    </p>
                  </section>
                  <label className="lab-consent">
                    <input
                      type="checkbox"
                      checked={draft.reviewed}
                      disabled={!progress.requirements}
                      onChange={(e) => update({ ...draft, reviewed: e.target.checked })}
                    />
                    <span>
                      I have reviewed the selected samples and the information to be shared with
                      GentleGen.
                    </span>
                  </label>
                </>
              )}
            </div>
          </div>
          <aside className="lab-summary" aria-label="Order summary">
            <h2>Order Summary</h2>
            <dl>
              <div>
                <dt>Lab partner</dt>
                <dd>GentleGen</dd>
              </div>
              <div>
                <dt>Service</dt>
                <dd>VHH expression</dd>
              </div>
              <div>
                <dt>Samples</dt>
                <dd aria-live="polite" data-testid="lab-sample-count">
                  {selected.length} selected
                </dd>
              </div>
              <div>
                <dt>Sequence readiness</dt>
                <dd>Full sequences needed</dd>
              </div>
              <div>
                <dt>Delivery</dt>
                <dd>Lab to confirm</dd>
              </div>
            </dl>
            <div className="lab-quote">
              <span>Quote</span>
              <strong>To be quoted</strong>
              <p>Price and turnaround are not yet confirmed.</p>
            </div>
          </aside>
        </div>
      </div>
      <footer className="lab-footer">
        <p role="status">{saved ? 'Draft retained in this workspace.' : footerMessage}</p>
        <div>
          <button
            className="secondary-button"
            onClick={() => {
              onChange(draft);
              setSaved(true);
            }}
          >
            Save Draft
          </button>
          {draft.step === 'review' ? (
            <button
              ref={previewButton}
              className="primary-button"
              disabled={!progress.review}
              onClick={() => dialog.current?.showModal()}
            >
              Preview confirmation <ArrowRight size={14} />
            </button>
          ) : (
            <button
              className="primary-button"
              disabled={draft.step === 'samples' ? !progress.samples : !progress.requirements}
              onClick={() => {
                changeStep(LAB_STEPS[stepIndex + 1]);
              }}
            >
              {draft.step === 'samples' ? 'Define requirements' : 'Review request'}{' '}
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </footer>
      <dialog
        className="lab-confirm"
        ref={dialog}
        aria-labelledby="lab-confirm-title"
        onClose={() => previewButton.current?.focus()}
      >
        <header>
          <h2 id="lab-confirm-title">Send a quote request?</h2>
          <button
            className="icon-button"
            aria-label="Close confirmation"
            onClick={() => dialog.current?.close()}
          >
            <X size={18} />
          </button>
        </header>
        <p>{selected.length} samples · VHH expression · GentleGen</p>
        <p>
          A connected service would share the approved full sequences, requirements and account
          details with the lab. Price and production start require confirmation.
        </p>
        <p className="lab-warning">
          No order submitted. This demo has no orderable sequences or connected lab account.
        </p>
        <div className="lab-confirm-actions">
          <button className="secondary-button" onClick={() => dialog.current?.close()}>
            Back to draft
          </button>
          <button className="primary-button" disabled>
            Request Quote
          </button>
        </div>
      </dialog>
    </section>
  );
}
