import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useSession } from './SessionProvider';
import { useI18n } from './I18nProvider';

/**
 * Overlay shown while the session state machine is `expired` (phase 2 of the
 * execution guide). The page underneath — including its unsaved input — stays
 * mounted; this modal performs the same-account re-login that restores the
 * interrupted route and drafts. It renders nothing in any other state.
 */
export function SessionRecoveryModal() {
  const { state, recoverSession, dismissRecovery } = useSession();
  const { t } = useI18n();
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const generation = useRef(0);
  useEffect(() => {
    if (state.kind !== 'expired') { generation.current++; setPassword(''); setError(''); setBusy(false); return; }
    const node = dialog.current;
    if (node && !node.open) {
      if (typeof node.showModal === 'function') node.showModal();
      else node.setAttribute('open', '');
    }
  }, [state.kind]);

  if (state.kind !== 'expired') return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || password.length === 0) return;
    const request = ++generation.current;
    setBusy(true);
    setError('');
    try {
      await recoverSession(password);
      // Success unmounts this modal through the state change.
    } catch (reason) {
      if (generation.current === request) setError(reason instanceof Error ? reason.message : t('recovery.failed'));
    } finally {
      if (generation.current === request) setBusy(false);
    }
  }

  return (
    <dialog ref={dialog} className="session-recovery-dialog" aria-label={t('recovery.title')} onCancel={event => { event.preventDefault(); dismissRecovery(); }}>
      <div className="session-recovery-modal">
        <h2>{t('recovery.title')}</h2>
        <p>{t('recovery.description')}</p>
        <p className="session-recovery-account">{t('recovery.account', { name: state.previousSession.user.display_name })}</p>
        <form onSubmit={submit}>
          <input
            type="password"
            value={password}
            autoFocus
            required
            autoComplete="current-password"
            placeholder={t('recovery.password')}
            aria-label={t('recovery.password')}
            onChange={(event) => { setPassword(event.target.value); }}
          />
          <button type="submit" className="session-recovery-primary" disabled={busy || password.length === 0}>
            {busy ? t('recovery.busy') : t('recovery.submit')}
          </button>
          <button type="button" onClick={dismissRecovery}>{t('recovery.cancel')}</button>
        </form>
        {error !== '' && <p className="session-recovery-error" role="alert">{error}</p>}
        <p className="recovery-hint">{t('recovery.hint')}</p>
      </div>
    </dialog>
  );
}
