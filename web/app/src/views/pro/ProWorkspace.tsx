import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../../shell/SessionProvider';
import { fetchAccountConfig, scopedTransport, type AccountConfig } from '../../shared/account-client';
import { LiveWorkbenchAdapter } from '../../adapters/LiveWorkbenchAdapter';
import { LiveWorkbench } from './LiveWorkbench';
import { workspaceHref } from '../easy/routeParams';
import './live.css';

/**
 * Pro 工作台视图：迁移自 legacy AccountWorkbench，会话来自 SessionProvider。
 * Easy/Pro 互跳为应用内 hash 路由。
 */
export function ProWorkspace() {
  const { state } = useSession();
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    fetchAccountConfig().then((value) => { if (!disposed) setConfig(value); }).catch(() => {});
    return () => { disposed = true; };
  }, []);

  const scopeId = useMemo(() => new URLSearchParams(location.hash.split('?')[1] ?? '').get('scope'), [location.hash]);

  const transport = useMemo(
    () => (state.kind === 'authenticated'
      ? scopedTransport(state.session, state.scope)
      : null),
    [state],
  );
  const adapter = useMemo(() => (transport ? new LiveWorkbenchAdapter(transport) : null), [transport]);

  useEffect(() => {
    if (!adapter) return;
    return adapter.subscribe((event) => setSelectedProject(event.snapshot.selectedProject));
  }, [adapter]);

  if (state.kind === 'checking') return <main className="account-pro-status">正在验证工作区权限…</main>;
  if (state.kind === 'expired') return <main className="account-pro-status">会话已过期，请在弹窗中重新登录。</main>;
  if (state.kind === 'network-error') return <main className="account-pro-status">暂时无法确认登录状态。</main>;
  if (state.kind === 'guest' || !adapter) {
    return (
      <main className="account-pro-status">
        <p>请先登录后使用专业版工作台。</p>
        <a href="#/account">前往账号与团队</a>
      </main>
    );
  }

  const { session, scope: machineScope } = state;
  const scope = session.scopes.find((item) => item.id === scopeId) ?? machineScope;
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
