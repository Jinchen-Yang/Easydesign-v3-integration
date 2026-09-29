import { useMemo } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { HashRouter, Link, Routes, Route, useSearchParams } from 'react-router-dom';
import { I18nProvider, useI18n } from './I18nProvider';
import { SessionProvider, useSession } from './SessionProvider';
import { SessionRecoveryModal } from './SessionRecoveryModal';
import { EasyWorkspace } from '../views/easy/EasyWorkspace';
import { EasyApp } from '../views/easy/EasyApp';
import { EasyDemoAdapter } from '../views/easy/EasyDemoAdapter';
import { ProWorkspace } from '../views/pro/ProWorkspace';
import { AccountApp } from '../views/account/AccountApp';
import { workspaceHref } from '../views/easy/routeParams';
import { fetchProjects } from '../data/projects';
import '../styles/shell.css';

/**
 * Unified application shell (execution guide phase 3). Hash Router keeps every
 * deep link on the single `/app/` document; the shell chrome (nav + language +
 * session chip) wraps portal-style routes, while the two workspaces render
 * full-bleed with their own bars. `/demo` mounts the bilingual Easy demo until
 * phase 4 promotes it to the guest home.
 */
export function AppShell() {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 } },
      }),
    [],
  );
  return (
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <HashRouter>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/projects" element={<ProjectRoute />} />
              <Route path="/projects/:id" element={<ProjectRoute />} />
              <Route path="/account" element={<AccountRoute />} />
              <Route path="/demo" element={<DemoRoute />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </HashRouter>
          <SessionRecoveryModal />
        </SessionProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}

function LanguageToggle() {
  const { locale, changeLocale, t } = useI18n();
  return (
    <div className="shell-language" role="group" aria-label={t('shell.language')}>
      <button type="button" aria-pressed={locale === 'zh'} onClick={() => changeLocale('zh')}>中文</button>
      <button type="button" aria-pressed={locale === 'en'} onClick={() => changeLocale('en')}>EN</button>
    </div>
  );
}

/** Shell chrome for portal-style pages; workspaces opt out (full-bleed). */
function ShellFrame({ title, children }: { title: string; children?: React.ReactNode }) {
  const { t } = useI18n();
  const { state } = useSession();
  return (
    <main className="shell-root">
      <header className="shell-header">
        <strong>{t('shell.brand')}</strong>
        <nav className="shell-nav">
          <Link to="/">{t('nav.home')}</Link>
          <Link to="/projects">{t('nav.projects')}</Link>
          <Link to="/account">{t('nav.account')}</Link>
          <Link to="/demo">{t('nav.demo')}</Link>
        </nav>
        <span className="shell-session">
          {state.kind === 'authenticated' ? state.session.user.display_name : <Link to="/account">{t('shell.signIn')}</Link>}
        </span>
        <LanguageToggle />
      </header>
      <section className="shell-body">
        <h1>{title}</h1>
        {children}
      </section>
    </main>
  );
}

function SessionStatus() {
  const { state, dismissRecovery } = useSession();
  const { t } = useI18n();
  if (state.kind === 'checking') return <p className="shell-status" data-testid="session-checking">{t('shell.loading')}</p>;
  if (state.kind === 'guest') return <p className="shell-status" data-testid="session-guest">{t('shell.guest')}</p>;
  if (state.kind === 'network-error') {
    return (
      <div className="shell-status" data-testid="session-network-error">
        <p>{t('shell.networkError')}</p>
        <button type="button" onClick={state.retry}>{t('shell.retry')}</button>
        <button type="button" onClick={dismissRecovery}>{t('shell.giveUp')}</button>
      </div>
    );
  }
  return null;
}

function HomePage() {
  const { t } = useI18n();
  const { state } = useSession();
  const [searchParams] = useSearchParams();
  const scopeId = searchParams.get('scope');
  const scope = state.kind === 'authenticated'
    ? (state.session.scopes.find((item) => item.id === scopeId) ?? state.scope)
    : null;
  const enabled = state.kind === 'authenticated' && scope !== null;
  const query = useQuery({
    queryKey: ['projects', scope?.id ?? '-', state.kind === 'authenticated' ? state.session.user.id : '-'],
    queryFn: () => (state.kind === 'authenticated' && scope ? fetchProjects(state.session, scope) : Promise.resolve([])),
    enabled,
  });
  return (
    <ShellFrame title={t('nav.home')}>
      <SessionStatus />
      {enabled && scope && (state.kind === 'authenticated') && (
        <div className="shell-projects">
          <div className="shell-projects-head">
            <span>{t('placeholder.projects')}</span>
            <a className="shell-new" href={workspaceHref(scope.id, 'easy')}>{t('projects.new')}</a>
          </div>
          {query.isLoading && <p className="shell-status">{t('projects.loading')}</p>}
          {query.isError && <p className="shell-status" role="alert">{(query.error as Error).message}</p>}
          {query.data?.length === 0 && <p className="shell-status">{t('projects.empty')}</p>}
          <ul>
            {query.data?.map((project) => (
              <li key={project.id}>
                <a href={workspaceHref(scope.id, 'easy', project.id)}>{project.title || project.id}</a>
                {project.status && <small>{project.status}</small>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </ShellFrame>
  );
}

function ProjectRoute() {
  const [searchParams] = useSearchParams();
  return searchParams.get('view') === 'pro' ? <ProWorkspace /> : <EasyWorkspace />;
}

function AccountRoute() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('nav.account')}>
      <AccountApp />
    </ShellFrame>
  );
}

function DemoRoute() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('nav.demo')}>
      <EasyApp adapter={new EasyDemoAdapter(safeStorage())} />
    </ShellFrame>
  );
}

function safeStorage(): Storage | undefined {
  try { return window.localStorage; } catch { return undefined; }
}

function NotFoundPage() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('notFound.title')}>
      <p className="shell-status">{t('notFound.title')}</p>
      <Link to="/">{t('notFound.back')}</Link>
    </ShellFrame>
  );
}
