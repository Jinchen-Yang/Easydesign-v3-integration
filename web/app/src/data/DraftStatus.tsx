import { useTranslation } from 'react-i18next';
import type { InputDraftStatus } from './useInputDraft';

export function DraftStatus({ status }: { status: InputDraftStatus }) {
  const { t } = useTranslation('pro');
  if (status === 'empty') return null;
  return <p className="draft-status muted" role="status">{status === 'local'
    ? t('Input kept in this browser tab; not saved to the server or submitted.')
    : status === 'saved'
      ? t('Saved to the server; not submitted for execution.')
      : t('Request submitted. Follow its status in the project; recovery will not submit it again.')}</p>;
}
