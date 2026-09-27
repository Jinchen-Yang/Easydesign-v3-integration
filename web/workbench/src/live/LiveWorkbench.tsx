import { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  Check,
  ChevronRight,
  ClipboardList,
  Columns2,
  Cpu,
  Layers,
  PanelLeft,
  PanelRight,
  Paperclip,
  PencilLine,
  RefreshCw,
  X,
} from 'lucide-react';
import { Brand } from '../components/Brand';
import { DemoBadge } from '../components/DemoBadge';
import { Landing, Modal } from '../app/App';
import { useWorkbenchPage } from '../app/navigation';
import { ProjectSidebar, type WorkbenchPage } from '../features/projects/ProjectSidebar';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { LiveResources } from '../features/compute/LiveResources';
import { Workflow } from '../features/workflow/Workflow';
import { Conversation } from '../features/conversation/Conversation';
import { LiveLabOrderPage } from '../features/lab-order/LiveLabOrderPage';
import type {
  ActivityStatus,
  ConversationActivityStatus,
  ConversationItem,
  DesignProject,
  WorkflowPhase,
  WorkflowTask,
} from '../adapters/WorkbenchAdapter';
import type { LiveWorkbenchPort } from '../adapters/LiveWorkbenchAdapter';
import { scopeDecisionLinks, surfaceRights } from '../../../shared/account-client';
import type { GateInput, LiveState, ProductSnapshot } from './contracts';
import { LiveContext } from './LiveContext';
import { GateReview } from './GateReview';
import './live.css';
const phaseOf = (phase: string): WorkflowPhase =>
  phase === 'handoff' ? 'candidates' : (phase as WorkflowPhase);
const statusOf = (status: string): DesignProject['status'] =>
  status === 'complete'
    ? 'complete'
    : status === 'awaiting_scientist'
      ? 'review'
      : status === 'running'
        ? 'running'
        : 'paused';
const specialistNames: Record<string, string> = {
  target: 'Structure Analyst',
  site: 'Site Strategist',
  binder: 'Binder Strategist',
  judge: 'Evidence Judge',
  'pilot-diagnosis': 'Pilot Ranking Specialist',
  'final-selection': 'Final Selection Specialist',
  coordinator: 'Design Scientist',
};
const stepTitles: Record<string, string> = {
  target: 'Review your target',
  site: 'Compare candidate sites',
  design: 'Review your design',
  pilot: 'Review the pilot',
  scale: 'Follow the campaign',
  candidates: 'Review your candidate panel',
  handoff: 'Your panel is finalized',
};
function dialogue(v: ProductSnapshot): ConversationItem[] {
  const phase = phaseOf(v.project.phase);
  const recommendedTarget =
    v.decision?.gate === 1
      ? v.decision.options.find((option) => option.option_id === v.decision?.default_option_id)
      : undefined;
  const currentDecisionText = recommendedTarget
    ? `Target Intelligence recommends ${recommendedTarget.label || recommendedTarget.option_id} as the prepared structure and chain. Review it, then approve the target or change the structure.`
    : v.decision?.question || v.current_action.message;
  // The asynchronous worker's generic wait is not a current scientific failure
  // once Runtime has produced a review or terminal disposition. Native history
  // stays intact; do not hide real answers, user messages or unresolved waits.
  const incompleteTurn =
    'Scientific work remains incomplete. The previous action has not produced the required verified result; inspect its status before continuing.';
  const result: ConversationItem[] = (v.conversation || [])
    .filter(
      (m) =>
        !(
          (v.decision ||
            v.project.status === 'stopped' ||
            v.current_action.stage === 'handoff-complete') &&
          m.kind === 'summary' &&
          m.text === incompleteTurn
        ),
    )
    .map((m) => ({
      ...m,
      phase: phaseOf(m.phase || v.project.phase),
    }));
  if (!result.some((m) => m.kind === 'user' && m.text === v.project.goal))
    result.unshift({ id: 'goal', phase: 'goal', kind: 'user', text: v.project.goal });
  if (!result.some((m) => m.phase === phase && m.kind === 'summary'))
    result.push({
      id: 'current',
      phase,
      kind: 'summary',
      title: stepTitles[v.project.phase] || 'Your research is in progress',
      text: currentDecisionText,
      focus: phase,
    });
  // Keep one current card per bounded task. Completion receipts replace their
  // matching start card, while scientific milestones remain separate. Raw native
  // events never substitute for the conversation.
  const collapsed = new Map<string, ProductSnapshot['recent_activity'][number]>();
  for (const event of v.recent_activity) {
    const key = event.task_id || `event-${event.id}`;
    collapsed.set(key, event);
  }
  const cards = [...collapsed.values()]
    .filter(
      (e) =>
        e.visible !== false &&
        !(v.current_action.stage === 'handoff-complete' && e.type === 'gate.awaiting') &&
        e.type !== 'runtime.record' &&
        !['assistant.summary', 'scientist.message'].includes(e.type) &&
        Boolean(e.summary || e.text),
    )
    .sort((a, b) => a.id - b.id)
    .slice(-7)
    .map((e) => ({
      id: `activity-${e.id}`,
      phase: phaseOf(e.phase || v.project.phase),
      kind: 'tool' as const,
      title: (e.title || e.tool || e.type || 'Research evidence updated')
        .replace(/[_:-]/g, ' ')
        .replace(/^./, (c) => c.toUpperCase()),
      text: e.summary || e.text || '',
      detail: [e.specialist || e.role, e.status].filter(Boolean).join(' · ') || e.type,
      focus: phaseOf(e.phase || v.project.phase),
      status: (e.status === 'failed'
        ? 'failed'
        : e.status === 'running'
          ? 'running'
          : e.status === 'blocked'
            ? 'blocked'
            : 'complete') as ConversationActivityStatus,
    }));
  const firstChat = result.findIndex(
    (m) => !m.id.startsWith('native-') && m.id !== 'goal' && m.id !== 'current',
  );
  result.splice(firstChat < 0 ? result.length : firstChat, 0, ...cards);
  return result;
}
export function LiveWorkbench({
  adapter,
  access,
  computeAvailable = true,
}: {
  adapter: LiveWorkbenchPort;
  access?: { id?: string; can_edit: boolean; can_execute: boolean; role: string };
  computeAvailable?: boolean;
}) {
  const { canExecute, canEdit, canDiscuss } = surfaceRights(access, computeAvailable);
  const [state, setState] = useState<LiveState>();
  const [page, setPage] = useWorkbenchPage();
  const [projectsOpen, setProjectsOpen] = useState(
    () => window.matchMedia('(min-width: 1101px)').matches,
  );
  const [newDesign, setNewDesign] = useState(false),
    [draftRevision, setDraftRevision] = useState(0);
  const [viewedPhase, setViewedPhase] = useState<WorkflowPhase>('goal');
  const [contextOpen, setContextOpen] = useState(false),
    [workflowOpen, setWorkflowOpen] = useState(false),
    [tasksOpen, setTasksOpen] = useState(false),
    [compare, setCompare] = useState(false),
    [reveal, setReveal] = useState(0),
    [labOrderOpen, setLabOrderOpen] = useState(false);
  const [site, setSite] = useState(''),
    [error, setError] = useState(''),
    [token, setToken] = useState(''),
    [file, setFile] = useState<File | null>(null);
  const [modal, setModal] = useState<'help' | 'edit' | 'handoff' | 'rename' | null>(null);
  const [renamingProject, setRenamingProject] = useState('');
  const [projectName, setProjectName] = useState('');
  const focusTrigger = useRef<HTMLElement | null>(null),
    contextToggle = useRef<HTMLButtonElement>(null);
  const run = (work: () => Promise<void>) => {
    setError('');
    void work().catch((e) => setError(e.message));
  };
  useEffect(() => {
    const unsubscribe = adapter.subscribe((e) => setState(e.snapshot));
    // Legacy single-user workspace tokens cannot authorize an account session;
    // drop the parameter silently (never printed, never sent) when scoped. The
    // unscoped token flow only remains for the non-account single-user surface.
    const legacyToken = new URLSearchParams(location.hash.slice(1)).get('access');
    const accountScoped = access !== undefined;
    if (legacyToken)
      history.replaceState(null, '', location.pathname + location.search + '#projects');
    const project = new URLSearchParams(location.search).get('project');
    void (async () => {
      if (legacyToken && !accountScoped) await adapter.authenticate(legacyToken);
      if (project) {
        if (!location.hash || legacyToken) setPage('workspace');
        // Open the requested workspace without waiting for every project card.
        await Promise.all([adapter.selectProject(project), adapter.load()]);
      } else setState(await adapter.load());
    })().catch((e) => setError(e.message));
    return () => {
      unsubscribe();
      adapter.dispose();
    };
  }, [adapter]);
  // In account mode the snapshot is scope-projected; link fields the server does
  // not rewrite (decision.details_url) must never fall back to unscoped calls.
  const v = state?.snapshot
    ? access?.id
      ? scopeDecisionLinks(state.snapshot, access.id)
      : state.snapshot
    : undefined;
  const phase = phaseOf(v?.project.phase || 'goal');
  useEffect(() => {
    setViewedPhase(phase);
    setLabOrderOpen(false);
    setSite(
      v?.decision?.default_option_id ||
        v?.scientific_context.approved_site?.selected_candidate_id ||
        '',
    );
    setCompare(false);
  }, [phase, v?.project.id, v?.decision?.id]);
  const closeProjects = () => {
    if (window.matchMedia('(max-width: 1100px)').matches) setProjectsOpen(false);
  };
  const navigate = (next: WorkbenchPage) => {
    setPage(next);
    setNewDesign(false);
    setModal(null);
    setContextOpen(false);
    setWorkflowOpen(false);
    setTasksOpen(false);
    setLabOrderOpen(false);
    closeProjects();
  };
  const open = (id: string) => {
    const query = new URLSearchParams(location.search);
    query.set('project', id);
    history.replaceState(null, '', location.pathname + '?' + query + '#workspace');
    setNewDesign(false);
    setSite('');
    navigate('workspace');
    run(() => adapter.selectProject(id));
  };
  const focus = (p: WorkflowPhase) => {
    focusTrigger.current = document.activeElement as HTMLElement | null;
    setViewedPhase(p);
    setContextOpen(true);
    setWorkflowOpen(false);
    setReveal((n) => n + 1);
    setLabOrderOpen(false);
  };
  const closeContext = () => {
    setContextOpen(false);
    (focusTrigger.current?.isConnected ? focusTrigger.current : contextToggle.current)?.focus({
      preventScroll: true,
    });
  };
  const create = (goal: string) => {
    if (!canExecute) {
      setError('当前身份不能启动计算，请由项目所有者或团队管理员执行。');
      return;
    }
    run(async () => {
      await adapter.createProject(goal.slice(0, 80), goal, file);
      setNewDesign(false);
      setPage('workspace');
      closeProjects();
    });
  };
  useEffect(() => {
    if (state?.selectedProject) {
      const q = new URLSearchParams(location.search);
      q.set('project', state.selectedProject);
      history.replaceState(null, '', location.pathname + '?' + q + location.hash);
    }
  }, [state?.selectedProject]);
  const busy = !!state?.pending || state?.connection !== 'connected';
  const answering = !!v?.requests.some(
    (r) => r.kind === 'conversation' && ['accepted', 'running'].includes(r.state),
  );
  const failedCreate = v?.requests.find((r) => r.kind === 'create' && r.state === 'failed');
  const inWorkbench = page === 'workspace' && !newDesign && !!state?.selectedProject;
  const projects: DesignProject[] = (state?.projects.items || []).map((p) => ({
    id: p.id,
    title: p.title,
    goal: p.goal,
    phase: phaseOf(p.phase),
    status: statusOf(p.status),
  }));
  const tasks: WorkflowTask[] = (v?.workflow || [])
    .filter((s) => s.id !== 'handoff')
    .map((s) => ({
      id: phaseOf(s.id),
      label: s.label,
      status:
        s.status === 'complete'
          ? 'complete'
          : s.status === 'locked'
            ? 'locked'
            : s.status === 'awaiting_scientist'
              ? 'approval'
              : 'current',
      subtasks: s.subtasks || [],
    }));
  const observedSpecialists = new Map<
    string,
    { role: string; status: string; description?: string }
  >();
  for (const event of v?.recent_activity || []) {
    if (event.role && event.role !== 'coordinator' && event.type.startsWith('specialist.')) {
      observedSpecialists.set(event.role, {
        role: event.role,
        status: event.type === 'specialist.completed' ? 'complete' : 'running',
        description:
          event.type === 'specialist.completed' ? 'Review response received' : 'Review in progress',
      });
    }
  }
  for (const item of v?.specialists || []) observedSpecialists.set(item.role, item);
  const specialists = [...observedSpecialists.values()].map((s) => ({
    name: specialistNames[s.role] || s.role,
    role: s.description || 'Scientific review',
    status: (s.status === 'complete'
      ? 'complete'
      : s.status === 'running'
        ? 'running'
        : s.status === 'failed'
          ? 'failed'
          : 'waiting') as ActivityStatus,
  }));
  const completed = v?.current_action.stage === 'handoff-complete';
  const stopped = v?.project.status === 'stopped';
  const agentTasks = (v?.tasks || [])
    .filter((task) => !(completed && task.type === 'gate.awaiting'))
    .map((task) => ({
      id: task.task_id,
      title: task.title || task.task_id.replace(/[-_]/g, ' '),
      detail:
        task.summary ||
        [task.specialist || task.role, task.progress?.label].filter(Boolean).join(' · ') ||
        'Execution state recorded by the backend',
      status: task.status || 'pending',
      progress: task.progress,
    }));
  const decision = completed ? null : v?.decision;
  const option =
    decision?.options.find((o) => o.option_id === site) ||
    decision?.options.find((o) => o.option_id === decision.default_option_id);
  const rank = v?.scientific_context.sites.find((s) => s.id === option?.option_id)?.rank;
  const approveLabel = decision
    ? {
        1: 'Approve target',
        2: `Approve Site ${rank || option?.label || ''}`,
        3: 'Approve design',
        4:
          (
            {
              PROMOTE_TO_SCALE: 'Promote pilot',
              RUN_ANOTHER_PILOT: 'Prepare another pilot',
              REVISE_DESIGN: 'Revise design',
              REVISE_SITE: 'Revise site',
              STOP: 'Stop campaign',
            } as Record<string, string>
          )[option?.option_id || ''] || 'Approve pilot route',
        5: 'Finalize candidate panel',
      }[decision.gate]
    : '';
  const decide = async (input: GateInput) => {
    if (!canExecute) throw new Error('当前身份不能批准或修改科学 Gate。');
    await adapter.decide(input);
    setModal(null);
  };
  return (
    <div
      className={`app live-workbench ${inWorkbench ? 'in-workbench' : ''} ${projectsOpen ? 'projects-expanded' : ''}`}
    >
      {access && !computeAvailable && (
        <p className="account-permission-note account-compute-note">
          当前服务未连接科学执行器（账号管理模式）：可以浏览与协作编辑，计算启动、审批与项目对话暂不可用。
        </p>
      )}
      <ProjectSidebar
        mode="live"
        expanded={projectsOpen}
        page={page}
        onToggle={() => setProjectsOpen((o) => !o)}
        onClose={() => setProjectsOpen(false)}
        onNavigate={navigate}
        onHelp={() => setModal('help')}
      />
      {state?.connection === 'authentication-required' ? (
        access ? (
          <main className="landing">
            <div className="landing-center">
              <Brand />
              <h1>会话需要重新登录</h1>
              <p>当前账号会话已过期或被撤销。工作区令牌不能替代账号登录。</p>
              <a className="primary-button" href="/account/">
                返回账号与团队 <ArrowRight size={15} />
              </a>
            </div>
          </main>
        ) : (
          <main className="landing">
            <div className="landing-center">
              <Brand />
              <h1>Connect to your research workspace</h1>
              <form
                className="goal-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  run(async () => {
                    await adapter.authenticate(token);
                    await adapter.refresh();
                  });
                }}
              >
                <label className="form-label">
                  Access token
                  <input
                    type="password"
                    autoComplete="off"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                </label>
                <button className="primary-button">
                  Connect <ArrowRight size={15} />
                </button>
              </form>
            </div>
          </main>
        )
      ) : !state || state.connection === 'loading' ? (
        <div className="app-loading">
          <Brand />
          <p>Opening your research workspace…</p>
        </div>
      ) : page === 'projects' ? (
        <>
          <ProjectsPage
            mode="live"
            snapshot={{ projects }}
            canCreate={canExecute}
            createDisabledReason={
              access
                ? access.role === 'observer'
                  ? '管理员只读访问：不能创建项目、批准 Gate 或启动计算。'
                  : !computeAvailable
                    ? '服务未连接科学执行器（账号管理模式）：暂不能创建项目；团队草稿协作仍可用。'
                    : '团队成员不能启动计算；请协作编辑团队草稿，由团队管理员创建项目。'
                : undefined
            }
            onNew={() => {
              setNewDesign(true);
              setDraftRevision((n) => n + 1);
              setPage('workspace');
              closeProjects();
            }}
            onOpen={open}
            onRename={
              canEdit
                ? (project) => {
                    setRenamingProject(project.id);
                    setProjectName(project.title);
                    setModal('rename');
                  }
                : undefined
            }
          />
          {state && state.projects.total > 20 && (
            <div className="project-pagination">
              <button
                disabled={!state.projects.offset}
                onClick={() => run(() => adapter.projectPage(state.projects.offset - 20))}
              >
                Previous
              </button>
              <button
                disabled={state.projects.offset + 20 >= state.projects.total}
                onClick={() => run(() => adapter.projectPage(state.projects.offset + 20))}
              >
                Next
              </button>
            </div>
          )}
        </>
      ) : page === 'compute' ? (
        <Compute
          state={state}
          onOpen={open}
          onSelect={(id) => run(() => adapter.selectProject(id))}
        />
      ) : !inWorkbench ? (
        <Landing
          key={draftRevision}
          mode="live"
          snapshot={{
            started: !!state?.selectedProject,
            completed: !!completed,
            phase,
            project: {
              title: v?.project.title || 'your project',
              exampleGoal:
                'Design a VHH binder against hen egg-white lysozyme and prioritize a compact accessible epitope.',
            },
          }}
          newDesign={newDesign}
          focusInput={newDesign}
          onStart={create}
          onResume={() => setNewDesign(false)}
          attachment={
            <label className="attach-target" title="Optionally attach a target structure seed">
              <Paperclip size={15} />
              {file ? file.name : 'Attach target (optional)'}
              <input
                aria-label="Target structure · PDB / mmCIF"
                type="file"
                accept=".pdb,.cif,.mmcif"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
          }
        />
      ) : !v ? (
        <div className="app-loading">
          <Brand />
          <p>Opening your research workspace…</p>
        </div>
      ) : (
        <div className="workspace">
          <header className="workspace-header">
            <button
              className="mobile-workflow icon-button"
              aria-label="Toggle workflow"
              onClick={() => setWorkflowOpen((o) => !o)}
            >
              <PanelLeft size={18} />
            </button>
            <div className="project-breadcrumb">
              <span>Agent Workspace</span>
              <ChevronRight size={13} />
              <select
                aria-label="Current project"
                value={v.project.id}
                onChange={(e) => open(e.target.value)}
              >
                {!projects.some((p) => p.id === v.project.id) && (
                  <option value={v.project.id}>{v.project.title}</option>
                )}
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </div>
            <span className="save-indicator">
              <span />
              {state?.connection === 'reconnecting'
                ? 'Reconnecting…'
                : answering
                  ? 'Answering…'
                  : 'Saved'}
            </span>
            <div className="header-actions">
              <DemoBadge mode="live" />
              <button className="header-button" onClick={() => run(() => adapter.refresh())}>
                <RefreshCw size={13} />
                Refresh
              </button>
              <button
                ref={contextToggle}
                className="mobile-context icon-button"
                aria-label="Open scientific context"
                aria-expanded={contextOpen}
                aria-controls="scientific-context"
                hidden={labOrderOpen}
                onClick={() => (contextOpen ? closeContext() : focus(viewedPhase))}
              >
                <PanelRight size={17} />
              </button>
            </div>
          </header>
          <div
            className={`workbench-grid ${contextOpen ? 'context-open' : ''} ${workflowOpen ? 'workflow-open' : ''}`}
          >
            <Workflow
              mode="live"
              snapshot={{ tasks, completed, specialists }}
              agentTasks={agentTasks}
              onOpenTasks={() => setTasksOpen(true)}
              viewedPhase={labOrderOpen ? 'lab-order' : viewedPhase}
              onView={focus}
              labOrderComplete={Boolean(v.lab_order?.receipt)}
              onLabOrder={() => {
                if (v.lab_order) {
                  setLabOrderOpen(true);
                  setContextOpen(false);
                  setWorkflowOpen(false);
                } else setModal('handoff');
              }}
            />
            {labOrderOpen && v.lab_order ? (
              <LiveLabOrderPage
                order={v.lab_order}
                busy={busy || !canExecute}
                error={error}
                onApply={(action, draft, acknowledgement) =>
                  adapter.applyLabOrder(action, draft, acknowledgement)
                }
              />
            ) : (
              <div className="research-main">
                <Conversation
                  key={v.project.id}
                  mode="live"
                  snapshot={{
                    messages: dialogue(v),
                    completed: completed || stopped,
                    phase,
                    busy: v.project.status === 'running',
                  }}
                  viewedPhase={viewedPhase}
                  onFocus={focus}
                  onSkip={() => {}}
                  onRetry={(id) => run(() => adapter.retryRequest(id))}
                  disabled={state?.connection !== 'connected' || !canDiscuss}
                  sending={answering}
                  error={error}
                  onSend={async (text) => {
                    setError('');
                    try {
                      await adapter.sendMessage(text, viewedPhase);
                    } catch (e) {
                      setError((e as Error).message);
                      throw e;
                    }
                  }}
                />
                <LiveContext
                  snapshot={v}
                  state={state!}
                  adapter={adapter}
                  phase={viewedPhase}
                  siteId={site}
                  onSite={setSite}
                  compare={compare}
                  onClose={closeContext}
                  revealRequest={reveal}
                />
                <footer
                  className={`decision-bar ${completed ? 'completed' : ''}`}
                  role="region"
                  aria-label={decision ? `Gate ${decision.gate} decision` : 'Research status'}
                >
                  <span className="decision-icon">
                    <Check size={17} />
                  </span>
                  <div className="decision-copy">
                    <strong>
                      {decision?.gate === 2
                        ? `Continue with Site ${rank || ''}?`
                        : completed
                          ? 'Panel finalized'
                          : stopped
                            ? 'Campaign stopped'
                            : v.lifecycle === 'failed'
                              ? 'Target research needs a retry'
                              : decision?.gate === 1
                                ? 'Approve the automatically selected target?'
                                : decision?.gate === 3
                                  ? 'Ready to start the pilot?'
                                  : decision
                                    ? 'Ready for your review'
                                    : stepTitles[v.project.phase] || 'Research in progress'}
                    </strong>
                    <span>
                      {v.project.validation_only
                        ? 'Validation only · not authorized for experiment'
                        : stopped
                          ? 'Scientific evidence is retained; no further computation is scheduled.'
                          : v.lifecycle === 'failed'
                            ? 'Verified evidence and recovery state were retained.'
                            : decision?.gate === 1
                              ? `${option?.label || 'The recommended structure and chain'} is already selected. Change it only if needed.`
                              : decision
                                ? 'Review the scientific context before continuing.'
                                : 'Your conversations, decisions and results stay with this project.'}
                    </span>
                  </div>
                  {decision ? (
                    <div className="decision-actions">
                      {[2, 5].includes(decision.gate) && (
                        <button
                          className="secondary-button"
                          onClick={() => {
                            setCompare((c) => !c);
                            focus(phase);
                          }}
                        >
                          <Columns2 size={14} />
                          Compare
                        </button>
                      )}
                      <button
                        className="secondary-button"
                        disabled={busy || !canExecute}
                        onClick={() => setModal('edit')}
                      >
                        <PencilLine size={14} />
                        {decision.gate === 1
                          ? 'Change structure'
                          : decision.gate === 4
                            ? 'Revise'
                            : 'Edit'}
                      </button>
                      <button
                        className="primary-button"
                        disabled={
                          busy ||
                          !canExecute ||
                          !v.capabilities.decide ||
                          !option?.eligible ||
                          !(
                            option.actions.includes('approve') ||
                            option.actions.includes('override')
                          )
                        }
                        onClick={() =>
                          option?.actions.includes('approve')
                            ? run(() =>
                                decide({ action: 'approve', selected_option_id: option.option_id }),
                              )
                            : setModal('edit')
                        }
                      >
                        {approveLabel}
                        <ArrowRight size={15} />
                      </button>
                    </div>
                  ) : failedCreate ? (
                    <button
                      className="primary-button"
                      disabled={busy || !canExecute}
                      onClick={() => run(() => adapter.retryRequest(failedCreate.id))}
                    >
                      Retry Target Intelligence <ArrowRight size={15} />
                    </button>
                  ) : v.capabilities.resume ? (
                    <button
                      className="primary-button"
                      disabled={busy || !canExecute}
                      onClick={() => run(() => adapter.resume())}
                    >
                      Continue research <ArrowRight size={15} />
                    </button>
                  ) : completed ? (
                    <button
                      className="primary-button"
                      disabled={!v.lab_order}
                      onClick={() => {
                        setLabOrderOpen(true);
                        setContextOpen(false);
                      }}
                    >
                      Open simulated Lab Order <ArrowRight size={15} />
                    </button>
                  ) : null}
                </footer>
              </div>
            )}
            {tasksOpen && (
              <aside className="task-inspector" aria-label="Agent Tasks" aria-modal="true">
                <header>
                  <div>
                    <span className="eyebrow">LIVE EXECUTION</span>
                    <h2>Agent Tasks</h2>
                    <p>
                      {
                        agentTasks.filter((task) => ['complete', 'completed'].includes(task.status))
                          .length
                      }{' '}
                      of {agentTasks.length} completed
                    </p>
                  </div>
                  <button
                    className="icon-button"
                    aria-label="Close Agent Tasks"
                    onClick={() => setTasksOpen(false)}
                  >
                    <X size={17} />
                  </button>
                </header>
                <div className="task-inspector-list">
                  {agentTasks.length ? (
                    agentTasks.map((task) => (
                      <article key={task.id} className={`task-inspector-row ${task.status}`}>
                        <span className={`specialist-dot ${task.status}`} />
                        <div>
                          <strong>{task.title}</strong>
                          <p>{task.detail}</p>
                          {task.progress?.total !== undefined && (
                            <small>
                              {task.progress.completed || 0} / {task.progress.total}
                            </small>
                          )}
                        </div>
                        <span>{task.status}</span>
                      </article>
                    ))
                  ) : (
                    <div className="task-inspector-empty">
                      <ClipboardList size={22} />
                      <p>No task authority has been produced yet.</p>
                    </div>
                  )}
                </div>
              </aside>
            )}
          </div>
        </div>
      )}
      {(error || state?.error) && (
        <div className="toast" role="alert">
          <span>{error || state?.error}</span>
          <button aria-label="Dismiss message" onClick={() => setError('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {modal === 'edit' && decision && (
        <Modal title="Review your decision" onClose={() => setModal(null)}>
          <GateReview
            decision={decision}
            selectedOptionId={option?.option_id}
            busy={busy || !v?.capabilities.decide || !canExecute}
            onSelect={setSite}
            onSubmit={(input) => run(() => decide(input))}
          />
        </Modal>
      )}
      {modal === 'rename' && (
        <Modal title="Rename project" onClose={() => setModal(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canEdit) {
                setError('当前是只读访问。');
                return;
              }
              run(async () => {
                await adapter.renameProject(renamingProject, projectName);
                setModal(null);
              });
            }}
          >
            <label className="form-label">
              Project name
              <input
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                maxLength={80}
                required
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setModal(null)}>
                Cancel
              </button>
              <button className="primary-button" disabled={!projectName.trim()}>
                Save name <ArrowRight size={14} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {modal === 'help' && (
        <Modal title="About EasyDesign" onClose={() => setModal(null)}>
          <p>
            A guided research workspace. Ask Design Scientist about the evidence, compare options in
            Scientific Context, and use the decision bar when you are ready to continue.
          </p>
        </Modal>
      )}
      {modal === 'handoff' && (
        <Modal title="Panel finalized" onClose={() => setModal(null)}>
          <p>
            Your final panel and its evidence are saved. No laboratory order has been submitted.
          </p>
          {v?.artifacts
            .filter((a) => a.format === 'json')
            .map((a) => (
              <a className="artifact-download" key={a.id} href={a.url} download>
                {a.label}
              </a>
            ))}
        </Modal>
      )}
    </div>
  );
}
function Compute({
  state,
  onOpen,
  onSelect,
}: {
  state?: LiveState;
  onOpen: (id: string) => void;
  onSelect: (id: string) => void;
}) {
  const v = state?.snapshot;
  const [status, setStatus] = useState('all');
  const jobs = (v?.jobs || []).filter((j) => status === 'all' || status === j.status);
  return (
    <main className="platform-page" aria-label="Compute & Queue">
      <header className="platform-header">
        <span>A clear view of the work in progress.</span>
        <DemoBadge mode="live" />
      </header>
      <div className="platform-content">
        <div className="platform-title-row">
          <div>
            <span className="eyebrow">RESOURCES & ACTIVITY</span>
            <h1>Compute & Queue</h1>
            <p>Follow your runs across projects, from pilot to scale.</p>
          </div>
        </div>
        <LiveResources />
        <section className="compute-connection" aria-label="Project activity connection">
          <span className="compute-icon">
            <Cpu size={25} />
          </span>
          <div>
            <h2>{v ? v.project.title : 'Your research workspace'}</h2>
            <p>
              {v?.project.validation_only
                ? 'Validation only · not authorized for experiment'
                : 'Execution status from your research project.'}
            </p>
          </div>
          <span className="connection-label">
            {state?.connection === 'connected' ? 'Connected' : 'Reconnecting'}
          </span>
        </section>
        <div className="run-section-heading">
          <div>
            <h2>Research runs</h2>
            <p>Pilot and Scale activity from the selected project.</p>
          </div>
          <span className="count-label">{v?.jobs.length || 0}</span>
        </div>
        <div className="run-filters">
          <label>
            Project
            <select
              aria-label="Filter runs by project"
              value={v?.project.id || ''}
              onChange={(e) => onSelect(e.target.value)}
            >
              <option value="" disabled>
                Choose a project
              </option>
              {v && !state?.projects.items.some((p) => p.id === v.project.id) && (
                <option value={v.project.id}>{v.project.title}</option>
              )}
              {state?.projects.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              aria-label="Filter runs by status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All statuses</option>
              {[...new Set(v?.jobs.map((j) => j.status))].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
        {jobs.length ? (
          <div className="runs-table-wrap">
            <table className="runs-table">
              <thead>
                <tr>
                  <th>Run / project</th>
                  <th>Status</th>
                  <th>Recovery</th>
                  <th>
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <strong>{j.phase[0].toUpperCase() + j.phase.slice(1)} exploration</strong>
                      <span>{v?.project.title}</span>
                    </td>
                    <td>
                      <span className="project-status">
                        <i />
                        {j.status}
                      </span>
                    </td>
                    <td>{j.resumable ? 'Available to resume' : '—'}</td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Open ${j.phase} project ${v?.project.title}`}
                        onClick={() => v && onOpen(v.project.id)}
                      >
                        <ArrowRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="platform-empty queue-empty">
            <Layers size={27} />
            <h2>Room for your next run</h2>
            <p>Once you approve a design in Agent Workspace, its pilot will appear here.</p>
          </div>
        )}
        <p className="platform-footnote">Approvals remain in Agent Workspace.</p>
      </div>
    </main>
  );
}
