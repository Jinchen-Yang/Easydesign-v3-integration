import {useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode} from 'react';
import {
  accountApi, AccountApiError, draftsApi, fetchAccountConfig, fetchFinalDesignsOverview, fetchScopeUsage,
  notifySessionChange, scopedTransport, type AccountConfig, type AccountScope,
  type AccountSession, type AccountUser, type FinalDesignEntry, type FinalDesignsBlock,
  type FinalDesignsOverview, type ProjectDraft, type QuotaLimits, type ScopeUsage,
} from '../../shared/account-client';
import {Brand} from '../../components/Brand';
import {useSession} from '../../shell/SessionProvider';
import {workspaceHref} from '../easy/routeParams';
import './accounts.css';

type Team = {
  id: string; name: string; status: string;
  members?: Array<{user_id: string; username: string; display_name: string; role: string; status: string; account_status: string}>;
};
type Audit = {seq: number; actor_id: string | null; action: string; scope_id: string | null; target_id: string | null; created_at: number};

/** Admission states that still count against scope/personal quotas (backend ACTIVE_ADMISSIONS). */
const ACTIVE_ADMISSION_STATES = new Set(['reserved', 'queued', 'starting', 'running', 'held']);
const AUDIT_PAGE = 100;

function errorText(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '操作失败，请重试';
}

function when(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString();
}

function bytes(value: number): string {
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

interface GuardedState<T> {
  value: T | null;
  error: string;
  busy: boolean;
  load: (work: (previous: T | null) => Promise<T>) => void;
  clear: () => void;
  patch: (update: (current: T) => T) => void;
}

/**
 * Generation-guarded async loader: only the most recent call may write state and
 * nothing writes after unmount. Quickly switching selections must never paint a
 * stale response that belongs to another selection. All returned functions are
 * referentially stable, so they are safe in effect dependency lists.
 */
function useGuardedLoad<T>(): GuardedState<T> {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const alive = useRef(true);
  const latest = useRef<T | null>(null);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  const load = useCallback((work: (previous: T | null) => Promise<T>) => {
    const id = ++generation.current;
    setBusy(true);
    setError('');
    void work(latest.current).then(
      result => {
        if (!alive.current || generation.current !== id) return;
        latest.current = result;
        setValue(result);
        setBusy(false);
      },
      reason => {
        if (!alive.current || generation.current !== id) return;
        setError(errorText(reason));
        setBusy(false);
      },
    );
  }, []);
  const clear = useCallback(() => {
    generation.current++;
    latest.current = null;
    setValue(null);
    setError('');
    setBusy(false);
  }, []);
  const patch = useCallback((update: (current: T) => T) => {
    setValue(current => current === null ? current : update(current));
  }, []);
  return {value, error, busy, load, clear, patch};
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const pending = useRef(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function run(action: () => Promise<void>, success = '') {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(''); setMessage('');
    try {
      await action();
      if (alive.current) setMessage(success);
    } catch (reason) {
      if (alive.current) setError(errorText(reason));
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return {busy, run, feedback: <>{error && <p className="account-error" role="alert">{error}</p>}{message && <p className="account-success" role="status">{message}</p>}</>};
}

function Login({onLogin, login}: {onLogin: (session: AccountSession) => void; login: (username: string, password: string) => Promise<AccountSession>}) {
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [setup, setSetup] = useState(false);
  const action = useAction();
  useEffect(() => {
    let disposed = false;
    accountApi<{setup_required: boolean}>('/accounts/config')
      .then(value => { if (!disposed) setSetup(value.setup_required); }).catch(() => {});
    return () => { disposed = true; };
  }, []);
  function submit(event: FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      if (register) {
        await accountApi('/accounts/register', null, {username, password, display_name: displayName || username});
        setPassword(''); setRegister(false);
      } else {
        const session = await login(username, password);
        setPassword('');
        onLogin(session);
      }
    }, register ? '注册已提交，等待管理员审核。审核通过后即可登录。' : '');
  }
  return <main className="account-login">
    <Brand/><h1>{register ? '申请 EasyDesign 账号' : '登录 EasyDesign'}</h1>
    <p>个人工作区独立，团队项目按权限协作。</p>
    {setup && <p role="status" className="account-notice">管理员尚未初始化，请联系部署负责人完成安全引导。</p>}
    <form onSubmit={submit}>
      <label>用户名<input required value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" minLength={3} maxLength={64}/></label>
      {register && <label>显示名称<input value={displayName} onChange={event => setDisplayName(event.target.value)} maxLength={100}/></label>}
      <label>密码<input type="password" required value={password} onChange={event => setPassword(event.target.value)} autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : undefined} maxLength={256}/></label>
      {register && <small>至少 12 个字符。注册后需管理员审核，才能使用工作区。</small>}
      <button className="account-primary" disabled={action.busy || setup}>{action.busy ? '正在处理…' : register ? '提交注册申请' : '登录'}</button>
      {action.feedback}
    </form>
    <button className="account-link" onClick={() => {setRegister(!register); setPassword('');}}>{register ? '已有账号，返回登录' : '没有账号？申请注册'}</button>
  </main>;
}

function Password({session, changed}: {session: AccountSession; changed: () => void}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const action = useAction();
  return <section className="account-panel"><h2>{session.user.must_change_password ? '请先修改临时密码' : '修改密码'}</h2>
    <p>修改后所有现有会话都会失效，需要重新登录。</p>
    <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await accountApi('/accounts/password', session, {current_password: current, password: next});
      setCurrent(''); setNext(''); notifySessionChange(); changed();
    });}}>
      <label>当前密码<input type="password" autoComplete="current-password" required value={current} onChange={event => setCurrent(event.target.value)}/></label>
      <label>新密码<input type="password" autoComplete="new-password" minLength={12} maxLength={256} required value={next} onChange={event => setNext(event.target.value)}/></label>
      <button className="account-primary" disabled={action.busy}>修改并重新登录</button>{action.feedback}
    </form>
  </section>;
}

function Workspaces({session, refresh}: {session: AccountSession; refresh: () => Promise<void>}) {
  const [teamName, setTeamName] = useState('');
  const action = useAction();
  return <>
    <section className="account-panel"><h2>我的工作区</h2><p>默认个人私有。进入团队工作区后，新建项目才会与团队共享。</p>
      <div className="account-grid">{session.scopes.map(scope => <article className="account-scope" key={scope.id}>
        <h3>{scope.name}</h3><span>{scope.kind === 'personal' ? '个人私有' : scope.role === 'observer' ? '只读访问' : scope.can_execute ? '团队管理员' : '团队成员'}</span>
        <p>{scope.can_execute ? '可以编辑、批准 Gate 和启动计算。' : '可以协作编辑和查看结果；科学审批与计算启动由团队管理员负责。'}</p>
        <a className="account-primary" href={workspaceHref(scope.id, 'easy')}>进入 Easy 工作区</a>
        <a href={workspaceHref(scope.id, 'pro')}>打开专业版</a>
      </article>)}</div>
    </section>
    {session.invitations.length > 0 && <section className="account-panel"><h2>团队邀请</h2>{session.invitations.map(invitation => <div className="account-row" key={invitation.id}>
      <span>{invitation.team_name} · {invitation.role === 'admin' ? '团队管理员' : '成员'}</span>
      {[true, false].map(accept => <button key={String(accept)} disabled={action.busy} onClick={() => void action.run(async () => {
        await accountApi(`/invitations/${invitation.id}`, session, {accept}); await refresh();
      })}>{accept ? '接受邀请' : '拒绝'}</button>)}
    </div>)}</section>}
    <section className="account-panel"><h2>创建团队</h2><form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await accountApi('/teams', session, {name: teamName}); setTeamName(''); await refresh();
    }, '团队已创建');}}>
      <label>团队名称<input value={teamName} onChange={event => setTeamName(event.target.value)} required maxLength={100}/></label>
      <button disabled={action.busy} className="account-primary">创建团队</button>{action.feedback}
    </form></section>
  </>;
}

function DraftEditor({draft, busy, onSave, onCancel}: {
  draft: ProjectDraft;
  busy: boolean;
  onSave: (value: {title: string; goal: string}, revision: number) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(draft.payload.title);
  const [goal, setGoal] = useState(draft.payload.goal);
  return <form className="account-draft-form" onSubmit={event => {
    event.preventDefault();
    onSave({title: title.trim(), goal: goal.trim()}, draft.revision);
  }}>
    <label>标题<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={80}/></label>
    <label>研究目标<textarea rows={3} value={goal} onChange={event => setGoal(event.target.value)} required maxLength={1500}/></label>
    <div className="account-row">
      <button className="account-primary" disabled={busy || !title.trim() || !goal.trim()}>保存新版本</button>
      <button type="button" disabled={busy} onClick={onCancel}>取消</button>
      <small>基于版本 r{draft.revision} 保存；其他成员同时保存会提示重新加载。</small>
    </div>
  </form>;
}

function TeamDrafts({session, scope, team, computeAvailable}: {
  session: AccountSession; scope: AccountScope; team: Team | null; computeAvailable: boolean;
}) {
  const {value: list, error, busy, load} = useGuardedLoad<ProjectDraft[]>();
  const [editing, setEditing] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [started, setStarted] = useState<{draftId: string; projectId: string} | null>(null);
  const [title, setTitle] = useState('');
  const [goal, setGoal] = useState('');
  const action = useAction();
  const reload = useCallback(() => {
    load(async () => (await draftsApi.list(scopedTransport(session, scope))).drafts);
  }, [load, session, scope]);
  useEffect(() => { setEditing(null); setCreating(false); setStarted(null); reload(); }, [reload]);
  const names = new Map((team?.members || []).map(member => [member.user_id, member.display_name]));
  const nameOf = (id: string) => names.get(id) || (id === session.user.id ? session.user.display_name : id.slice(0, 12));
  const canEdit = scope.can_edit;
  return <section className="account-panel" aria-label="团队项目草稿">
    <div className="account-row"><h2>团队项目草稿</h2>
      {busy && <span role="status">加载中…</span>}
      <button disabled={busy} onClick={reload}>刷新</button>
      {canEdit && !creating && <button className="account-primary" onClick={() => {setCreating(true); setTitle(''); setGoal('');}}>新建草稿</button>}
    </div>
    <p>成员可以共同编辑草稿；保存草稿不会启动任何科学计算。只有团队管理员能把草稿作为项目启动，启动后草稿冻结为当时的科学输入。</p>
    {error && <p className="account-error" role="alert">{error}</p>}
    {creating && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await draftsApi.save(scopedTransport(session, scope), {title: title.trim(), goal: goal.trim()});
      setCreating(false); reload();
    }, '草稿已创建');}}>
      <label>标题<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={80}/></label>
      <label>研究目标<textarea rows={3} value={goal} onChange={event => setGoal(event.target.value)} required maxLength={1500}/></label>
      <div className="account-row">
        <button className="account-primary" disabled={action.busy || !title.trim() || !goal.trim()}>创建草稿</button>
        <button type="button" disabled={action.busy} onClick={() => setCreating(false)}>取消</button>
      </div>
      {action.feedback}
    </form>}
    {list && list.length === 0 && !creating && <p>还没有草稿。团队成员可以先在这里共同打磨研究目标，再由团队管理员启动。</p>}
    <div className="account-table-scroll"><table><thead><tr><th>草稿</th><th>状态</th><th>协作</th><th>操作</th></tr></thead>
      <tbody>{(list || []).map(draft => <tr key={draft.id}>
        <td><strong>{draft.payload.title}</strong><small>{draft.payload.goal}</small></td>
        <td>{draft.state === 'started'
          ? <>已启动 {draft.project_id && <small><a href={workspaceHref(scope.id, 'easy', draft.project_id)}>打开项目</a></small>}</>
          : draft.state === 'starting' ? '启动中' : `草稿 · r${draft.revision}`}</td>
        <td><small>创建 {nameOf(draft.created_by)}<br/>更新 {nameOf(draft.updated_by)} · {when(draft.updated_at)}</small></td>
        <td className="account-actions">
          {draft.state === 'draft' && canEdit && (editing === draft.id
            ? <DraftEditor draft={draft} busy={action.busy} onCancel={() => setEditing(null)}
                onSave={(value, revision) => void action.run(async () => {
                  try {
                    await draftsApi.save(scopedTransport(session, scope), value, draft.id, revision);
                    setEditing(null);
                  } catch (reason) {
                    // A conflicted editor must close: the surviving revision is
                    // the other member's, never a merge of stale local text.
                    if (reason instanceof AccountApiError && ['stale_draft', 'draft_frozen'].includes(reason.code))
                      setEditing(null);
                    throw reason;
                  } finally {
                    reload();
                  }
                }, '草稿已保存')}/>
            : <button disabled={action.busy} onClick={() => {setEditing(draft.id); setCreating(false);}}>编辑</button>)}
          {draft.state === 'draft' && scope.can_execute && computeAvailable && <button disabled={action.busy} onClick={() => {
            if (window.confirm(`以当前版本 r${draft.revision} 启动「${draft.payload.title}」？启动会创建团队科学项目。`))
              void action.run(async () => {
                const result = await draftsApi.start(scopedTransport(session, scope), draft.id, draft.revision);
                const projectId = result.project?.id || result.draft?.project_id || '';
                if (projectId) setStarted({draftId: draft.id, projectId});
                reload();
              }, '项目已启动');
          }}>启动项目</button>}
        </td>
      </tr>)}</tbody></table></div>
    {!scope.can_execute && <p className="account-permission-note">当前身份是团队成员：可以编辑和讨论草稿；启动计算与科学审批由团队管理员执行。</p>}
    {scope.can_execute && !computeAvailable && <p className="account-permission-note">当前服务未连接科学执行器（账号管理模式）：草稿协作可用，启动项目暂不可用。</p>}
    {started && <p className="account-success" role="status">草稿已转为项目。<a href={workspaceHref(scope.id, 'easy', started.projectId)}>在工作区打开新项目</a></p>}
    {action.feedback}
  </section>;
}

function Teams({session, refresh, computeAvailable}: {
  session: AccountSession; refresh: () => Promise<void>; computeAvailable: boolean;
}) {
  const [selected, setSelected] = useState('');
  const {value: team, error: teamError, busy: teamBusy, load: loadTeam, clear: clearTeam} = useGuardedLoad<Team>();
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('member');
  const action = useAction();
  const scope = session.scopes.find(item => item.id === selected);
  const reloadTeam = useCallback((id: string) => {
    loadTeam(async () => (await accountApi<{team: Team}>(`/teams/${id}`, session)).team);
  }, [loadTeam, session]);
  useEffect(() => { if (selected) reloadTeam(selected); else clearTeam(); }, [selected, reloadTeam, clearTeam]);
  // Team admins manage membership; a system administrator may too, because member
  // administration is account work, not scientific approval or execution.
  const manage = scope?.role === 'admin' || scope?.role === 'owner' || session.user.role === 'admin';
  return <>
    <section className="account-panel"><h2>团队协作</h2>
      <label>选择团队<select value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">请选择</option>
        {session.scopes.filter(item => item.kind === 'team').map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      {teamBusy && <p role="status">加载团队信息…</p>}
      {teamError && <p className="account-error" role="alert">{teamError}</p>}
      {team && <><h3>{team.name}</h3><div className="account-table-scroll"><table><thead><tr><th>成员</th><th>角色</th><th>状态</th><th>操作</th></tr></thead><tbody>{team.members?.filter(item => item.status === 'active').map(member => <tr key={member.user_id}>
        <td>{member.display_name} <small>@{member.username}</small></td><td>{member.role === 'admin' || member.role === 'owner' ? '团队管理员' : '成员'}</td><td>{member.account_status === 'active' ? '已启用' : '不可用'}</td>
        <td className="account-actions">
          {manage && member.role !== 'owner' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/teams/${team.id}/members/${member.user_id}`, session, {role: member.role === 'admin' ? 'member' : 'admin'}); await reloadTeam(team.id); await refresh();})}>{member.role === 'admin' ? '设为成员' : '设为管理员'}</button>}
          {(manage || member.user_id === session.user.id) && member.role !== 'owner' && <button disabled={action.busy} onClick={() => {
            if (window.confirm(member.user_id === session.user.id ? '确认退出这个团队？' : `确认移除 ${member.display_name}？`)) void action.run(async () => {
              await accountApi(`/teams/${team.id}/members/${member.user_id}`, session, {remove: true}); await refresh();
              if (member.user_id === session.user.id) {setSelected('');} else await reloadTeam(team.id);
            });
          }}>{member.user_id === session.user.id ? '退出团队' : '移除'}</button>}
        </td></tr>)}</tbody></table></div>
        {manage && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
          await accountApi(`/teams/${team.id}/invitations`, session, {username, role}); setUsername('');
        }, '邀请已发送，等待对方接受');}}><h3>邀请已启用的用户</h3>
          <label>用户名<input required value={username} onChange={event => setUsername(event.target.value)}/></label>
          <label>加入后的角色<select value={role} onChange={event => setRole(event.target.value)}><option value="member">成员</option><option value="admin">团队管理员</option></select></label>
          <button className="account-primary" disabled={action.busy}>发送邀请</button>
        </form>}
      </>}{action.feedback}
    </section>
    {scope && scope.kind === 'team' && team && <TeamDrafts session={session} scope={scope} team={team} computeAvailable={computeAvailable}/>}
  </>;
}

const LIMIT_LABELS: Record<keyof QuotaLimits, string> = {
  max_active_jobs: '并发科学请求', max_active_chats: '并发对话',
  max_gpu_devices: 'GPU 槽位上限', max_upload_bytes: '单文件上传上限',
  max_stored_upload_bytes: '上传存储额度', max_candidates_per_job: '单次生成候选上限',
  final_designs_allowance: '最终设计个人累计额度',
  pilot_stage_budget: 'Pilot 阶段预算（新项目）',
  scale_stage_budget: 'Scale 阶段预算（新项目）',
};

function UsagePanel({usage}: {usage: ScopeUsage}) {
  const active = usage.admissions.filter(item => ACTIVE_ADMISSION_STATES.has(item.state));
  const jobs = active.filter(item => item.kind === 'scientific').length;
  const chats = active.filter(item => item.kind === 'conversation').length;
  const gpus = active.reduce((total, item) => total + item.gpu_slots, 0);
  const stageBudget = (value: number | null) => value === null ? '原生默认' : String(value);
  const rows: Array<[string, string]> = [
    [LIMIT_LABELS.max_active_jobs, `${jobs} / ${usage.limits.max_active_jobs}${usage.limits.max_active_jobs === 0 ? '（暂停新请求）' : ''}`],
    [LIMIT_LABELS.max_active_chats, `${chats} / ${usage.limits.max_active_chats}`],
    [LIMIT_LABELS.max_gpu_devices, `${gpus} / ${usage.limits.max_gpu_devices}`],
    [LIMIT_LABELS.max_upload_bytes, bytes(usage.limits.max_upload_bytes)],
    [LIMIT_LABELS.max_stored_upload_bytes, `${bytes(usage.stored_upload_bytes)} / ${bytes(usage.limits.max_stored_upload_bytes)}`],
    [LIMIT_LABELS.max_candidates_per_job, `${usage.limits.max_candidates_per_job}（单次执行上限，非累计余额）`],
    [LIMIT_LABELS.pilot_stage_budget, stageBudget(usage.limits.pilot_stage_budget)],
    [LIMIT_LABELS.scale_stage_budget, stageBudget(usage.limits.scale_stage_budget)],
  ];
  return <section className="account-panel" aria-label="资源用量">
    <div className="account-row"><h2>{usage.scope.name} · 资源用量</h2>
      <span>{usage.scope.kind === 'personal' ? '按个人额度检查' : usage.scope.role === 'observer' ? '团队口径（只读查看）' : '计算同时受发起人个人额度与团队额度约束'}</span>
    </div>
    <div className="account-grid">{rows.map(([label, value]) => <article className="account-scope" key={label}>
      <h3>{value}</h3><span>{label}</span>
    </article>)}</div>
    <p className="account-field-help">阶段预算是本范围内新建项目的冻结默认值；已有项目的冻结预算不受后续修改影响。</p>
    <FinalDesignsBalance block={usage.final_designs}/>
    <h3>最近准入记录</h3>
    <div className="account-table-scroll"><table><thead><tr><th>类型</th><th>状态</th><th>GPU</th><th>请求</th><th>时间</th></tr></thead>
      <tbody>{usage.admissions.map(item => <tr key={item.id}>
        <td>{item.kind === 'scientific' ? '科学计算' : '对话'}</td>
        <td>{item.state}{item.reason ? <small>{item.reason}</small> : null}</td>
        <td>{item.gpu_slots}{item.devices.length ? <small>设备 {item.devices.join(', ')}</small> : null}</td>
        <td><code>{item.request_id.slice(0, 8)}</code></td>
        <td>{when(item.created_at)}</td>
      </tr>)}</tbody></table></div>
    {usage.admissions.length === 0 && <p>暂无准入记录。发起科学请求或豆豆对话后，这里会显示配额检查与释放轨迹。</p>}
  </section>;
}

function Usage({session}: {session: AccountSession}) {
  const [selected, setSelected] = useState(session.scopes[0]?.id || '');
  const {value, error, busy, load, clear} = useGuardedLoad<ScopeUsage>();
  const reload = useCallback(() => {
    if (selected) load(() => fetchScopeUsage(session, selected));
  }, [load, session, selected]);
  useEffect(() => { clear(); reload(); }, [clear, reload]);
  if (!session.scopes.length) return <section className="account-panel"><h2>资源用量</h2><p>当前账号没有可用工作区。</p></section>;
  return <>
    <section className="account-panel"><h2>资源用量</h2>
      <div className="account-row">
        <label>选择工作区<select value={selected} onChange={event => setSelected(event.target.value)}>
          {session.scopes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <button disabled={busy} onClick={reload}>{busy ? '加载中…' : '刷新'}</button>
      </div>
      <p>额度由服务端在实际执行路径上检查；这里的数字是准入台账的只读投影，不构成资源隔离本身。</p>
      {error && <p className="account-error" role="alert">{error}</p>}
      {busy && !value && <p role="status">正在读取资源用量…</p>}
    </section>
    {value && <UsagePanel usage={value}/>}
  </>;
}

/**
 * Mirror of the backend ResourceLimits schema (accounts.py) so the form refuses
 * values the server would reject. The server remains the authority; this only
 * gives field-level feedback instead of a guaranteed-invalid request.
 */
export type RequiredLimitKey =
  | 'max_active_jobs'
  | 'max_active_chats'
  | 'max_gpu_devices'
  | 'max_upload_bytes'
  | 'max_stored_upload_bytes'
  | 'max_candidates_per_job';
export type NullableLimitKey = 'final_designs_allowance' | 'pilot_stage_budget' | 'scale_stage_budget';

const LIMIT_CONSTRAINTS: Record<RequiredLimitKey, {min: number; max: number; label: string}> = {
  max_active_jobs: {min: 0, max: 64, label: '并发科学请求（0 表示暂停新请求）'},
  max_active_chats: {min: 0, max: 64, label: '并发对话'},
  max_gpu_devices: {min: 1, max: 64, label: 'GPU 槽位上限'},
  max_upload_bytes: {min: 1024, max: 32 * 1024 ** 2, label: '单文件上传字节上限'},
  max_stored_upload_bytes: {min: 1024, max: 10 * 1024 ** 4, label: '上传存储字节额度'},
  max_candidates_per_job: {min: 1, max: 1_000_000, label: '单次生成候选数量上限'},
};
const LIMIT_KEYS = Object.keys(LIMIT_CONSTRAINTS) as Array<RequiredLimitKey>;

/** Nullable limits carry an explicit meaning; `unlimited` submits null. */
export interface NullableLimitDraft {
  unlimited: boolean;
  text: string;
}

const NULLABLE_LIMIT_CONSTRAINTS: Record<NullableLimitKey, {
  min: number; max: number; label: string; nullLabel: string; help: string;
}> = {
  final_designs_allowance: {
    min: 0, max: 1_000_000,
    label: '最终设计个人累计额度',
    nullLabel: '不限制（不启用余额检查）',
    help: '按审批人个人累计计费：依据经过核验的 Scale 全局候选池或完整原生批次回执，'
      + '完整科学负结果同样计入已交付；技术失败、证据不完整或待恢复时保留预留。'
      + 'Pilot 候选池与 Gate-5 面板修订不消耗该额度。'
      + '修改额度只影响之后的预留，不会改写已冻结的科学计划或已消耗数量。',
  },
  pilot_stage_budget: {
    min: 1, max: 10_000,
    label: 'Pilot 阶段预算（新项目默认）',
    nullLabel: '使用原生默认（不设阶段预算）',
    help: '只作为本范围内新建项目冻结的阶段预算默认值；已有项目的冻结预算不变。',
  },
  scale_stage_budget: {
    min: 1, max: 10_000,
    label: 'Scale 阶段预算（新项目默认）',
    nullLabel: '使用原生默认（不设阶段预算）',
    help: '只作为本范围内新建项目冻结的阶段预算默认值；已有项目的冻结预算不变。',
  },
};
const NULLABLE_LIMIT_KEYS = Object.keys(NULLABLE_LIMIT_CONSTRAINTS) as Array<NullableLimitKey>;

export type LimitDraft = Record<RequiredLimitKey, string> & Record<NullableLimitKey, NullableLimitDraft>;

const draftOf = (limits: QuotaLimits): LimitDraft => ({
  ...Object.fromEntries(LIMIT_KEYS.map(key => [key, String(limits[key])])) as Record<RequiredLimitKey, string>,
  ...Object.fromEntries(NULLABLE_LIMIT_KEYS.map(key => [
    key,
    {unlimited: limits[key] === null, text: limits[key] === null ? '' : String(limits[key])},
  ])) as Record<NullableLimitKey, NullableLimitDraft>,
});

/** Turns a validated draft into the POST body; `unlimited` fields become null. */
export function limitPayloadFromDraft(draft: LimitDraft): QuotaLimits {
  return {
    ...Object.fromEntries(LIMIT_KEYS.map(key => [key, Number(draft[key])])) as Record<RequiredLimitKey, number>,
    ...Object.fromEntries(NULLABLE_LIMIT_KEYS.map(key => [
      key,
      draft[key].unlimited ? null : Number(draft[key].text),
    ])) as Record<NullableLimitKey, number | null>,
  } as QuotaLimits;
}

/** Returns the first human-readable problem for each invalid field. */
export function limitDraftProblems(draft: LimitDraft): Partial<Record<keyof QuotaLimits, string>> {
  const problems: Partial<Record<keyof QuotaLimits, string>> = {};
  for (const key of LIMIT_KEYS) {
    const {min, max} = LIMIT_CONSTRAINTS[key];
    const raw = draft[key].trim();
    if (!raw) {
      problems[key] = '不能为空；请填写服务端允许范围内的整数。';
      continue;
    }
    const value = Number(raw);
    if (!Number.isInteger(value)) {
      problems[key] = '请输入有效整数。';
      continue;
    }
    if (value < min || value > max) problems[key] = `必须在 ${min} 到 ${max} 之间。`;
  }
  for (const key of NULLABLE_LIMIT_KEYS) {
    const {min, max} = NULLABLE_LIMIT_CONSTRAINTS[key];
    if (draft[key].unlimited) continue; // null is an explicit, valid choice
    const raw = draft[key].text.trim();
    if (!raw) {
      problems[key] = `不能为空；请填写 ${min} 到 ${max} 之间的整数，或勾选“${NULLABLE_LIMIT_CONSTRAINTS[key].nullLabel}”。`;
      continue;
    }
    const value = Number(raw);
    if (!Number.isInteger(value)) {
      problems[key] = '请输入有效整数。';
      continue;
    }
    if (value < min || value > max) problems[key] = `必须在 ${min} 到 ${max} 之间。`;
  }
  return problems;
}

function QuotaEditor({session, subject, name, subjectKind}: {
  session: AccountSession; subject: string; name: string; subjectKind: 'personal' | 'team';
}) {
  const {value: limits, error, busy, load} = useGuardedLoad<QuotaLimits>();
  const [draft, setDraft] = useState<LimitDraft | null>(null);
  const action = useAction();
  const reload = useCallback(() => {
    load(async () => (await accountApi<{limits: QuotaLimits}>(`/quotas/${subject}`, session)).limits);
  }, [load, subject, session]);
  useEffect(() => { reload(); }, [reload]);
  // Seed the editable copy once per loaded subject; server values stay authoritative.
  useEffect(() => { if (limits) setDraft(previous => previous ?? draftOf(limits)); }, [limits]);
  const problems = draft ? limitDraftProblems(draft) : {};
  const invalid = Object.keys(problems).length > 0;
  return <section className="account-panel"><h3>{name} · 资源额度</h3>
    {busy && !limits && <p role="status">正在读取额度…</p>}
    {error && <p className="account-error" role="alert">{error}</p>}
    {limits && draft && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      // Invalid fields cannot reach the submit button, so the parse is total.
      const saved = await accountApi<{limits: QuotaLimits}>(`/admin/quotas/${subject}`, session, limitPayloadFromDraft(draft));
      setDraft(draftOf(saved.limits));
    }, '资源额度已保存，后续准入按新额度检查');}}>
      {LIMIT_KEYS.map(key => <label key={key}>{LIMIT_CONSTRAINTS[key].label}
        <input
          type="number"
          required
          step={1}
          min={LIMIT_CONSTRAINTS[key].min}
          max={LIMIT_CONSTRAINTS[key].max}
          aria-invalid={problems[key] ? true : undefined}
          aria-label={LIMIT_CONSTRAINTS[key].label}
          value={draft[key]}
          onChange={event => setDraft({...draft, [key]: event.target.value})}
        />
        {problems[key] && <small className="account-field-error" role="alert">{problems[key]}</small>}
      </label>)}
      <p className="account-field-help">单次生成候选数量上限是一次执行内的即时上限，不是累计最终设计余额；后者由下面的个人累计额度控制。</p>
      {NULLABLE_LIMIT_KEYS.map(key => {const constraint = NULLABLE_LIMIT_CONSTRAINTS[key]; const field = draft[key]; return <label key={key}>
        {constraint.label}
        <span className="account-nullable-limit">
          <input
            type="number"
            step={1}
            min={constraint.min}
            max={constraint.max}
            required={!field.unlimited}
            disabled={field.unlimited}
            aria-invalid={problems[key] ? true : undefined}
            aria-label={constraint.label}
            value={field.text}
            onChange={event => setDraft({...draft, [key]: {...field, text: event.target.value}})}
          />
          <span className="account-null-toggle">
            <input
              type="checkbox"
              checked={field.unlimited}
              aria-label={`${constraint.label}：${constraint.nullLabel}`}
              onChange={event => setDraft({...draft, [key]: {unlimited: event.target.checked, text: event.target.checked ? '' : field.text}})}
            />
            {constraint.nullLabel}
          </span>
        </span>
        {problems[key] && <small className="account-field-error" role="alert">{problems[key]}</small>}
        <small className="account-field-help">{constraint.help}</small>
        {key === 'final_designs_allowance' && subjectKind === 'team' &&
          <small className="account-field-help">该额度只按审批人个人计费：在团队主体上保存的数值不会形成团队池，也不会改变计费单位。</small>}
      </label>;})}
      <button className="account-primary" disabled={action.busy || invalid || busy}>保存额度</button>
      {invalid && <p className="account-field-error" role="alert">仍有字段超出服务端允许范围，修正后才能保存。</p>}
    </form>}{action.feedback}</section>;
}

function FinalDesignsEntriesTable({entries}: {entries: FinalDesignEntry[]}) {
  return <div className="account-table-scroll"><table><thead><tr><th>项目</th><th>计费人</th><th>预留</th><th>已交付</th><th>状态</th><th>更新</th></tr></thead>
    <tbody>{entries.map(entry => <tr key={entry.id}>
      <td><code>{entry.project_id.slice(0, 12)}</code><small>{entry.scope_id === entry.subject_id ? '个人范围' : `范围 ${entry.scope_id.slice(0, 8)}`}</small></td>
      <td><code>{entry.subject_id.slice(0, 12)}</code></td>
      <td>{entry.amount}</td>
      <td>{entry.delivered === null ? '—' : entry.delivered}</td>
      <td>{entry.state}{entry.reason ? <small>{entry.reason}</small> : null}</td>
      <td>{when(entry.updated_at)}</td>
    </tr>)}</tbody></table></div>;
}

function FinalDesignsBalance({block}: {block: FinalDesignsBlock}) {
  const personal = block.kind === 'personal';
  const cards: Array<[string, string, string?]> = personal
    ? [
      ['额度', block.allowance === null ? '不限制' : String(block.allowance)],
      ['已预留（进行中的战役）', String(block.reserved)],
      ['已交付（含科学负结果）', String(block.delivered)],
      ['剩余可用', block.remaining === null ? '不限制' : String(block.remaining),
        block.remaining === null ? undefined : block.remaining <= 0 ? 'account-warn' : undefined],
    ]
    : [
      ['已预留（本团队，进行中的战役）', String(block.reserved)],
      ['已交付（本团队，含科学负结果）', String(block.delivered)],
    ];
  const stateText = personal && block.remaining !== null
    ? block.remaining > 0
      ? `还可预留 ${block.remaining} 个最终设计；新的 Gate-4 预留超限会被拒绝（final_designs_exhausted）。`
      : '可用额度已耗尽：新的 Gate-4 预留会被拒绝（final_designs_exhausted），需管理员调整额度。'
    : null;
  return <section className="account-panel" aria-label={personal ? '最终设计余额（个人累计）' : '最终设计用量（团队口径）'}>
    <div className="account-row"><h3>{personal ? '最终设计余额（按审批人个人累计）' : '最终设计用量（团队口径）'}</h3>
      {personal && block.allowance === null && <span>不限制：未启用余额检查</span>}
    </div>
    <p>{personal
      ? '按审批人个人累计，覆盖其个人与团队范围内的战役；不包含其他人的余额或私有项目。'
      : '仅统计计入本团队账目的预留与交付；不披露成员的个人余额、其他团队或个人项目的数据。'}</p>
    {stateText && <p className="account-permission-note" role="status">{stateText}</p>}
    <div className="account-grid">{cards.map(([label, value, warn]) => <article className="account-scope" key={label}>
      <h3 className={warn}>{value}</h3><span>{label}</span>
    </article>)}</div>
    <details><summary>计费规则</summary><p>{block.rule}</p></details>
    <h4>最终设计记录</h4>
    <FinalDesignsEntriesTable entries={block.entries}/>
    {block.entries.length === 0 && <p>还没有最终设计预留。Gate-4 批准生产战役后，这里会显示预留与结算轨迹。</p>}
  </section>;
}

type AdminData = {users: AccountUser[]; teams: Team[]; events: Audit[]};

function FinalDesignsOverview({session}: {session: AccountSession}) {
  const {value, error, busy, load} = useGuardedLoad<FinalDesignsOverview>();
  const reload = useCallback(() => {
    load(() => fetchFinalDesignsOverview(session));
  }, [load, session]);
  useEffect(() => { reload(); }, [reload]);
  return <section className="account-panel" aria-label="最终设计余额总览">
    <div className="account-row"><h2>最终设计余额总览</h2><button disabled={busy} onClick={reload}>{busy ? '加载中…' : '刷新'}</button></div>
    <p>全站只读聚合（读取会被审计）。额度按审批人个人累计；预留为进行中战役，已交付含科学负结果。</p>
    {error && <p className="account-error" role="alert">{error}</p>}
    {busy && !value && <p role="status">正在读取最终设计余额…</p>}
    {value && <>
      <div className="account-table-scroll"><table><thead><tr><th>人员</th><th>额度</th><th>已预留</th><th>已交付</th><th>剩余</th></tr></thead>
        <tbody>{value.subjects.map(subject => <tr key={subject.subject_id}>
          <td>{subject.display_name || subject.subject_id.slice(0, 12)}{subject.username ? <small>@{subject.username}</small> : null}</td>
          <td>{subject.allowance === null ? '不限制' : subject.allowance}</td>
          <td>{subject.reserved}</td>
          <td>{subject.delivered}</td>
          <td className={subject.remaining !== null && subject.remaining <= 0 ? 'account-warn' : undefined}>
            {subject.remaining === null ? '不限制' : subject.remaining}</td>
        </tr>)}</tbody></table></div>
      {value.subjects.length === 0 && <p>还没有任何最终设计预留记录。</p>}
      <details><summary>计费规则</summary><p>{value.rule}</p></details>
      <h3>最近预留记录（最多 200 条）</h3>
      <FinalDesignsEntriesTable entries={value.entries}/>
    </>}
  </section>;
}

function Administration({session}: {session: AccountSession}) {
  const {value: data, error, busy, load} = useGuardedLoad<AdminData>();
  const [selection, setSelection] = useState<{id: string; name: string; kind: 'personal' | 'team'} | null>(null);
  const [resetUser, setResetUser] = useState<AccountUser | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState('');
  const action = useAction();
  const refresh = useCallback((offset = 0) => {
    load(async previous => {
      const [u, t, a] = await Promise.all([
        accountApi<{users: AccountUser[]}>('/admin/users', session),
        accountApi<{teams: Team[]}>('/admin/teams', session),
        accountApi<{events: Audit[]}>(`/admin/audit?offset=${offset}`, session),
      ]);
      return offset && previous
        ? {users: u.users, teams: t.teams, events: [...previous.events, ...a.events]}
        : {users: u.users, teams: t.teams, events: a.events};
    });
  }, [load, session]);
  useEffect(() => { refresh(0); }, [refresh]);
  const users = data?.users || [];
  const teams = data?.teams || [];
  const events = data?.events || [];
  return <>
    <section className="account-panel"><div className="account-row"><h2>用户审核与管理</h2><button disabled={busy} onClick={() => {setSelection(null); refresh(0);}}>{busy ? '加载中…' : '刷新'}</button></div>
      <p>管理员可只读查看全站项目；科学操作仍需项目所有者或团队角色授权。</p>
      {error && <p className="account-error" role="alert">{error}</p>}
      <div className="account-table-scroll"><table><thead><tr><th>用户</th><th>状态</th><th>角色</th><th>操作</th></tr></thead><tbody>{users.map(user => <tr key={user.id}>
        <td>{user.display_name}<small>@{user.username}</small></td><td>{{pending:'待审核',active:'已启用',suspended:'已停用',rejected:'已拒绝'}[user.status]}</td><td>{user.role === 'admin' ? '系统管理员' : '用户'}</td>
        <td className="account-actions">
          {user.status !== 'active' && user.status !== 'rejected' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'active'}); refresh(0);})}>{user.status === 'pending' ? '批准注册' : '启用'}</button>}
          {user.status === 'pending' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'rejected'}); refresh(0);})}>拒绝</button>}
          {user.status === 'active' && <button disabled={action.busy} onClick={() => {if (window.confirm(`停用 ${user.display_name} 并撤销其登录会话？`)) void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'suspended'}); refresh(0);});}}>停用</button>}
          {user.status !== 'rejected' && <button onClick={() => {setResetUser(user); setTemporaryPassword('');}}>重置密码</button>}
          <button onClick={() => setSelection({id: user.id, name: user.display_name, kind: 'personal'})}>资源额度</button>
          <a href={workspaceHref(user.id, 'easy')}>只读查看项目</a>
        </td></tr>)}</tbody></table></div>{action.feedback}
    </section>
    {resetUser && <section className="account-panel"><h3>重置 {resetUser.display_name} 的密码</h3><p>旧会话会立即失效；用户下次登录必须修改临时密码。</p>
      <form onSubmit={event => {event.preventDefault(); void action.run(async () => {await accountApi(`/admin/users/${resetUser.id}/password`, session, {password:temporaryPassword}); setTemporaryPassword(''); setResetUser(null);}, '密码已重置');}}>
        <label>临时密码<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={temporaryPassword} onChange={event => setTemporaryPassword(event.target.value)}/></label>
        <button disabled={action.busy} className="account-primary">确认重置</button><button type="button" onClick={() => {setTemporaryPassword('');setResetUser(null);}}>取消</button>
      </form>
    </section>}
    <section className="account-panel"><h2>全站团队</h2>{teams.map(team => <div className="account-row" key={team.id}><strong>{team.name}</strong><span>{team.status === 'active' ? '已启用' : '已停用'}</span>
      <a href={workspaceHref(team.id, 'easy')}>只读查看项目</a><button onClick={() => setSelection({id: team.id, name: team.name, kind: 'team'})}>团队额度</button>
      <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/teams/${team.id}`, session, {status:team.status === 'active' ? 'suspended' : 'active'});refresh(0);})}>{team.status === 'active' ? '停用团队' : '启用团队'}</button>
    </div>)}</section>
    {selection && <QuotaEditor key={selection.id} session={session} subject={selection.id} name={selection.name} subjectKind={selection.kind}/>}
    <FinalDesignsOverview session={session}/>
    <section className="account-panel"><h2>最近审计记录</h2><div className="account-table-scroll"><table><thead><tr><th>时间</th><th>操作</th><th>操作人</th><th>对象</th></tr></thead><tbody>{events.map(item => <tr key={item.seq}><td>{when(item.created_at)}</td><td>{item.action}</td><td>{users.find(u => u.id === item.actor_id)?.username || '未认证请求'}</td><td><code>{item.target_id || item.scope_id || '—'}</code></td></tr>)}</tbody></table></div>
      {events.length >= AUDIT_PAGE && events.length % AUDIT_PAGE === 0 && <button disabled={busy} onClick={() => refresh(events.length)}>加载更多</button>}
    </section>
  </>;
}

const TABS: Array<[string, string]> = [
  ['workspaces', '我的工作区'], ['teams', '团队协作'], ['usage', '资源用量'], ['password', '账号安全'],
];

export function AccountApp() {
  const [session, setSession] = useState<AccountSession | null>(null);
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('workspaces');
  const action = useAction();
  const machine = useSession();
  const refresh = useCallback(async () => setSession(await accountApi<AccountSession>('/accounts/me')), []);
  const machineLogin = useCallback(async (username: string, password: string): Promise<AccountSession> => {
    await machine.login(username, password);
    return accountApi<AccountSession>('/accounts/me');
  }, [machine]);
  useEffect(() => {
    let disposed = false;
    accountApi<AccountSession>('/accounts/me').then(value => {if (!disposed) setSession(value);})
      .catch(reason => {if (!disposed && !(reason instanceof AccountApiError && reason.status === 401)) setError(errorText(reason));})
      .finally(() => {if (!disposed) setLoading(false);});
    fetchAccountConfig().then(value => {if (!disposed) setConfig(value);}).catch(() => {});
    return () => {disposed = true;};
  }, []);
  if (loading) return <main className="account-loading">正在检查会话…</main>;
  if (!session) return <>{error && <p role="alert" className="account-error">{error}</p>}<Login onLogin={setSession} login={machineLogin}/></>;
  const computeAvailable = config ? config.compute_available : true;
  const tabs: Array<[string, string]> = session.user.role === 'admin' ? [...TABS, ['admin', '管理员后台']] : TABS;
  const main: ReactNode = tab === 'workspaces' ? <Workspaces session={session} refresh={refresh}/>
    : tab === 'teams' ? <Teams session={session} refresh={refresh} computeAvailable={computeAvailable}/>
    : tab === 'usage' ? <Usage session={session}/>
    : tab === 'password' ? <Password session={session} changed={() => setSession(null)}/>
    : <Administration session={session}/>;
  return <div className="account-shell"><header className="account-header"><Brand/><strong>{session.user.display_name}</strong><span>{session.user.role === 'admin' ? '系统管理员' : '研究用户'}</span>
    <button disabled={action.busy} onClick={() => void action.run(async () => {await machine.logout(); setSession(null);setTab('workspaces');})}>退出登录</button>
  </header>{action.feedback}
    {session.user.must_change_password ? <Password session={session} changed={() => setSession(null)}/> : <>
      <nav className="account-tabs">{tabs.map(([key,label]) => <button key={key} aria-current={tab === key ? 'page' : undefined} onClick={() => setTab(key)}>{label}</button>)}</nav>
      <main>{tab === 'admin' && session.user.role !== 'admin' ? <Workspaces session={session} refresh={refresh}/> : main}</main>
    </>}
  </div>;
}
