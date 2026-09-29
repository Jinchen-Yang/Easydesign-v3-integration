import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from './SessionProvider';
import '../views/account/accounts.css';

export type AccountSection = 'workspaces' | 'teams' | 'usage' | 'password' | 'admin';
export const accountSections: AccountSection[] = ['workspaces', 'teams', 'usage', 'password', 'admin'];
const AccountApp = lazy(() => import('../views/account/AccountApp').then(m => ({ default: m.AccountApp })));
const AccountPanelContext = createContext<((section: AccountSection) => void) | null>(null);
export function useAccountPanel() { return useContext(AccountPanelContext); }

/** Settings are a sibling overlay: opening them never replaces the active project. */
export function AccountPanelProvider({ children }: { children: ReactNode }) {
  const { state } = useSession();
  const { t } = useTranslation('common');
  const [section, setSection] = useState<AccountSection | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const owner = useRef<string | null>(null);
  const close = useCallback(() => {
    // Release native modal inertness before restoring focus outside the dialog.
    const node = dialog.current;
    if (node?.open) {
      if (typeof node.close === 'function') node.close();
      else node.removeAttribute('open');
    }
    setSection(null);
    trigger.current?.focus();
  }, []);
  useEffect(() => {
    window.addEventListener('hashchange', close);
    return () => window.removeEventListener('hashchange', close);
  }, [close]);
  const open = useCallback((next: AccountSection) => {
    if (state.kind !== 'authenticated') return;
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    owner.current = state.session.user.id;
    setSection(next);
  }, [state]);
  useEffect(() => {
    if (state.kind === 'guest' || (state.kind === 'authenticated' && owner.current !== state.session.user.id)) close();
  }, [state, close]);
  const visible = section !== null && state.kind !== 'guest' && state.kind !== 'expired';
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (visible && !node.open) {
      if (typeof node.showModal === 'function') node.showModal();
      else node.setAttribute('open', '');
    } else if (!visible && node.open) {
      if (typeof node.close === 'function') node.close();
      else node.removeAttribute('open');
    }
  }, [visible]);
  return <AccountPanelContext.Provider value={open}>
    {children}
    {section !== null && <dialog ref={dialog} className="account-dialog" aria-label={t('Account and workspace settings')}
      onCancel={event => { event.preventDefault(); close(); }} onClick={event => {
        if (event.target === event.currentTarget) {
          const rect = event.currentTarget.getBoundingClientRect();
          if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
        }
      }}>
      <Suspense fallback={<div className="account-loading">{t('Checking session…')}</div>}>
        <AccountApp presentation="dialog" initialSection={section} onClose={close}/>
      </Suspense>
    </dialog>}
  </AccountPanelContext.Provider>;
}
