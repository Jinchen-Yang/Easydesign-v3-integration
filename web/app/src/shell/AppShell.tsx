import { useMemo, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HashRouter, Link, Routes, Route, useParams, useSearchParams } from 'react-router-dom';
import { I18nProvider, useI18n } from './I18nProvider';
import { SessionProvider, useSession } from './SessionProvider';
import '../styles/shell.css';

/**
 * Phase-1 application shell: providers plus the hash route table with
 * placeholder views. Views migrate into `src/views/` in phase 3; the guest
 * surface arrives in phase 4. The route table itself is final.
 *
 * Hash Router keeps every deep link on the single `/app/` document, so the
 * Python backend never needs new routes.
 */
export function AppShell() {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 5_000 },
        },
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
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/projects/:id" element={<ProjectViewPage />} />
              <Route path="/account" element={<AccountPage />} />
              <Route path="/demo" element={<DemoPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </HashRouter>
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

/** Session-status panel: the only view state that matters before phase 3. */
function SessionPanel() {
  const { state, dismissRecovery } = useSession();
  const { t } = useI18n();
  if (state.kind === 'checking') return <p className="shell-status" data-testid="session-checking">{t('shell.loading')}</p>;
  if (state.kind === 'guest') return <p className="shell-status" data-testid="session-guest">{t('shell.guest')}</p>;
  if (state.kind === 'authenticated') {
    return (
      <p className="shell-status" data-testid="session-authenticated">
        {t('shell.authenticated', { name: state.session.user.display_name })}
      </p>
    );
  }
  if (state.kind === 'expired') {
    return (
      <div className="shell-status" data-testid="session-expired">
        <p>{t('shell.expired')}</p>
        <button type="button" onClick={dismissRecovery}>{t('shell.dismiss')}</button>
      </div>
    );
  }
  return (
    <div className="shell-status" data-testid="session-network-error">
      <p>{t('shell.networkError')}</p>
      <button type="button" onClick={state.retry}>{t('shell.retry')}</button>
      <button type="button" onClick={dismissRecovery}>{t('shell.giveUp')}</button>
    </div>
  );
}

function ShellFrame({ title, children }: { title: string; children?: ReactNode }) {
  const { t } = useI18n();
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
        <LanguageToggle />
      </header>
      <section className="shell-body">
        <h1>{title}</h1>
        {children}
      </section>
    </main>
  );
}

function HomePage() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('shell.brand')}>
      <SessionPanel />
    </ShellFrame>
  );
}

function ProjectsPage() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('nav.projects')}>
      <p className="shell-status">{t('placeholder.projects')}</p>
      <SessionPanel />
    </ShellFrame>
  );
}

function ProjectViewPage() {
  const { t } = useI18n();
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  return (
    <ShellFrame title={t('nav.projects')}>
      <p className="shell-status">{t('placeholder.projectView', { id: id ?? '?', view: searchParams.get('view') ?? 'easy' })}</p>
      <SessionPanel />
    </ShellFrame>
  );
}

function AccountPage() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('nav.account')}>
      <p className="shell-status">{t('placeholder.account')}</p>
      <SessionPanel />
    </ShellFrame>
  );
}

function DemoPage() {
  const { t } = useI18n();
  return (
    <ShellFrame title={t('nav.demo')}>
      <p className="shell-status">{t('placeholder.demo')}</p>
    </ShellFrame>
  );
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
