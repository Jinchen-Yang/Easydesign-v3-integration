import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { MolViewer } from "./MolViewer";
import type { Artifact, Project, ProjectResponse, Replay, Run, Stage, StageState } from "./types";
import "./styles.css";

const nav = [
  ["overview", "总览", "⌂"],
  ["new", "新建设计", "＋"],
  ["run", "运行工作台", "◎"],
  ["decisions", "待审批", "◇"],
  ["environment", "运行环境", "◉"],
  ["audit", "证据审计", "≡"],
] as const;

const stateCopy: Record<StageState, { label: string; description: string }> = {
  draft: { label: "草稿", description: "尚未提交运行" },
  validating: { label: "校验中", description: "正在验证配置与输入" },
  ready: { label: "可运行", description: "已通过配置和环境检查" },
  queued: { label: "排队中", description: "等待可用计算资源" },
  running: { label: "运行中", description: "正在执行结构化任务" },
  "awaiting-human-approval": { label: "等待审批", description: "需要人工确认后继续" },
  succeeded: { label: "已完成", description: "阶段成功发布正式产物" },
  "scientific-stop": { label: "科学停止", description: "软件正常，科学门槛未通过" },
  "operational-failed": { label: "运行故障", description: "后端或产物发生操作失败" },
  "not-reached": { label: "未到达", description: "当前运行没有进入本阶段" },
  "simulated-preview": { label: "演示回放", description: "模拟状态，不是新科学运行" },
};

function formatNumber(value: unknown, digits = 1) {
  if (typeof value !== "number") return value == null ? "—" : String(value);
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

function formatTime(value?: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function humanBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}

async function fileAsBase64(file: File) {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("无法读取输入文件"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

function Status({ state, small = false }: { state: StageState; small?: boolean }) {
  return (
    <span className={`status status-${state} ${small ? "small" : ""}`}>
      <span className="status-mark" />
      {stateCopy[state].label}
    </span>
  );
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

function StageRail({
  stages,
  selected,
  onSelect,
}: {
  stages: Stage[];
  selected: number;
  onSelect: (value: number) => void;
}) {
  return (
    <div className="stage-rail" aria-label="七阶段进度">
      {stages.map((stage) => (
        <button
          key={stage.stage_number}
          type="button"
          className={`stage-node ${selected === stage.stage_number ? "selected" : ""}`}
          onClick={() => onSelect(stage.stage_number)}
          aria-current={selected === stage.stage_number ? "step" : undefined}
        >
          <span className={`stage-orb state-${stage.state}`}>
            {String(stage.stage_number).padStart(2, "0")}
          </span>
          <span className="stage-name">{stage.title}</span>
          <span className="stage-mini-state">{stateCopy[stage.state].label}</span>
        </button>
      ))}
    </div>
  );
}

function artifactUrl(artifacts: Artifact[], id: string) {
  const value = artifacts.find((item) => item.artifact_id === id);
  return value ? `/api/v1/artifacts/${value.token}` : undefined;
}

function StageOne({ stage }: { stage: Stage }) {
  const h = stage.highlights;
  const structure = artifactUrl(stage.artifacts, "target-structure");
  return (
    <div className="stage-grid">
      <MolViewer structureUrl={structure} />
      <div className="evidence-stack">
        <section className="panel">
          <p className="panel-kicker">标准 Target Bundle</p>
          <h3>{String(h.target_id || "Target")}</h3>
          <div className="compact-metrics">
            <Metric label="序列" value={`${formatNumber(h.sequence_length, 0)} aa`} />
            <Metric label="来源" value={String(h.origin || "—")} />
            <Metric label="模型" value={formatNumber(h.model_count, 0)} />
            <Metric label="缺失 CA" value={formatNumber(h.missing_ca_count, 0)} />
          </div>
        </section>
        <EvidenceList stage={stage} limit={8} />
      </div>
    </div>
  );
}

function StageTwo({ stage, run }: { stage: Stage; run: Run }) {
  const stageOne = run.stages[0];
  const structure = artifactUrl(stageOne.artifacts, "target-structure");
  const regions = (stage.tables.regions || []).map((item) => ({
    id: String(item.id),
    label_seq_ids: String(item.label_ranges || "")
      .split(",")
      .map(Number)
      .filter(Number.isFinite),
  }));
  return (
    <div className="stage-grid">
      <MolViewer structureUrl={structure} regions={regions} />
      <div className="evidence-stack">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">已批准区域</p>
              <h3>{formatNumber(stage.highlights.region_count, 0)} 个用户区域</h3>
            </div>
            <span className="evidence-chip">{String(stage.highlights.region_source || "—")}</span>
          </div>
          <div className="region-list">
            {(stage.tables.regions || []).map((region) => (
              <div className={`region-row region-${String(region.id).toLowerCase()}`} key={String(region.id)}>
                <strong>{String(region.id)}</strong>
                <div>
                  <span>{formatNumber(region.member_count, 0)} residues</span>
                  <small>label {String(region.label_ranges)}</small>
                </div>
              </div>
            ))}
          </div>
          <p className="fine">
            用户区域属于结构先验，不自动等同于能量学 hotspot；批准人：
            {String(stage.highlights.approved_by || "—")}。
          </p>
        </section>
        <EvidenceList stage={stage} />
      </div>
    </div>
  );
}

function StageThree({ stage }: { stage: Stage }) {
  const rows = stage.tables.strategies || [];
  return (
    <div className="content-stack">
      <div className="metric-row">
        <Metric label="策略矩阵" value={formatNumber(stage.highlights.strategy_count, 0)} note="region × scaffold" />
        <Metric label="区域" value={formatNumber(stage.highlights.region_count, 0)} />
        <Metric label="Scaffold" value={formatNumber(stage.highlights.scaffold_count, 0)} />
        <Metric label="Pilot 预算" value={formatNumber(stage.highlights.planned_candidates, 0)} note="完整候选" />
      </div>
      <section className="panel matrix-panel">
        <div className="panel-header">
          <div><p className="panel-kicker">BoltzGen strategy compiler</p><h3>基础 VHH 设计矩阵</h3></div>
          <span className="evidence-chip">非 hotspot 保持中性</span>
        </div>
        <div className="matrix-grid">
          {rows.map((row) => (
            <article key={String(row.strategy_id)} className="strategy-tile">
              <span className={`region-letter region-${String(row.region_id)}`}>{String(row.region_id).toUpperCase()}</span>
              <strong>{String(row.scaffold_id)}</strong>
              <small>{formatNumber(row.candidates_per_strategy, 0)} candidates</small>
              <code>H_all · C_full</code>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function StageFour({ stage }: { stage: Stage }) {
  const h = stage.highlights;
  const planned = Number(h.planned_candidates || 0);
  const collected = Number(h.collected_candidates || 0);
  const percentage = planned ? Math.min(100, (collected / planned) * 100) : 0;
  return (
    <div className="content-stack">
      <section className="progress-hero panel">
        <div className="progress-copy">
          <p className="panel-kicker">双 GPU · 可恢复执行</p>
          <h3>{collected === planned ? "Pilot generation 完整收集" : "Pilot generation 进行中"}</h3>
          <p>每个 strategy 独立 attempt；完整候选和失败原因均已进入 manifest。</p>
        </div>
        <div className="progress-number"><strong>{percentage.toFixed(0)}%</strong><span>{collected} / {planned}</span></div>
        <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
      </section>
      <div className="metric-row">
        <Metric label="策略" value={formatNumber(h.strategy_count, 0)} />
        <Metric label="完成任务" value={formatNumber(h.succeeded_tasks, 0)} />
        <Metric label="运行时长" value={`${formatNumber(Number(h.elapsed_seconds || 0) / 3600, 2)} h`} />
        <Metric label="吞吐" value={formatNumber(h.throughput_candidates_per_hour, 1)} note="candidates / hour" />
      </div>
      <section className="panel gpu-panel">
        <div className="panel-header"><div><p className="panel-kicker">执行轨迹</p><h3>GPU strategy lanes</h3></div><Status state={stage.state} /></div>
        <div className="gpu-lanes">
          {[0, 1].map((device, index) => (
            <div className="gpu-lane" key={device}>
              <div><strong>GPU {device}</strong><small>RTX 4080 · one worker</small></div>
              <div className="lane-track">
                {Array.from({ length: index === 0 ? 11 : 10 }).map((_, item) => <span key={item} />)}
              </div>
              <b>{index === 0 ? 11 : 10} strategies</b>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function StageFive({ stage }: { stage: Stage }) {
  const h = stage.highlights;
  const predictions = stage.tables.predictions || [];
  const tier = h.tier_counts as Record<string, number> | undefined;
  const funnel = [
    ["Pilot candidates", Number(h.pilot_candidate_count || 0)],
    ["Tier A strategies", Number(tier?.["tier-a"] || 0)],
    ["Expanded strategy", Number(h.expanded_candidate_count || 0)],
    ["Local gate pass", Number(h.local_gate_pass_count || 0)],
    ["Protenix full-target", Number(h.protenix_prediction_count || 0)],
    ["Scale winner", h.winner_strategy_id ? 1 : 0],
  ] as const;
  return (
    <div className="content-stack">
      <section className="science-stop">
        <div className="stop-icon">∥</div>
        <div>
          <p className="panel-kicker">SCIENTIFIC STOP · 软件运行正常</p>
          <h3>没有策略通过 full-target binder-pose gate</h3>
          <p>12 个候选通过 local gate；Top 10 Protenix 均未保持原 binder pose。现有证据不等同于证明 Protenix 软件有 bug。</p>
        </div>
        <span className="val-tag">VAL-003 · planned</span>
      </section>
      <div className="filter-layout">
        <section className="panel funnel-panel">
          <div className="panel-header"><div><p className="panel-kicker">筛选漏斗</p><h3>840 → scientific stop</h3></div></div>
          <div className="funnel">
            {funnel.map(([label, value], index) => (
              <div key={label} style={{ width: `${100 - index * 9}%` }}>
                <span>{label}</span><strong>{value}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="panel comparison-panel">
          <p className="panel-kicker">两套结构证据</p>
          <h3>BoltzGen local vs. Protenix independent</h3>
          <div className="comparison-split">
            <div><span>BoltzGen filter-rmsd-design</span><strong>{rangeText(h.boltzgen_filter_rmsd_design_range)}</strong><small>生成流程内部结构指标</small></div>
            <div><span>Protenix binder pose RMSD</span><strong>{rangeText(h.protenix_binder_pose_rmsd_range)}</strong><small>独立、无模板复折叠</small></div>
          </div>
        </section>
      </div>
      <section className="panel">
        <div className="panel-header"><div><p className="panel-kicker">Top 10 full-target predictions</p><h3>候选逐项证据</h3></div><span className="evidence-chip">target RMSD 全部通过</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Candidate</th><th>Target RMSD</th><th>Binder pose RMSD</th><th>pairwise ipTM</th><th>Min interface PAE</th><th>结论</th></tr></thead>
            <tbody>
              {predictions.map((item) => (
                <tr key={String(item.candidate_id)}>
                  <td><code>{shortCandidate(String(item.candidate_id))}</code></td>
                  <td>{formatNumber(item.target_ca_rmsd_angstrom, 2)} Å</td>
                  <td className="failed-value">{formatNumber(item.binder_pose_rmsd_angstrom, 2)} Å</td>
                  <td>{formatNumber(item.pairwise_iptm, 3)}</td>
                  <td>{formatNumber(item.minimum_interface_pae_angstrom, 2)} Å</td>
                  <td><Status state={item.passed ? "succeeded" : "scientific-stop"} small /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function rangeText(value: unknown) {
  return Array.isArray(value) && value.length === 2
    ? `${formatNumber(value[0], 2)}–${formatNumber(value[1], 2)} Å`
    : "—";
}

function shortCandidate(value: string) {
  const match = value.match(/candidate-(\d+)$/);
  return match ? `candidate-${match[1]}` : value;
}

function FutureStage({ stage, run }: { stage: Stage; run: Run }) {
  const stageFive = run.stages[4];
  const isSix = stage.stage_number === 6;
  return (
    <div className="content-stack">
      <section className="not-reached-card">
        <div>
          <p className="panel-kicker">当前 APOE RUN</p>
          <h3>本阶段未到达</h3>
          <p>Stage 05 已发布 <code>stopped-no-scale-winner</code>，因此没有合法上游 artifact 可以进入本阶段。</p>
        </div>
        <Status state="not-reached" />
      </section>
      <section className="panel capability-panel">
        <div className="capability-head">
          <div><span className="capability-label">SOFTWARE CAPABILITY</span><h3>{stage.capability.summary}</h3><p>功能存在不代表本次 APOE 已执行。</p></div>
          <span className="implemented-badge">{stage.capability.status}</span>
        </div>
        {isSix ? (
          <>
            <div className="profile-cards">
              <article><span>SMOKE PROFILE</span><strong>2 × 500</strong><small>两张 GPU，各一个可恢复 shard</small></article>
              <article><span>PRODUCTION PLAN</span><strong>20 × 2,500</strong><small>50k 只生成计划，需预算授权</small></article>
            </div>
            <div className="ghost-progress"><span /><p>等待 Stage 05 唯一 winner</p></div>
          </>
        ) : (
          <>
            <div className="candidate-preview">
              {(stageFive.tables.predictions || []).slice(0, 4).map((item, index) => (
                <article key={String(item.candidate_id)}>
                  <span>PRELIMINARY {String(index + 1).padStart(2, "0")}</span>
                  <strong>{shortCandidate(String(item.candidate_id))}</strong>
                  <small>Stage 05 evidence · 不是最终候选</small>
                </article>
              ))}
            </div>
            <button className="primary-button disabled" disabled title="当前 run 没有 FinalCandidatePackage">
              生成湿实验候选草案
            </button>
            <p className="fine">只有 checksum 验证通过的 Stage 07 FinalCandidatePackage 才能解锁；仍不会自动向供应商下单。</p>
          </>
        )}
      </section>
    </div>
  );
}

function EvidenceList({ stage, limit = 12 }: { stage: Stage; limit?: number }) {
  return (
    <section className="panel evidence-panel">
      <div className="panel-header"><div><p className="panel-kicker">MANIFEST ARTIFACTS</p><h3>证据与下载</h3></div><span>{stage.artifacts.length}</span></div>
      <div className="artifact-list">
        {stage.artifacts.slice(0, limit).map((artifact) => (
          <a key={artifact.artifact_id} href={`/api/v1/artifacts/${artifact.token}?download=true`}>
            <span className={`file-icon file-${artifact.file_format}`}>{artifact.file_format.slice(0, 3).toUpperCase()}</span>
            <div><strong>{artifact.artifact_id}</strong><small>{artifact.role} · {humanBytes(artifact.size_bytes)}</small></div>
            <b>↓</b>
          </a>
        ))}
      </div>
    </section>
  );
}

function StageContent({ stage, run }: { stage: Stage; run: Run }) {
  if (stage.stage_number === 1) return <StageOne stage={stage} />;
  if (stage.stage_number === 2) return <StageTwo stage={stage} run={run} />;
  if (stage.stage_number === 3) return <StageThree stage={stage} />;
  if (stage.stage_number === 4) return <StageFour stage={stage} />;
  if (stage.stage_number === 5) return <StageFive stage={stage} />;
  return <FutureStage stage={stage} run={run} />;
}

function RunWorkspace({
  run,
  onReplay,
  onClone,
  onResume,
  replay,
}: {
  run: Run;
  onReplay: () => void;
  onClone: () => Promise<void>;
  onResume: () => Promise<void>;
  replay?: Replay;
}) {
  const [selected, setSelected] = useState(5);
  const [cloneStatus, setCloneStatus] = useState("");
  const [liveStatus, setLiveStatus] = useState("");
  const stage = run.stages[selected - 1];
  useEffect(() => {
    if (!run.stages.some((item) => item.state === "running")) return;
    const source = new EventSource(`/api/v1/runs/${run.run_key}/events`);
    source.addEventListener("progress", () => setLiveStatus("已收到最新结构化进度"));
    source.onerror = () => setLiveStatus("进度流已断开；刷新后可恢复观察");
    return () => source.close();
  }, [run]);

  async function clone() {
    setCloneStatus("正在复制配置与可用 runtime 输入…");
    try {
      await onClone();
      setCloneStatus("已创建独立草稿；不会覆盖历史 run。");
    } catch (value) {
      setCloneStatus(value instanceof Error ? value.message : "创建草稿失败");
    }
  }
  return (
    <div className="workspace-page">
      {replay && <div className="replay-banner"><strong>DEMO REPLAY</strong><span>正在回放真实审计终态；不会启动 GPU 或修改科学证据。</span><b>{replay.frames.length} frames</b></div>}
      <header className="run-header">
        <div>
          <div className="breadcrumbs"><span>Projects</span><b>/</b><span>{run.project_id}</span><b>/</b><strong>{run.run_id}</strong></div>
          <h1>{run.project_id}</h1>
          <p>{run.run_id} · code {run.code_version} · profile {run.profile_id || "—"}</p>
        </div>
        <div className="run-actions">
          <button type="button" className="secondary-button" onClick={onReplay}>▶ 回放已验证案例</button>
          {run.stages.some((item) => item.state === "operational-failed") && <button type="button" className="secondary-button" onClick={onResume}>恢复未完成任务</button>}
          <button type="button" className="primary-button" onClick={clone}>按相同配置重新运行</button>
        </div>
      </header>
      {(cloneStatus || liveStatus) && <div className="inline-notice"><span>{cloneStatus || liveStatus}</span></div>}
      <StageRail stages={run.stages} selected={selected} onSelect={setSelected} />
      <div className="stage-title-row">
        <div><p className="panel-kicker">STAGE {String(stage.stage_number).padStart(2, "0")}</p><h2>{stage.title}</h2><p>{stateCopy[stage.state].description} · {stage.summary}</p></div>
        <div className="stage-state-block"><Status state={stage.state} /><span>能力：{stage.capability.status}</span></div>
      </div>
      <StageContent stage={stage} run={run} />
    </div>
  );
}

function Dashboard({
  projects,
  onOpen,
  onNew,
}: {
  projects: Project[];
  onOpen: (run: Run) => void;
  onNew: () => void;
}) {
  const latest = projects.flatMap((item) => item.runs).sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  const stops = latest.filter((item) => item.stages.some((stage) => stage.state === "scientific-stop"));
  return (
    <div className="dashboard-page">
      <header className="page-heading"><div><p className="eyebrow">SCIENTIFIC OPERATIONS</p><h1>早上好，今天继续把证据做扎实。</h1><p>从 target 到候选包，每个决定、失败和 checksum 都有出处。</p></div><button className="primary-button" onClick={onNew}>＋ 新建设计</button></header>
      <div className="overview-grid">
        <section className="panel overview-main">
          <div className="panel-header"><div><p className="panel-kicker">ACTIVE PORTFOLIO</p><h3>项目与运行</h3></div><span>{projects.length} projects</span></div>
          <div className="project-list">
            {projects.map((project) => (
              <button type="button" key={project.project_id} onClick={() => project.latest_run && onOpen(project.latest_run)}>
                <span className="project-mark">{project.project_id.slice(0, 2).toUpperCase()}</span>
                <div><strong>{project.project_id}</strong><small>{project.run_count} runs · 最近更新 {formatTime(project.latest_run?.updated_at)}</small></div>
                {project.latest_run && <Status state={project.latest_run.stages.find((stage) => stage.state === "scientific-stop") ? "scientific-stop" : "succeeded"} small />}
                <b>→</b>
              </button>
            ))}
            {projects.length === 0 && <div className="empty-state"><strong>还没有可验证的运行</strong><span>从“新建设计”开始，或用 --runs-root 连接现有 run index。</span></div>}
          </div>
        </section>
        <section className="panel attention-card">
          <p className="panel-kicker">NEEDS ATTENTION</p>
          <strong>{stops.length}</strong>
          <h3>科学停止</h3>
          <p>不是软件故障；需要审视证据或选择下一项验证。</p>
          <span className="val-tag">VAL-003 · Protenix benchmark</span>
        </section>
        <section className="panel environment-card">
          <div className="environment-ring"><span>5/5</span></div>
          <div><p className="panel-kicker">RUNTIME HEALTH</p><h3>环境由 doctor 验证</h3><p>只检查本次配置需要的 backend。</p></div>
        </section>
      </div>
      <section className="recent-section">
        <div className="section-heading"><div><p className="panel-kicker">RECENT RUNS</p><h2>最近运行</h2></div></div>
        <div className="run-cards">
          {latest.slice(0, 3).map((run) => (
            <button key={run.run_key} type="button" onClick={() => onOpen(run)}>
              <div className="run-card-top"><span>{run.project_id}</span><span className="integrity">✓ verified</span></div>
              <h3>{run.run_id}</h3>
              <div className="mini-rail">{run.stages.map((stage) => <span key={stage.stage_number} className={`state-${stage.state}`} />)}</div>
              <div className="run-card-bottom"><span>{formatTime(run.updated_at)}</span><b>查看证据 →</b></div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function NewDesign({
  projects,
  onCreated,
}: {
  projects: Project[];
  onCreated: (projectId: string) => Promise<void>;
}) {
  const [source, setSource] = useState("pse");
  const [stage, setStage] = useState(2);
  const [projectId, setProjectId] = useState("new-design");
  const [sourceValue, setSourceValue] = useState("");
  const [inputFile, setInputFile] = useState<File>();
  const [taxonId, setTaxonId] = useState("9606");
  const [uniprotMode, setUniprotMode] = useState("accession");
  const [executionMode, setExecutionMode] = useState("review-gated");
  const [stage02Method, setStage02Method] = useState("both");
  const [generatedYaml, setGeneratedYaml] = useState("");
  const [createdProject, setCreatedProject] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const availableRuns = projects.flatMap((project) => project.runs);
  const previewYaml = useMemo(() => `schema_version: "0.7"
project_id: ${projectId || "new-design"}
design:
  binder_profile: vhh
  intent: exploratory
workflow:
  execution_mode: ${executionMode}
  stop_after_stage: ${stage}
stage01:
  target:
    source:
      type: ${source === "pse" ? "local-file" : source}
      ${source === "pse" ? "format: pse" : `value: "${sourceValue}"`}
stage02:
  mode: ${source === "pse" ? "detect" : "automatic"}
  methods: [${stage02Method === "both" ? "sasa, scannet" : stage02Method}]
stage03: ${stage >= 3 ? "{profile: boltzgen-vhh-basic-v1}" : "null"}
stage04: ${stage >= 4 ? "{backend: boltzgen-0.3.2}" : "null"}
stage05: ${stage >= 5 ? "{filter_profile: nanobody-filter-standard-v1.5}" : "null"}
stage06: ${stage >= 6 ? "{scale_profile: smoke-1000}" : "null"}
stage07: ${stage >= 7 ? "{final_filter_profile: nanobody-final-v1.5}" : "null"}
`, [executionMode, projectId, source, sourceValue, stage, stage02Method]);
  const yaml = generatedYaml || previewYaml;

  async function createDraft() {
    setBusy(true);
    setActionStatus("正在上传输入并由 Python API 生成 canonical YAML…");
    try {
      let selectedValue = sourceValue.trim();
      let sourceType = source;
      let sourceRunKey: string | undefined;
      if (["pse", "local-file", "sequence"].includes(source)) {
        if (!inputFile) throw new Error("请选择本地输入文件");
        const receipt = await api.upload(inputFile.name, await fileAsBase64(inputFile));
        selectedValue = receipt.upload_token;
        sourceType = "local-file";
      } else if (source === "target-bundle") {
        const selectedRun = availableRuns.find((run) => run.run_key === sourceValue);
        const bundle = selectedRun?.stages[0]?.artifacts.find(
          (item) => item.artifact_id === "target-bundle",
        );
        if (!selectedRun || !bundle) throw new Error("所选 run 没有正式 Target Bundle");
        selectedValue = bundle.token;
        sourceRunKey = selectedRun.run_key;
      } else if (!selectedValue) {
        throw new Error("请填写 PDB ID 或 UniProt 标识");
      }
      if (source === "uniprot" && uniprotMode === "search") {
        sourceType = "uniprot-search";
      }
      const result = await api.createProject({
        project_id: projectId,
        source_type: sourceType,
        source_value: selectedValue,
        taxon_id: sourceType === "uniprot-search" ? Number(taxonId) : undefined,
        execution_mode: executionMode,
        stop_after_stage: stage,
        stage02_method: stage02Method,
        source_run_key: sourceRunKey,
      });
      setCreatedProject(result.project_id);
      setGeneratedYaml(result.config);
      setActionStatus("草稿已创建。下一步先校验 YAML 与运行环境。");
      await onCreated(result.project_id);
    } catch (value) {
      setActionStatus(value instanceof Error ? value.message : "创建项目失败");
    } finally {
      setBusy(false);
    }
  }

  async function validateDraft() {
    if (!createdProject) return;
    setBusy(true);
    setActionStatus("正在进行配置规范化和 doctor 检查…");
    try {
      await api.updateConfig(createdProject, generatedYaml);
      const result = await api.preflight(createdProject);
      const diagnostic = result.diagnostic as { ok?: boolean };
      setActionStatus(
        diagnostic.ok
          ? "配置与所需 backend 检查通过，可以明确确认后真实运行。"
          : "配置有效，但 doctor 发现当前运行所需环境尚未就绪。",
      );
    } catch (value) {
      setActionStatus(value instanceof Error ? value.message : "校验失败");
    } finally {
      setBusy(false);
    }
  }

  async function launch() {
    if (!createdProject) return;
    setBusy(true);
    setActionStatus("正在完成 preflight 并创建独立 worker…");
    try {
      await api.preflight(createdProject);
      const job = await api.launch(createdProject);
      setActionStatus(`真实任务已创建：${String(job.job_id || "job")}。`);
    } catch (value) {
      setActionStatus(value instanceof Error ? value.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="new-page">
      <header className="page-heading compact"><div><p className="eyebrow">NEW DESIGN</p><h1>创建一条可追溯设计任务</h1><p>先讲清输入和科学意图，再决定运行到哪里。</p></div></header>
      <div className="wizard">
        <div className="wizard-steps">
          {["Target 输入", "设计意图", "区域策略", "预算与资源", "检查并启动"].map((item, i) => <div className={i === 0 ? "active" : ""} key={item}><span>{i + 1}</span><strong>{item}</strong></div>)}
        </div>
        <section className="wizard-form">
          <p className="panel-kicker">STEP 01 · TARGET SOURCE</p>
          <h2>你的 target 从哪里来？</h2>
          <p>六条入口最后都会发布同一种 Target Bundle 和 chain A 的 target.cif。</p>
          <div className="two-field-row">
            <label><span>Project ID</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
            <label><span>运行模式</span><select value={executionMode} onChange={(event) => setExecutionMode(event.target.value)}><option value="review-gated">review-gated（推荐）</option><option value="unattended">unattended</option></select></label>
          </div>
          <div className="source-grid">
            {[
              ["pse", "PyMOL PSE", "读取单 target 与红/蓝/黄标注"],
              ["local-file", "PDB / mmCIF", "本地实验结构与编号映射"],
              ["sequence", "FASTA / 序列", "RCSB 检索或 required-MSA 预测"],
              ["pdb-id", "RCSB PDB ID", "下载指定实验结构"],
              ["uniprot", "UniProt", "身份、feature 与候选结构"],
              ["target-bundle", "Target Bundle", "复用已验证上游结果"],
            ].map(([id, title, copy]) => (
              <button type="button" className={source === id ? "selected" : ""} onClick={() => setSource(id)} key={id}><span className="source-icon">{title.slice(0, 1)}</span><strong>{title}</strong><small>{copy}</small></button>
            ))}
          </div>
          <label className="upload-field">
            <span>输入文件、accession 或来源 run</span>
            {["pse", "local-file", "sequence"].includes(source) ? (
              <div><input type="text" readOnly value={inputFile?.name || ""} placeholder="尚未选择文件" /><label className="file-button">浏览…<input type="file" onChange={(event) => setInputFile(event.target.files?.[0])} /></label></div>
            ) : source === "target-bundle" ? (
              <select value={sourceValue} onChange={(event) => setSourceValue(event.target.value)}>
                <option value="">选择一个已有 run</option>
                {availableRuns.map((run) => <option key={run.run_key} value={run.run_key}>{run.project_id} / {run.run_id}</option>)}
              </select>
            ) : (
              <div><input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder={source === "pdb-id" ? "例如 1UBQ" : uniprotMode === "search" ? "例如 EGFR" : "例如 P00533"} /></div>
            )}
          </label>
          {source === "uniprot" && <div className="two-field-row"><label><span>UniProt 解析</span><select value={uniprotMode} onChange={(event) => setUniprotMode(event.target.value)}><option value="accession">精确 accession</option><option value="search">名称 / gene 搜索</option></select></label>{uniprotMode === "search" && <label><span>Taxonomy ID</span><input value={taxonId} onChange={(event) => setTaxonId(event.target.value)} /></label>}</div>}
          <label className="upload-field"><span>Stage 02 方法</span><select value={stage02Method} onChange={(event) => setStage02Method(event.target.value)}><option value="both">SASA + ScanNet（独立比较）</option><option value="sasa">SASA</option><option value="scannet">ScanNet</option></select></label>
          <div className="stage-budget"><span>运行到 Stage</span>{[1,2,3,4,5,6,7].map((value) => <button className={stage === value ? "active" : ""} type="button" onClick={() => setStage(value)} key={value}>{String(value).padStart(2,"0")}</button>)}</div>
          {actionStatus && <div className="form-status">{actionStatus}</div>}
          <div className="wizard-actions">
            <button className="secondary-button" onClick={createDraft} disabled={busy || Boolean(createdProject)}>生成项目草稿</button>
            <button className="secondary-button" onClick={validateDraft} disabled={busy || !createdProject}>校验 + doctor</button>
            <button className="primary-button" onClick={launch} disabled={busy || !createdProject}>确认并真实启动 →</button>
          </div>
        </section>
        <aside className="yaml-preview">
          <div><span>CANONICAL YAML · PREVIEW</span><b>schema 0.7</b></div>
          {createdProject
            ? <textarea aria-label="Canonical YAML" value={generatedYaml} onChange={(event) => setGeneratedYaml(event.target.value)} />
            : <pre>{yaml}</pre>}
          <p>最终配置由 Python API 生成并再次校验；此预览不是运行证据。</p>
        </aside>
      </div>
    </div>
  );
}

function OperationsPage({
  type,
  projects,
  editableProjects,
  selectedRun,
}: {
  type: string;
  projects: Project[];
  editableProjects: string[];
  selectedRun?: Run;
}) {
  const [selectedProject, setSelectedProject] = useState(editableProjects[0] || "");
  const [diagnostic, setDiagnostic] = useState<Record<string, unknown>>();
  const [message, setMessage] = useState("");
  const [decision, setDecision] = useState<Record<string, unknown>>();
  const [selectedOption, setSelectedOption] = useState("");
  const [approvedBy, setApprovedBy] = useState("");
  const runs = projects.flatMap((project) => project.runs);
  const approvals = runs.flatMap((run) =>
    run.stages
      .filter((stage) => stage.state === "awaiting-human-approval")
      .map((stage) => ({ run, stage })),
  );
  const audited = selectedRun || runs[0];
  const approvalRunKey = approvals[0]?.run.run_key;
  useEffect(() => {
    if (type !== "decisions" || !approvalRunKey) return;
    api.decision(approvalRunKey)
      .then((result) => {
        setDecision(result.request);
        const options = result.request.options as Array<Record<string, unknown>> | undefined;
        const first = options?.find((option) => option.eligible !== false);
        setSelectedOption(String(first?.option_id || ""));
      })
      .catch((value: unknown) => {
        setMessage(value instanceof Error ? value.message : "无法读取待审批请求");
      });
  }, [approvalRunKey, type]);

  if (type === "decisions") {
    async function approvePending() {
      if (!approvalRunKey || !selectedOption || !approvedBy.trim()) return;
      setMessage("正在写入不可变 DecisionRecord 并创建 continuation worker…");
      try {
        const job = await api.approveDecision(
          approvalRunKey,
          [selectedOption],
          approvedBy.trim(),
          "Approved in EasyDesign localhost workbench.",
        );
        setMessage(`审批已记录；continuation job：${String(job.job_id || "created")}`);
      } catch (value) {
        setMessage(value instanceof Error ? value.message : "审批失败");
      }
    }
    const options = decision?.options as Array<Record<string, unknown>> | undefined;
    return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">DECISION AUTHORITY</p><h1>待审批</h1><p>身份、结构、hotspot 与高成本预算均保留人工 authority。</p></div></header><section className="panel utility-panel">{approvals.length ? <>{approvals.map(({ run, stage }) => <div className="utility-row" key={`${run.run_key}-${stage.stage_number}`}><div><strong>{run.project_id} · Stage {stage.stage_number}</strong><small>{stage.summary}</small></div><Status state={stage.state} /></div>)}{decision && <div className="decision-form"><p>{String(decision.message || "请选择经过验证的 option")}</p><div className="option-list">{(options || []).map((option) => <label key={String(option.option_id)} className={option.eligible === false ? "ineligible" : ""}><input type="radio" name="decision-option" value={String(option.option_id)} checked={selectedOption === String(option.option_id)} disabled={option.eligible === false} onChange={(event) => setSelectedOption(event.target.value)} /><span><strong>{String(option.label)}</strong><small>{String(option.description || "")}</small></span></label>)}</div><div className="two-field-row"><label><span>批准人</span><input value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} placeholder="真实姓名或稳定 ID" /></label><button className="primary-button" onClick={approvePending} disabled={!selectedOption || !approvedBy.trim()}>确认并继续</button></div></div>}{message && <div className="form-status">{message}</div>}</> : <div className="empty-state"><strong>当前没有待审批事项</strong><span>审批不会被 UI 自动跳过。</span></div>}</section></div>;
  }
  if (type === "environment") {
    async function diagnose() {
      setMessage("正在调用 Python doctor…");
      try {
        const result = await api.preflight(selectedProject);
        setDiagnostic(result.diagnostic);
        setMessage("检查完成；只检查此配置真正需要的 backend。");
      } catch (value) {
        setMessage(value instanceof Error ? value.message : "环境检查失败");
      }
    }
    return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">RUNTIME HEALTH</p><h1>运行环境</h1><p>不自动扫描或安装环境；路径与模型由 runtime profile 明确声明。</p></div></header><section className="panel utility-panel"><div className="two-field-row"><label><span>项目配置</span><select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)}>{editableProjects.map((project) => <option key={project}>{project}</option>)}</select></label><button className="primary-button" onClick={diagnose} disabled={!selectedProject}>运行 doctor</button></div>{message && <div className="form-status">{message}</div>}{diagnostic && <pre className="audit-json">{JSON.stringify(diagnostic, null, 2)}</pre>}</section></div>;
  }
  return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">EVIDENCE CHAIN</p><h1>证据审计</h1><p>所有内容来自当前 manifest 声明并通过 checksum 的 artifact。</p></div></header>{audited ? <><div className="metric-row"><Metric label="Run" value={audited.run_id} /><Metric label="代码版本" value={audited.code_version} /><Metric label="Commit" value={audited.code_commit?.slice(0, 10) || "installed package"} /><Metric label="完整性" value={audited.integrity_status} /></div><section className="panel utility-panel"><div className="audit-chain">{audited.stages.map((stage) => <div key={stage.stage_number}><span>Stage {stage.stage_number}</span><strong>{stage.artifacts.length} artifacts</strong><Status state={stage.state} small /></div>)}</div></section></> : <div className="empty-state"><strong>暂无 run 可审计</strong></div>}</div>;
}

function App() {
  const [data, setData] = useState<ProjectResponse>({ projects: [], editable_projects: [] });
  const [page, setPage] = useState("overview");
  const [selectedRun, setSelectedRun] = useState<Run>();
  const [replay, setReplay] = useState<Replay>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refreshProjects() {
    try {
      setData(await api.projects());
      setError("");
    } catch (value) {
      setError(value instanceof Error ? value.message : "无法连接本地 API");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshProjects();
  }, []);

  function openRun(run: Run) {
    setSelectedRun(run);
    setReplay(undefined);
    setPage("run");
  }

  async function startReplay() {
    if (!selectedRun) return;
    setReplay(await api.replay(selectedRun.run_key));
  }

  async function cloneSelectedRun() {
    if (!selectedRun) return;
    const suffix = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
    const projectId = `${selectedRun.project_id}-rerun-${suffix}`.toLowerCase();
    await api.clone(selectedRun.run_key, projectId);
    await refreshProjects();
  }

  async function resumeSelectedRun() {
    if (!selectedRun) return;
    await api.resume(selectedRun.run_key);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><i /><i /><i /></span><div><strong>EasyDesign</strong><small>Scientific Workbench</small></div></div>
        <nav>{nav.map(([id, label, icon]) => <button type="button" key={id} onClick={() => setPage(id)} className={page === id ? "active" : ""}><span>{icon}</span>{label}{id === "decisions" && <b>0</b>}</button>)}</nav>
        <div className="sidebar-footer">
          <div className="profile-avatar">K</div>
          <div><strong>Local researcher</strong><small>localhost · private</small></div>
          <span className="online-dot" />
        </div>
      </aside>
      <main className="main-shell">
        <div className="topbar">
          <div className="search"><span>⌕</span><input aria-label="搜索项目和运行" placeholder="搜索项目、run、candidate…" /><kbd>⌘ K</kbd></div>
          <div className="top-status"><span className="privacy-badge">● PRIVATE LOCAL</span><button type="button">?</button><button type="button">⋯</button></div>
        </div>
        {error && <div className="api-error"><strong>本地 API 暂不可用</strong><span>{error}</span></div>}
        {loading ? <div className="loading-screen"><span /><strong>正在验证 run index…</strong></div> :
          page === "overview" ? <Dashboard projects={data.projects} onOpen={openRun} onNew={() => setPage("new")} /> :
          page === "new" ? <NewDesign projects={data.projects} onCreated={refreshProjects} /> :
          page === "run" && selectedRun ? <RunWorkspace run={selectedRun} onReplay={startReplay} onClone={cloneSelectedRun} onResume={resumeSelectedRun} replay={replay} /> :
          <OperationsPage type={page} projects={data.projects} editableProjects={data.editable_projects} selectedRun={selectedRun} />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
