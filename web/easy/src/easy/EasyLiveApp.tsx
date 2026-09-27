import { useEffect, useRef, useState } from 'react';
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
import { Brand } from '../components/Brand';
import { emptyInput, INPUT_TYPES, STEPS, type EasyInput, type InputType } from './contracts';
import { fileTypes, inputLabel, readInputFile, validateInput } from './inputs';
import { RabbitMascot } from './RabbitMascot';
import { EasyStructureViewer } from './EasyStructureViewer';
import {
  awaitingDecisionRecovery,
  summarizeEasyActivity,
  summarizeGoal,
} from './live-presentation';
import type { EasyProductPort } from './EasyProductAdapter';
import type {
  Artifact,
  Candidate,
  GateInput,
  LabOrderDraftInput,
  LabOrderView,
  LiveState,
  ProductSnapshot,
} from './product-contracts';

type CandidatePhase = 'pilot' | 'scale' | 'candidates';

const STAGE_SUMMARY_TITLES = [
  '目标信息',
  '位点选择结果',
  '设计方案',
  '小规模试运行',
  '扩大测试',
  '最终候选',
];

const PHASE_INDEX: Record<string, number> = {
  target: 0,
  site: 1,
  design: 2,
  pilot: 3,
  scale: 4,
  candidates: 5,
  handoff: 5,
};

function productGoal(input: EasyInput) {
  if (input.type === 'description') return input.text.trim();
  const source = input.file?.name || input.text.trim();
  const organism = input.species.trim() ? ` Organism: ${input.species.trim()}.` : '';
  return `${input.goal.trim()} Input ${input.type}: ${source}.${organism}`.slice(0, 1500);
}

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
  ['native-filter', 'AFO / native filter'],
] as const;

function ExecutionProgress({
  snapshot,
  phase,
  candidates,
  candidatePhase,
}: {
  snapshot: ProductSnapshot;
  phase: 'pilot' | 'scale';
  candidates: Candidate[];
  candidatePhase: CandidatePhase | null;
}) {
  const phaseJobs = snapshot.jobs.filter((item) => item.phase === phase && item.progress);
  const job = phaseJobs.reduce<(typeof phaseJobs)[number] | undefined>(
    (best, item) =>
      !best || (item.progress?.completed || 0) > (best.progress?.completed || 0) ? item : best,
    undefined,
  );
  const progress = job?.progress;
  const recorded = candidatePhase === phase ? candidates : [];
  const workflowComplete =
    snapshot.workflow.find((item) => item.id === phase)?.status === 'complete';
  if (!progress && !recorded.length) return null;
  const native =
    progress?.stage_id.startsWith('05-') === true || progress?.stage_id.startsWith('07-') === true;
  const current = native ? 'native-filter' : progress?.substage;
  const currentIndex = PIPELINE_STEPS.findIndex(([id]) => id === current);
  const pipelineComplete = workflowComplete && recorded.length > 0;
  const completed =
    workflowComplete && recorded.length ? recorded.length : progress?.completed || 0;
  const total = recorded.length || progress?.total || 0;
  const completedTasks =
    workflowComplete && recorded.length
      ? new Set(recorded.map((item) => item.arm)).size
      : progress?.completed_tasks || 0;
  const totalTasks = recorded.length
    ? new Set(recorded.map((item) => item.arm)).size
    : progress?.total_tasks || 0;
  const overall = total ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  const substage =
    progress?.substage_total && progress.substage_completed !== null
      ? `${progress.substage_completed} / ${progress.substage_total}`
      : null;
  return (
    <section className="easy-execution-progress" aria-label="真实执行进度">
      <div className="easy-execution-title">
        <div>
          <span>REAL EXECUTION</span>
          <strong>
            {phase === 'pilot' ? 'Pilot' : 'Scale'} ·{' '}
            {native ? 'AFO 预测与原生过滤' : progress?.substage_label || 'BoltzGen'}
          </strong>
        </div>
        <b>{total ? `${completed} / ${total} 条` : '等待资源'}</b>
      </div>
      <div
        className="easy-progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total || 1}
        aria-valuenow={completed}
      >
        <span style={{ width: `${overall}%` }} />
      </div>
      <div className="easy-pipeline-steps">
        {PIPELINE_STEPS.map(([id, label], stepIndex) => {
          const done =
            pipelineComplete || native || (currentIndex >= 0 && stepIndex < currentIndex);
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
        {completedTasks} / {totalTasks} 个 scaffold 任务完成
        {progress?.running_tasks ? `，${progress.running_tasks} 个正在运行` : ''}
      </p>
    </section>
  );
}

function candidateScaffold(candidate: Candidate) {
  return candidate.scaffold || candidate.arm.split('-scaffold-').at(-1) || '未标注';
}

function CandidatePanel({
  phase,
  candidates,
  selected,
  onSelect,
}: {
  phase: CandidatePhase;
  candidates: Candidate[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const passed = candidates.filter((candidate) => candidate.native_status === 'pass');
  const notPassed = candidates.filter((candidate) => candidate.native_status !== 'pass');
  const card = (candidate: Candidate, rank: number, passedCandidate: boolean) => (
    <button
      key={candidate.id}
      className={selected === candidate.id ? 'selected' : ''}
      onClick={() => onSelect(candidate.id)}
      title={`技术 ID：${candidate.id}`}
    >
      <span>
        <strong>{passedCandidate ? `Top ${rank}` : `未通过 ${rank}`}</strong>
        <small>
          Scaffold {candidateScaffold(candidate).toUpperCase()} ·{' '}
          {passedCandidate
            ? '已通过'
            : candidate.native_status === 'incomplete'
              ? '未完成'
              : '未通过'}
        </small>
      </span>
      <em>
        {candidate.panel_role === 'primary'
          ? '主候选'
          : candidate.panel_role === 'backup'
            ? '备选'
            : ''}
      </em>
    </button>
  );
  return (
    <section className="easy-live-candidate-panel" aria-label={`${phase} 候选分子`}>
      <div className="easy-live-candidate-heading">
        <div>
          <span>{phase === 'pilot' ? 'PILOT' : phase === 'scale' ? 'SCALE' : 'FINAL PANEL'}</span>
          <h3>候选分子</h3>
        </div>
        <b>{passed.length} 条通过</b>
      </div>
      <div className="easy-live-candidates">
        {passed.length ? (
          passed.map((candidate, index) => card(candidate, index + 1, true))
        ) : (
          <p className="easy-live-empty-candidates">当前阶段尚无通过候选。</p>
        )}
      </div>
      {notPassed.length > 0 && (
        <details className="easy-live-filtered-candidates">
          <summary>查看未通过或未完成的候选（{notPassed.length}）</summary>
          <div className="easy-live-candidates">
            {notPassed.map((candidate, index) => card(candidate, index + 1, false))}
          </div>
        </details>
      )}
    </section>
  );
}

function asReadableText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return value.map(asReadableText).filter(Boolean).join('；');
  return '';
}

function DesignYamlDisclosure({
  artifact,
  adapter,
}: {
  artifact: Artifact;
  adapter: EasyProductPort;
}) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  async function load() {
    if (content || loading) return;
    setLoading(true);
    setError('');
    try {
      setContent(await adapter.artifactText(artifact.url));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <details
      className="easy-live-explanation"
      onToggle={(event) => {
        if (event.currentTarget.open) void load();
      }}
    >
      <summary>查看详细 YAML</summary>
      {loading && <p>正在读取已冻结的设计文件…</p>}
      {error && <p className="easy-error">{error}</p>}
      {content && <pre>{content}</pre>}
    </details>
  );
}

function HistoricalStagePanel({
  snapshot,
  stageIndex,
  adapter,
}: {
  snapshot: ProductSnapshot;
  stageIndex: number;
  adapter: EasyProductPort;
}) {
  const context = snapshot.scientific_context;
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
    const jobs = snapshot.jobs.filter((item) => item.phase === phase);
    rows.push([
      'Execution status',
      jobs.some((item) => item.status === 'running') ? 'Running' : 'Complete',
    ]);
  } else {
    rows.push(
      ['Candidate total', snapshot.candidates.total],
      ['Native pass', snapshot.candidates.counts.pass || 0],
      ['Workflow state', snapshot.current_action.stage],
    );
  }
  const approvedSite = context.sites.find(
    (site) => site.id === context.approved_site?.selected_candidate_id,
  );
  const designYaml = snapshot.artifacts.find((artifact) =>
    ['yaml', 'yml'].includes(artifact.format.toLowerCase()),
  );
  return (
    <section className="easy-live-history-card" aria-label={STAGE_SUMMARY_TITLES[stageIndex]}>
      <h3>{STAGE_SUMMARY_TITLES[stageIndex]}</h3>
      <dl>
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {stageIndex === 1 && approvedSite && (
        <details className="easy-live-explanation">
          <summary>为什么选择 Site {approvedSite.rank}</summary>
          <h4>{approvedSite.name}</h4>
          <p>{approvedSite.why_ranked}</p>
          {approvedSite.risks.length > 0 && (
            <p>
              <strong>主要风险：</strong>
              {approvedSite.risks.join('；')}
            </p>
          )}
          {approvedSite.uncertainty.length > 0 && (
            <p>
              <strong>仍需确认：</strong>
              {approvedSite.uncertainty.join('；')}
            </p>
          )}
        </details>
      )}
      {stageIndex === 2 && context.arms.length > 0 && (
        <details className="easy-live-explanation">
          <summary>为什么采用这个设计方案</summary>
          <div className="easy-live-arm-reasons">
            {context.arms.map((arm, index) => {
              const title =
                asReadableText(arm.name) || asReadableText(arm.arm_id) || `设计 ${index + 1}`;
              const rationale =
                asReadableText(arm.rationale) ||
                asReadableText(arm.hypothesis) ||
                asReadableText(arm.expected_result);
              return (
                <article key={asReadableText(arm.arm_id) || title}>
                  <h4>{title}</h4>
                  <p>{rationale || '该设计遵循已批准位点与冻结的设计约束。'}</p>
                </article>
              );
            })}
          </div>
        </details>
      )}
      {stageIndex === 2 && designYaml && (
        <DesignYamlDisclosure artifact={designYaml} adapter={adapter} />
      )}
    </section>
  );
}

function GatePanel({
  snapshot,
  busy,
  onDecide,
}: {
  snapshot: ProductSnapshot;
  busy: boolean;
  onDecide: (input: GateInput) => Promise<void>;
}) {
  const decision = snapshot.decision!;
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
      <h3>{decision.gate === 1 ? '确认自动推荐的目标结构' : decision.question}</h3>
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
              <small>{item.description || (item.eligible ? '可选择' : '已阻断')}</small>
              {item.design_labels && <em>Hotspot: {item.design_labels.join(', ')}</em>}
            </span>
          </label>
        ))}
      </div>
      {(decision.warnings.length > 0 || decision.limitations.length > 0) && (
        <details>
          <summary>风险与局限（{decision.warnings.length + decision.limitations.length}）</summary>
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
          placeholder="说明希望科学 Agent 修改什么"
          onChange={(event) => setInstruction(event.target.value)}
        />
      )}
      {error && <p className="easy-error">{error}</p>}
      <div className="easy-live-gate-actions">
        <button
          className="easy-primary"
          disabled={!approveAction || busy}
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
          {approveAction === 'override' ? '确认并覆盖' : '批准并继续'}
          <ArrowRight size={15} />
        </button>
        <button className="easy-outline" onClick={() => setShowRevise((value) => !value)}>
          修改
        </button>
        {showRevise && (
          <button
            className="easy-outline"
            disabled={!instruction.trim() || busy}
            onClick={() =>
              void submit({
                action: 'revise',
                selected_option_id: selected,
                instruction,
                revision_target: decision.revision_targets[0],
              })
            }
          >
            提交修改意见
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
      <h3>{order.receipt ? '模拟下单回执已生成' : '模拟实验下单'}</h3>
      <p>{order.disclaimer}</p>
      <div className="easy-live-order-candidates">
        {order.candidates.map((item, index) => (
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
              <strong>Top {index + 1}</strong>
              <small>
                {item.selection_class === 'primary' ? '主候选' : '备选'} · {item.sequence_length} aa
                · 完整序列已验证
              </small>
            </span>
          </label>
        ))}
      </div>
      {!order.receipt && (
        <div className="easy-live-order-fields">
          <label>
            构建形式
            <select
              value={format}
              onChange={(event) => setFormat(event.target.value as typeof format)}
            >
              <option value="VHH">VHH</option>
              <option value="VHH-Fc">VHH-Fc</option>
            </select>
          </label>
          <label>
            每个样品用量
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
          非约束性模拟报价：{String(order.quote.illustrative_total)} {String(order.quote.currency)}
        </p>
      )}
      {order.receipt && (
        <dl className="easy-live-receipt">
          <div>
            <dt>模拟订单</dt>
            <dd>{String(order.receipt.order_id)}</dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd>{String(order.receipt.status)}</dd>
          </div>
          <div>
            <dt>真实外部请求</dt>
            <dd>未发送</dd>
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
              保存模拟订单草稿
            </button>
          )}
          {order.draft && !order.quote && (
            <button
              className="easy-primary"
              disabled={busy}
              onClick={() => void run(() => adapter.quoteLabOrder())}
            >
              生成模拟报价
            </button>
          )}
          {order.quote && (
            <button
              className="easy-primary"
              disabled={busy}
              onClick={() => void run(() => adapter.submitLabOrder())}
            >
              确认仅模拟并提交
            </button>
          )}
        </div>
      )}
    </section>
  );
}

export function EasyLiveApp({ adapter }: { adapter: EasyProductPort }) {
  const [state, setState] = useState<LiveState | null>(null);
  const [input, setInput] = useState<EasyInput>(() => emptyInput());
  const [file, setFile] = useState<File | null>(null);
  const [token, setToken] = useState('');
  const [selectedSite, setSelectedSite] = useState<string | undefined>();
  const [viewedIndex, setViewedIndex] = useState<number | null>(null);
  const [order, setOrder] = useState<LabOrderView | null>(null);
  const [error, setError] = useState('');
  const autoContinuation = useRef<string | null>(null);
  useEffect(() => {
    const unsubscribe = adapter.subscribe((event) => setState(event.snapshot));
    void (async () => {
      const params = new URLSearchParams(location.search);
      const access = params.get('token');
      if (access) {
        await adapter.authenticate(access);
        params.delete('token');
        history.replaceState(
          {},
          '',
          `${location.pathname}${params.size ? `?${params}` : ''}${location.hash}`,
        );
      }
      const requested = params.get('project');
      if (requested) {
        // A shared/deep link must not wait for every historical project card to
        // project before the requested scientific workspace becomes visible.
        await Promise.all([adapter.selectProject(requested), adapter.load()]);
      } else {
        const loaded = await adapter.load();
        setState(loaded);
      }
    })().catch((reason) => setError((reason as Error).message));
    return () => {
      unsubscribe();
      adapter.dispose();
    };
  }, [adapter]);
  const snapshot = state?.snapshot || null;
  const completed = snapshot?.current_action.stage === 'handoff-complete';
  useEffect(() => {
    if (
      !snapshot ||
      !canAutoContinue(snapshot, Boolean(state?.pending), state?.pendingRequest?.state)
    )
      return;
    const key = `${snapshot.project.id}:${snapshot.revision}:${snapshot.current_action.id}`;
    if (autoContinuation.current === key) return;
    autoContinuation.current = key;
    void adapter.resume().catch((reason) => setError((reason as Error).message));
  }, [adapter, snapshot, state?.pending, state?.pendingRequest?.state]);
  useEffect(() => {
    const defaultSite = snapshot?.scientific_context.approved_site?.selected_candidate_id;
    setSelectedSite(defaultSite || snapshot?.decision?.default_option_id || undefined);
    setOrder(snapshot?.lab_order || null);
  }, [snapshot?.revision]);
  useEffect(() => {
    setViewedIndex(null);
  }, [snapshot?.project.id]);
  const issue = validateInput(input);
  const index = activeIndex(snapshot);
  const shownIndex = viewedIndex ?? index;
  const shownCandidatePhase: CandidatePhase | null =
    shownIndex === 3
      ? 'pilot'
      : shownIndex === 4
        ? 'scale'
        : shownIndex === 5
          ? 'candidates'
          : null;
  useEffect(() => {
    if (!snapshot || !shownCandidatePhase || state?.candidatePhase === shownCandidatePhase) return;
    void adapter
      .candidatePage(0, shownCandidatePhase)
      .catch((reason) => setError((reason as Error).message));
  }, [adapter, shownCandidatePhase, snapshot?.project.id, state?.candidatePhase]);
  const active = Boolean(
    state?.pending ||
      snapshot?.project.status === 'running' ||
      snapshot?.project.status === 'incomplete',
  );
  const candidateArtifact = state?.selectedCandidate?.artifacts.find((item) =>
    ['pdb', 'cif', 'mmcif'].includes(item.format),
  );
  const candidateDataReady = Boolean(
    shownCandidatePhase && state?.candidatePhase === shownCandidatePhase,
  );
  const artifact =
    (candidateDataReady ? candidateArtifact : null) ||
    snapshot?.scientific_context.structure ||
    null;
  const roles = candidateDataReady ? state?.selectedCandidate?.structure_roles || {} : {};
  const technicalActivity = (snapshot?.recent_activity || [])
    .filter((item) => item.visible !== false && !(completed && item.type === 'gate.awaiting'))
    .slice(-8)
    .reverse();
  const activity = snapshot ? summarizeEasyActivity(snapshot) : [];
  const projects = state?.projects.items || [];
  const gateOption = snapshot?.decision?.options.find((item) => item.option_id === selectedSite);
  const visibleSite = gateOption?.rank
    ? snapshot?.scientific_context.sites.find((site) => site.rank === gateOption.rank)
    : selectedSite;
  const visibleSiteId = typeof visibleSite === 'string' ? visibleSite : visibleSite?.id;
  const candidates = candidateDataReady ? state?.candidates.items || [] : [];

  async function start() {
    if (issue || !state) return;
    setError('');
    try {
      const goal = productGoal(input);
      await adapter.createProject(input.name.trim() || inputLabel(input).slice(0, 80), goal, file);
      const created = await adapter.load();
      if (created.selectedProject) {
        const params = new URLSearchParams(location.search);
        params.delete('token');
        params.set('project', created.selectedProject);
        history.replaceState({}, '', `${location.pathname}?${params.toString()}${location.hash}`);
      }
      setFile(null);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  function newDesign() {
    adapter.clearProject();
    setOrder(null);
    setSelectedSite(undefined);
    setViewedIndex(null);
    autoContinuation.current = null;
    const params = new URLSearchParams(location.search);
    params.delete('project');
    params.delete('token');
    history.replaceState({}, '', `${location.pathname}${params.size ? `?${params}` : ''}#design`);
    document.getElementById('design')?.scrollIntoView({ behavior: 'smooth' });
  }

  async function openProject(id: string) {
    await adapter.selectProject(id);
    const params = new URLSearchParams(location.search);
    params.delete('token');
    params.set('project', id);
    history.replaceState({}, '', `${location.pathname}?${params.toString()}#current-design`);
  }

  if (!state)
    return (
      <div className="easy-live-loading">
        <LoaderCircle className="easy-spin" /> 正在连接 EasyDesign…
      </div>
    );
  if (state.connection === 'authentication-required')
    return (
      <main className="easy-live-login">
        <Brand />
        <h1>连接本地研究工作区</h1>
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
          连接 <ArrowRight size={16} />
        </button>
        {error && <p className="easy-error">{error}</p>}
      </main>
    );

  return (
    <div className="easy-app easy-live-app">
      <header className="easy-header">
        <a className="easy-brand" href="/easy/">
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
            新设计
          </a>
          {snapshot && <a href="#current-design">当前任务</a>}
          <a href="#my-designs">我的设计</a>
        </nav>
        <div className="easy-header-end">
          <span className={`easy-live-connection ${state.connection}`}>● {state.connection}</span>
          <button className="easy-help" onClick={() => void adapter.refresh()}>
            <RefreshCw size={14} /> 刷新
          </button>
        </div>
      </header>

      <main className="easy-main">
        <section className="easy-intro">
          <h1>
            从一句话开始<span>真实设计</span>
          </h1>
        </section>
        <section className="easy-input-card" id="design">
          <div className="easy-section-top">
            <span className="easy-demo-pill easy-live-pill">
              <Sparkles size={12} /> LIVE BACKEND
            </span>
          </div>
          <div className="easy-input-row">
            <label className="easy-type-label">
              <span>输入类型</span>
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
                        {item.label}
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
                  <span>{file?.name || '上传 PDB / mmCIF'}</span>
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
                <textarea
                  rows={3}
                  value={input.text}
                  placeholder="例如：请为人源 NK2R 设计一个抑制受体信号的胞外 VHH binder"
                  onChange={(event) => setInput({ ...input, text: event.target.value })}
                />
              ) : (
                <>
                  <input
                    value={input.text}
                    placeholder="目标名称或数据库 ID"
                    onChange={(event) => setInput({ ...input, text: event.target.value })}
                  />
                  {input.type === 'protein-name' && (
                    <input
                      value={input.species}
                      placeholder="物种，例如 Homo sapiens"
                      onChange={(event) => setInput({ ...input, species: event.target.value })}
                    />
                  )}
                </>
              )}
            </div>
            <button
              className="easy-primary easy-start"
              disabled={state.pending || !!issue}
              onClick={() => void start()}
            >
              {state.pending ? <LoaderCircle className="easy-spin" size={16} /> : '开始设计'}{' '}
              <ArrowRight size={16} />
            </button>
          </div>
          <div className="easy-options">
            <label>
              设计名称
              <input
                value={input.name}
                onChange={(event) => setInput({ ...input, name: event.target.value })}
              />
            </label>
            {input.type !== 'description' && (
              <label>
                设计目标
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
                {snapshot.project.status}
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
                  <>
                    <HistoricalStagePanel
                      snapshot={snapshot}
                      stageIndex={shownIndex}
                      adapter={adapter}
                    />
                    {(shownIndex === 3 || shownIndex === 4) && (
                      <ExecutionProgress
                        snapshot={snapshot}
                        phase={shownIndex === 3 ? 'pilot' : 'scale'}
                        candidates={candidates}
                        candidatePhase={state.candidatePhase}
                      />
                    )}
                  </>
                ) : completed ? (
                  <section className="easy-live-progress-card easy-live-complete-card">
                    <Check size={22} />
                    <div>
                      <h3>设计闭环已完成</h3>
                      <p>Gate 5 已记录；实验与真实下单仍未授权。</p>
                    </div>
                  </section>
                ) : snapshot.decision ? (
                  <GatePanel
                    key={snapshot.decision.id}
                    snapshot={snapshot}
                    busy={state.pending}
                    onDecide={async (value) => {
                      if (value.selected_option_id) setSelectedSite(value.selected_option_id);
                      await adapter.decide(value);
                    }}
                  />
                ) : awaitingDecisionRecovery(snapshot) ? (
                  <section className="easy-live-progress-card easy-live-gate-recovery" role="alert">
                    <ShieldCheck size={22} />
                    <div>
                      <h3>正在恢复审批卡</h3>
                      <p>项目正在等待 Scientist 批准；在审批选项恢复前不会显示为 Agent 工作中。</p>
                    </div>
                    <button
                      className="easy-primary"
                      disabled={state.pending}
                      onClick={() => void adapter.refresh()}
                    >
                      刷新审批卡 <RefreshCw size={14} />
                    </button>
                  </section>
                ) : snapshot.capabilities.resume ? (
                  <section className="easy-live-progress-card">
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>
                        {snapshot.capabilities.auto_continue ? '正在自动继续' : '当前步骤可以继续'}
                      </h3>
                      <p>{snapshot.current_action.message || snapshot.current_action.stage}</p>
                    </div>
                    {!snapshot.capabilities.auto_continue && (
                      <button
                        className="easy-primary"
                        disabled={state.pending}
                        onClick={() => void adapter.resume()}
                      >
                        继续研究 <ArrowRight size={14} />
                      </button>
                    )}
                  </section>
                ) : (
                  <section className="easy-live-progress-card">
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>Agent 正在工作</h3>
                      <p>{snapshot.current_action.stage}</p>
                    </div>
                  </section>
                )}
                {shownIndex === index && (shownIndex === 3 || shownIndex === 4) && (
                  <ExecutionProgress
                    snapshot={snapshot}
                    phase={shownIndex === 3 ? 'pilot' : 'scale'}
                    candidates={candidates}
                    candidatePhase={state.candidatePhase}
                  />
                )}
                {shownIndex === index && (
                  <section className="easy-live-activity">
                    <h3>实时过程</h3>
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
                        <summary>查看技术详情</summary>
                        {snapshot.decision?.details_url && (
                          <a href={snapshot.decision.details_url} target="_blank" rel="noreferrer">
                            查看当前 Gate 的审查与 provenance
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
                {shownCandidatePhase && state.candidatePhase === shownCandidatePhase && (
                  <CandidatePanel
                    phase={shownCandidatePhase}
                    candidates={candidates}
                    selected={state.selectedCandidate?.id || null}
                    onSelect={(id) => void adapter.selectCandidate(id)}
                  />
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
              </aside>
            </div>
            {shownIndex === index && order && (
              <SimulatedOrder order={order} adapter={adapter} onUpdate={setOrder} />
            )}
          </section>
        )}

        <section className="easy-history" id="my-designs">
          <div className="easy-history-heading">
            <h2>
              我的设计 <span>{projects.length}</span>
            </h2>
            <p>最近 5 个有效设计</p>
          </div>
          <div className="easy-history-table">
            <table>
              <thead>
                <tr>
                  <th>设计</th>
                  <th>阶段</th>
                  <th>状态</th>
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
                    <td>{project.status}</td>
                    <td>
                      <button className="easy-outline" onClick={() => void openProject(project.id)}>
                        打开
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
        locale="zh"
        mood={
          state.pending || (active && shownIndex === index)
            ? 'running'
            : snapshot
              ? 'complete'
              : 'idle'
        }
        stage={(snapshot ? STEPS[shownIndex] : 'Idle') as (typeof STEPS)[number] | 'Idle'}
        chatContext={{
          stage: snapshot ? STEPS[shownIndex] : 'Idle',
          status: active && shownIndex === index ? 'running' : snapshot ? 'complete' : 'idle',
          goal: snapshot?.project.goal.slice(0, 1200) || '',
        }}
      />
    </div>
  );
}
