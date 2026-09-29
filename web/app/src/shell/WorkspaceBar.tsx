import { useEffect, useRef, useState } from 'react';
import { ChevronDown, LayoutGrid, Users, ChartNoAxesCombined, ShieldCheck, Settings, LogOut } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AccountScope, AccountSession } from '../shared/account-client';
import { useSession } from './SessionProvider';
import { useI18n } from './I18nProvider';
import { useAccountPanel, type AccountSection } from './AccountPanel';
import { readProjectRoute, workspaceHref } from '../views/easy/routeParams';

export function AccountLanguage() {
  const { locale, changeLocale } = useI18n();
  const { t } = useTranslation('account');
  return <div className="account-language" role="group" aria-label={t('Language')}>
    <button type="button" aria-pressed={locale === 'zh'} onClick={() => changeLocale('zh')}>中文</button>
    <button type="button" aria-pressed={locale === 'en'} onClick={() => changeLocale('en')}>EN</button>
  </div>;
}

export function AccountMenu({ session, expanded = false }: { session: AccountSession; expanded?: boolean }) {
  const { t } = useTranslation('account');
  const { logout } = useSession();
  const openPanel = useAccountPanel();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    root.current?.addEventListener('keydown', escape);
    const node = root.current;
    return () => { document.removeEventListener('pointerdown', outside); node?.removeEventListener('keydown', escape); };
  }, [open]);
  const links: Array<[AccountSection, string, typeof Users]> = [
    ['workspaces', 'My workspaces', LayoutGrid], ['teams', 'Team collaboration', Users],
    ['usage', 'Resource usage', ChartNoAxesCombined], ['password', 'Account security', ShieldCheck],
    ...(session.user.role === 'admin' ? [['admin', 'Administration', Settings] as [AccountSection, string, typeof Users]] : []),
  ];
  return <div className={`account-menu${expanded ? ' account-menu-expanded' : ''}`} ref={root}>
    <button ref={trigger} type="button" className="account-avatar-trigger" aria-label={t('Open account menu')} aria-expanded={open}
      onClick={() => setOpen(!open)}>
      <span className="account-avatar">{(session.user.display_name || session.user.username).slice(0, 1).toUpperCase()}</span>
      {expanded && <span className="account-profile-name">{session.user.display_name}<small>@{session.user.username}</small></span>}
      <ChevronDown size={14}/>
    </button>
    {open && <div className="account-popover" aria-label={t('Account menu')}>
      <div className="account-popover-identity"><strong>{session.user.display_name}</strong><small>@{session.user.username}</small></div>
      {links.map(([key, label, Icon]) => <a key={key} href={`#/account?section=${key}`} onClick={event => {
        setOpen(false);
        if (openPanel) { event.preventDefault(); trigger.current?.focus(); openPanel(key); }
      }}><Icon size={17}/>{t(label)}</a>)}
      <AccountLanguage/>
      <button type="button" onClick={() => { setOpen(false); void logout(); }}><LogOut size={17}/>{t('Sign out')}</button>
    </div>}
  </div>;
}

export function WorkspaceBar({ session, scope, view, project, computeAvailable }: {
  session: AccountSession; scope: AccountScope; view: 'easy' | 'pro'; project?: string | null; computeAvailable: boolean;
}) {
  const { t } = useTranslation('account');
  const projectId = project ?? readProjectRoute();
  return <header className="workspace-bar">
    <LayoutGrid size={17} aria-hidden="true"/>
    <select aria-label={t('Switch workspace')} value={scope.id} onChange={event => { location.hash = workspaceHref(event.target.value, view); }}>
      {session.scopes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    <span className="workspace-role">{scope.role === 'observer' ? t('Read-only observer') : scope.can_execute ? t('Scientific approver') : t('Team collaborator')}</span>
    {!computeAvailable && <span className="account-compute-off">{t('No scientific executor connected')}</span>}
    <nav className="workspace-view-switch" aria-label={t('Workspace view')}>
      {(['easy', 'pro'] as const).map(mode => <a key={mode} aria-current={view === mode ? 'page' : undefined}
        href={workspaceHref(scope.id, mode, projectId)}>{mode === 'easy' ? 'Easy' : 'Pro'}</a>)}
    </nav>
    <AccountMenu session={session}/>
  </header>;
}
