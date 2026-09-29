import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useSession } from '../../shell/SessionProvider';
import {
  fetchAccountConfig, scopedTransportFromRef,
  type AccountConfig, type AccountScope, type AccountSession,
} from '../../shared/account-client';
import { LiveWorkbenchAdapter } from '../../adapters/LiveWorkbenchAdapter';
import type { LiveWorkbenchPort } from '../../adapters/LiveWorkbenchAdapter';
import { LiveWorkbench } from './LiveWorkbench';
import { workspaceHref } from '../easy/routeParams';
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
    if (state.kind === 'checking') return <main className="account-pro-status">正在验证工作区权限…</main>;
    if (state.kind === 'guest') {
      return (
        <SignInPrompt
          title="登录后使用专业版工作台"
          description="当前为访客状态，登录后即可审批科学 Gate 与查看真实项目。"
        />
      );
    }
    return <main className="account-pro-status">暂时无法确认登录状态。</main>;
  }

  const easyUrl = workspaceHref(scope.id, 'easy', selectedProject);
  return (
    <div className="account-pro-root">
      <div className="account-pro-bar"><strong>{session.user.display_name}</strong><span>{scope.name}</span>
        <span>{scope.role === 'observer' ? '管理员只读访问 · 已审计' : scope.can_execute ? '科研审批人' : '协作成员'}</span>
        {config && !config.compute_available && <span className="account-compute-off">未连接科学执行器</span>}
        <select aria-label="切换工作区" value={scope.id} onChange={(event) => { location.hash = workspaceHref(event.target.value, 'pro'); }}>
          {session.scopes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select><a href="#/account">账号、团队与资源</a><a href={easyUrl}>Easy 版</a>
      </div>
      <LiveWorkbench
        key={`${session.user.id}:${scope.id}`}
        adapter={adapter}
        access={scope}
        computeAvailable={config ? config.compute_available : true}
      />
    </div>
  );
}
