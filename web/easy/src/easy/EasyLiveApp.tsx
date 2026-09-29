import { useEffect, useRef, useState, type ReactNode } from 'react';
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
  Trash2,
} from 'lucide-react';
import { Brand } from '../components/Brand';
import { emptyInput, INPUT_TYPES, STEPS, type EasyInput, type InputType } from './contracts';
import { fileTypes, inputLabel, readInputFile, validateInput } from './inputs';
import {
  gateIntro,
  gateOptionFallback,
  gateTitle,
  liveActionName,
  liveConnectionName,
  liveInputTypeName,
  liveStageName,
  liveStatusName,
  normalizeLiveScientificChinese,
} from './liveChinese';
import { RabbitMascot } from './RabbitMascot';
import {
  formatProjectOpenTime,
  loadRecentProjectOpens,
  rememberProjectOpen,
} from './recent-projects';
import { EasyStructureViewer } from './EasyStructureViewer';
import {
  awaitingDecisionRecovery,
  shouldShowGateRiskDisclosure,
  summarizeEasyDesignPlan,
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
  LocalizationPassage,
  Project,
  ProductSnapshot,
} from './product-contracts';
import { optionIdForSite, siteDisplayRank, siteIdForOption } from './site-selection';

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

export function shouldOfferManualResume(
  snapshot: ProductSnapshot | null,
  pending: boolean,
  requestState?: string,
) {
  if (!snapshot || !snapshot.capabilities.resume || pending) return false;
  if (['running', 'accepted'].includes(requestState || '')) return false;
  return ['available', 'incomplete'].includes(snapshot.project.status);
}

export function visibleDesignActionError(
  actionError: string,
  _backgroundError: string | null,
): string | null {
  const message = actionError.trim();
  return message || null;
}

export function isProductExecutionActive(
  snapshot: ProductSnapshot | null,
  pending: boolean,
  requestState?: string,
) {
  return Boolean(
    pending ||
      ['accepted', 'running'].includes(requestState || '') ||
      snapshot?.project.status === 'running' ||
      snapshot?.project.status === 'incomplete',
  );
}

function stageStatus(snapshot: ProductSnapshot | null, index: number) {
  if (!snapshot) return 'waiting';
  const phase = STEPS[index].toLowerCase();
  const row = snapshot.workflow.find((item) => item.id === phase);
  return row?.status || (index < activeIndex(snapshot) ? 'complete' : 'waiting');
}

const PIPELINE_STEPS = [
  ['boltzgen-initialize', '初始化'],
  ['boltzgen-generate', '生成'],
  ['boltzgen-inverse-fold', '逆折叠'],
  ['boltzgen-refold', '重折叠'],
  ['boltzgen-analysis', '分析'],
  ['boltzgen-filter', '筛选'],
  ['native-filter', 'AFO / 原生筛选'],
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
  const currentLabel = PIPELINE_STEPS.find(([id]) => id === current)?.[1];
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
          <span>真实计算</span>
          <strong>
            {phase === 'pilot' ? '小规模试运行' : '扩大测试'} ·{' '}
            {native ? 'AFO 独立结构预测与原生筛选' : currentLabel || 'BoltzGen'}
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
        {completedTasks} / {totalTasks} 个设计策略任务完成
        {progress?.running_tasks ? `，${progress.running_tasks} 个正在运行` : ''}
      </p>
      {phase === 'pilot' &&
        totalTasks > 0 &&
        snapshot.scientific_context.arms.length > 0 &&
        totalTasks % snapshot.scientific_context.arms.length === 0 && (
          <p className="easy-execution-allocation">
            {snapshot.scientific_context.arms.length} 个设计分支 ×{' '}
            {totalTasks / snapshot.scientific_context.arms.length} 个 VHH 骨架 = {totalTasks}{' '}
            个策略任务；当前显示的是经 Gate 3 批准后的实际执行范围。
          </p>
        )}
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
          骨架 {candidateScaffold(candidate).toUpperCase()} ·{' '}
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
          <span>
            {phase === 'pilot' ? '小规模试运行' : phase === 'scale' ? '扩大测试' : '最终候选组'}
          </span>
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

export function gateLocalizationText(
  localized: Record<string, string>,
  id: string,
  source: string,
) {
  return normalizeLiveScientificChinese(localized[id] || source);
}

function AcademicChineseDetails({
  summary,
  passages,
  stage,
  goal,
  adapter,
  children,
}: {
  summary: string;
  passages: LocalizationPassage[];
  stage: string;
  goal: string;
  adapter: EasyProductPort;
  children: (localized: Record<string, string>) => ReactNode;
}) {
  const [localized, setLocalized] = useState<Record<string, string> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const sourceKey = JSON.stringify(passages);
  const activeSource = useRef(sourceKey);
  useEffect(() => {
    activeSource.current = sourceKey;
    setLocalized(null);
    setLoading(false);
    setError('');
  }, [sourceKey]);
  async function load() {
    if (localized || loading) return;
    const requestedSource = sourceKey;
    setLoading(true);
    setError('');
    try {
      const result = await adapter.localizeScientific(passages, { stage, goal });
      if (activeSource.current === requestedSource) setLocalized(result.items);
    } catch (reason) {
      if (activeSource.current === requestedSource) setError((reason as Error).message);
    } finally {
      if (activeSource.current === requestedSource) setLoading(false);
    }
  }
  return (
    <details
      className="easy-live-explanation"
      onToggle={(event) => {
        if (event.currentTarget.open) void load();
      }}
    >
      <summary>{summary}</summary>
      {loading && <p>正在生成忠实保留残基编号与结论强度的学术中文…</p>}
      {error && (
        <p className="easy-error">
          学术中文暂未生成。<button onClick={() => void load()}>重试</button>
        </p>
      )}
      {localized && children(localized)}
      {localized && (
        <details className="easy-live-source-audit">
          <summary>查看英文原文（审计）</summary>
          {passages.map((passage) => (
            <p key={passage.id}>{passage.text}</p>
          ))}
        </details>
      )}
    </details>
  );
}

function DesignYamlDisclosure({
  artifacts,
  adapter,
  summary,
}: {
  artifacts: Artifact[];
  adapter: EasyProductPort;
  summary?: string;
}) {
  const [selected, setSelected] = useState(artifacts[0]?.id || '');
  const [content, setContent] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');
  const artifact = artifacts.find((item) => item.id === selected) || artifacts[0];
  async function load(item: Artifact) {
    if (content[item.id] || loading === item.id) return;
    setLoading(item.id);
    setError('');
    try {
      const text = await adapter.artifactText(item.url);
      setContent((current) => ({ ...current, [item.id]: text }));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoading('');
    }
  }
  return (
    <details
      className="easy-live-explanation"
      onClick={(event) => event.stopPropagation()}
      onToggle={(event) => {
        if (event.currentTarget.open && artifact) void load(artifact);
      }}
    >
      <summary>{summary || `查看详细 YAML（${artifacts.length} 个）`}</summary>
      <p>以下为可执行的冻结配置；字段名与标识符保留原始语法，不作翻译。</p>
      {artifacts.length > 1 && (
        <div className="easy-live-yaml-tabs" role="tablist" aria-label="Scaffold YAML">
          {artifacts.map((item) => {
            const [arm, scaffold = item.label] = item.label.split('-scaffold-');
            const armNumber = arm.match(/^arm-(\d+)$/)?.[1];
            return (
              <button
                key={item.id}
                className={item.id === artifact?.id ? 'selected' : ''}
                role="tab"
                aria-selected={item.id === artifact?.id}
                onClick={() => {
                  setSelected(item.id);
                  void load(item);
                }}
              >
                {armNumber ? `方案 ${armNumber} · ` : ''}
                {scaffold.toUpperCase()}
              </button>
            );
          })}
        </div>
      )}
      {loading === artifact?.id && <p>正在读取已冻结的设计文件…</p>}
      {error && <p className="easy-error">{error}</p>}
      {artifact && content[artifact.id] && <pre>{content[artifact.id]}</pre>}
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
      ['靶标', context.target_id || '已验证靶标'],
      ['序列长度', context.sequence_length || '—'],
      ['目标链', context.chains?.join(', ') || '—'],
      ['结构', context.structure?.label || '—'],
    );
  } else if (stageIndex === 1) {
    rows.push(
      ['候选位点', context.sites.length],
      ['已批准位点', context.approved_site?.selected_rank || '尚未记录'],
    );
    const approved = context.sites.find(
      (site) => site.id === context.approved_site?.selected_candidate_id,
    );
    if (approved) rows.push(['热点残基', approved.design_labels.join(', ')]);
  } else if (stageIndex === 2) {
    rows.push(
      ['设计分支', context.arms.length],
      ['设计审批', context.design_approved ? '已记录' : '尚未记录'],
    );
  } else if (stageIndex === 3 || stageIndex === 4) {
    const phase = stageIndex === 3 ? 'pilot' : 'scale';
    const jobs = snapshot.jobs.filter((item) => item.phase === phase);
    rows.push(['运行状态', jobs.some((item) => item.status === 'running') ? '运行中' : '已完成']);
  } else {
    rows.push(
      ['候选总数', snapshot.candidates.total],
      ['通过原生筛选', snapshot.candidates.counts.pass || 0],
      ['工作流状态', liveActionName(snapshot.current_action.stage)],
    );
  }
  const approvedSite = context.sites.find(
    (site) => site.id === context.approved_site?.selected_candidate_id,
  );
  const designYamls = snapshot.artifacts.filter(
    (artifact) =>
      ['yaml', 'yml'].includes(artifact.format.toLowerCase()) &&
      !artifact.label.startsWith('compiled-asset-'),
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
      {stageIndex === 1 &&
        approvedSite &&
        (() => {
          const passages: LocalizationPassage[] = [
            { id: 'site.why', text: approvedSite.why_ranked },
            ...approvedSite.risks.map((text, index) => ({ id: `site.risk.${index}`, text })),
            ...approvedSite.uncertainty.map((text, index) => ({
              id: `site.uncertainty.${index}`,
              text,
            })),
          ].filter((item) => item.text.trim());
          return (
            <AcademicChineseDetails
              summary={`为什么选择位点 ${approvedSite.rank}`}
              passages={passages}
              stage="Site"
              goal={snapshot.project.goal}
              adapter={adapter}
            >
              {(zh) => (
                <>
                  <h4>位点 {approvedSite.rank}（已批准）</h4>
                  <p>{zh['site.why']}</p>
                  {approvedSite.risks.length > 0 && (
                    <p>
                      <strong>主要风险：</strong>
                      {approvedSite.risks.map((_, index) => zh[`site.risk.${index}`]).join('；')}
                    </p>
                  )}
                  {approvedSite.uncertainty.length > 0 && (
                    <p>
                      <strong>仍需确认：</strong>
                      {approvedSite.uncertainty
                        .map((_, index) => zh[`site.uncertainty.${index}`])
                        .join('；')}
                    </p>
                  )}
                </>
              )}
            </AcademicChineseDetails>
          );
        })()}
      {stageIndex === 2 &&
        context.arms.length > 0 &&
        (() => {
          const passages = context.arms.flatMap((arm, index) => {
            const title =
              asReadableText(arm.name) || asReadableText(arm.arm_id) || `设计 ${index + 1}`;
            const rationale =
              asReadableText(arm.rationale) ||
              asReadableText(arm.hypothesis) ||
              asReadableText(arm.expected_result) ||
              '该设计遵循已批准位点与冻结的设计约束。';
            return [
              { id: `design.${index}.title`, text: title },
              { id: `design.${index}.rationale`, text: rationale },
            ];
          });
          return (
            <AcademicChineseDetails
              summary="为什么采用这个设计方案"
              passages={passages}
              stage="Design"
              goal={snapshot.project.goal}
              adapter={adapter}
            >
              {(zh) => (
                <div className="easy-live-arm-reasons">
                  {context.arms.map((arm, index) => {
                    return (
                      <article key={asReadableText(arm.arm_id) || `design-${index}`}>
                        <h4>{zh[`design.${index}.title`]}</h4>
                        <p>{zh[`design.${index}.rationale`]}</p>
                      </article>
                    );
                  })}
                </div>
              )}
            </AcademicChineseDetails>
          );
        })()}
      {stageIndex === 2 && designYamls.length > 0 && (
        <DesignYamlDisclosure artifacts={designYamls} adapter={adapter} />
      )}
    </section>
  );
}

function GatePanel({
  snapshot,
  busy,
  connection,
  onDecide,
  selectedOptionId,
  onSelectedOptionChange,
  adapter,
}: {
  snapshot: ProductSnapshot;
  busy: boolean;
  connection: LiveState['connection'];
  onDecide: (input: GateInput) => Promise<void>;
  selectedOptionId?: string;
  onSelectedOptionChange?: (optionId: string) => void;
  adapter: EasyProductPort;
}) {
  const decision = snapshot.decision!;
  const [localSelected, setLocalSelected] = useState(decision.default_option_id);
  const [showRevise, setShowRevise] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    setLocalSelected(decision.default_option_id);
    setShowRevise(false);
    setInstruction('');
    setError('');
  }, [decision.id, decision.default_option_id]);
  const selected = decision.options.some((item) => item.option_id === selectedOptionId)
    ? selectedOptionId!
    : localSelected;
  function selectOption(optionId: string) {
    setLocalSelected(optionId);
    onSelectedOptionChange?.(optionId);
  }
  const option = decision.options.find((item) => item.option_id === selected);
  const visibleOptions =
    decision.gate === 1
      ? decision.options.filter((item) => item.option_id === decision.default_option_id)
      : decision.options;
  const designPlanSummary = summarizeEasyDesignPlan(snapshot);
  const designYamls = snapshot.artifacts.filter(
    (artifact) =>
      ['yaml', 'yml'].includes(artifact.format.toLowerCase()) &&
      !artifact.label.startsWith('compiled-asset-'),
  );
  const showRiskDisclosure = shouldShowGateRiskDisclosure(
    decision.gate,
    decision.warnings.length,
    decision.limitations.length,
  );
  const gatePassages: LocalizationPassage[] = showRiskDisclosure
    ? [
        ...decision.warnings.map((text, index) => ({ id: `gate.warning.${index}`, text })),
        ...decision.limitations.map((text, index) => ({ id: `gate.limitation.${index}`, text })),
      ].filter((item) => item.text.trim())
    : [];
  const [gateChinese, setGateChinese] = useState<Record<string, string>>({});
  const [gateLanguageError, setGateLanguageError] = useState(false);
  const [gateLocalizationAttempt, setGateLocalizationAttempt] = useState(0);
  const gateSourceKey = JSON.stringify(gatePassages);
  useEffect(() => {
    if (connection !== 'connected' || gatePassages.length === 0) return;
    let current = true;
    setGateChinese({});
    setGateLanguageError(false);
    void adapter
      .localizeScientific(gatePassages, {
        stage: STEPS[activeIndex(snapshot)],
        goal: snapshot.project.goal,
      })
      .then((result) => {
        if (current) setGateChinese(result.items);
      })
      .catch(() => {
        if (current) setGateLanguageError(true);
      });
    return () => {
      current = false;
    };
  }, [
    adapter,
    connection,
    decision.id,
    gateLocalizationAttempt,
    gateSourceKey,
    snapshot.project.goal,
  ]);
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
    <section className="easy-live-gate" aria-label={`第 ${decision.gate} 关科学家审批`}>
      <div className="easy-live-kicker">
        <ShieldCheck size={14} /> 科学家审批 · 第 {decision.gate} 关
      </div>
      <h3>{gateTitle(decision.gate)}</h3>
      <p>{gateIntro(decision.gate)}</p>
      <div className="easy-live-options" role="radiogroup" aria-label="科学决策选项">
        {visibleOptions.map((item, index) => {
          const fallback = gateOptionFallback(decision, item, index);
          return (
            <label key={item.option_id} className={selected === item.option_id ? 'selected' : ''}>
              <input
                type="radio"
                name="easy-live-option"
                checked={selected === item.option_id}
                disabled={!item.eligible || busy}
                onChange={() => selectOption(item.option_id)}
              />
              <span>
                <strong>
                  {normalizeLiveScientificChinese(fallback.label)}
                </strong>
                {fallback.description && (
                  <small>{normalizeLiveScientificChinese(fallback.description)}</small>
                )}
                {item.design_labels && <em>热点残基：{item.design_labels.join(', ')}</em>}
                {designPlanSummary && (
                  <div className="easy-live-design-plan-summary" aria-label="设计方案规模">
                    <strong>
                      针对{designPlanSummary.siteLabel}，共设计 {designPlanSummary.planCount}{' '}
                      种方案
                    </strong>
                    <ul>
                      {designPlanSummary.plans.map((plan) => (
                        <li key={plan.id}>
                          {plan.label}：
                          {plan.scaffoldCount > 0
                            ? `${plan.scaffoldCount} 种 scaffold`
                            : 'scaffold 数量待确认'}
                        </li>
                      ))}
                    </ul>
                    {designPlanSummary.yamlCount > 0 && designYamls.length > 0 && (
                      <DesignYamlDisclosure
                        artifacts={designYamls}
                        adapter={adapter}
                        summary={`合计 ${designPlanSummary.yamlCount} 个可执行 YAML · 查看详情`}
                      />
                    )}
                  </div>
                )}
              </span>
            </label>
          );
        })}
      </div>
      {showRiskDisclosure && (
        <details>
          <summary>风险与局限（{decision.warnings.length + decision.limitations.length}）</summary>
          <ul>
            {decision.warnings.map((_, index) => (
              <li key={`warning-${index}`}>
                {gateLocalizationText(
                  gateChinese,
                  `gate.warning.${index}`,
                  decision.warnings[index],
                )}
              </li>
            ))}
            {decision.limitations.map((_, index) => (
              <li key={`limitation-${index}`}>
                {gateLocalizationText(
                  gateChinese,
                  `gate.limitation.${index}`,
                  decision.limitations[index],
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
      {gateLanguageError && (
        <p className="easy-error">
          学术中文暂未生成；当前显示英文原文。
          <button
            type="button"
            disabled={connection !== 'connected'}
            onClick={() => setGateLocalizationAttempt((attempt) => attempt + 1)}
          >
            重试
          </button>
        </p>
      )}
      {showRevise && (
        <textarea
          aria-label="修改意见"
          value={instruction}
          maxLength={1500}
          placeholder="说明希望设计助手修改什么"
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
        <FlaskConical size={14} /> 第 5 关 · 模拟实验下单
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
                {item.selection_class === 'primary' ? '主候选' : '备选'} · {item.sequence_length}{' '}
                个氨基酸 · 完整序列已验证
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
  const [selectedOptionId, setSelectedOptionId] = useState<string | undefined>();
  const [previewSiteId, setPreviewSiteId] = useState<string | undefined>();
  const [viewedIndex, setViewedIndex] = useState<number | null>(null);
  const [order, setOrder] = useState<LabOrderView | null>(null);
  const [error, setError] = useState('');
  const [deleteCandidate, setDeleteCandidate] = useState<Project | null>(null);
  const [deletingProject, setDeletingProject] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [recentProjectOpens, setRecentProjectOpens] = useState(loadRecentProjectOpens);
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
    const selection = defaultSite || snapshot?.decision?.default_option_id || undefined;
    const sites = snapshot?.scientific_context.sites || [];
    setSelectedOptionId(selection);
    setPreviewSiteId(siteIdForOption(sites, snapshot?.decision, selection));
    setOrder(snapshot?.lab_order || null);
  }, [snapshot?.revision]);
  useEffect(() => {
    setViewedIndex(null);
  }, [snapshot?.project.id]);
  useEffect(() => {
    const project = snapshot?.project.id;
    if (!project) return;
    setRecentProjectOpens((current) => rememberProjectOpen(current, project));
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
  const requestInFlight = Boolean(
    state?.pending || ['accepted', 'running'].includes(state?.pendingRequest?.state || ''),
  );
  // Adapter errors describe background polling, connection recovery and deferred
  // candidate reads.  The connection badge already represents that transient
  // state.  Only failures caused by an explicit user action belong in the
  // persistent design-form error slot.
  const designActionError = visibleDesignActionError(error, state?.error || null);
  const active = isProductExecutionActive(
    snapshot,
    Boolean(state?.pending),
    state?.pendingRequest?.state,
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
  const sites = snapshot?.scientific_context.sites || [];
  const visibleSiteId = sites.some((site) => site.id === previewSiteId)
    ? previewSiteId
    : siteIdForOption(sites, snapshot?.decision, selectedOptionId);
  const candidates = candidateDataReady ? state?.candidates.items || [] : [];

  async function start() {
    if (issue || !state) return;
    setError('');
    try {
      const goal = productGoal(input);
      await adapter.createProject(
        input.name.trim() || inputLabel(input).slice(0, 80),
        goal,
        input,
        file,
      );
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
    setSelectedOptionId(undefined);
    setPreviewSiteId(undefined);
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

  async function confirmDelete() {
    if (!deleteCandidate || deletingProject) return;
    const deletedSelected = state?.selectedProject === deleteCandidate.id;
    setDeletingProject(true);
    setDeleteError('');
    try {
      await adapter.deleteProject(deleteCandidate.id);
      if (deletedSelected) {
        setOrder(null);
        setSelectedOptionId(undefined);
        setPreviewSiteId(undefined);
        setViewedIndex(null);
        autoContinuation.current = null;
        const params = new URLSearchParams(location.search);
        params.delete('project');
        params.delete('token');
        history.replaceState(
          {},
          '',
          `${location.pathname}${params.size ? `?${params}` : ''}#my-designs`,
        );
      }
      setDeleteCandidate(null);
    } catch (reason) {
      setDeleteError(
        (reason as { code?: string }).code === 'project_busy'
          ? '当前设计仍在运行，完成或停止后才能删除。'
          : '删除失败，请稍后重试。',
      );
    } finally {
      setDeletingProject(false);
    }
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
          访问令牌
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
          <span className={`easy-live-connection ${state.connection}`}>
            ● {liveConnectionName(state.connection)}
          </span>
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
              <Sparkles size={12} /> 实时后端
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
                        {liveInputTypeName(item.id)}
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
          {designActionError && <p className="easy-error">{designActionError}</p>}
          {issue && Boolean(input.text || input.file) && <p className="easy-validation">{issue}</p>}
        </section>

        {snapshot && (
          <section className="easy-run" id="current-design">
            <div className="easy-run-heading">
              <div>
                <span className="easy-kicker">{snapshot.project.title}</span>
                <h2>{liveStageName(shownIndex)}</h2>
              </div>
              <span className={`easy-status ${snapshot.project.status}`}>
                {state.pending || active ? (
                  <LoaderCircle className="easy-spin" size={12} />
                ) : (
                  <Check size={12} />
                )}
                {liveStatusName(snapshot.project.status)}
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
                  <b>{liveStageName(step.toLowerCase())}</b>
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
                      <p>第 5 关已记录；实验与真实下单仍未授权。</p>
                    </div>
                  </section>
                ) : requestInFlight && snapshot.decision ? (
                  <section
                    className="easy-live-progress-card easy-live-approval-starting"
                    role="status"
                    aria-live="polite"
                  >
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>审批已提交</h3>
                      <p>正在启动下一阶段，请稍候。</p>
                    </div>
                  </section>
                ) : snapshot.decision && !active ? (
                  <GatePanel
                    key={snapshot.decision.id}
                    snapshot={snapshot}
                    busy={requestInFlight}
                    connection={state.connection}
                    adapter={adapter}
                    selectedOptionId={
                      snapshot.decision.gate === 2 ? selectedOptionId : undefined
                    }
                    onSelectedOptionChange={
                      snapshot.decision.gate === 2
                        ? (optionId) => {
                            setSelectedOptionId(optionId);
                            const siteId = siteIdForOption(sites, snapshot.decision, optionId);
                            if (siteId) setPreviewSiteId(siteId);
                          }
                        : undefined
                    }
                    onDecide={async (value) => {
                      if (value.selected_option_id) setSelectedOptionId(value.selected_option_id);
                      await adapter.decide(value);
                    }}
                  />
                ) : awaitingDecisionRecovery(snapshot) ? (
                  <section className="easy-live-progress-card easy-live-gate-recovery" role="alert">
                    <ShieldCheck size={22} />
                    <div>
                      <h3>正在恢复审批卡</h3>
                      <p>项目正在等待科学家批准；审批选项恢复前不会显示为正在工作。</p>
                    </div>
                    <button
                      className="easy-primary"
                      disabled={state.pending}
                      onClick={() => void adapter.refresh()}
                    >
                      刷新审批卡 <RefreshCw size={14} />
                    </button>
                  </section>
                ) : shouldOfferManualResume(
                    snapshot,
                    Boolean(state.pending),
                    state.pendingRequest?.state,
                  ) ? (
                  <section className="easy-live-progress-card">
                    <RefreshCw size={22} />
                    <div>
                      <h3>上次运行已暂停</h3>
                      <p>{liveActionName(snapshot.current_action.stage)}</p>
                    </div>
                    <button className="easy-primary" onClick={() => void adapter.resume()}>
                      恢复运行 <ArrowRight size={14} />
                    </button>
                  </section>
                ) : (
                  <section className="easy-live-progress-card">
                    <LoaderCircle className="easy-spin" size={22} />
                    <div>
                      <h3>设计助手正在工作</h3>
                      <p>{liveActionName(snapshot.current_action.stage)}</p>
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
                      <AcademicChineseDetails
                        summary="查看技术详情"
                        passages={technicalActivity.flatMap((item, itemIndex) => {
                          const title = item.title || item.role || item.type;
                          const body = item.summary || item.text || '';
                          return [
                            { id: `activity.${itemIndex}.title`, text: title },
                            ...(body ? [{ id: `activity.${itemIndex}.body`, text: body }] : []),
                          ];
                        })}
                        stage={STEPS[shownIndex]}
                        goal={snapshot.project.goal}
                        adapter={adapter}
                      >
                        {(zh) => (
                          <>
                            {snapshot.decision?.details_url && (
                              <a
                                href={snapshot.decision.details_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                查看当前科学审批的来源与审计记录
                              </a>
                            )}
                            <div>
                              {technicalActivity.map((item, itemIndex) => (
                                <article key={`technical-${item.id}`}>
                                  <span className={item.status || ''} />
                                  <div>
                                    <strong>{zh[`activity.${itemIndex}.title`]}</strong>
                                    {(item.summary || item.text) && (
                                      <p>{zh[`activity.${itemIndex}.body`]}</p>
                                    )}
                                  </div>
                                </article>
                              ))}
                            </div>
                          </>
                        )}
                      </AcademicChineseDetails>
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
                  科学信息 · {STAGE_SUMMARY_TITLES[shownIndex]}
                </div>
                <EasyStructureViewer
                  artifact={artifact}
                  roles={roles}
                  sites={sites}
                  selectedSite={visibleSiteId}
                />
                {shownIndex >= 1 && sites.length > 0 && (
                  <div className="easy-live-site-tabs">
                    {sites.map((site, siteIndex) => {
                      const displayRank = siteDisplayRank(site, siteIndex);
                      return (
                        <button
                          key={site.id}
                          className={`${site.id === visibleSiteId ? 'selected' : ''}${
                            site.selectable ? '' : ' preview-only'
                          }`}
                          aria-label={
                            site.selectable
                              ? `选择并预览位点 ${displayRank}`
                              : `预览位点 ${displayRank}，该位点不可批准`
                          }
                          onClick={() => {
                            setPreviewSiteId(site.id);
                            if (
                              shownIndex === index &&
                              snapshot.decision?.gate === 2 &&
                              site.selectable
                            ) {
                              const optionId = optionIdForSite(sites, snapshot.decision, site.id);
                              if (optionId) setSelectedOptionId(optionId);
                            }
                          }}
                        >
                          <span>位点 {displayRank}</span>
                          {!site.selectable && <small>仅供比较</small>}
                        </button>
                      );
                    })}
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
                  <th>最近打开</th>
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
                    <td>{liveStageName(project.phase)}</td>
                    <td>{liveStatusName(project.status)}</td>
                    <td className="easy-history-opened">
                      {recentProjectOpens[project.id] ? (
                        <time dateTime={new Date(recentProjectOpens[project.id]).toISOString()}>
                          {formatProjectOpenTime(recentProjectOpens[project.id])}
                        </time>
                      ) : (
                        <span title="本设备尚无打开记录">—</span>
                      )}
                    </td>
                    <td>
                      <div className="easy-history-actions">
                        <button
                          className="easy-outline"
                          onClick={() => void openProject(project.id)}
                        >
                          打开
                        </button>
                        <button
                          className="easy-delete-project"
                          disabled={['running', 'incomplete'].includes(project.status)}
                          title={
                            ['running', 'incomplete'].includes(project.status)
                              ? '正在运行的设计暂不能删除'
                              : `删除 ${project.title}`
                          }
                          onClick={() => {
                            setDeleteError('');
                            setDeleteCandidate(project);
                          }}
                        >
                          <Trash2 size={14} /> 删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
      {deleteCandidate && (
        <div className="easy-delete-backdrop" role="presentation">
          <section
            className="easy-delete-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="easy-delete-title"
          >
            <h2 id="easy-delete-title">确认删除这个设计？</h2>
            <strong>{deleteCandidate.title}</strong>
            <p>
              删除后，它将立即从“我的设计”中移除。为避免误操作造成不可逆损失，底层科学运行记录仍保留在本地归档中。
            </p>
            {deleteError && <p className="easy-error">{deleteError}</p>}
            <div>
              <button
                className="easy-outline"
                disabled={deletingProject}
                onClick={() => {
                  setDeleteError('');
                  setDeleteCandidate(null);
                }}
              >
                取消
              </button>
              <button
                className="easy-confirm-delete"
                disabled={deletingProject}
                onClick={() => void confirmDelete()}
              >
                <Trash2 size={15} /> {deletingProject ? '正在删除…' : '确认删除'}
              </button>
            </div>
          </section>
        </div>
      )}
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
