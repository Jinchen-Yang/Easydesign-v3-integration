import { useTranslation } from 'react-i18next';
import { FlaskConical } from 'lucide-react';
export function DemoBadge({
  short = false,
  mode = 'demo',
}: {
  short?: boolean;
  mode?: 'demo' | 'live';
}) {
  const { t } = useTranslation('pro');
  return (
    <span className="demo-badge">
      <FlaskConical size={12} />
      {mode === 'live' ? t('Live workspace') : short ? t('Demo') : t('Demo fixture')}
    </span>
  );
}
