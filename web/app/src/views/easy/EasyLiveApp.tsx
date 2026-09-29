import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowRight,
  Check,
  ChevronDown,
  FileUp,
  FlaskConical,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { Brand } from '../../components/Brand';
import { emptyInput, INPUT_TYPES, STEPS, type EasyInput, type InputType } from './contracts';
import { fileTypes, inputLabel, readInputFile } from './inputs';
import { productGoal, validateLiveInput } from './live-input';
import { latestQueueCancellation, projectListStatus } from './queue-presentation';
import { RabbitMascot } from './RabbitMascot';
import { EasyStructureViewer } from './EasyStructureViewer';
import {
  awaitingDecisionRecovery,
  summarizeEasyActivity,
  summarizeGoal,
} from './live-presentation';
import type { EasyProductPort } from './EasyProductAdapter';
import { readProjectRoute, stripLegacySearch, workspaceHref, writeProjectRoute } from './routeParams';
import { draftRecovery, DRAFT_KEYS } from '../../data/draftRecovery';
import { scopeProductUrl, surfaceRights } from '../../shared/account-client';
import type {
  GateInput,
  LabOrderDraftInput,
  LabOrderView,
  LiveState,
  ProductSnapshot,
} from './product-contracts';

const PHASE_INDEX: Record<string, number> = {
  target: 0,
  site: 1,
  design: 2,
  pilot: 3,
  scale: 4,
  candidates: 5,
  handoff: 5,
};

function activeIndex(snapshot: ProductSnapshot | null) {
  if (!snapshot) return 0;
  return PHASE_INDEX[snapshot.project.phase] ?? 0;
}

export function canAutoContinue(
  snapshot: ProductSnapshot | null,
  pending: boolean,
  requestState?: string,
) {
  if (!snapshot || !snapshot.capabilities.auto_continue || !snapshot.capabilities.resume)
    return false;
  // An incomplete execution may have been recovered by a newer durable worker.
  // Reconciliation only attaches that verified successor receipt; it does not
  // retry scientific compute.  Allow this bounded action to run automatically
  // while keeping all other incomplete states stopped for explicit review.
  const safeStatus =
    snapshot.project.status === 'available' ||
    (snapshot.project.status === 'incomplete' &&
      snapshot.current_action.stage.endsWith('-reconcile'));
  return !pending && !['running', 'accepted'].includes(requestState || '') && safeStatus;
}

function stageStatus(snapshot: ProductSnapshot | null, index: number) {
  if (!snapshot) return 'waiting';
  const phase = STEPS[index].toLowerCase();
  const row = snapshot.workflow.find((item) => item.id === phase);
  return row?.status || (index < activeIndex(snapshot) ? 'complete' : 'waiting');
}

const PIPELINE_STEPS = [
  ['boltzgen-initialize', 'Initialize'],
  ['boltzgen-generate', 'Generate'],
  ['boltzgen-inverse-fold', 'Inverse fold'],
  ['boltzgen-refold', 'Refold'],
  ['boltzgen-analysis', 'Analyze'],
  ['boltzgen-filter', 'Filter'],
  ['native-filter', 'Independent prediction / native filter'],
] as const;

function ExecutionProgress({ snapshot }: { snapshot: ProductSnapshot }) {
  const { t } = useTranslation('easy');
  const job =
    snapshot.jobs.find((item) => item.phase === snapshot.project.phase && item.progress) ||
    snapshot.jobs.find((item) => item.progress);
  const progress = job?.progress;
  if (!progress) return null;
  const native = progress.stage_id.startsWith('05-') || progress.stage_id.startsWith('07-');
  const current = native ? 'native-filter' : progress.substage;
  const currentIndex = PIPELINE_STEPS.findIndex(([id]) => id === current);
  const overall = progress.total
    ? Math.min(100, Math.round((progress.completed / progress.total) * 100))
    : 0;
  const substage =
    progress.substage_total && progress.substage_completed !== null
      ? `${progress.substage_completed} / ${progress.substage_total}`
      : null;
  return (
    <section className="easy-execution-progress" aria-label={t('Live execution progress')}>
      <div className="easy-execution-title">
        <div>
          <span>REAL EXECUTION</span>
          <strong>
            {native ? t('Independent structure prediction and native filter') : progress.substage_label || 'BoltzGen'}
          </strong>
        </div>
        <b>
          {progress.total
            ? t('{{completed}} / {{total}} candidates', {
                completed: progress.completed,
                total: progress.total,
              })
            : t('Waiting for resources')}
        </b>
      </div>
      <div
        className="easy-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={progress.total || 1}
        aria-valuenow={progress.completed}
      >
        <span style={{ width: `${overall}%` }} />
      </div>
      <div className="easy-pipeline-steps">
        {PIPELINE_STEPS.map(([id, label], stepIndex) => {
          const done = native || (currentIndex >= 0 && stepIndex < currentIndex);
          const active = id === current;
          return (
            <div key={id} className={active ? 'active' : done ? 'done' : ''}>
              <span>{done ? <Check size={11} /> : stepIndex + 1}</span>
              <small>{label}</small>
              {active && substage && <em>{substage}</em>}
            </div>
          );
        })}
      </div>
      <p>
        {t('{{completed}} / {{total}} strategy tasks complete', {
          completed: progress.completed_tasks,
          total: progress.total_tasks,
        })}
        {progress.running_tasks ? t(', {{count}} running', { count: progress.running_tasks }) : ''}
      </p>
    </section>
  );
}

function HistoricalStagePanel({
  snapshot,
  stageIndex,
  onReturn,
}: {
  snapshot: ProductSnapshot;
  stageIndex: number;
  onReturn: () => void;
}) {
  const { t } = useTranslation('easy');
  const context = snapshot.scientific_context;
  const workflow = snapshot.workflow.find((item) => item.id === STEPS[stageIndex].toLowerCase());
  const rows: [string, string | number][] = [];
  if (stageIndex === 0) {
    rows.push(
      ['Target', context.target_id || 'Verified target'],
      ['Sequence length', context.sequence_length || '—'],
      ['Chains', context.chains?.join(', ') || '—'],
      ['Structure', context.structure?.label || '—'],
    );
  } else if (stageIndex === 1) {
    rows.push(
      ['Candidate sites', context.sites.length],
      ['Approved site', context.approved_site?.selected_rank || 'Not recorded'],
    );
    const approved = context.sites.find(
      (site) => site.id === context.approved_site?.selected_candidate_id,
    );
    if (approved) rows.push(['Hotspots', approved.design_labels.join(', ')]);
  } else if (stageIndex === 2) {
    rows.push(
      ['Design arms', context.arms.length],
      ['Design approval', context.design_approved ? 'Recorded' : 'Not recorded'],
    );
  } else if (stageIndex === 3 || stageIndex === 4) {
    const phase = stageIndex === 3 ? 'pilot' : 'scale';
    const job = snapshot.jobs.find((item) => item.phase === phase);
    rows.push(['Execution status', job?.status || 'Complete']);
    if (job?.progress)
      rows.push(
        ['Candidates', `${job.progress.completed} / ${job.progress.total}`],
        ['Strategy tasks', `${job.progress.completed_tasks} / ${job.progress.total_tasks}`],
      );
  } else {
    rows.push(
      ['Candidate total', snapshot.candidates.total],
      ['Native pass', snapshot.candidates.counts.pass || 0],
      ['Workflow state', snapshot.current_action.stage],
    );
  }
  return (
    <section className="easy-live-history-card" aria-label={`${STEPS[stageIndex]} history`}>
      <div className="easy-live-kicker">HISTORICAL STAGE · READ ONLY</div>
      <h3>{t('{{stage}} stage record', { stage: STEPS[stageIndex] })}</h3>
      <p>
        {t('{{count}} steps recorded.', {
          count: workflow?.subtasks?.filter((item) => item.status === 'complete').length || 0,
        })}
      </p>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <button className="easy-outline" onClick={onReturn}>
        {t('Back to current stage')}
      </button>
    </section>
  );
}

function GatePanel({
  snapshot,
  busy,
  onDecide,
  canDecide = true,
}: {
  snapshot: ProductSnapshot;
  busy: boolean;
  onDecide: (input: GateInput) => Promise<void>;
  canDecide?: boolean;
}) {
  const decision = snapshot.decision!;
  const { t } = useTranslation('easy');
  const [selected, setSelected] = useState(decision.default_option_id);
  const [showRevise, setShowRevise] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    setSelected(decision.default_option_id);
    setShowRevise(false);
    setInstruction('');
    setError('');
  }, [decision.id, decision.default_option_id]);
  const option = decision.options.find((item) => item.option_id === selected);
  const visibleOptions =
    decision.gate === 1
      ? decision.options.filter((item) => item.option_id === decision.default_option_id)
      : decision.options;
  const approveAction = option?.actions.includes('approve')
    ? 'approve'
    : option?.actions.includes('override')
      ? 'override'
      : null;
  async function submit(input: GateInput) {
    if (!canDecide) return;
    setError('');
    try {
      await onDecide(input);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  return (
    <section className="easy-live-gate" aria-label={`Gate ${decision.gate}`}>
      <div className="easy-live-kicker">
        <ShieldCheck size={14} /> SCIENTIST GATE {decision.gate}
      </div>
      <h3>{decision.gate === 1 ? t('Confirm the automatically recommended target structure') : decision.question}</h3>
      <p>{decision.action_summary}</p>
      <div className="easy-live-options" role="radiogroup" aria-label="Scientific options">
        {visibleOptions.map((item) => (
          <label key={item.option_id} className={selected === item.option_id ? 'selected' : ''}>
            <input
              type="radio"
              name="easy-live-option"
              checked={selected === item.option_id}
              disabled={!item.eligible || busy}
              onChange={() => setSelected(item.option_id)}
            />
            <span>
              <strong>
                {item.rank ? `Site ${item.rank} · ` : ''}
                {item.label || item.option_id}
              </strong>
              <small>{item.description || (item.eligible ? t('Selectable') : t('Blocked'))}</small>
              {item.design_labels && <em>Hotspot: {item.design_labels.join(', ')}</em>}
            </span>
          </label>
        ))}
      </div>
      {(decision.warnings.length > 0 || decision.limitations.length > 0) && (
        <details>
          <summary>{t('Risks and limitations ({{count}})', { count: decision.warnings.length + decision.limitations.length })}</summary>
          <ul>
            {[...decision.warnings, ...decision.limitations].map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </details>
      )}
      {showRevise && (
        <textarea
          aria-label="Revision instruction"
          value={instruction}
          maxLength={1500}
          placeholder={t('Describe what you want the science Agent to change')}
          onChange={(event) => setInstruction(event.target.value)}
        />
      )}
      {error && <p className="easy-error">{error}</p>}
      <div className="easy-live-gate-actions">
        <button
          className="easy-primary"
          disabled={!approveAction || busy || !canDecide}
          onClick={() =>
            void submit({
              action: approveAction || 'approve',
              selected_option_id: selected,
              ...(approveAction === 'override'
                ? {
                    reason: 'Scientist explicitly accepts the displayed discouraged option.',
                    acknowledgement: decision.warnings.join(' ').slice(0, 1500) || 'Acknowledged',
                  }
                : {}),
            })
          }
        >
          {busy ? <LoaderCircle className="easy-spin" size={15} /> : <Check size={15} />}
          {approveAction === 'override' ? t('Confirm and override') : t('Approve and continue')}
          <ArrowRight size={15} />
        </button>
        <button
          className="easy-outline"
          disabled={busy || !canDecide}
          onClick={() => setShowRevise((value) => !value)}
        >
          {t('Revise')}
        </button>
        {showRevise && (
          <button
            className="easy-outline"
            disabled={!instruction.trim() || busy || !canDecide}
            onClick={() =>
              void submit({
                action: 'revise',
                selected_option_id: selected,
                instruction,
                revision_target: decision.revision_targets[0],
              })
            }
          >
            {t('Submit revision')}
          </button>
        )}
      </div>
    </section>
  );
}

function SimulatedOrder({
  order,
  adapter,
  onUpdate,
}: {
  order: LabOrderView;
  adapter: EasyProductPort;
  onUpdate: (value: LabOrderView) => void;
}) {
  const { t } = useTranslation('easy');
  const [selected, setSelected] = useState(() => order.candidates.map((item) => item.id));
  const [amount, setAmount] = useState('1 mg per sample');
  const [format, setFormat] = useState<'VHH' | 'VHH-Fc'>('VHH');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(operation: () => Promise<LabOrderView>) {
    setBusy(true);
    setError('');
    try {
      onUpdate(await operation());
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const draft: LabOrderDraftInput = {
    schema_version: '1',
    candidate_ids: selected,
    requirements: {
      format,
      amount,
      host: 'E. coli',
      buffer: 'PBS',
      profile: 'simulation-lab',
      preferred_date: '',
      purchase_order: '',
      sds_purity: '',
      sec_purity: '',
      endotoxin: '',
      concentration: '',
      notes: 'Easy UI full-flow acceptance; simulation only.',
    },
    reviewed: true,
  };
  return (
    <section className="easy-live-order">
      <div className="easy-live-kicker">
        <FlaskConical size={14} /> GATE 5 · SIMULATED LAB ORDER
      </div>
      <h3>{order.receipt ? t('Simulated order receipt generated') : t('Simulated lab order')}</h3>
      <p>{order.disclaimer}</p>
      <div className="easy-live-order-candidates">
        {order.candidates.map((item) => (
          <label key={item.id}>
            <input
              type="checkbox"
              checked={selected.includes(item.id)}
              disabled={!!order.receipt || busy}
              onChange={(event) =>
                setSelected((values) =>
                  event.target.checked
                    ? [...values, item.id]
                    : values.filter((id) => id !== item.id),
                )
              }
            />
            <span>
              <strong>{item.id}</strong>
              <small>
                {item.selection_class} · {item.sequence_length} aa · {t('Full sequence verified')}
              </small>
            </span>
          </label>
        ))}
      </div>
      {!order.receipt && (
        <div className="easy-live-order-fields">
          <label>
            {t('Construct format')}
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value as typeof format)}
            >
              <option value="VHH">VHH</option>
              <option value="VHH-Fc">VHH-Fc</option>
            </select>
          </label>
          <label>
            {t('Amount per sample')}
            <input
              value={amount}
              maxLength={160}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
        </div>
      )}
      {order.quote && !order.receipt && (
        <p className="easy-live-quote">
          {t('Non-binding simulated quote: {{total}} {{currency}}', {
            total: String(order.quote.illustrative_total),
            currency: String(order.quote.currency),
          })}
        </p>
      )}
      {order.receipt && (
        <dl className="easy-live-receipt">
          <div>
            <dt>{t('Simulated order')}</dt>
            <dd>{String(order.receipt.order_id)}</dd>
          </div>
          <div>
            <dt>{t('Status')}</dt>
            <dd>{String(order.receipt.status)}</dd>
          </div>
          <div>
            <dt>{t('Real external request')}</dt>
            <dd>{t('Not sent')}</dd>
          </div>
        </dl>
      )}
      {error && <p className="easy-error">{error}</p>}
      {!order.receipt && (
        <div className="easy-live-gate-actions">
          {!order.draft && (
            <button
              className="easy-primary"
              disabled={!selected.length || !amount.trim() || busy}
              onClick={() => void run(() => adapter.saveLabOrder(draft))}
            >
              {t('Save simulated order draft')}
            </button>
          )}
          {order.draft && !order.quote && (
            <button
              className="easy-primary"
              disabled={busy}
              onClick={() => void run(() => adapter.quoteLabOrder())}
            >
              {t('Generate simulated quote')}
            </button>
          )}
          {order.quote && (
            <button
              className="easy-primary"
              disabled={busy}
              onClick={() => void run(() => adapter.submitLabOrder())}
            >
              {t('Confirm simulation-only and submit')}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function EasyLiveApp({
  adapter,
  access,
  computeAvailable = true,
}: {
  adapter: EasyProductPort;
  access?: { id: string; can_edit: boolean; can_execute: boolean; role: string };
  computeAvailable?: boolean;
}) {
  const { t, i18n } = useTranslation('easy');
  const locale = i18n.language === 'en' ? ('en' as const) : ('zh' as const);
  const { canExecute } = surfaceRights(access, computeAvailable);
  const [state, setState] = useState<LiveState | null>(null);
  const [input, setInput] = useState<EasyInput>(() => emptyInput());
  const [file, setFile] = useState<File | null>(null);
  const draftRestored = useRef(false);
  // 设计输入实时暂存（仅创建表单）。文件本身不可序列化，只存元数据，
  // 恢复时提示重新选择 —— 与执行指南的存储策略表一致。
  useEffect(() => {
    if (!draftRestored.current || readProjectRoute() !== null) return;
    draftRecovery.saveLocal(DRAFT_KEYS.projectCreate, {
      input,
      file: file ? { name: file.name, size: file.size } : null,
    });
  }, [input, file]);
  const [token, setToken] = useState('');
  const [selectedSite, setSelectedSite] = useState<string | undefined>();
  const [viewedIndex, setViewedIndex] = useState<number | null>(null);
  const [order, setOrder] = useState<LabOrderView | null>(null);
  const [error, setError] = useState('');
  const autoContinuation = useRef<string | null>(null);
  useEffect(() => {
    const unsubscribe = adapter.subscribe((event) => setState(event.snapshot));
    void (async () => {
      // 旧单机 token 静默摘除：账号会话是唯一身份，绝不能打印或发送。
      stripLegacySearch();
      const requested = readProjectRoute();
      if (requested) {
        // A shared/deep link must not wait for every historical project card to
        // project before the requested scientific workspace becomes visible.
        await Promise.all([adapter.selectProject(requested), adapter.load()]);
      } else {
        const loaded = await adapter.load();
        setState(loaded);
        if (readProjectRoute() === null) {
          const saved = draftRecovery.recover(DRAFT_KEYS.projectCreate);
          const payload = saved.data as
            | { input?: Partial<EasyInput>; file?: { name: string; size: number } | null }
            | null;
          if (saved.hasLocal && payload?.input) {
            setInput((current) => ({ ...current, ...payload.input }));
          }
        }
      }
      draftRestored.current = true;
    })().catch((reason) => setError((reason as Error).message));
    return () => {
      unsubscribe();
      adapter.dispose();
    };
  }, [adapter]);
  const snapshot = state?.snapshot || null;
  const queueCancelled = latestQueueCancellation(snapshot?.project.id, [
    state?.pendingRequest,
    ...(snapshot?.requests || []),
  ]);
  const queuedRequest = [state?.pendingRequest, ...(snapshot?.requests || [])].find(
    (request) =>
      request?.project === snapshot?.project.id &&
      ['accepted', 'running'].includes(request?.state || '') &&
      request?.result?.queue,
  );
  const currentProject = snapshot?.project.id || readProjectRoute();
  const professionalUrl = workspaceHref(access?.id ?? '', 'pro', currentProject);
  const autoContinuationEligible =
    !queueCancelled && canExecute && canAutoContinue(snapshot, false);
  const executionBlocked =
    snapshot !== null && ['blocked', 'incomplete'].includes(snapshot.project.status);
  const failedCreate = !snapshot?.capabilities.resume
    ? snapshot?.requests.find(
        (request) => request.kind === 'create' && ['failed', 'interrupted'].includes(request.state),
      )
    : undefined;
  const completed = snapshot?.current_action.stage === 'handoff-complete';
  const stopped = snapshot?.project.status === 'stopped';
  useEffect(() => {
    if (
      !canExecute || // team members, read-only observers and compute-off surfaces never auto-resume
      !snapshot ||
      !canAutoContinue(snapshot, Boolean(state?.pending), state?.pendingRequest?.state)
    )
      return;
    const key = `${snapshot.project.id}:${snapshot.revision}:${snapshot.current_action.id}`;
    if (autoContinuation.current === key) return;
    autoContinuation.current = key;
    void adapter.resume().catch((reason) => setError((reason as Error).message));
  }, [adapter, canExecute, snapshot, state?.pending, state?.pendingRequest?.state]);
  useEffect(() => {
    const defaultSite = snapshot?.scientific_context.approved_site?.selected_candidate_id;
    setSelectedSite(defaultSite || snapshot?.decision?.default_option_id || undefined);
    setOrder(snapshot?.lab_order || null);
  }, [snapshot?.revision]);
  useEffect(() => {
    setViewedIndex(null);
  }, [snapshot?.project.id]);
  const issue = validateLiveInput(input);
  const index = activeIndex(snapshot);
  const shownIndex = viewedIndex ?? index;
  const active = Boolean(
    state?.pending ||
      (!queueCancelled &&
        (snapshot?.project.status === 'running' || snapshot?.project.status === 'incomplete')),
  );
  const candidateArtifact = state?.selectedCandidate?.artifacts.find((item) =>
    ['pdb', 'cif', 'mmcif'].includes(item.format),
  );
  const artifact =
    (shownIndex >= 3 ? candidateArtifact : null) || snapshot?.scientific_context.structure || null;
  const roles = shownIndex >= 3 ? state?.selectedCandidate?.structure_roles || {} : {};
  const technicalActivity = (snapshot?.recent_activity || [])
    .filter((item) => item.visible !== false && !(completed && item.type === 'gate.awaiting'))
    .slice(-8)
    .reverse();
  const activity =
    queueCancelled && !snapshot?.decision
      ? [
          {
            id: 'queue-cancelled',
            title: t('This request was not executed'),
            summary: t('Queue cancelled; existing scientific evidence is retained.'),
            status: 'waiting',
          },
        ]
      : snapshot
        ? summarizeEasyActivity(snapshot)
        : [];
  const projects = state?.projects.items || [];
  const gateOption = snapshot?.decision?.options.find((item) => item.option_id === selectedSite);
  const visibleSite = gateOption?.rank
    ? snapshot?.scientific_context.sites.find((site) => site.rank === gateOption.rank)
    : selectedSite;
  const visibleSiteId = typeof visibleSite === 'string' ? visibleSite : visibleSite?.id;
  const candidates = state?.candidates.items || [];

  async function start() {
    if (issue || !state || !canExecute) return;
    setError('');
    try {
      const goal = productGoal(input);
      await adapter.createTypedProject(
        input.name.trim() || inputLabel(input).slice(0, 80),
        goal,
        input,
        file,
      );
      const created = await adapter.load();
      if (created.selectedProject) {
        writeProjectRoute(created.selectedProject);
        draftRecovery.clearLocal(DRAFT_KEYS.projectCreate);
      }
      setFile(null);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  function newDesign() {
    adapter.clearProject();
    draftRecovery.clearLocal(DRAFT_KEYS.projectCreate);
    setOrder(null);
    setSelectedSite(undefined);
    setViewedIndex(null);
    autoContinuation.current = null;
    writeProjectRoute(null);
    document.getElementById('design')?.scrollIntoView({ behavior: 'smooth' });
  }

  async function openProject(id: string) {
    await adapter.selectProject(id);
    writeProjectRoute(id);
    document.getElementById('current-design')?.scrollIntoView({ behavior: 'smooth' });
  }

  if (!state)
    return (
      <div className="easy-live-loading">
        <LoaderCircle className="easy-spin" /> {t('Connecting to EasyDesign…')}
      </div>
    );
  if (state.connection === 'authentication-required')
    return access ? (
      <main className="easy-live-login">
        <Brand />
        <h1>{t('Please sign in again')}</h1>
        <p>{t('The current account session has expired or been revoked; returning to the account page.')}</p>
        <a className="easy-primary" href="#/account">
          {t('Back to account and teams')}
        </a>
        {error && <p className="easy-error">{error}</p>}
      </main>
    ) : (
      <main className="easy-live-login">
        <Brand />
        <h1>{t('Connect to the local research workspace')}</h1>
        <label>
          Access token
          <input value={token} onChange={(event) => setToken(event.target.value)} />
        </label>
        <button
          className="easy-primary"
          onClick={() =>
            void adapter
              .authenticate(token)
              .then(() => adapter.refresh())
              .catch((reason) => setError((reason as Error).message))
          }
        >
          {t('Connect')} <ArrowRight size={16} />
        </button>
        {error && <p className="easy-error">{error}</p>}
      </main>
    );

  return (
    <div className="easy-app easy-live-app">
      <header className="easy-header">
        <a className="easy-brand" href={workspaceHref(access?.id ?? '', 'easy')}>
          <Brand /> <span className="easy-edition">EASY · LIVE</span>
        </a>
        <nav>
          <a
            href="#design"
            onClick={(event) => {
              event.preventDefault();
              newDesign();
            }}
          >
            {t('Create new design')}
          </a>
          {snapshot && <a href="#current-design" onClick={(event) => {
            event.preventDefault();
            document.getElementById('current-design')?.scrollIntoView({ behavior: 'smooth' });
          }}>{t('Current task')}</a>}
          <a href="#my-designs" onClick={(event) => {
            event.preventDefault();
            document.getElementById('my-designs')?.scrollIntoView({ behavior: 'smooth' });
          }}>{t('My designs')}</a>
        </nav>
        <div className="easy-header-end">
          <span className={`easy-live-connection ${state.connection}`}>● {state.connection}</span>
          <button className="easy-help" onClick={() => void adapter.refresh()}>
            <RefreshCw size={14} /> {t('Refresh')}
          </button>
          <a className="easy-pro-link" href={professionalUrl}>
            {t('Open the Pro version')}
          </a>
        </div>
      </header>

      <main className="easy-main">
        {!canExecute && (
          <p className="account-permission-note">
            {access?.role === 'observer'
              ? t('Administrator read-only view: you cannot modify projects of others, approve Gates, or start compute.')
              : !computeAvailable
                ? t('This server has no scientific executor connected (account-management mode): browsing and collaborative editing are available; compute start and approval are temporarily unavailable.')
                : t('Team collaborator: you can view and discuss; scientific approval and compute start are handled by team admins.')}
          </p>
        )}
        <section className="easy-intro">
          <h1>
            {t('Start from one sentence')}<span>{t('Real design')}</span>
          </h1>
          <p>{t('Same frozen backend, same Scientist Gates; only the operation is simplified here, never the scientific boundaries.')}</p>
        </section>
        <section className="easy-input-card" id="design">
          <div className="easy-section-top">
            <span className="easy-demo-pill easy-live-pill">
              <Sparkles size={12} /> LIVE BACKEND
            </span>
          </div>
          <div className="easy-input-row">
            <label className="easy-type-label">
              <span>{t('Input type')}</span>
              <div className="easy-select-wrap">
                <select
                  value={input.type}
                  onChange={(event) => {
                    setInput({ ...emptyInput(), type: event.target.value as InputType });
                    setFile(null);
                  }}
                >
                  {INPUT_TYPES.filter((item) => !['pse', 'bundle'].includes(item.id)).map(
                    (item) => (
                      <option key={item.id} value={item.id}>
                        {t(item.label)}
                      </option>
                    ),
                  )}
                </select>
                <ChevronDown size={14} />
              </div>
            </label>
            <div className="easy-input-body">
              {input.type === 'structure' ? (
                <label className="easy-live-upload">
                  <FileUp size={20} />
                  <span>{file?.name || t('Upload PDB / mmCIF')}</span>
                  <input
                    type="file"
                    accept={fileTypes.structure}
                    onChange={(event) => {
                      const next = event.target.files?.[0];
                      if (!next) return;
                      void readInputFile('structure', next)
                        .then((value) => {
                          setFile(next);
                          setInput((current) => ({ ...current, ...value }));
                        })
                        .catch((reason) => setError((reason as Error).message));
                    }}
                  />
                </label>
              ) : input.type === 'description' || input.type === 'sequence' ? (
                <>
                  <textarea
                    rows={3}
                    value={input.text}
                    placeholder={
                      input.type === 'sequence'
                        ? '>target\nACDEFGHIKLMNPQRSTVWY'
                        : t('e.g. Design an extracellular VHH binder that inhibits receptor signaling for human NK2R')
                    }
                    onChange={(event) => {
                      setFile(null);
                      setInput({ ...input, text: event.target.value, file: null });
                    }}
                  />
                  {input.type === 'sequence' && (
                    <label className="easy-live-upload">
                      <FileUp size={20} />
                      <span>{file?.name || t('or upload a FASTA file')}</span>
                      <input
                        type="file"
                        accept={fileTypes.sequence}
                        onChange={(event) => {
                          const next = event.target.files?.[0];
                          if (!next) return;
                          void readInputFile('sequence', next)
                            .then((value) => {
                              setFile(next);
                              setInput((current) => ({ ...current, ...value }));
                            })
                            .catch((reason) => setError((reason as Error).message));
                        }}
                      />
                    </label>
                  )}
                </>
              ) : (
                <>
                  <input
                    value={input.text}
                    placeholder={t('Target name or database ID')}
                    onChange={(event) => setInput({ ...input, text: event.target.value })}
                  />
                  {input.type === 'protein-name' && (
                    <input
                      value={input.species}
                      placeholder={t('Species, e.g. Homo sapiens')}
                      onChange={(event) => setInput({ ...input, species: event.target.value })}
                    />
                  )}
                </>
              )}
            </div>
            <button
              className="easy-primary easy-start"
              disabled={state.pending || !!issue || !canExecute}
              onClick={() => void start()}
            >
              {state.pending ? <LoaderCircle className="easy-spin" size={16} /> : t('Start design')}{' '}
              <ArrowRight size={16} />
            </button>
          </div>
          <div className="easy-options">
            <label>
              {t('Design name')}
              <input
                value={input.name}
                onChange={(event) => setInput({ ...input, name: event.target.value })}
              />
            </label>
            {input.type !== 'description' && (
              <label>
                {t('Design goal')}
                <input
                  value={input.goal}
                  onChange={(event) => setInput({ ...input, goal: event.target.value })}
                />
              </label>
            )}
          </div>
          {(error || state.error) && <p className="easy-error">{error || state.error}</p>}
          {issue && Boolean(input.text || input.file) && <p className="easy-validation">{issue}</p>}
        </section>

        {snapshot && (
          <section className="easy-run" id="current-design">
            <div className="easy-run-heading">
              <div>
                <span className="easy-kicker">{snapshot.project.title}</span>
                <h2>{STEPS[shownIndex]}</h2>
              </div>
              <span className={`easy-status ${snapshot.project.status}`}>
                {state.pending || active ? (
                  <LoaderCircle className="easy-spin" size={12} />
                ) : (
                  <Check size={12} />
                )}
                {queueCancelled && !snapshot.decision ? t('Queue cancelled') : snapshot.project.status}
              </span>
            </div>
            <div className="easy-steps">
              {STEPS.map((step, stepIndex) => (
                <button
                  key={step}
                  className={`${stageStatus(snapshot, stepIndex) === 'complete' ? 'done' : ''} ${stepIndex === shownIndex ? 'current' : ''}`}
                  aria-pressed={stepIndex === shownIndex}
                  disabled={stepIndex > index && stageStatus(snapshot, stepIndex) !== 'complete'}
                  onClick={() => setViewedIndex(stepIndex === index ? null : stepIndex)}
                >
                  <span>
                    {stageStatus(snapshot, stepIndex) === 'complete' ? (
                      <Check size={12} />
                    ) : (
                      stepIndex + 1
                    )}
                  </span>
                  <b>{step}</b>
                </button>
              ))}
            </div>
            <div className="easy-live-workspace">
              <div className="easy-live-center">
                {shownIndex !== index ? (
                  <HistoricalStagePanel
                    snapshot={snapshot}
                    stageIndex={shownIndex}
                    onReturn={() => setViewedIndex(null)}
                  />
                ) : stopped ? (
                  <section className="easy-live-progress-card">
                    <ShieldCheck size={22} />
                    <div>
                      <h3>{t('Research stopped')}</h3>
                      <p>{t('The Scientist has stopped this research run; scientific evidence is retained and no further compute will be started.')}</p>
                    </div>
                  </section>
                ) : completed ? (
                  <section className="easy-live-progress-card easy-live-complete-card">
                    <Check size={22} />
                    <div>
                      <h3>{t('Design loop complete')}</h3>
                      <p>{t('Gate 5 recorded; experiments and real ordering remain unauthorized.')}</p>
                    </div>
                  </section>
                ) : queuedRequest?.result?.queue ? (
                  <section className="easy-live-progress-card" role="status">
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>
                        {queuedRequest.result.queue.state === 'starting'
                          ? t('Starting executor')
                          : t('Waiting for execution resources')}
                      </h3>
                      <p>
                        {queuedRequest.result.queue.position != null
                          ? t('Queue position: {{position}}.', { position: queuedRequest.result.queue.position })
                          : ''}
                        {t('The task is saved; no need to resubmit.')}
                      </p>
                    </div>
                    {queuedRequest.result.queue.cancellable && (
                      <button
                        className="easy-primary"
                        disabled={state.pending || (access !== undefined && !access.can_edit)}
                        onClick={() =>
                          void adapter
                            .cancelRequest(queuedRequest.id)
                            .catch((reason) => setError((reason as Error).message))
                        }
                      >
                        {t('Cancel queueing')}
                      </button>
                    )}
                  </section>
                ) : queueCancelled && !snapshot.decision ? (
                  <section className="easy-live-progress-card" role="status">
                    <ShieldCheck size={22} />
                    <div>
                      <h3>{t('Queue cancelled')}</h3>
                      <p>{t('This request did not start compute; existing scientific evidence is retained; it will not be re-queued automatically.')}</p>
                    </div>
                    {(failedCreate || snapshot.capabilities.resume) && (
                      <button
                        className="easy-primary"
                        disabled={state.pending || !canExecute}
                        onClick={() =>
                          void (
                            failedCreate ? adapter.retryRequest(failedCreate.id) : adapter.resume()
                          ).catch((reason) => setError((reason as Error).message))
                        }
                      >
                        {t('Re-queue')}
                      </button>
                    )}
                  </section>
                ) : snapshot.decision ? (
                  <GatePanel
                    key={snapshot.decision.id}
                    snapshot={snapshot}
                    busy={
                      state.pending ||
                      ['accepted', 'running'].includes(state.pendingRequest?.state || '')
                    }
                    canDecide={canExecute && Boolean(snapshot.capabilities.decide)}
                    onDecide={async (value) => {
                      if (value.selected_option_id) setSelectedSite(value.selected_option_id);
                      await adapter.decide(value);
                    }}
                  />
                ) : awaitingDecisionRecovery(snapshot) ? (
                  <section className="easy-live-progress-card easy-live-gate-recovery" role="alert">
                    <ShieldCheck size={22} />
                    <div>
                      <h3>{t('Restoring the approval card')}</h3>
                      <p>{t('The project is waiting for Scientist approval; it will not show as Agent working until the approval options are restored.')}</p>
                    </div>
                    <button
                      className="easy-primary"
                      disabled={state.pending}
                      onClick={() => void adapter.refresh()}
                    >
                      {t('Refresh approval card')} <RefreshCw size={14} />
                    </button>
                  </section>
                ) : snapshot.capabilities.resume || executionBlocked ? (
                  <section
                    className="easy-live-progress-card"
                    role={executionBlocked ? 'alert' : undefined}
                  >
                    {executionBlocked ? (
                      <ShieldCheck size={22} />
                    ) : (
                      <LoaderCircle className="easy-spin" size={22} />
                    )}
                    <div>
                      <h3>
                        {autoContinuationEligible
                          ? t('Auto-continuing')
                          : executionBlocked
                            ? t('Current execution is blocked')
                            : t('Current step can continue')}
                      </h3>
                      <p>
                        {executionBlocked && !autoContinuationEligible
                          ? t('The current execution is incomplete; evidence and recovery state are retained. Review the technical details before deciding whether to continue.')
                          : snapshot.current_action.message || snapshot.current_action.stage}
                      </p>
                    </div>
                    {/* Unauthorized roles never auto-continue; keep the explicit
                        disabled control visible instead of hiding it behind
                        capabilities.auto_continue. */}
                    {snapshot.capabilities.resume && !autoContinuationEligible && (
                      <button
                        className="easy-primary"
                        disabled={state.pending || !canExecute}
                        onClick={() => {
                          if (canExecute) {
                            setError('');
                            void adapter
                              .resume()
                              .catch((reason) => setError((reason as Error).message));
                          }
                        }}
                      >
                        {t('Continue research')} <ArrowRight size={14} />
                      </button>
                    )}
                    {failedCreate && (
                      <button
                        className="easy-primary"
                        disabled={
                          state.pending ||
                          !canExecute ||
                          ['accepted', 'running'].includes(state.pendingRequest?.state || '')
                        }
                        onClick={() => {
                          if (!canExecute) return;
                          setError('');
                          void adapter
                            .retryRequest(failedCreate.id)
                            .catch((reason) => setError((reason as Error).message));
                        }}
                      >
                        {t('Retry target resolution')} <RefreshCw size={14} />
                      </button>
                    )}
                  </section>
                ) : (
                  <section className="easy-live-progress-card">
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>{t('Agent is working')}</h3>
                      <p>{snapshot.current_action.stage}</p>
                    </div>
                  </section>
                )}
                {shownIndex === index && !queueCancelled && (
                  <ExecutionProgress snapshot={snapshot} />
                )}
                {shownIndex === index && (
                  <section className="easy-live-activity">
                    <h3>{t('Live activity')}</h3>
                    {activity.map((item) => (
                      <article key={item.id}>
                        <span className={item.status || ''} />
                        <div>
                          <strong>{item.title}</strong>
                          <p>{item.summary}</p>
                        </div>
                      </article>
                    ))}
                    {technicalActivity.length > 0 && (
                      <details className="easy-live-technical-details">
                        <summary>{t('View technical details')}</summary>
                        {snapshot.decision?.details_url && (
                          <a
                            href={
                              access
                                ? scopeProductUrl(access.id, snapshot.decision.details_url)
                                : snapshot.decision.details_url
                            }
                            target="_blank"
                            rel="noreferrer"
                          >
                            {t('View review and provenance for the current Gate')}
                          </a>
                        )}
                        <div>
                          {technicalActivity.map((item) => (
                            <article key={`technical-${item.id}`}>
                              <span className={item.status || ''} />
                              <div>
                                <strong>{item.title || item.role || item.type}</strong>
                                <p>{item.summary || item.text}</p>
                              </div>
                            </article>
                          ))}
                        </div>
                      </details>
                    )}
                  </section>
                )}
              </div>
              <aside className="easy-live-science">
                <div className="easy-live-kicker">
                  SCIENTIFIC CONTEXT · {STEPS[shownIndex].toUpperCase()}
                </div>
                <EasyStructureViewer
                  artifact={artifact}
                  roles={roles}
                  sites={snapshot.scientific_context.sites}
                  selectedSite={visibleSiteId}
                />
                {shownIndex >= 1 && snapshot.scientific_context.sites.length > 0 && (
                  <div className="easy-live-site-tabs">
                    {snapshot.scientific_context.sites.map((site) => (
                      <button
                        key={site.id}
                        className={site.id === visibleSiteId ? 'selected' : ''}
                        onClick={() => setSelectedSite(site.id)}
                      >
                        Site {site.rank}
                      </button>
                    ))}
                  </div>
                )}
                {shownIndex >= 3 && candidates.length > 0 && (
                  <div className="easy-live-candidates">
                    <h3>{t('Candidate molecules')}</h3>
                    {candidates.map((candidate) => (
                      <button
                        key={candidate.id}
                        className={state.selectedCandidate?.id === candidate.id ? 'selected' : ''}
                        onClick={() => void adapter.selectCandidate(candidate.id)}
                      >
                        <span>
                          <strong>{candidate.id}</strong>
                          <small>
                            {candidate.arm} · {candidate.native_status}
                          </small>
                        </span>
                        <em>{candidate.panel_role || ''}</em>
                      </button>
                    ))}
                  </div>
                )}
              </aside>
            </div>
            {shownIndex === index && order && (
              <fieldset className="account-readonly-order" disabled={!canExecute}>
                <SimulatedOrder order={order} adapter={adapter} onUpdate={setOrder} />
              </fieldset>
            )}
          </section>
        )}

        <section className="easy-history" id="my-designs">
          <div className="easy-history-heading">
            <h2>
              {t('My designs')} <span>{projects.length}</span>
            </h2>
            <p>{t('Latest 5 active designs')}</p>
          </div>
          <div className="easy-history-table">
            <table>
              <thead>
                <tr>
                  <th>{t('Design')}</th>
                  <th>{t('Stage')}</th>
                  <th>{t('Status')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {projects.map((project) => (
                  <tr key={project.id}>
                    <td>
                      <strong>{project.title}</strong>
                      <small>{summarizeGoal(project.goal)}</small>
                    </td>
                    <td>{project.phase}</td>
                    <td>
                      {projectListStatus(
                        project,
                        state.connection === 'connected' ? snapshot : null,
                        state.pendingRequest,
                      )}
                    </td>
                    <td>
                      <button className="easy-outline" onClick={() => void openProject(project.id)}>
                        {t('Open')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
      <RabbitMascot
        locale={locale}
        mood={state.pending || active ? 'running' : snapshot ? 'complete' : 'idle'}
        stage={(snapshot ? STEPS[index] : 'Idle') as (typeof STEPS)[number] | 'Idle'}
        chatContext={{
          stage: snapshot ? STEPS[index] : 'Idle',
          status: active ? 'running' : snapshot ? 'complete' : 'idle',
          goal: snapshot?.project.goal.slice(0, 1200) || '',
        }}
      />
    </div>
  );
}
