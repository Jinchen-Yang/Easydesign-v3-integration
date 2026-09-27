import {useEffect, useMemo, useState} from 'react';
import {
  accountApi, AccountApiError, currentAccountScope, fetchAccountConfig, scopedTransport,
  watchSessionChanges, workspaceUrl, type AccountConfig, type AccountScope, type AccountSession,
} from '../../../shared/account-client';
import {EasyLiveApp} from '../easy/EasyLiveApp';
import {EasyProductAdapter} from '../easy/EasyProductAdapter';
import {AccountTransportContext} from './AccountTransportContext';
import './accounts.css';

export function AccountWorkspace() {
  const [value, setValue] = useState<{session: AccountSession; scope: AccountScope} | null>(null);
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        // Config is public; it decides whether execution affordances can work at all.
        const settings = await fetchAccountConfig();
        if (disposed) return;
        setConfig(settings);
        const session = await accountApi<AccountSession>('/accounts/me');
        if (session.user.must_change_password) { location.replace('/account/'); return; }
        const scope = await currentAccountScope(session);
        if (!disposed) setValue({session, scope});
      } catch (reason) {
        if (disposed) return;
        if (reason instanceof AccountApiError && reason.status === 401) location.replace('/account/');
        else setError(reason instanceof Error ? reason.message : '无法读取工作区权限');
      }
    })();
    const stop = watchSessionChanges();
    return () => {disposed = true; stop();};
  }, []);
  const transport = useMemo(() => value ? scopedTransport(value.session, value.scope) : null, [value]);
  const adapter = useMemo(() => transport ? new EasyProductAdapter(transport) : null, [transport]);
  if (error) return <main className="account-login"><h1>工作区不可用</h1><p role="alert">{error}</p><a href="/account/">返回账号与团队</a></main>;
  if (!value || !transport || !adapter) return <main className="account-loading">正在验证工作区权限…</main>;
  const {session, scope} = value;
  return <AccountTransportContext.Provider value={{transport, scope}}>
    <div className="account-workspace-bar">
      <strong>{session.user.display_name}</strong><span>{scope.name}</span>
      <span>{scope.role === 'observer' ? '管理员只读访问 · 已审计' : scope.can_execute ? '可执行科学审批' : '团队协作成员'}</span>
      {config && !config.compute_available && <span className="account-compute-off">未连接科学执行器</span>}
      <label>切换工作区<select aria-label="切换工作区" value={scope.id} onChange={event => location.assign(workspaceUrl(event.target.value))}>
        {!session.scopes.some(item => item.id === scope.id) && <option value={scope.id}>{scope.name}（只读）</option>}
        {session.scopes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <a href="/account/">账号、团队与资源</a>
    </div>
    <EasyLiveApp
      key={`${session.user.id}:${scope.id}`}
      adapter={adapter}
      access={scope}
      computeAvailable={config ? config.compute_available : true}
    />
  </AccountTransportContext.Provider>;
}
