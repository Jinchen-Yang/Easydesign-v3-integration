import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';

/** A permission denial is distinct from an expired session or network retry. */
export function WorkspaceAccessNotice({ message, refresh }: { message?: string | null; refresh: () => Promise<void> }) {
  const { t } = useTranslation('common');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return <main className="account-login">
    <div className="account-auth-mark"><ShieldCheck size={25}/></div>
    <h1>{t('Workspace access is unavailable.')}</h1>
    <p role="alert">{error || message}</p>
    <button type="button" className="account-primary" disabled={busy} onClick={() => {
      setBusy(true); setError('');
      void refresh().catch(reason => setError(reason instanceof Error ? reason.message : t('Workspace access is unavailable.'))).finally(() => setBusy(false));
    }}>{t('shell.retry')}</button>
  </main>;
}
