import {useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode} from 'react';
import {useTranslation} from 'react-i18next';
import {
  accountApi, AccountApiError, draftsApi, fetchAccountConfig, fetchFinalDesignsOverview, fetchScopeUsage,
  notifySessionChange, scopedTransport, type AccountConfig, type AccountScope,
  type AccountSession, type AccountUser, type FinalDesignEntry, type FinalDesignsBlock,
  type FinalDesignsOverview, type ProjectDraft, type QuotaLimits, type ScopeUsage,
} from '../../shared/account-client';
import {Brand} from '../../components/Brand';
import {useSession} from '../../shell/SessionProvider';
import {appI18n} from '../../shell/I18nProvider';
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
  return error instanceof Error && error.message
    ? error.message
    : appI18n.t('Operation failed, please try again', { ns: 'account' });
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
  const { t } = useTranslation('account');
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
    }, register ? t('Registration submitted and awaiting administrator review. You can sign in once approved.') : '');
  }
  return <main className="account-login">
    <Brand/><h1>{register ? t('Apply for an EasyDesign account') : t('Sign in to EasyDesign')}</h1>
    <p>{t('Personal workspaces are private; team projects are shared by permission.')}</p>
    {setup && <p role="status" className="account-notice">{t('The administrator has not completed setup; contact the deployment owner to finish the security bootstrap.')}</p>}
    <form onSubmit={submit}>
      <label>{t('Username')}<input required value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" minLength={3} maxLength={64}/></label>
      {register && <label>{t('Display name')}<input value={displayName} onChange={event => setDisplayName(event.target.value)} maxLength={100}/></label>}
      <label>{t('Password')}<input type="password" required value={password} onChange={event => setPassword(event.target.value)} autoComplete={register ? 'new-password' : 'current-password'} minLength={register ? 12 : undefined} maxLength={256}/></label>
      {register && <small>{t('At least 12 characters. Registration requires administrator approval before workspace access.')}</small>}
      <button className="account-primary" disabled={action.busy || setup}>{action.busy ? t('Processing…') : register ? t('Submit registration') : t('Sign in')}</button>
      {action.feedback}
    </form>
    <button className="account-link" onClick={() => {setRegister(!register); setPassword('');}}>{register ? t('Have an account? Back to sign in') : t('No account? Apply for registration')}</button>
  </main>;
}

function Password({session, changed}: {session: AccountSession; changed: () => void}) {
  const { t } = useTranslation('account');
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const action = useAction();
  return <section className="account-panel"><h2>{session.user.must_change_password ? t('Change your temporary password first') : t('Change password')}</h2>
    <p>{t('Changing the password invalidates all existing sessions; you will need to sign in again.')}</p>
    <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await accountApi('/accounts/password', session, {current_password: current, password: next});
      setCurrent(''); setNext(''); notifySessionChange(); changed();
    });}}>
      <label>{t('Current password')}<input type="password" autoComplete="current-password" required value={current} onChange={event => setCurrent(event.target.value)}/></label>
      <label>{t('New password')}<input type="password" autoComplete="new-password" minLength={12} maxLength={256} required value={next} onChange={event => setNext(event.target.value)}/></label>
      <button className="account-primary" disabled={action.busy}>{t('Change and sign in again')}</button>{action.feedback}
    </form>
  </section>;
}

function Workspaces({session, refresh}: {session: AccountSession; refresh: () => Promise<void>}) {
  const { t } = useTranslation('account');
  const [teamName, setTeamName] = useState('');
  const action = useAction();
  return <>
    <section className="account-panel"><h2>{t('My workspaces')}</h2><p>{t('Personal by default. New projects are shared with a team only after you enter its workspace.')}</p>
      <div className="account-grid">{session.scopes.map(scope => <article className="account-scope" key={scope.id}>
        <h3>{scope.name}</h3><span>{scope.kind === 'personal' ? t('Personal private') : scope.role === 'observer' ? t('Read-only access') : scope.can_execute ? t('Team admin') : t('Team member')}</span>
        <p>{scope.can_execute ? t('You can edit, approve Gates, and start compute.') : t('You can collaboratively edit and view results; scientific approval and compute start are handled by team admins.')}</p>
        <a className="account-primary" href={workspaceHref(scope.id, 'easy')}>{t('Enter Easy workspace')}</a>
        <a href={workspaceHref(scope.id, 'pro')}>{t('Open Pro')}</a>
      </article>)}</div>
    </section>
    {session.invitations.length > 0 && <section className="account-panel"><h2>{t('Team invitations')}</h2>{session.invitations.map(invitation => <div className="account-row" key={invitation.id}>
      <span>{invitation.team_name} · {invitation.role === 'admin' ? t('Team admin') : t('Member')}</span>
      {[true, false].map(accept => <button key={String(accept)} disabled={action.busy} onClick={() => void action.run(async () => {
        await accountApi(`/invitations/${invitation.id}`, session, {accept}); await refresh();
      })}>{accept ? t('Accept invitation') : t('Decline')}</button>)}
    </div>)}</section>}
    <section className="account-panel"><h2>{t('Create team')}</h2><form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await accountApi('/teams', session, {name: teamName}); setTeamName(''); await refresh();
    }, t('Team created'));}}>
      <label>{t('Team name')}<input value={teamName} onChange={event => setTeamName(event.target.value)} required maxLength={100}/></label>
      <button disabled={action.busy} className="account-primary">{t('Create team')}</button>{action.feedback}
    </form></section>
  </>;
}

function DraftEditor({draft, busy, onSave, onCancel}: {
  draft: ProjectDraft;
  busy: boolean;
  onSave: (value: {title: string; goal: string}, revision: number) => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation('account');
  const [title, setTitle] = useState(draft.payload.title);
  const [goal, setGoal] = useState(draft.payload.goal);
  return <form className="account-draft-form" onSubmit={event => {
    event.preventDefault();
    onSave({title: title.trim(), goal: goal.trim()}, draft.revision);
  }}>
    <label>{t('Title')}<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={80}/></label>
    <label>{t('Research goal')}<textarea rows={3} value={goal} onChange={event => setGoal(event.target.value)} required maxLength={1500}/></label>
    <div className="account-row">
      <button className="account-primary" disabled={busy || !title.trim() || !goal.trim()}>{t('Save new version')}</button>
      <button type="button" disabled={busy} onClick={onCancel}>{t('Cancel')}</button>
      <small>{t('Saving on top of revision r{{revision}}; if another member saves at the same time you will be asked to reload.', {revision: draft.revision})}</small>
    </div>
  </form>;
}

function TeamDrafts({session, scope, team, computeAvailable}: {
  session: AccountSession; scope: AccountScope; team: Team | null; computeAvailable: boolean;
}) {
  const { t } = useTranslation('account');
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
  return <section className="account-panel" aria-label={t('Team project drafts')}>
    <div className="account-row"><h2>{t('Team project drafts')}</h2>
      {busy && <span role="status">{t('Loading…')}</span>}
      <button disabled={busy} onClick={reload}>{t('Refresh')}</button>
      {canEdit && !creating && <button className="account-primary" onClick={() => {setCreating(true); setTitle(''); setGoal('');}}>{t('New draft')}</button>}
    </div>
    <p>{t('Members can edit drafts together; saving a draft never starts scientific compute. Only team admins can start a draft as a project; once started, the draft freezes as the scientific input of that moment.')}</p>
    {error && <p className="account-error" role="alert">{error}</p>}
    {creating && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      await draftsApi.save(scopedTransport(session, scope), {title: title.trim(), goal: goal.trim()});
      setCreating(false); reload();
    }, t('Draft created'));}}>
      <label>{t('Title')}<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={80}/></label>
      <label>{t('Research goal')}<textarea rows={3} value={goal} onChange={event => setGoal(event.target.value)} required maxLength={1500}/></label>
      <div className="account-row">
        <button className="account-primary" disabled={action.busy || !title.trim() || !goal.trim()}>{t('Create draft')}</button>
        <button type="button" disabled={action.busy} onClick={() => setCreating(false)}>{t('Cancel')}</button>
      </div>
      {action.feedback}
    </form>}
    {list && list.length === 0 && !creating && <p>{t('No drafts yet. Team members can refine the research goal here together before a team admin starts it.')}</p>}
    <div className="account-table-scroll"><table><thead><tr><th>{t('Draft')}</th><th>{t('Status')}</th><th>{t('Collaboration')}</th><th>{t('Actions')}</th></tr></thead>
      <tbody>{(list || []).map(draft => <tr key={draft.id}>
        <td><strong>{draft.payload.title}</strong><small>{draft.payload.goal}</small></td>
        <td>{draft.state === 'started'
          ? <>{t('Started')} {draft.project_id && <small><a href={workspaceHref(scope.id, 'easy', draft.project_id)}>{t('Open project')}</a></small>}</>
          : draft.state === 'starting' ? t('Starting') : t('Draft · r{{revision}}', {revision: draft.revision})}</td>
        <td><small>{t('Created {{name}}', {name: nameOf(draft.created_by)})}<br/>{t('Updated {{name}} · {{time}}', {name: nameOf(draft.updated_by), time: when(draft.updated_at)})}</small></td>
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
                }, t('Draft saved'))}/>
            : <button disabled={action.busy} onClick={() => {setEditing(draft.id); setCreating(false);}}>{t('Edit')}</button>)}
          {draft.state === 'draft' && scope.can_execute && computeAvailable && <button disabled={action.busy} onClick={() => {
            if (window.confirm(t('Start "{{title}}" at the current revision r{{revision}}? Starting creates a team scientific project.', {title: draft.payload.title, revision: draft.revision})))
              void action.run(async () => {
                const result = await draftsApi.start(scopedTransport(session, scope), draft.id, draft.revision);
                const projectId = result.project?.id || result.draft?.project_id || '';
                if (projectId) setStarted({draftId: draft.id, projectId});
                reload();
              }, t('Project started'));
          }}>{t('Start project')}</button>}
        </td>
      </tr>)}</tbody></table></div>
    {!scope.can_execute && <p className="account-permission-note">{t('Your role is team member: you can edit and discuss drafts; compute start and scientific approval are performed by team admins.')}</p>}
    {scope.can_execute && !computeAvailable && <p className="account-permission-note">{t('This server has no scientific executor connected (account-management mode): draft collaboration is available; project start is temporarily unavailable.')}</p>}
    {started && <p className="account-success" role="status">{t('Draft converted to project.')}<a href={workspaceHref(scope.id, 'easy', started.projectId)}>{t('Open the new project in the workspace')}</a></p>}
    {action.feedback}
  </section>;
}

function Teams({session, refresh, computeAvailable}: {
  session: AccountSession; refresh: () => Promise<void>; computeAvailable: boolean;
}) {
  const { t } = useTranslation('account');
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
    <section className="account-panel"><h2>{t('Team collaboration')}</h2>
      <label>{t('Select team')}<select value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">{t('Please select')}</option>
        {session.scopes.filter(item => item.kind === 'team').map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      {teamBusy && <p role="status">{t('Loading team…')}</p>}
      {teamError && <p className="account-error" role="alert">{teamError}</p>}
      {team && <><h3>{team.name}</h3><div className="account-table-scroll"><table><thead><tr><th>{t('Member')}</th><th>{t('Role')}</th><th>{t('Status')}</th><th>{t('Actions')}</th></tr></thead><tbody>{team.members?.filter(item => item.status === 'active').map(member => <tr key={member.user_id}>
        <td>{member.display_name} <small>@{member.username}</small></td><td>{member.role === 'admin' || member.role === 'owner' ? t('Team admin') : t('Member')}</td><td>{member.account_status === 'active' ? t('Active') : t('Unavailable')}</td>
        <td className="account-actions">
          {manage && member.role !== 'owner' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/teams/${team.id}/members/${member.user_id}`, session, {role: member.role === 'admin' ? 'member' : 'admin'}); await reloadTeam(team.id); await refresh();})}>{member.role === 'admin' ? t('Make member') : t('Make admin')}</button>}
          {(manage || member.user_id === session.user.id) && member.role !== 'owner' && <button disabled={action.busy} onClick={() => {
            if (window.confirm(member.user_id === session.user.id ? t('Leave this team?') : t('Remove {{name}}?', {name: member.display_name}))) void action.run(async () => {
              await accountApi(`/teams/${team.id}/members/${member.user_id}`, session, {remove: true}); await refresh();
              if (member.user_id === session.user.id) {setSelected('');} else await reloadTeam(team.id);
            });
          }}>{member.user_id === session.user.id ? t('Leave team') : t('Remove')}</button>}
        </td></tr>)}</tbody></table></div>
        {manage && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
          await accountApi(`/teams/${team.id}/invitations`, session, {username, role}); setUsername('');
        }, t('Invitation sent; waiting for the recipient to accept'));}}><h3>{t('Invite an active user')}</h3>
          <label>{t('Username')}<input required value={username} onChange={event => setUsername(event.target.value)}/></label>
          <label>{t('Role after joining')}<select value={role} onChange={event => setRole(event.target.value)}><option value="member">{t('Member')}</option><option value="admin">{t('Team admin')}</option></select></label>
          <button className="account-primary" disabled={action.busy}>{t('Send invitation')}</button>
        </form>}
      </>}{action.feedback}
    </section>
    {scope && scope.kind === 'team' && team && <TeamDrafts session={session} scope={scope} team={team} computeAvailable={computeAvailable}/>}
  </>;
}

const LIMIT_LABELS: Record<keyof QuotaLimits, string> = {
  max_active_jobs: 'Concurrent scientific requests', max_active_chats: 'Concurrent conversations',
  max_gpu_devices: 'GPU slot limit', max_upload_bytes: 'Single-file upload limit',
  max_stored_upload_bytes: 'Upload storage quota', max_candidates_per_job: 'Candidates per run limit',
  final_designs_allowance: 'Final designs personal cumulative allowance',
  pilot_stage_budget: 'Pilot stage budget (new projects)',
  scale_stage_budget: 'Scale stage budget (new projects)',
};

function UsagePanel({usage}: {usage: ScopeUsage}) {
  const { t } = useTranslation('account');
  const active = usage.admissions.filter(item => ACTIVE_ADMISSION_STATES.has(item.state));
  const jobs = active.filter(item => item.kind === 'scientific').length;
  const chats = active.filter(item => item.kind === 'conversation').length;
  const gpus = active.reduce((total, item) => total + item.gpu_slots, 0);
  const stageBudget = (value: number | null) => value === null ? t('Native default') : String(value);
  const rows: Array<[string, string]> = [
    [t(LIMIT_LABELS.max_active_jobs), `${jobs} / ${usage.limits.max_active_jobs}${usage.limits.max_active_jobs === 0 ? t('(new requests paused)') : ''}`],
    [t(LIMIT_LABELS.max_active_chats), `${chats} / ${usage.limits.max_active_chats}`],
    [t(LIMIT_LABELS.max_gpu_devices), `${gpus} / ${usage.limits.max_gpu_devices}`],
    [t(LIMIT_LABELS.max_upload_bytes), bytes(usage.limits.max_upload_bytes)],
    [t(LIMIT_LABELS.max_stored_upload_bytes), `${bytes(usage.stored_upload_bytes)} / ${bytes(usage.limits.max_stored_upload_bytes)}`],
    [t(LIMIT_LABELS.max_candidates_per_job), `${usage.limits.max_candidates_per_job}${t('(per-execution limit, not a cumulative balance)')}`],
    [t(LIMIT_LABELS.pilot_stage_budget), stageBudget(usage.limits.pilot_stage_budget)],
    [t(LIMIT_LABELS.scale_stage_budget), stageBudget(usage.limits.scale_stage_budget)],
  ];
  return <section className="account-panel" aria-label={t('Resource usage')}>
    <div className="account-row"><h2>{usage.scope.name} · {t('Resource usage')}</h2>
      <span>{usage.scope.kind === 'personal' ? t('Checked against personal quota') : usage.scope.role === 'observer' ? t('Team view (read-only)') : t("Compute is constrained by both the initiator's personal quota and the team quota")}</span>
    </div>
    <div className="account-grid">{rows.map(([label, value]) => <article className="account-scope" key={label}>
      <h3>{value}</h3><span>{label}</span>
    </article>)}</div>
    <p className="account-field-help">{t('Stage budgets are frozen defaults for new projects in this scope; frozen budgets of existing projects are unaffected by later changes.')}</p>
    <FinalDesignsBalance block={usage.final_designs}/>
    <h3>{t('Recent admissions')}</h3>
    <div className="account-table-scroll"><table><thead><tr><th>{t('Type')}</th><th>{t('Status')}</th><th>GPU</th><th>{t('Request')}</th><th>{t('Time')}</th></tr></thead>
      <tbody>{usage.admissions.map(item => <tr key={item.id}>
        <td>{item.kind === 'scientific' ? t('Scientific compute') : t('Conversation')}</td>
        <td>{item.state}{item.reason ? <small>{item.reason}</small> : null}</td>
        <td>{item.gpu_slots}{item.devices.length ? <small>{t('Devices {{devices}}', {devices: item.devices.join(', ')})}</small> : null}</td>
        <td><code>{item.request_id.slice(0, 8)}</code></td>
        <td>{when(item.created_at)}</td>
      </tr>)}</tbody></table></div>
    {usage.admissions.length === 0 && <p>{t('No admissions yet. After you start a scientific request or a Doudou conversation, quota checks and release traces appear here.')}</p>}
  </section>;
}

function Usage({session}: {session: AccountSession}) {
  const { t } = useTranslation('account');
  const [selected, setSelected] = useState(session.scopes[0]?.id || '');
  const {value, error, busy, load, clear} = useGuardedLoad<ScopeUsage>();
  const reload = useCallback(() => {
    if (selected) load(() => fetchScopeUsage(session, selected));
  }, [load, session, selected]);
  useEffect(() => { clear(); reload(); }, [clear, reload]);
  if (!session.scopes.length) return <section className="account-panel"><h2>{t('Resource usage')}</h2><p>{t('This account has no available workspace.')}</p></section>;
  return <>
    <section className="account-panel"><h2>{t('Resource usage')}</h2>
      <div className="account-row">
        <label>{t('Select workspace')}<select value={selected} onChange={event => setSelected(event.target.value)}>
          {session.scopes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        <button disabled={busy} onClick={reload}>{busy ? t('Loading…') : t('Refresh')}</button>
      </div>
      <p>{t('Quotas are enforced by the server on the actual execution path; the numbers here are a read-only projection of the admission ledger, not resource isolation itself.')}</p>
      {error && <p className="account-error" role="alert">{error}</p>}
      {busy && !value && <p role="status">{t('Reading resource usage…')}</p>}
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
  max_active_jobs: {min: 0, max: 64, label: 'Concurrent scientific requests (0 pauses new requests)'},
  max_active_chats: {min: 0, max: 64, label: 'Concurrent conversations'},
  max_gpu_devices: {min: 1, max: 64, label: 'GPU slot limit'},
  max_upload_bytes: {min: 1024, max: 32 * 1024 ** 2, label: 'Single-file upload byte limit'},
  max_stored_upload_bytes: {min: 1024, max: 10 * 1024 ** 4, label: 'Upload storage byte quota'},
  max_candidates_per_job: {min: 1, max: 1_000_000, label: 'Max candidates per run'},
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
    label: 'Final designs personal cumulative allowance',
    nullLabel: 'Unlimited (balance check disabled)',
    help: 'Billed per approver: delivery counts verified Scale global candidate pools or complete native-batch receipts, '
      + 'and complete scientific negative results count as delivered; reservations are kept on technical failure, incomplete evidence, or pending recovery. '
      + 'Pilot candidate pools and Gate-5 panel revisions do not consume this allowance. '
      + 'Changes only affect future reservations and never rewrite frozen scientific plans or amounts already consumed.',
  },
  pilot_stage_budget: {
    min: 1, max: 10_000,
    label: 'Pilot stage budget (default for new projects)',
    nullLabel: 'Use native default (no stage budget)',
    help: 'Only the frozen stage-budget default for new projects in this scope; frozen budgets of existing projects are unchanged.',
  },
  scale_stage_budget: {
    min: 1, max: 10_000,
    label: 'Scale stage budget (default for new projects)',
    nullLabel: 'Use native default (no stage budget)',
    help: 'Only the frozen stage-budget default for new projects in this scope; frozen budgets of existing projects are unchanged.',
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
export function limitDraftProblems(
  draft: LimitDraft,
  t: (key: string, values?: Record<string, string | number>) => string,
): Partial<Record<keyof QuotaLimits, string>> {
  const problems: Partial<Record<keyof QuotaLimits, string>> = {};
  for (const key of LIMIT_KEYS) {
    const {min, max} = LIMIT_CONSTRAINTS[key];
    const raw = draft[key].trim();
    if (!raw) {
      problems[key] = t('Required; enter an integer within the server-allowed range.');
      continue;
    }
    const value = Number(raw);
    if (!Number.isInteger(value)) {
      problems[key] = t('Enter a valid integer.');
      continue;
    }
    if (value < min || value > max) problems[key] = t('Must be between {{min}} and {{max}}.', {min, max});
  }
  for (const key of NULLABLE_LIMIT_KEYS) {
    const {min, max} = NULLABLE_LIMIT_CONSTRAINTS[key];
    if (draft[key].unlimited) continue; // null is an explicit, valid choice
    const raw = draft[key].text.trim();
    if (!raw) {
      problems[key] = t('Required; enter an integer between {{min}} and {{max}}, or check "{{nullLabel}}".', {
        min, max, nullLabel: t(NULLABLE_LIMIT_CONSTRAINTS[key].nullLabel),
      });
      continue;
    }
    const value = Number(raw);
    if (!Number.isInteger(value)) {
      problems[key] = t('Enter a valid integer.');
      continue;
    }
    if (value < min || value > max) problems[key] = t('Must be between {{min}} and {{max}}.', {min, max});
  }
  return problems;
}

function QuotaEditor({session, subject, name, subjectKind}: {
  session: AccountSession; subject: string; name: string; subjectKind: 'personal' | 'team';
}) {
  const { t } = useTranslation('account');
  const {value: limits, error, busy, load} = useGuardedLoad<QuotaLimits>();
  const [draft, setDraft] = useState<LimitDraft | null>(null);
  const action = useAction();
  const reload = useCallback(() => {
    load(async () => (await accountApi<{limits: QuotaLimits}>(`/quotas/${subject}`, session)).limits);
  }, [load, subject, session]);
  useEffect(() => { reload(); }, [reload]);
  // Seed the editable copy once per loaded subject; server values stay authoritative.
  useEffect(() => { if (limits) setDraft(previous => previous ?? draftOf(limits)); }, [limits]);
  const problems = draft ? limitDraftProblems(draft, t) : {};
  const invalid = Object.keys(problems).length > 0;
  return <section className="account-panel"><h3>{name} · {t('Resource quota')}</h3>
    {busy && !limits && <p role="status">{t('Reading quota…')}</p>}
    {error && <p className="account-error" role="alert">{error}</p>}
    {limits && draft && <form onSubmit={event => {event.preventDefault(); void action.run(async () => {
      // Invalid fields cannot reach the submit button, so the parse is total.
      const saved = await accountApi<{limits: QuotaLimits}>(`/admin/quotas/${subject}`, session, limitPayloadFromDraft(draft));
      setDraft(draftOf(saved.limits));
    }, t('Resource quota saved; future admissions are checked against the new quota'));}}>
      {LIMIT_KEYS.map(key => <label key={key}>{t(LIMIT_CONSTRAINTS[key].label)}
        <input
          type="number"
          required
          step={1}
          min={LIMIT_CONSTRAINTS[key].min}
          max={LIMIT_CONSTRAINTS[key].max}
          aria-invalid={problems[key] ? true : undefined}
          aria-label={t(LIMIT_CONSTRAINTS[key].label)}
          value={draft[key]}
          onChange={event => setDraft({...draft, [key]: event.target.value})}
        />
        {problems[key] && <small className="account-field-error" role="alert">{problems[key]}</small>}
      </label>)}
      <p className="account-field-help">{t('The candidates-per-run limit is an immediate cap within one execution, not a cumulative final-designs balance; the latter is controlled by the personal cumulative allowance below.')}</p>
      {NULLABLE_LIMIT_KEYS.map(key => {const constraint = NULLABLE_LIMIT_CONSTRAINTS[key]; const field = draft[key]; return <label key={key}>
        {t(constraint.label)}
        <span className="account-nullable-limit">
          <input
            type="number"
            step={1}
            min={constraint.min}
            max={constraint.max}
            required={!field.unlimited}
            disabled={field.unlimited}
            aria-invalid={problems[key] ? true : undefined}
            aria-label={t(constraint.label)}
            value={field.text}
            onChange={event => setDraft({...draft, [key]: {...field, text: event.target.value}})}
          />
          <span className="account-null-toggle">
            <input
              type="checkbox"
              checked={field.unlimited}
              aria-label={t('{{label}}: {{nullLabel}}', {label: t(constraint.label), nullLabel: t(constraint.nullLabel)})}
              onChange={event => setDraft({...draft, [key]: {unlimited: event.target.checked, text: event.target.checked ? '' : field.text}})}
            />
            {t(constraint.nullLabel)}
          </span>
        </span>
        {problems[key] && <small className="account-field-error" role="alert">{problems[key]}</small>}
        <small className="account-field-help">{t(constraint.help)}</small>
        {key === 'final_designs_allowance' && subjectKind === 'team' &&
          <small className="account-field-help">{t('This allowance is billed per approver only: values saved on a team subject do not form a team pool and do not change the billing unit.')}</small>}
      </label>;})}
      <button className="account-primary" disabled={action.busy || invalid || busy}>{t('Save quota')}</button>
      {invalid && <p className="account-field-error" role="alert">{t('Some fields are outside the server-allowed range; fix them before saving.')}</p>}
    </form>}{action.feedback}</section>;
}

function FinalDesignsEntriesTable({entries}: {entries: FinalDesignEntry[]}) {
  const { t } = useTranslation('account');
  return <div className="account-table-scroll"><table><thead><tr><th>{t('Project')}</th><th>{t('Billed to')}</th><th>{t('Reserved')}</th><th>{t('Delivered')}</th><th>{t('Status')}</th><th>{t('Updated')}</th></tr></thead>
    <tbody>{entries.map(entry => <tr key={entry.id}>
      <td><code>{entry.project_id.slice(0, 12)}</code><small>{entry.scope_id === entry.subject_id ? t('Personal scope') : t('Scope {{id}}', {id: entry.scope_id.slice(0, 8)})}</small></td>
      <td><code>{entry.subject_id.slice(0, 12)}</code></td>
      <td>{entry.amount}</td>
      <td>{entry.delivered === null ? '—' : entry.delivered}</td>
      <td>{entry.state}{entry.reason ? <small>{entry.reason}</small> : null}</td>
      <td>{when(entry.updated_at)}</td>
    </tr>)}</tbody></table></div>;
}

function FinalDesignsBalance({block}: {block: FinalDesignsBlock}) {
  const { t } = useTranslation('account');
  const personal = block.kind === 'personal';
  const cards: Array<[string, string, string?]> = personal
    ? [
      [t('Allowance'), block.allowance === null ? t('Unlimited') : String(block.allowance)],
      [t('Reserved (campaigns in progress)'), String(block.reserved)],
      [t('Delivered (including scientific negative results)'), String(block.delivered)],
      [t('Remaining available'), block.remaining === null ? t('Unlimited') : String(block.remaining),
        block.remaining === null ? undefined : block.remaining <= 0 ? 'account-warn' : undefined],
    ]
    : [
      [t('Reserved (this team, campaigns in progress)'), String(block.reserved)],
      [t('Delivered (this team, including scientific negative results)'), String(block.delivered)],
    ];
  const stateText = personal && block.remaining !== null
    ? block.remaining > 0
      ? t('{{count}} final designs can still be reserved; new Gate-4 reservations beyond this are rejected (final_designs_exhausted).', {count: block.remaining})
      : t('Allowance exhausted: new Gate-4 reservations are rejected (final_designs_exhausted); an administrator must adjust the allowance.')
    : null;
  return <section className="account-panel" aria-label={personal ? t('Final designs balance (personal cumulative)') : t('Final designs usage (team view)')}>
    <div className="account-row"><h3>{personal ? t('Final designs balance (cumulative per approver)') : t('Final designs usage (team view)')}</h3>
      {personal && block.allowance === null && <span>{t('Unlimited: balance check disabled')}</span>}
    </div>
    <p>{personal
      ? t("Cumulative per approver across their personal and team-scope campaigns; excludes other people's balances and private projects.")
      : t("Only counts reservations and deliveries billed to this team; members' personal balances, other teams, and personal projects are not disclosed.")}</p>
    {stateText && <p className="account-permission-note" role="status">{stateText}</p>}
    <div className="account-grid">{cards.map(([label, value, warn]) => <article className="account-scope" key={label}>
      <h3 className={warn}>{value}</h3><span>{label}</span>
    </article>)}</div>
    <details><summary>{t('Billing rules')}</summary><p>{block.rule}</p></details>
    <h4>{t('Final designs records')}</h4>
    <FinalDesignsEntriesTable entries={block.entries}/>
    {block.entries.length === 0 && <p>{t('No final-design reservations yet. After Gate-4 approves a production campaign, reservations and settlement traces appear here.')}</p>}
  </section>;
}

type AdminData = {users: AccountUser[]; teams: Team[]; events: Audit[]};

function FinalDesignsOverview({session}: {session: AccountSession}) {
  const { t } = useTranslation('account');
  const {value, error, busy, load} = useGuardedLoad<FinalDesignsOverview>();
  const reload = useCallback(() => {
    load(() => fetchFinalDesignsOverview(session));
  }, [load, session]);
  useEffect(() => { reload(); }, [reload]);
  return <section className="account-panel" aria-label={t('Final designs balance overview')}>
    <div className="account-row"><h2>{t('Final designs balance overview')}</h2><button disabled={busy} onClick={reload}>{busy ? t('Loading…') : t('Refresh')}</button></div>
    <p>{t('Site-wide read-only aggregation (reads are audited). Allowances are cumulative per approver; reservations are campaigns in progress; delivered includes scientific negative results.')}</p>
    {error && <p className="account-error" role="alert">{error}</p>}
    {busy && !value && <p role="status">{t('Reading final designs balance…')}</p>}
    {value && <>
      <div className="account-table-scroll"><table><thead><tr><th>{t('Person')}</th><th>{t('Allowance')}</th><th>{t('Reserved')}</th><th>{t('Delivered')}</th><th>{t('Remaining')}</th></tr></thead>
        <tbody>{value.subjects.map(subject => <tr key={subject.subject_id}>
          <td>{subject.display_name || subject.subject_id.slice(0, 12)}{subject.username ? <small>@{subject.username}</small> : null}</td>
          <td>{subject.allowance === null ? t('Unlimited') : subject.allowance}</td>
          <td>{subject.reserved}</td>
          <td>{subject.delivered}</td>
          <td className={subject.remaining !== null && subject.remaining <= 0 ? 'account-warn' : undefined}>
            {subject.remaining === null ? t('Unlimited') : subject.remaining}</td>
        </tr>)}</tbody></table></div>
      {value.subjects.length === 0 && <p>{t('No final-design reservation records yet.')}</p>}
      <details><summary>{t('Billing rules')}</summary><p>{value.rule}</p></details>
      <h3>{t('Recent reservations (up to 200)')}</h3>
      <FinalDesignsEntriesTable entries={value.entries}/>
    </>}
  </section>;
}

function Administration({session}: {session: AccountSession}) {
  const { t } = useTranslation('account');
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
    <section className="account-panel"><div className="account-row"><h2>{t('User review and management')}</h2><button disabled={busy} onClick={() => {setSelection(null); refresh(0);}}>{busy ? t('Loading…') : t('Refresh')}</button></div>
      <p>{t('Administrators can view all projects read-only; scientific operations still require authorization from the project owner or a team role.')}</p>
      {error && <p className="account-error" role="alert">{error}</p>}
      <div className="account-table-scroll"><table><thead><tr><th>{t('User')}</th><th>{t('Status')}</th><th>{t('Role')}</th><th>{t('Actions')}</th></tr></thead><tbody>{users.map(user => <tr key={user.id}>
        <td>{user.display_name}<small>@{user.username}</small></td><td>{t(USER_STATUS_LABELS[user.status] ?? user.status)}</td><td>{user.role === 'admin' ? t('System administrator') : t('User')}</td>
        <td className="account-actions">
          {user.status !== 'active' && user.status !== 'rejected' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'active'}); refresh(0);})}>{user.status === 'pending' ? t('Approve registration') : t('Enable')}</button>}
          {user.status === 'pending' && <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'rejected'}); refresh(0);})}>{t('Reject')}</button>}
          {user.status === 'active' && <button disabled={action.busy} onClick={() => {if (window.confirm(t('Suspend {{name}} and revoke their sign-in sessions?', {name: user.display_name}))) void action.run(async () => {await accountApi(`/admin/users/${user.id}`, session, {status:'suspended'}); refresh(0);});}}>{t('Suspend')}</button>}
          {user.status !== 'rejected' && <button onClick={() => {setResetUser(user); setTemporaryPassword('');}}>{t('Reset password')}</button>}
          <button onClick={() => setSelection({id: user.id, name: user.display_name, kind: 'personal'})}>{t('Resource quota')}</button>
          <a href={workspaceHref(user.id, 'easy')}>{t('View projects read-only')}</a>
        </td></tr>)}</tbody></table></div>{action.feedback}
    </section>
    {resetUser && <section className="account-panel"><h3>{t('Reset password for {{name}}', {name: resetUser.display_name})}</h3><p>{t('Existing sessions become invalid immediately; the user must change the temporary password at next sign-in.')}</p>
      <form onSubmit={event => {event.preventDefault(); void action.run(async () => {await accountApi(`/admin/users/${resetUser.id}/password`, session, {password:temporaryPassword}); setTemporaryPassword(''); setResetUser(null);}, t('Password reset'));}}>
        <label>{t('Temporary password')}<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={temporaryPassword} onChange={event => setTemporaryPassword(event.target.value)}/></label>
        <button disabled={action.busy} className="account-primary">{t('Confirm reset')}</button><button type="button" onClick={() => {setTemporaryPassword('');setResetUser(null);}}>{t('Cancel')}</button>
      </form>
    </section>}
    <section className="account-panel"><h2>{t('All teams')}</h2>{teams.map(team => <div className="account-row" key={team.id}><strong>{team.name}</strong><span>{team.status === 'active' ? t('Active') : t('Suspended')}</span>
      <a href={workspaceHref(team.id, 'easy')}>{t('View projects read-only')}</a><button onClick={() => setSelection({id: team.id, name: team.name, kind: 'team'})}>{t('Team quota')}</button>
      <button disabled={action.busy} onClick={() => void action.run(async () => {await accountApi(`/admin/teams/${team.id}`, session, {status:team.status === 'active' ? 'suspended' : 'active'});refresh(0);})}>{team.status === 'active' ? t('Suspend team') : t('Enable team')}</button>
    </div>)}</section>
    {selection && <QuotaEditor key={selection.id} session={session} subject={selection.id} name={selection.name} subjectKind={selection.kind}/>}
    <FinalDesignsOverview session={session}/>
    <section className="account-panel"><h2>{t('Recent audit records')}</h2><div className="account-table-scroll"><table><thead><tr><th>{t('Time')}</th><th>{t('Action')}</th><th>{t('Actor')}</th><th>{t('Target')}</th></tr></thead><tbody>{events.map(item => <tr key={item.seq}><td>{when(item.created_at)}</td><td>{item.action}</td><td>{users.find(u => u.id === item.actor_id)?.username || t('Unauthenticated request')}</td><td><code>{item.target_id || item.scope_id || '—'}</code></td></tr>)}</tbody></table></div>
      {events.length >= AUDIT_PAGE && events.length % AUDIT_PAGE === 0 && <button disabled={busy} onClick={() => refresh(events.length)}>{t('Load more')}</button>}
    </section>
  </>;
}

const USER_STATUS_LABELS: Record<string, string> = {
  pending: 'Pending review', active: 'Active', suspended: 'Suspended', rejected: 'Rejected',
};

const TABS: Array<[string, string]> = [
  ['workspaces', 'My workspaces'], ['teams', 'Team collaboration'], ['usage', 'Resource usage'], ['password', 'Account security'],
];

export function AccountApp() {
  const { t } = useTranslation('account');
  const [localSession, setLocalSession] = useState<AccountSession | null>(null);
  const [config, setConfig] = useState<AccountConfig | null>(null);
  const [tab, setTab] = useState('workspaces');
  const action = useAction();
  const machine = useSession();
  // 唯一真相源是会话状态机；本地副本仅承载主动刷新（建团队/改配额/改密码后）
  // 拿到的最新数据，登出或换号即丢弃，避免两个真相。
  const session = localSession ?? (machine.state.kind === 'authenticated' ? machine.state.session : null);
  const refresh = useCallback(async () => setLocalSession(await accountApi<AccountSession>('/accounts/me')), []);
  const machineLogin = useCallback(async (username: string, password: string): Promise<AccountSession> => {
    await machine.login(username, password);
    return accountApi<AccountSession>('/accounts/me');
  }, [machine]);
  useEffect(() => {
    if (machine.state.kind !== 'authenticated') setLocalSession(null);
  }, [machine.state.kind]);
  useEffect(() => {
    let disposed = false;
    fetchAccountConfig().then(value => {if (!disposed) setConfig(value);}).catch(() => {});
    return () => {disposed = true;};
  }, []);
  if (machine.state.kind === 'checking' && session === null) return <main className="account-loading">{t('Checking session…')}</main>;
  if (!session) return <Login onLogin={setLocalSession} login={machineLogin}/>;
  const computeAvailable = config ? config.compute_available : true;
  const tabs: Array<[string, string]> = session.user.role === 'admin' ? [...TABS, ['admin', t('Administration')]] : TABS;
  const main: ReactNode = tab === 'workspaces' ? <Workspaces session={session} refresh={refresh}/>
    : tab === 'teams' ? <Teams session={session} refresh={refresh} computeAvailable={computeAvailable}/>
    : tab === 'usage' ? <Usage session={session}/>
    : tab === 'password' ? <Password session={session} changed={() => setLocalSession(null)}/>
    : <Administration session={session}/>;
  return <div className="account-shell"><header className="account-header"><Brand/><strong>{session.user.display_name}</strong><span>{session.user.role === 'admin' ? t('System administrator') : t('Research user')}</span>
    <button disabled={action.busy} onClick={() => void action.run(async () => {await machine.logout(); setLocalSession(null);setTab('workspaces');})}>{t('Sign out')}</button>
  </header>{action.feedback}
    {session.user.must_change_password ? <Password session={session} changed={() => setLocalSession(null)}/> : <>
      <nav className="account-tabs">{tabs.map(([key,label]) => <button key={key} aria-current={tab === key ? 'page' : undefined} onClick={() => setTab(key)}>{t(label)}</button>)}</nav>
      <main>{tab === 'admin' && session.user.role !== 'admin' ? <Workspaces session={session} refresh={refresh}/> : main}</main>
    </>}
  </div>;
}
