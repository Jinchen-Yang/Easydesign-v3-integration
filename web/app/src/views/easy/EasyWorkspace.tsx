import { useEffect, useMemo, useState } from 'react';
import { useSession } from '../../shell/SessionProvider';
import { fetchAccountConfig, scopedTransport, type AccountConfig } from '../../shared/account-client';
import { AccountTransportContext } from './AccountTransportContext';
import { EasyLiveApp } from './EasyLiveApp';
import { EasyProductAdapter } from './EasyProductAdapter';
import { workspaceHref } from './routeParams';
import '../account/accounts.css';

/**
 * Easy Live 工作区视图：迁移自 legacy AccountWorkspace，会话来自
 * SessionProvider（不再自探测 /accounts/me、401 不再整页跳转）。
 * 工作区切换/账号入口改为应用内 hash 路由，无整页刷新。
 */
export function EasyWorkspace() {
  const { state } = useSession();
  const [config, setConfig] = useState<AccountConfig | null>(null);
  useEffect(() => {
    let disposed = false;
    // 公开配置决定执行类控件是否可用；失败不阻塞浏览。
    fetchAccountConfig().then((value) => { if (!disposed) setConfig(value); }).catch(() => {});
    return () => { disposed = true; };
  }, []);

  const scopeId = useMemo(() => new URLSearchParams(location.hash.split('?')[1] ?? '').get('scope'), [location.hash]);

  if (state.kind === 'checking') return <main className="account-loading">正在验证工作区权限…</main>;
  if (state.kind === 'expired') return <main className="account-loading">会话已过期，请在弹窗中重新登录。</main>;
  if (state.kind === 'network-error') return <main className="account-login"><h1>暂时无法确认登录状态</h1><p role="alert">网络异常，请稍后重试。</p></main>;
  if (state.kind === 'guest') {
    return (
      <main className="account-login">
        <h1>请先登录</h1>
        <p>登录后即可使用 Easy 工作区。</p>
        <a className="account-primary" href="#/account">前往账号与团队</a>
      </main>
    );
  }

  const { session, scope: machineScope } = state;
  const scope = session.scopes.find((item) => item.id === scopeId) ?? machineScope;
  const transport = scopedTransport(session, scope);
  const adapter = new EasyProductAdapter(transport);

  return (
    <AccountTransportContext.Provider value={{ transport, scope }}>
      <div className="account-workspace-bar">
        <strong>{session.user.display_name}</strong><span>{scope.name}</span>
        <span>{scope.role === 'observer' ? '管理员只读访问 · 已审计' : scope.can_execute ? '可执行科学审批' : '团队协作成员'}</span>
        {config && !config.compute_available && <span className="account-compute-off">未连接科学执行器</span>}
        <label>切换工作区<select aria-label="切换工作区" value={scope.id} onChange={(event) => { location.hash = workspaceHref(event.target.value, 'easy'); }}>
          {session.scopes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <a href="#/account">账号、团队与资源</a>
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
