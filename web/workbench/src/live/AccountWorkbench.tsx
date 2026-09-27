import {useEffect, useMemo, useState} from 'react';
import {
  accountApi, AccountApiError, currentAccountScope, fetchAccountConfig, scopedTransport,
  watchSessionChanges, workspaceUrl, type AccountConfig, type AccountScope, type AccountSession,
} from '../../../shared/account-client';
import {LiveWorkbenchAdapter} from '../adapters/LiveWorkbenchAdapter';
import {LiveWorkbench} from './LiveWorkbench';
import './live.css';

export function AccountWorkbench() {
  const [value, setValue] = useState<{session: AccountSession; scope: AccountScope} | null>(null);
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        const settings = await fetchAccountConfig();
        if (disposed) return;
        setConfig(settings);
        const session = await accountApi<AccountSession>('/accounts/me');
        if (session.user.must_change_password) {location.replace('/account/'); return;}
        const scope = await currentAccountScope(session);
        if (!disposed) setValue({session, scope});
      } catch (reason) {
        if (disposed) return;
        if (reason instanceof AccountApiError && reason.status === 401) location.replace('/account/');
        else setError(reason instanceof Error ? reason.message : '工作区不可用');
      }
    })();
    const stop = watchSessionChanges();
    return () => {disposed = true; stop();};
  }, []);
  const adapter = useMemo(() => value ? new LiveWorkbenchAdapter(scopedTransport(value.session, value.scope)) : null, [value]);
  if (error) return <main className="account-pro-status"><p role="alert">{error}</p><a href="/account/">返回账号与团队</a></main>;
  if (!value || !adapter) return <main className="account-pro-status">正在验证工作区权限…</main>;
  const {session, scope} = value;
  return <div className="account-pro-root">
    <div className="account-pro-bar"><strong>{session.user.display_name}</strong><span>{scope.name}</span>
      <span>{scope.role === 'observer' ? '管理员只读访问 · 已审计' : scope.can_execute ? '科研审批人' : '协作成员'}</span>
      {config && !config.compute_available && <span className="account-compute-off">未连接科学执行器</span>}
      <select aria-label="切换工作区" value={scope.id} onChange={event => location.assign(workspaceUrl(event.target.value, 'professional'))}>
        {!session.scopes.some(item => item.id === scope.id) && <option value={scope.id}>{scope.name}（只读）</option>}
        {session.scopes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select><a href="/account/">账号、团队与资源</a><a href={workspaceUrl(scope.id)}>Easy 版</a>
    </div>
    <LiveWorkbench
      key={`${session.user.id}:${scope.id}`}
      adapter={adapter}
      access={scope}
      computeAvailable={config ? config.compute_available : true}
    />
  </div>;
}
