import { useTranslation } from 'react-i18next';
import { ArrowRight, Check, Columns2, PencilLine, RotateCcw } from 'lucide-react';
import type { WorkbenchSnapshot } from '../../adapters/WorkbenchAdapter';
export function DecisionBar({
  snapshot,
  onApprove,
  onCompare,
  onEdit,
  onRevise,
  onReplay,
  onLabOrder,
}: {
  snapshot: WorkbenchSnapshot;
  onApprove: () => void;
  onCompare: () => void;
  onEdit: () => void;
  onRevise: () => void;
  onReplay: () => void;
  onLabOrder: () => void;
}) {
  const { t } = useTranslation('pro');
  const d = snapshot.decision;
  if (snapshot.completed)
    return (
      <footer className="decision-bar completed" role="region" aria-label={t('Demo completed')}>
        <span className="decision-icon">
          <Check size={17} />
        </span>
        <div className="decision-copy">
          <strong>{t('Panel finalized')}</strong>
          <span>{t('6 finalists · Demo complete · Every step is still available to review.')}</span>
        </div>
        <button className="secondary-button" onClick={onReplay}>
          <RotateCcw size={14} /> {t('Replay demo')}
        </button>
        <button className="primary-button" onClick={onLabOrder}>
          {t('Prepare Lab Order')}
          <ArrowRight size={15} />
        </button>
      </footer>
    );
  if (!d) return null;
  return (
    <footer className="decision-bar" role="region" aria-label={t('Decision')}>
      <span className="decision-icon">
        <Check size={17} />
      </span>
      <div className="decision-copy">
        <strong>{t(d.title)}</strong>
        <span>{t(d.description)}</span>
      </div>
      <div className="decision-actions">
        {['site', 'candidates'].includes(d.phase) && (
          <button className="secondary-button" onClick={onCompare}>
            <Columns2 size={14} /> {t('Compare')}
          </button>
        )}
        {['site', 'design'].includes(d.phase) && (
          <button className="secondary-button" onClick={onEdit}>
            <PencilLine size={14} /> {t('Edit')}
          </button>
        )}
        {d.phase === 'pilot' && (
          <button className="secondary-button" onClick={onRevise}>
            <PencilLine size={14} /> {t('Revise')}
          </button>
        )}
        <button className="primary-button" onClick={onApprove}>
          {t(d.label)}
          <ArrowRight size={15} />
        </button>
      </div>
    </footer>
  );
}
