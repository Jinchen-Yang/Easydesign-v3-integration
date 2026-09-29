import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
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
import { Brand } from '../../components/Brand';
import { WorkspaceAccessNotice } from '../../components/WorkspaceAccessNotice';
import { DemoBadge } from '../../components/DemoBadge';
import { Landing, Modal } from '../../app/App';
import { ProjectSidebar, type WorkbenchPage } from '../../features/projects/ProjectSidebar';
import { ProjectsPage } from '../../features/projects/ProjectsPage';
import { LiveResources } from '../../features/compute/LiveResources';
import { Workflow } from '../../features/workflow/Workflow';
import { Conversation } from '../../features/conversation/Conversation';
import { LiveLabOrderPage } from '../../features/lab-order/LiveLabOrderPage';
import type {
  ActivityStatus,
  ConversationActivityStatus,
  ConversationItem,
  DesignProject,
  WorkflowPhase,
  WorkflowTask,
} from '../../adapters/WorkbenchAdapter';
import type { LiveWorkbenchPort } from '../../adapters/LiveWorkbenchAdapter';
import { scopeDecisionLinks, surfaceRights } from '../../shared/account-client';
import type { GateInput, LiveState, ProductSnapshot } from './contracts';
import { LiveContext } from './LiveContext';
import { GateReview } from './GateReview';
import { DRAFT_KEYS } from '../../data/draftRecovery';
import { useInputDraft } from '../../data/useInputDraft';
import { DraftStatus } from '../../data/DraftStatus';
import { latestQueueCancellation } from './queue-presentation';
import { readProjectRoute, writeProjectRoute } from '../easy/routeParams';
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
function dialogue(
  v: ProductSnapshot,
  t: TFunction<'pro'>,
  queueCancelled = false,
): ConversationItem[] {
  const phase = phaseOf(v.project.phase);
  const recommendedTarget =
    v.decision?.gate === 1
      ? v.decision.options.find((option) => option.option_id === v.decision?.default_option_id)
      : undefined;
  const currentDecisionText = recommendedTarget
    ? t(
        'Target Intelligence recommends {{name}} as the prepared structure and chain. Review it, then approve the target or change the structure.',
        { name: recommendedTarget.label || recommendedTarget.option_id },
      )
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
    result.unshift({
      id: 'goal',
      phase: 'goal',
      kind: 'user',
      text: v.project.goal,
    });
  if (!result.some((m) => m.phase === phase && m.kind === 'summary'))
    result.push({
      id: 'current',
      phase,
      kind: 'summary',
      title:
        queueCancelled && !v.decision
          ? t('Request cancelled before execution')
          : t(stepTitles[v.project.phase] || 'Your research is in progress'),
      text:
        queueCancelled && !v.decision
          ? t(
              'This request did not start computation. Scientific evidence is retained; it will not restart automatically.',
            )
          : currentDecisionText,
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
      title: (e.title || e.tool || e.type || t('Research evidence updated'))
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
  access?: {
    id?: string;
    can_edit: boolean;
    can_execute: boolean;
    role: string;
  };
  computeAvailable?: boolean;
}) {
  const { t } = useTranslation('pro');
  const { canExecute, canEdit, canDiscuss } = surfaceRights(access, computeAvailable);
  const [state, setState] = useState<LiveState>();
  // 统一应用里 hash 属于路由器；Pro 内部页签只保留组件状态（?page= 仅作初始值）。
  const [page, setPage] = useState<WorkbenchPage>(() => {
    const initial = new URLSearchParams(location.hash.split('?')[1] ?? '').get('page');
    return initial === 'workspace' || initial === 'compute' || initial === 'projects'
      ? initial
      : readProjectRoute()
        ? 'workspace'
        : 'projects';
  });
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
  const [renameOriginal, setRenameOriginal] = useState('');
  const scopeId = access?.id || 'single-user';
  const renameDraft = useInputDraft(
    renamingProject ? DRAFT_KEYS.scoped(scopeId, 'project', renamingProject, 'rename') : null,
    renameOriginal,
  );
  const { value: projectName, setValue: setProjectName } = renameDraft;
  const fileDraft = useInputDraft<{ name: string; size: number } | null>(
    DRAFT_KEYS.scoped(scopeId, 'pro', 'create', 'file'),
    null,
    {
      valid: (value): value is { name: string; size: number } | null =>
        value === null ||
        (typeof value === 'object' &&
          typeof (value as { name?: unknown }).name === 'string' &&
          typeof (value as { size?: unknown }).size === 'number'),
    },
  );
  const needsFile = !!fileDraft.value && !file;
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
    const project = readProjectRoute();
    void (async () => {
      if (legacyToken && !accountScoped) await adapter.authenticate(legacyToken);
      if (project) {
        if (!new URLSearchParams(location.hash.split('?')[1] ?? '').has('page'))
          setPage('workspace');
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
  const queueCancelled = latestQueueCancellation(v?.project.id, [
    state?.pendingRequest,
    ...(v?.requests || []),
  ]);
  const queuedRequest = [state?.pendingRequest, ...(v?.requests || [])].find(
    (request) =>
      request?.project === v?.project.id &&
      ['accepted', 'running'].includes(request?.state || '') &&
      request?.result?.queue,
  );
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
    writeProjectRoute(id);
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
  const create = async (goal: string) => {
    if (!canExecute) {
      setError(
        t(
          'The current role cannot start compute; ask the project owner or a team admin to execute.',
        ),
      );
      throw new Error(
        t(
          'The current role cannot start compute; ask the project owner or a team admin to execute.',
        ),
      );
    }
    if (needsFile) throw new Error(t('Select the attachment again before submitting.'));
    setError('');
    try {
      await adapter.createProject(goal.slice(0, 80), goal, file);
      fileDraft.complete('submitted', null);
      setFile(null);
      setNewDesign(false);
      setPage('workspace');
      closeProjects();
    } catch (reason) {
      setError((reason as Error).message);
      throw reason;
    }
  };
  useEffect(() => {
    if (state?.selectedProject) {
      if (readProjectRoute() !== state.selectedProject) writeProjectRoute(state.selectedProject);
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
    status: queueCancelled && p.id === v?.project.id ? 'paused' : statusOf(p.status),
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
          event.type === 'specialist.completed'
            ? t('Review response received')
            : t('Review in progress'),
      });
    }
  }
  for (const item of v?.specialists || []) observedSpecialists.set(item.role, item);
  const specialists = [...observedSpecialists.values()].map((s) => ({
    name: specialistNames[s.role] || s.role,
    role: s.description || t('Scientific review'),
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
        t('Execution state recorded by the backend'),
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
        1: t('Approve target'),
        2: t('Approve Site {{name}}', { name: rank || option?.label || '' }),
        3: t('Approve design'),
        4:
          (
            {
              PROMOTE_TO_SCALE: t('Promote pilot'),
              RUN_ANOTHER_PILOT: t('Prepare another pilot'),
              REVISE_DESIGN: t('Revise design'),
              REVISE_SITE: t('Revise site'),
              STOP: t('Stop campaign'),
            } as Record<string, string>
          )[option?.option_id || ''] || t('Approve pilot route'),
        5: t('Finalize candidate panel'),
      }[decision.gate]
    : '';
  const decide = async (input: GateInput) => {
    if (!canExecute)
      throw new Error(t('The current role cannot approve or revise scientific Gates.'));
    setError('');
    try {
      await adapter.decide(input);
      setModal(null);
    } catch (reason) {
      setError((reason as Error).message);
      throw reason;
    }
  };
  if (state?.connection === 'access-denied') return <WorkspaceAccessNotice message={state.error} refresh={() => adapter.refresh()}/>;
  return (
    <div
      className={`app live-workbench ${inWorkbench ? 'in-workbench' : ''} ${projectsOpen ? 'projects-expanded' : ''}`}
    >
      {access && !computeAvailable && (
        <p className="account-permission-note account-compute-note">
          {t(
            'This server has no scientific executor connected (account-management mode): browsing and collaborative editing are available; compute start, approval, and project conversations are temporarily unavailable.',
          )}
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
              <h1>{t('Please sign in again')}</h1>
              <p>
                {t(
                  'The current account session has expired or been revoked. A workspace token cannot replace account sign-in.',
                )}
              </p>
              <a className="primary-button" href="#/account">
                {t('Back to account and teams')} <ArrowRight size={15} />
              </a>
            </div>
          </main>
        ) : (
          <main className="landing">
            <div className="landing-center">
              <Brand />
              <h1>{t('Connect to your research workspace')}</h1>
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
                  {t('Access token')}
                  <input
                    type="password"
                    autoComplete="off"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                </label>
                <button className="primary-button">
                  {t('Connect')}
                  <ArrowRight size={15} />
                </button>
              </form>
            </div>
          </main>
        )
      ) : !state || state.connection === 'loading' ? (
        <div className="app-loading">
          <Brand />
          <p>{t('Opening your research workspace…')}</p>
        </div>
      ) : page === 'projects' ? (
        <>
          <ProjectsPage
            mode="live"
            draftKey={DRAFT_KEYS.scoped(scopeId, 'pro', 'projects', 'query')}
            snapshot={{ projects }}
            canCreate={canExecute}
            createDisabledReason={
              access
                ? access.role === 'observer'
                  ? t(
                      'Administrator read-only access: you cannot create projects, approve Gates, or start compute.',
                    )
                  : !computeAvailable
                    ? t(
                        'This server has no scientific executor connected (account-management mode): creating projects is temporarily unavailable; team draft collaboration remains available.',
                      )
                    : t(
                        'Team members cannot start compute; collaborate on team drafts and let a team admin create the project.',
                      )
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
                    setRenameOriginal(project.title);
                    setRenamingProject(project.id);
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
                {t('Previous')}
              </button>
              <button
                disabled={state.projects.offset + 20 >= state.projects.total}
                onClick={() => run(() => adapter.projectPage(state.projects.offset + 20))}
              >
                {t('Next')}
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
          draftKey={DRAFT_KEYS.scoped(scopeId, 'pro', 'create', 'goal')}
          mode="live"
          snapshot={{
            started: !!state?.selectedProject,
            completed: !!completed,
            phase,
            project: {
              title: v?.project.title || 'your project',
              exampleGoal: t(
                'Design a VHH binder against hen egg-white lysozyme and prioritize a compact accessible epitope.',
              ),
            },
          }}
          newDesign={newDesign}
          focusInput={newDesign}
          onStart={create}
          canStart={canExecute && !state?.pending && !needsFile}
          onResume={() => setNewDesign(false)}
          attachment={
            <>
              <label
                className="attach-target"
                title={t('Optionally attach a target structure seed')}
              >
                <Paperclip size={15} />
                {file ? file.name : t('Attach target (optional)')}
                <input
                  aria-label={t('Target structure · PDB / mmCIF')}
                  type="file"
                  accept=".pdb,.cif,.mmcif"
                  onChange={(e) => {
                    const selectedFile = e.target.files?.[0] || null;
                    setFile(selectedFile);
                    fileDraft.setValue(
                      selectedFile ? { name: selectedFile.name, size: selectedFile.size } : null,
                    );
                  }}
                />
              </label>
              {needsFile && (
                <span role="status">
                  {t(
                    'Attachment {{name}} ({{size}} bytes) must be selected again after refresh.',
                    fileDraft.value!,
                  )}
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => fileDraft.setValue(null)}
                  >
                    {t('Remove attachment')}
                  </button>
                </span>
              )}
            </>
          }
        />
      ) : !v ? (
        <div className="app-loading">
          <Brand />
          <p>{t('Opening your research workspace…')}</p>
        </div>
      ) : (
        <div className="workspace">
          <header className="workspace-header">
            <button
              className="mobile-workflow icon-button"
              aria-label={t('Toggle workflow')}
              onClick={() => setWorkflowOpen((o) => !o)}
            >
              <PanelLeft size={18} />
            </button>
            <div className="project-breadcrumb">
              <span>{t('Agent Workspace')}</span>
              <ChevronRight size={13} />
              <select
                aria-label={t('Current project')}
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
                ? t('Reconnecting…')
                : answering
                  ? t('Answering…')
                  : t('Saved')}
            </span>
            <div className="header-actions">
              <DemoBadge mode="live" />
              <button className="header-button" onClick={() => run(() => adapter.refresh())}>
                <RefreshCw size={13} />
                {t('Refresh')}
              </button>
              <button
                ref={contextToggle}
                className="mobile-context icon-button"
                aria-label={t('Open scientific context')}
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
                key={v.project.id}
                draftKey={DRAFT_KEYS.scoped(scopeId, 'project', v.project.id, 'lab-order')}
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
                  draftKey={DRAFT_KEYS.scoped(scopeId, 'project', v.project.id, 'conversation')}
                  mode="live"
                  snapshot={{
                    messages: dialogue(v, t, queueCancelled),
                    completed: completed || stopped,
                    phase,
                    busy: !queueCancelled && v.project.status === 'running',
                  }}
                  viewedPhase={viewedPhase}
                  onFocus={focus}
                  onSkip={() => {}}
                  onRetry={(id) => run(() => adapter.retryRequest(id))}
                  disabled={state?.connection !== 'connected' || !canDiscuss}
                  sending={answering}
                  awaitingReview={!queueCancelled || Boolean(v.decision)}
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
                  draftKey={DRAFT_KEYS.scoped(scopeId, 'project', v.project.id, 'candidate-view')}
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
                {queuedRequest?.result?.queue && (
                  <section role="status" className="decision-bar">
                    <div className="decision-copy">
                      <strong>
                        {queuedRequest.result.queue.state === 'starting'
                          ? t('Starting executor')
                          : t('Waiting for execution resources')}
                      </strong>
                      <p>
                        {queuedRequest.result.queue.position != null
                          ? t('Queue position: {{position}}.', {
                              position: queuedRequest.result.queue.position,
                            })
                          : ''}
                        {t('Request saved; do not submit again.')}
                      </p>
                    </div>
                    {queuedRequest.result.queue.cancellable && (
                      <button
                        disabled={busy || !canEdit}
                        onClick={() => run(() => adapter.cancelRequest(queuedRequest.id))}
                      >
                        {t('Cancel queued request')}
                      </button>
                    )}
                  </section>
                )}
                <footer
                  className={`decision-bar ${completed ? 'completed' : ''}`}
                  role="region"
                  aria-label={
                    decision
                      ? t('Gate {{number}} decision', { number: decision.gate })
                      : t('Research status')
                  }
                >
                  <span className="decision-icon">
                    <Check size={17} />
                  </span>
                  <div className="decision-copy">
                    <strong>
                      {decision?.gate === 2
                        ? t('Continue with Site {{name}}?', {
                            name: rank || '',
                          })
                        : completed
                          ? t('Panel finalized')
                          : stopped
                            ? t('Campaign stopped')
                            : queueCancelled && !decision
                              ? t('Queue cancelled')
                              : v.lifecycle === 'failed'
                                ? t('Target research needs a retry')
                                : decision?.gate === 1
                                  ? t('Approve the automatically selected target?')
                                  : decision?.gate === 3
                                    ? t('Ready to start the pilot?')
                                    : decision
                                      ? t('Ready for your review')
                                      : t(stepTitles[v.project.phase] || 'Research in progress')}
                    </strong>
                    <span>
                      {queueCancelled && !decision
                        ? t(
                            'This request did not start computation; scientific evidence is retained.',
                          )
                        : v.project.validation_only
                          ? t('Validation only · not authorized for experiment')
                          : stopped
                            ? t(
                                'Scientific evidence is retained; no further computation is scheduled.',
                              )
                            : v.lifecycle === 'failed'
                              ? t('Verified evidence and recovery state were retained.')
                              : decision?.gate === 1
                                ? t('{{name}} is already selected. Change it only if needed.', {
                                    name: option?.label || t('The recommended structure and chain'),
                                  })
                                : decision
                                  ? t('Review the scientific context before continuing.')
                                  : t(
                                      'Your conversations, decisions and results stay with this project.',
                                    )}
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
                          {t('Compare')}
                        </button>
                      )}
                      <button
                        className="secondary-button"
                        disabled={busy || !canExecute}
                        onClick={() => setModal('edit')}
                      >
                        <PencilLine size={14} />
                        {decision.gate === 1
                          ? t('Change structure')
                          : decision.gate === 4
                            ? t('Revise')
                            : t('Edit')}
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
                                decide({
                                  action: 'approve',
                                  selected_option_id: option.option_id,
                                }),
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
                      {t('Retry Target Intelligence')}
                      <ArrowRight size={15} />
                    </button>
                  ) : v.capabilities.resume ? (
                    <button
                      className="primary-button"
                      disabled={busy || !canExecute}
                      onClick={() => run(() => adapter.resume())}
                    >
                      {t('Continue research')}
                      <ArrowRight size={15} />
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
                      {t('Open simulated Lab Order')}
                      <ArrowRight size={15} />
                    </button>
                  ) : null}
                </footer>
              </div>
            )}
            {tasksOpen && (
              <aside className="task-inspector" aria-label={t('Agent Tasks')} aria-modal="true">
                <header>
                  <div>
                    <span className="eyebrow">{t('LIVE EXECUTION')}</span>
                    <h2>{t('Agent Tasks')}</h2>
                    <p>
                      {
                        agentTasks.filter((task) => ['complete', 'completed'].includes(task.status))
                          .length
                      }{' '}
                      {t('of')} {agentTasks.length} {t('completed')}
                    </p>
                  </div>
                  <button
                    className="icon-button"
                    aria-label={t('Close Agent Tasks')}
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
                        <span>{t(task.status[0].toUpperCase() + task.status.slice(1))}</span>
                      </article>
                    ))
                  ) : (
                    <div className="task-inspector-empty">
                      <ClipboardList size={22} />
                      <p>{t('No task authority has been produced yet.')}</p>
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
          <button aria-label={t('Dismiss message')} onClick={() => setError('')}>
            <X size={14} />
          </button>
        </div>
      )}
      {modal === 'edit' && decision && (
        <Modal title={t('Review your decision')} onClose={() => setModal(null)}>
          <GateReview
            key={decision.id}
            draftKey={DRAFT_KEYS.scoped(scopeId, 'project', v!.project.id, 'gate', decision.id)}
            decision={decision}
            selectedOptionId={option?.option_id}
            busy={busy || !v?.capabilities.decide || !canExecute}
            onSelect={setSite}
            onSubmit={decide}
          />
        </Modal>
      )}
      {modal === 'rename' && (
        <Modal title={t('Rename project')} onClose={() => setModal(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canEdit) {
                setError(t('This is read-only access.'));
                return;
              }
              run(async () => {
                await adapter.renameProject(renamingProject, projectName);
                renameDraft.complete('saved');
                setModal(null);
              });
            }}
          >
            <label className="form-label">
              {t('Project name')}
              <input
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                maxLength={80}
                required
              />
            </label>
            <DraftStatus status={renameDraft.status} />
            <div className="modal-actions">
              <button type="button" className="secondary-button" onClick={() => setModal(null)}>
                {t('Cancel')}
              </button>
              <button className="primary-button" disabled={!projectName.trim()}>
                {t('Save name')}
                <ArrowRight size={14} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {modal === 'help' && (
        <Modal title={t('About EasyDesign')} onClose={() => setModal(null)}>
          <p>
            {t(
              'A guided research workspace. Ask Design Scientist about the evidence, compare options in Scientific Context, and use the decision bar when you are ready to continue.',
            )}
          </p>
        </Modal>
      )}
      {modal === 'handoff' && (
        <Modal title={t('Panel finalized')} onClose={() => setModal(null)}>
          <p>
            {t(
              'Your final panel and its evidence are saved. No laboratory order has been submitted.',
            )}
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
  const { t } = useTranslation('pro');
  const v = state?.snapshot;
  const [status, setStatus] = useState('all');
  const jobs = (v?.jobs || []).filter((j) => status === 'all' || status === j.status);
  return (
    <main className="platform-page" aria-label={t('Compute & Queue')}>
      <header className="platform-header">
        <span>{t('A clear view of the work in progress.')}</span>
        <DemoBadge mode="live" />
      </header>
      <div className="platform-content">
        <div className="platform-title-row">
          <div>
            <span className="eyebrow">{t('RESOURCES & ACTIVITY')}</span>
            <h1>{t('Compute & Queue')}</h1>
            <p>{t('Follow your runs across projects, from pilot to scale.')}</p>
          </div>
        </div>
        <LiveResources />
        <section className="compute-connection" aria-label={t('Project activity connection')}>
          <span className="compute-icon">
            <Cpu size={25} />
          </span>
          <div>
            <h2>{v ? v.project.title : t('Your research workspace')}</h2>
            <p>
              {v?.project.validation_only
                ? t('Validation only · not authorized for experiment')
                : t('Execution status from your research project.')}
            </p>
          </div>
          <span className="connection-label">
            {state?.connection === 'connected' ? t('Connected') : t('Reconnecting')}
          </span>
        </section>
        <div className="run-section-heading">
          <div>
            <h2>{t('Research runs')}</h2>
            <p>{t('Pilot and Scale activity from the selected project.')}</p>
          </div>
          <span className="count-label">{v?.jobs.length || 0}</span>
        </div>
        <div className="run-filters">
          <label>
            {t('Project')}
            <select
              aria-label={t('Filter runs by project')}
              value={v?.project.id || ''}
              onChange={(e) => onSelect(e.target.value)}
            >
              <option value="" disabled>
                {t('Choose a project')}
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
            {t('Status')}
            <select
              aria-label={t('Filter runs by status')}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">{t('All statuses')}</option>
              {[...new Set(v?.jobs.map((j) => j.status))].map((s) => (
                <option key={s} value={s}>
                  {t(s[0].toUpperCase() + s.slice(1))}
                </option>
              ))}
            </select>
          </label>
        </div>
        {jobs.length ? (
          <div className="runs-table-wrap">
            <table className="runs-table">
              <thead>
                <tr>
                  <th>{t('Run / project')}</th>
                  <th>{t('Status')}</th>
                  <th>{t('Recovery')}</th>
                  <th>
                    <span className="sr-only">{t('Open')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id}>
                    <td>
                      <strong>
                        {t('{{phase}} exploration', {
                          phase: t(j.phase[0].toUpperCase() + j.phase.slice(1)),
                        })}
                      </strong>
                      <span>{v?.project.title}</span>
                    </td>
                    <td>
                      <span className="project-status">
                        <i />
                        {t(j.status[0].toUpperCase() + j.status.slice(1))}
                      </span>
                    </td>
                    <td>{j.resumable ? t('Available to resume') : '—'}</td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={t('Open {{phase}} project {{name}}', {
                          phase: t(j.phase[0].toUpperCase() + j.phase.slice(1)),
                          name: v?.project.title || '',
                        })}
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
            <h2>{t('Room for your next run')}</h2>
            <p>{t('Once you approve a design in Agent Workspace, its pilot will appear here.')}</p>
          </div>
        )}
        <p className="platform-footnote">{t('Approvals remain in Agent Workspace.')}</p>
      </div>
    </main>
  );
}
