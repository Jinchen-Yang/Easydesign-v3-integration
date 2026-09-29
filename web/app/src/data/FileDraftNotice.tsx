import { useTranslation } from 'react-i18next';

export function FileDraftNotice({ file, onRemove }: { file: { name: string; size: number }; onRemove: () => void }) {
  const { t } = useTranslation('pro');
  return <p className="draft-status muted" role="status">
    {t('Attachment {{name}} ({{size}} bytes) must be selected again after refresh.', { name: file.name, size: file.size })}{' '}
    <button type="button" className="text-button" onClick={onRemove}>{t('Remove attachment')}</button>
  </p>;
}
