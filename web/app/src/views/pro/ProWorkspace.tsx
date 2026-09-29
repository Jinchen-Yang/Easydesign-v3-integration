import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '../../shell/SessionProvider';
import {
  fetchAccountConfig, scopedTransportFromRef,
  type AccountConfig, type AccountScope, type AccountSession,
} from '../../shared/account-client';
import { LiveWorkbenchAdapter } from '../../adapters/LiveWorkbenchAdapter';
import type { LiveWorkbenchPort } from '../../adapters/LiveWorkbenchAdapter';
import { LiveWorkbench } from './LiveWorkbench';
import { WorkspaceBar } from '../../shell/WorkspaceBar';
import { SignInPrompt } from '../../shell/SignInPrompt';
import '../workspaceStyles';
import './live.css';

const defaultAdapterFactory = (transport: typeof fetch): LiveWorkbenchPort =>
  new LiveWorkbenchAdapter(transport);

/**
 * Pro 工作台视图。与 EasyWorkspace 相同的会话策略：过期不卸载、
 * 适配器只随「用户 + 工作区」重建、传输层从 ref 读 CSRF、
 * 过期暂停轮询 / 恢复后继续。
 */
export function ProWorkspace(
  { adapterFactory = defaultAdapterFactory }: { adapterFactory?: (transport: typeof fetch) => LiveWorkbenchPort } = {},
) {
  const { t } = useTranslation(['pro', 'account']);
  const { state } = useSession();
  const [searchParams] = useSearchParams();
  const scopeId = searchParams.get('scope');
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const sessionRef = useRef<AccountSession | null>(null);
  const lastValidRef = useRef<{ session: AccountSession; scope: AccountScope } | null>(null);

  useEffect(() => {
    let disposed = false;
    fetchAccountConfig().then((value) => { if (!disposed) setConfig(value); }).catch(() => {});
    return () => { disposed = true; };
  }, []);

  if (state.kind === 'authenticated') {
    const scope =
      state.session.scopes.find((item) => item.id === scopeId) ?? state.scope;
    sessionRef.current = state.session;
    lastValidRef.current = { session: state.session, scope };
  } else if (state.kind === 'guest') {
    sessionRef.current = null;
    lastValidRef.current = null;
  }

  const session = lastValidRef.current?.session ?? null;
  const scope = lastValidRef.current?.scope ?? null;

  const adapter = useMemo(() => {
    if (scope === null || session === null) return null;
    return adapterFactory(scopedTransportFromRef(sessionRef, scope));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.id, session?.user.id]);

  useEffect(() => () => { adapter?.dispose(); }, [adapter]);

  useEffect(() => {
    const lifecycle = adapter as unknown as { pausePolling?: () => void; resumePolling?: () => void } | null;
    if (lifecycle === null) return;
    if (state.kind === 'expired') lifecycle.pausePolling?.();
    else lifecycle.resumePolling?.();
  }, [state.kind, adapter]);

  useEffect(() => {
    if (!adapter) return;
    return adapter.subscribe((event) => setSelectedProject(event.snapshot.selectedProject));
  }, [adapter]);

  if (session === null || scope === null || adapter === null) {
    if (state.kind === 'checking') return <main className="account-pro-status">{t('Verifying workspace permissions…')}</main>;
    if (state.kind === 'guest') {
      return (
        <SignInPrompt
          title={t('Sign in to use the Pro workbench')}
          description={t('You are currently a guest; after signing in you can approve scientific Gates and view real projects.')}
        />
      );
    }
    return <main className="account-pro-status">{t('Unable to confirm sign-in state for now.')}</main>;
  }

  return (
    <div className="account-pro-root">
      <WorkspaceBar session={session} scope={scope} view="pro" project={selectedProject} computeAvailable={config ? config.compute_available : true}/>
      <LiveWorkbench
        key={`${session.user.id}:${scope.id}`}
        adapter={adapter}
        access={scope}
        computeAvailable={config ? config.compute_available : true}
      />
    </div>
  );
}
