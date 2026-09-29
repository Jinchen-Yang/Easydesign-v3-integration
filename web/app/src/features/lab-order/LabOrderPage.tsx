import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('pro');
  return (
    <label>
      {t(requirementLabels[name])}
      <input
        aria-label={t(requirementLabels[name])}
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
  const { t } = useTranslation('pro');
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
    ? t('Select at least one sample.')
    : !progress.requirements && draft.step !== 'samples'
      ? t('Choose a format, amount and delivery profile.')
      : draft.step === 'review' && !draft.reviewed
        ? t('Review the request and confirm below.')
        : t('Demo only · No data is sent to the lab.');
  return (
    <section className="lab-order" aria-label={t('Lab order preparation')}>
      <div className="lab-order-scroll" ref={scroll}>
        <header className="lab-title">
          <div>
            <h1>{t('Lab Order')}</h1>
            <span className="lab-draft-badge">{t('Draft')}</span>
          </div>
          <p>{t('Turn your selected candidates into a lab request.')}</p>
        </header>
        <div className="lab-layout">
          <div className="lab-form">
            <details className="lab-scientist">
              <summary>{t('Design Scientist · Request preparation')}</summary>
              <p>
                {t(
                  'Choose your samples, then confirm their expression requirements. Full expression sequences are required before submission. Binding assays are not included in this request.',
                )}
              </p>
            </details>
            <nav className="lab-tabs" aria-label={t('Request preparation')}>
              {LAB_STEPS.map((step, index) => (
                <button
                  key={step}
                  type="button"
                  aria-current={step === draft.step ? 'step' : undefined}
                  onClick={() => changeStep(step)}
                >
                  {index + 1} {[t('Samples'), t('Requirements'), t('Review')][index]}
                </button>
              ))}
            </nav>
            <div className="lab-panel" key={draft.step}>
              <h2 ref={stepHeading} tabIndex={-1}>
                {
                  [
                    t('Choose samples to send'),
                    t('Expression requirements'),
                    t('Review your lab request'),
                  ][stepIndex]
                }
              </h2>
              <p className="lab-caption">
                {
                  [
                    t('Selected candidates from your finalized panel.'),
                    t('Shared settings for selected samples. Final scope is confirmed by the lab.'),
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
                          aria-label={t('Send {{name}}', {
                            name: candidate.id,
                          })}
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
                          <small>{t('Lysozyme / VHH · Demo candidate')}</small>
                        </span>
                        <span className="lab-sequence-needed">{t('Full sequence required')}</span>
                      </label>
                    ))}
                  </div>
                  <details className="lab-sequence-previews">
                    <summary>{t('View sequence previews')}</summary>
                    <p>{t('Truncated previews cannot be used as expression sequences.')}</p>
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
                      {t('Construct format')}
                      <select
                        aria-label={t('Construct format')}
                        value={r.format}
                        onChange={(e) => changeRequirement('format', e.target.value)}
                      >
                        <option value="">{t('Select a format')}</option>
                        <option>VHH</option>
                        <option>VHH-Fc</option>
                      </select>
                    </label>
                    <RequirementField
                      name="amount"
                      value={r.amount}
                      onChange={changeRequirement}
                      placeholder={t('Specify amount and unit')}
                    />
                    <RequirementField
                      name="host"
                      value={r.host}
                      onChange={changeRequirement}
                      placeholder={t('To be agreed with the lab')}
                    />
                    <RequirementField
                      name="buffer"
                      value={r.buffer}
                      onChange={changeRequirement}
                      placeholder={t('Specify buffer requirements')}
                    />
                    <label className="lab-full">
                      {t('Delivery & billing profile')}
                      <select
                        aria-label={t('Delivery & billing profile')}
                        value={r.profile}
                        onChange={(e) => changeRequirement('profile', e.target.value)}
                      >
                        <option value="">{t('Select saved details')}</option>
                        <option value="demo-lab">{t('Research lab · Example profile')}</option>
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
                      placeholder={t('Optional')}
                    />
                  </div>
                  <details className="lab-advanced">
                    <summary>{t('Quality & delivery details')}</summary>
                    <div className="lab-fields">
                      <RequirementField
                        name="sdsPurity"
                        value={r.sdsPurity}
                        onChange={changeRequirement}
                        placeholder={t('Lab to confirm')}
                      />
                      <RequirementField
                        name="secPurity"
                        value={r.secPurity}
                        onChange={changeRequirement}
                        placeholder={t('Lab to confirm')}
                      />
                      <RequirementField
                        name="endotoxin"
                        value={r.endotoxin}
                        onChange={changeRequirement}
                        placeholder={t('Include units')}
                      />
                      <RequirementField
                        name="concentration"
                        value={r.concentration}
                        onChange={changeRequirement}
                        placeholder={t('Lab to confirm')}
                      />
                      <label className="lab-full">
                        {t('Additional requirements')}
                        <textarea
                          aria-label={t('Additional requirements')}
                          rows={3}
                          value={r.notes}
                          maxLength={2000}
                          onChange={(e) => changeRequirement('notes', e.target.value)}
                          placeholder={t('Special packaging or other requirements')}
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
                      <h3>{t('Selected samples')}</h3>
                      <button className="text-button" onClick={() => changeStep('samples')}>
                        {t('Edit samples')}
                      </button>
                    </header>
                    <p>
                      {selected.map((candidate) => candidate.id).join(', ') ||
                        t('No samples selected')}
                    </p>
                    <p className="lab-warning">
                      {t('Full expression sequences required. Demo previews cannot be ordered.')}
                    </p>
                  </section>
                  <section className="lab-review-block">
                    <header>
                      <h3>{t('Service & requirements')}</h3>
                      <button className="text-button" onClick={() => changeStep('requirements')}>
                        {t('Edit requirements')}
                      </button>
                    </header>
                    <dl className="lab-review-values">
                      <div>
                        <dt>{t('Service')}</dt>
                        <dd>{t('VHH expression')}</dd>
                      </div>
                      <div>
                        <dt>{t('Construct')}</dt>
                        <dd>{r.format || t('Not selected')}</dd>
                      </div>
                      <div>
                        <dt>{t('Amount per sample')}</dt>
                        <dd>{r.amount || t('To be specified')}</dd>
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
                    <p>{t('Binding assays are not included in this request.')}</p>
                  </section>
                  <section className="lab-review-block">
                    <header>
                      <h3>{t('Delivery & billing')}</h3>
                      <button className="text-button" onClick={() => changeStep('requirements')}>
                        {t('Edit profile')}
                      </button>
                    </header>
                    <p>
                      {r.profile
                        ? t('Research lab · Example profile (not a live account)')
                        : t('Choose a saved delivery, pickup and invoice profile.')}
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
                      {t(
                        'I have reviewed the selected samples and the information to be shared with GentleGen.',
                      )}
                    </span>
                  </label>
                </>
              )}
            </div>
          </div>
          <aside className="lab-summary" aria-label={t('Order summary')}>
            <h2>{t('Order Summary')}</h2>
            <dl>
              <div>
                <dt>{t('Lab partner')}</dt>
                <dd>{t('GentleGen')}</dd>
              </div>
              <div>
                <dt>{t('Service')}</dt>
                <dd>{t('VHH expression')}</dd>
              </div>
              <div>
                <dt>{t('Samples')}</dt>
                <dd aria-live="polite" data-testid="lab-sample-count">
                  {selected.length} {t('selected')}
                </dd>
              </div>
              <div>
                <dt>{t('Sequence readiness')}</dt>
                <dd>{t('Full sequences needed')}</dd>
              </div>
              <div>
                <dt>{t('Delivery')}</dt>
                <dd>{t('Lab to confirm')}</dd>
              </div>
            </dl>
            <div className="lab-quote">
              <span>{t('Quote')}</span>
              <strong>{t('To be quoted')}</strong>
              <p>{t('Price and turnaround are not yet confirmed.')}</p>
            </div>
          </aside>
        </div>
      </div>
      <footer className="lab-footer">
        <p role="status">{saved ? t('Draft retained in this workspace.') : footerMessage}</p>
        <div>
          <button
            className="secondary-button"
            onClick={() => {
              onChange(draft);
              setSaved(true);
            }}
          >
            {t('Save Draft')}
          </button>
          {draft.step === 'review' ? (
            <button
              ref={previewButton}
              className="primary-button"
              disabled={!progress.review}
              onClick={() => dialog.current?.showModal()}
            >
              {t('Preview confirmation')}
              <ArrowRight size={14} />
            </button>
          ) : (
            <button
              className="primary-button"
              disabled={draft.step === 'samples' ? !progress.samples : !progress.requirements}
              onClick={() => {
                changeStep(LAB_STEPS[stepIndex + 1]);
              }}
            >
              {draft.step === 'samples' ? t('Define requirements') : t('Review request')}{' '}
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
          <h2 id="lab-confirm-title">{t('Send a quote request?')}</h2>
          <button
            className="icon-button"
            aria-label={t('Close confirmation')}
            onClick={() => dialog.current?.close()}
          >
            <X size={18} />
          </button>
        </header>
        <p>
          {selected.length} {t('samples · VHH expression · GentleGen')}
        </p>
        <p>
          {t(
            'A connected service would share the approved full sequences, requirements and account details with the lab. Price and production start require confirmation.',
          )}
        </p>
        <p className="lab-warning">
          {t('No order submitted. This demo has no orderable sequences or connected lab account.')}
        </p>
        <div className="lab-confirm-actions">
          <button className="secondary-button" onClick={() => dialog.current?.close()}>
            {t('Back to draft')}
          </button>
          <button className="primary-button" disabled>
            {t('Request Quote')}
          </button>
        </div>
      </dialog>
    </section>
  );
}
