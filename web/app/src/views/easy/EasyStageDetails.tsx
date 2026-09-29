import { translate, type Locale } from './i18n';
import type { EasySnapshot } from './contracts';

/** Read-only stage outputs from the adapter. Never changes a design or its progress. */
export function EasyStageDetails({
  step,
  state,
  locale,
}: {
  step: number;
  state: EasySnapshot;
  locale: Locale;
}) {
  const t = (key: string, values?: Record<string, string | number>) =>
    translate(locale, key, values);
  const { reference, review } = state;
  const site = review.sites.find((item) => item.id === review.selectedSite);
  const counts = step === 3 ? review.pilot : review.scale;
  const titles = [
    'Reference target',
    site ? t('Site {site}', { site: site.id }) : t('Site'),
    review.design.binderType,
    'Pilot results',
    'Scale results',
  ];
  return (
    <div className="easy-results-panel">
      <div className="easy-result-section-title">
        <h3>{t(titles[step])}</h3>
        <span>{t('DEMO')}</span>
      </div>
      {step === 0 && (
        <dl className="easy-review-facts">
          <div>
            <dt>{t('Target')}</dt>
            <dd>{t(reference.targetName)}</dd>
          </div>
          <div>
            <dt>UniProt</dt>
            <dd>{reference.uniprot}</dd>
          </div>
          <div>
            <dt>{t('Structure / chain')}</dt>
            <dd>
              {reference.pdbId} / {reference.targetChain}
            </dd>
          </div>
        </dl>
      )}
      {step === 1 && site && (
        <dl className="easy-review-facts">
          <div>
            <dt>{t('Residues')}</dt>
            <dd>{site.residues.join(' · ')}</dd>
          </div>
          <div>
            <dt>{t('Accessibility / geometry')}</dt>
            <dd>
              {site.accessibility.toFixed(2)} / {site.geometry.toFixed(2)}
            </dd>
          </div>
        </dl>
      )}
      {step === 2 && (
        <dl className="easy-review-facts">
          <div>
            <dt>{t('Scaffold')}</dt>
            <dd>{t(review.design.scaffold)}</dd>
          </div>
          {review.design.arms.map((arm) => (
            <div key={arm.id}>
              <dt>{t(arm.label)}</dt>
              <dd>{t('{count} candidates', { count: arm.count })}</dd>
            </div>
          ))}
        </dl>
      )}
      {(step === 3 || step === 4) && (
        <>
          <div className="easy-review-counts">
            <div>
              <strong>{counts.total}</strong>
              <span>{t('Candidates')}</span>
            </div>
            <div>
              <strong>{counts.passed}</strong>
              <span>{t('Passing')}</span>
            </div>
            <div>
              <strong>{counts.filtered}</strong>
              <span>{t('Filtered')}</span>
            </div>
          </div>
          {step === 3 ? (
            <table className="easy-pilot-table" aria-label={t('Pilot candidates')}>
              <thead>
                <tr>
                  <th>{t('Candidate')}</th>
                  <th>{t('Interface')}</th>
                  <th>{t('Status')}</th>
                </tr>
              </thead>
              <tbody>
                {review.pilot.candidates.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td>
                    <td>{item.interface.toFixed(2)}</td>
                    <td className={item.status}>
                      {item.status === 'pass' ? t('Pass') : t('Filtered')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="easy-result-note">
              {t('{batches} batches × {size} candidates', {
                batches: review.scale.batches,
                size: review.scale.batchSize,
              })}
            </p>
          )}
        </>
      )}
      <p className="easy-result-note">
        {t(step === 1 ? 'Simulated site · Not a validated epitope' : 'Fixed lysozyme demo')}
      </p>
    </div>
  );
}
