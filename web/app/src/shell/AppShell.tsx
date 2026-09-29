import { Suspense, lazy, useEffect, useMemo, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { HashRouter, Link, Routes, Route, useNavigate, useSearchParams } from 'react-router-dom';
import { I18nProvider, useI18n } from './I18nProvider';
import { SessionProvider, useSession } from './SessionProvider';
import { SessionRecoveryModal } from './SessionRecoveryModal';
import { bindRouterNavigate, workspaceHref } from '../views/easy/routeParams';
import { fetchProjects } from '../data/projects';
import '../styles/shell.css';

/**
 * Unified application shell (execution guide phases 3-4).
 *
 * Route-level code splitting: the shell (nav, language, session machine,
 * recovery overlay, home project list) ships in the main bundle; every view —
 * both workspaces, the account portal and the guest demo — is a lazy chunk
 * loaded on first navigation. Hash Router keeps all deep links on the single
 * `/app/` document, so the backend needs no new routes.
 */
const EasyWorkspace = lazy(() => import('../views/easy/EasyWorkspace').then((m) => ({ default: m.EasyWorkspace })));
const ProWorkspace = lazy(() => import('../views/pro/ProWorkspace').then((m) => ({ default: m.ProWorkspace })));
const AccountApp = lazy(() => import('../views/account/AccountApp').then((m) => ({ default: m.AccountApp })));
const GuestView = lazy(() => import('../views/guest/GuestView').then((m) => ({ default: m.GuestView })));

function RouteLoading() {
  const { t } = useI18n();
  return <main className="route-loading" role="status">{t('shell.routeLoading')}</main>;
}

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
            <RouterBridge />
            <Suspense fallback={<RouteLoading />}>
              <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/projects" element={<ProjectRoute />} />
                <Route path="/projects/:id" element={<ProjectRoute />} />
                <Route path="/account" element={<AccountRoute />} />
                <Route path="/demo" element={<GuestDemoRoute />} />
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </Suspense>
          </HashRouter>
          <SessionRecoveryModal />
        </SessionProvider>
      </QueryClientProvider>
    </I18nProvider>
  );
}

/** 把路由器的 navigate(replace) 绑给路由桥：程序化写址后路由器保持同步。 */
function RouterBridge() {
  const navigate = useNavigate();
  useEffect(() => bindRouterNavigate(navigate), [navigate]);
  return null;
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

/** Shell chrome for portal-style pages; workspaces and the demo are full-bleed. */
function ShellFrame({ title, children }: { title: string; children?: ReactNode }) {
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

/** 首页：访客看到演示工作台（先看到，用时登录），已登录看到项目列表。 */
function HomePage() {
  const { state } = useSession();
  const { t } = useI18n();
  if (state.kind === 'guest') return <GuestView />;
  if (state.kind === 'checking' || state.kind === 'network-error') {
    return (
      <ShellFrame title={t('nav.home')}>
        <SessionStatus />
      </ShellFrame>
    );
  }
  return <ProjectListPage />;
}

function ProjectListPage() {
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
      {enabled && scope && state.kind === 'authenticated' && (
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

/** 显式演示路由：与首页访客视图同一组件，已登录也可随时回看演示。 */
function GuestDemoRoute() {
  return <GuestView />;
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
