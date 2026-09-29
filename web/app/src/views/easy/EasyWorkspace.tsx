import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '../../shell/SessionProvider';
import {
  fetchAccountConfig, scopedTransportFromRef,
  type AccountConfig, type AccountScope, type AccountSession,
} from '../../shared/account-client';
import { AccountTransportContext } from './AccountTransportContext';
import { EasyLiveApp } from './EasyLiveApp';
import { EasyProductAdapter } from './EasyProductAdapter';
import type { EasyProductPort } from './EasyProductAdapter';
import { workspaceHref } from './routeParams';
import { SignInPrompt } from '../../shell/SignInPrompt';
import './easyStyles';
import '../workspaceStyles';
import '../account/accounts.css';

const defaultAdapterFactory = (transport: typeof fetch): EasyProductPort =>
  new EasyProductAdapter(transport);

/**
 * Easy Live 工作区视图。迁移自 legacy AccountWorkspace，关键差异：
 *
 * - 会话来自 SessionProvider；过期时**不卸载工作区**——用最后一次有效
 *   会话继续渲染（恢复遮罩浮在上层），未保存输入原地保留，适配器轮询
 *   暂停，恢复登录后原适配器（含防重复提交的请求编号表）继续使用。
 * - 适配器只随「用户 + 工作区」重建；传输层从 sessionRef 读当前 CSRF，
 *   同账号恢复后无需重建。
 */
export function EasyWorkspace(
  { adapterFactory = defaultAdapterFactory }: { adapterFactory?: (transport: typeof fetch) => EasyProductPort } = {},
) {
  const { t } = useTranslation('easy');
  const { state } = useSession();
  const [searchParams] = useSearchParams();
  const scopeId = searchParams.get('scope');
  const [config, setConfig] = useState<AccountConfig | null>(null);
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
    // 主动登出后不复用旧身份渲染。
    sessionRef.current = null;
    lastValidRef.current = null;
  }

  const session = lastValidRef.current?.session ?? null;
  const scope = lastValidRef.current?.scope ?? null;

  // 适配器只依赖「用户 + 工作区」；恢复登录（同账号）不触发重建。
  const adapter = useMemo(() => {
    if (scope === null || session === null) return null;
    return adapterFactory(scopedTransportFromRef(sessionRef, scope));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope?.id, session?.user.id]);

  // 卸载或切换工作区时释放旧适配器。
  useEffect(() => () => { adapter?.dispose(); }, [adapter]);

  // RabbitChat 等使用的上下文传输层：同样从 ref 读会话。
  const contextTransport = useMemo(
    () => (scope === null ? null : scopedTransportFromRef(sessionRef, scope)),
    [scope?.id], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // 过期 → 暂停轮询；恢复（或仍在有效会话）→ 继续轮询。
  const adapterRef = useRef(adapter);
  adapterRef.current = adapter;
  useEffect(() => {
    const lifecycle = adapter as unknown as { pausePolling?: () => void; resumePolling?: () => void } | null;
    if (lifecycle === null) return;
    if (state.kind === 'expired') lifecycle.pausePolling?.();
    else lifecycle.resumePolling?.();
  }, [state.kind, adapter]);

  if (session === null || scope === null || adapter === null) {
    if (state.kind === 'checking') return <main className="account-loading">{t('Verifying workspace permissions…')}</main>;
    if (state.kind === 'guest') {
      return (
        <SignInPrompt
          title={t('Sign in to use the Easy workspace')}
          description={t('You are currently a guest; after signing in you can submit real design tasks.')}
        />
      );
    }
    return <main className="account-login"><h1>{t('Unable to confirm sign-in state for now')}</h1><p role="alert">{t('Network error; please try again later.')}</p></main>;
  }

  return (
    <AccountTransportContext.Provider value={{ transport: contextTransport!, scope }}>
      <div className="account-workspace-bar">
        <strong>{session.user.display_name}</strong><span>{scope.name}</span>
        <span>{scope.role === 'observer' ? t('Administrator read-only · audited') : scope.can_execute ? t('Can execute scientific approval') : t('Team collaborator')}</span>
        {config && !config.compute_available && <span className="account-compute-off">{t('No scientific executor connected')}</span>}
        <label>{t('Switch workspace')}<select aria-label={t('Switch workspace')} value={scope.id} onChange={(event) => { location.hash = workspaceHref(event.target.value, 'easy'); }}>
          {session.scopes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <a href="#/account">{t('Account, teams and resources')}</a>
      </div>
      <EasyLiveApp
        key={`${session.user.id}:${scope.id}`}
        adapter={adapter}
        access={scope}
        computeAvailable={config ? config.compute_available : true}
      />
    </AccountTransportContext.Provider>
  );
}
