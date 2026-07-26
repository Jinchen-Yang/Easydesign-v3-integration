import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { MolViewer } from "./MolViewer";
import { artifactName, capabilityLabel, stageNames, stageShortNames, stateCopy } from "./product";
import { StageFive as FilterStageFive } from "./StageFive";
import type { Artifact, Project, ProjectResponse, Replay, Run, Stage, StageState } from "./types";
import "./styles.css";

const nav = [
  ["projects", "我的项目", "⌂"],
  ["new", "新建设计", "＋"],
  ["tasks", "运行任务", "◎"],
] as const;

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
          title={stageNames[stage.stage_number - 1]}
        >
          <span className={`stage-orb state-${stage.state}`}>
            {String(stage.stage_number).padStart(2, "0")}
          </span>
          <span className="stage-name">{stageShortNames[stage.stage_number - 1]}</span>
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

function parseLabelRanges(value: unknown) {
  const selected: number[] = [];
  for (const token of String(value || "").split(",")) {
    const normalized = token.trim();
    if (!normalized) continue;
    const range = normalized.match(/^(\d+)\.\.(\d+)$/);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      for (let position = start; position <= end; position += 1) selected.push(position);
      continue;
    }
    const position = Number(normalized);
    if (Number.isFinite(position)) selected.push(position);
  }
  return [...new Set(selected)];
}

function StageOne({ stage }: { stage: Stage }) {
  const h = stage.highlights;
  const structure = artifactUrl(stage.artifacts, "target-structure");
  return (
    <div className="structure-workspace">
      <aside className="structure-sidebar">
        <section className="panel">
          <p className="section-label">目标结构</p>
          <h3>{String(h.target_id || "未命名目标")}</h3>
          <div className="compact-metrics">
            <Metric label="序列长度" value={`${formatNumber(h.sequence_length, 0)} aa`} />
            <Metric label="来源" value={String(h.origin || "—")} />
            <Metric label="结构模型数" value={formatNumber(h.model_count, 0)} />
            <Metric label="缺失的 CA 原子" value={formatNumber(h.missing_ca_count, 0)} />
          </div>
        </section>
        <EvidenceList stage={stage} limit={8} />
      </aside>
      <MolViewer structureUrl={structure} />
    </div>
  );
}

function StageTwo({ stage, run }: { stage: Stage; run: Run }) {
  const stageOne = run.stages[0];
  const structure = artifactUrl(stageOne.artifacts, "target-structure");
  const regions = (stage.tables.regions || []).map((item) => ({
    id: String(item.id),
    label_seq_ids: parseLabelRanges(item.label_ranges),
  }));
  return (
    <div className="structure-workspace">
      <aside className="structure-sidebar">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">已确认的结合区域</p>
              <h3>{formatNumber(stage.highlights.region_count, 0)} 个区域</h3>
            </div>
            <span className="evidence-chip">
              {stage.highlights.region_source === "pse-color-annotation"
                ? "来自 PSE 染色"
                : String(stage.highlights.region_source || "—")}
            </span>
          </div>
          <div className="region-list">
            {(stage.tables.regions || []).map((region) => (
              <div className={`region-row region-${String(region.id).toLowerCase()}`} key={String(region.id)}>
                <strong>{String(region.id)}</strong>
                <div>
                  <span>{formatNumber(region.member_count, 0)} 个残基</span>
                  <small>规范编号 {String(region.label_ranges)}</small>
                </div>
              </div>
            ))}
          </div>
          <p className="fine">
            用户区域属于人工结构先验，不自动等同于经过能量学验证的结合热点；确认人：
            {String(stage.highlights.approved_by || "—")}。
          </p>
        </section>
        <EvidenceList stage={stage} />
      </aside>
      <MolViewer structureUrl={structure} regions={regions} />
    </div>
  );
}

function StageThree({ stage }: { stage: Stage }) {
  const rows = stage.tables.strategies || [];
  const regions = [...new Set(rows.map((row) => String(row.region_id)))];
  const scaffolds = [...new Set(rows.map((row) => String(row.scaffold_id)))];
  const matrix = new Map(rows.map((row) => [`${row.region_id}:${row.scaffold_id}`, row]));
  return (
    <div className="content-stack">
      <div className="metric-row">
        <Metric label="设计方案" value={formatNumber(stage.highlights.strategy_count, 0)} note="结合区域 × VHH 骨架" />
        <Metric label="结合区域" value={formatNumber(stage.highlights.region_count, 0)} />
        <Metric label="VHH 骨架" value={formatNumber(stage.highlights.scaffold_count, 0)} />
        <Metric label="小规模候选预算" value={formatNumber(stage.highlights.planned_candidates, 0)} note="完整候选" />
      </div>
      <section className="panel matrix-panel">
        <div className="panel-header">
          <div><p className="section-label">BoltzGen 基础模板</p><h3>结合区域 × VHH 骨架设计矩阵</h3></div>
          <span className="evidence-chip">非结合区域残基保持中性</span>
        </div>
        <div className="design-matrix">
          <div className="matrix-corner">结合区域</div>
          {scaffolds.map((scaffold) => <strong key={scaffold}>{scaffold}</strong>)}
          {regions.flatMap((region) => [
            <strong className="matrix-region" key={`${region}-label`}>{region}</strong>,
            ...scaffolds.map((scaffold) => {
              const row = matrix.get(`${region}:${scaffold}`);
              return (
                <button type="button" key={`${region}-${scaffold}`} title={String(row?.strategy_id || "")}>
                  <b>{formatNumber(row?.candidates_per_strategy, 0)}</b>
                  <small>个候选</small>
                  <span>✓ 配置有效</span>
                </button>
              );
            }),
          ])}
        </div>
        <p className="matrix-note">
          每个区域内的残基被写为正向结合约束；所有未标注残基不添加反向约束。原始 BoltzGen YAML 可在“技术记录”中查看和下载。
        </p>
      </section>
      <EvidenceList stage={stage} />
    </div>
  );
}

function StageFour({ stage }: { stage: Stage }) {
  const h = stage.highlights;
  const planned = Number(h.planned_candidates || 0);
  const collected = Number(h.collected_candidates || 0);
  const percentage = planned ? Math.min(100, (collected / planned) * 100) : 0;
  const devices = stage.tables.devices || [];
  return (
    <div className="content-stack">
      <section className="progress-hero panel">
        <div className="progress-copy">
          <p className="section-label">多 GPU · 可恢复运行</p>
          <h3>{collected === planned ? "小规模候选已全部生成" : "正在生成小规模候选"}</h3>
          <p>每个设计方案独立执行；已完成候选、失败原因和重试记录都会保留。</p>
        </div>
        <div className="progress-number"><strong>{percentage.toFixed(0)}%</strong><span>{collected} / {planned}</span></div>
        <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
      </section>
      <div className="metric-row">
        <Metric label="设计方案" value={formatNumber(h.strategy_count, 0)} />
        <Metric label="完成任务" value={formatNumber(h.succeeded_tasks, 0)} />
        <Metric label="运行时长" value={`${formatNumber(Number(h.elapsed_seconds || 0) / 3600, 2)} h`} />
        <Metric label="生成速度" value={formatNumber(h.throughput_candidates_per_hour, 1)} note="候选 / 小时" />
      </div>
      <section className="panel gpu-panel">
        <div className="panel-header"><div><p className="section-label">运行进度</p><h3>每张 GPU 的任务分配</h3></div><Status state={stage.state} /></div>
        <div className="gpu-lanes">
          {devices.map((device) => {
            const completed = Number(device.completed ?? device.succeeded ?? device.completed_tasks ?? 0);
            return (
            <div className="gpu-lane" key={String(device.device)}>
              <div><strong>GPU {String(device.device)}</strong><small>按正式任务记录分配</small></div>
              <div className="lane-track">
                {Array.from({ length: Math.max(1, completed) }).map((_, item) => <span key={item} />)}
              </div>
              <b>已完成 {completed}</b>
            </div>
          )})}
          {!devices.length && <div className="empty-state"><strong>当前运行记录没有设备分配信息</strong><span>页面不会根据目录或终端文本猜测 GPU。</span></div>}
        </div>
      </section>
      <EvidenceList stage={stage} />
    </div>
  );
}

function shortCandidate(value: string) {
  const match = value.match(/candidate-(\d+)$/);
  return match ? `candidate-${match[1]}` : value;
}

function FutureStage({ stage, run }: { stage: Stage; run: Run }) {
  const stageFive = run.stages[4];
  const isSix = stage.stage_number === 6;
  const upstreamReason = stageFive.state === "scientific-stop"
    ? "第5步没有选出可放大的设计策略，因此本次运行不能进入这一阶段。"
    : "当前运行还没有生成进入这一阶段所需的完整结果。";
  return (
    <div className="content-stack">
      <section className="not-reached-card">
        <div>
          <p className="section-label">本次运行 · {run.project_id}</p>
          <h3>本步骤尚未开始</h3>
          <p>{upstreamReason}</p>
        </div>
        <Status state="not-reached" />
      </section>
      <section className="panel capability-panel">
        <div className="capability-head">
          <div><span className="capability-label">软件能力</span><h3>{stage.capability.summary}</h3><p>软件已经具备这项能力，不代表本次运行执行过这一步。</p></div>
          <span className="implemented-badge">{capabilityLabel(stage.capability.status)}</span>
        </div>
        {isSix ? (
          <>
            <div className="profile-cards">
              <article><span>工程验证方案</span><strong>2 × 500</strong><small>两张 GPU，各运行一个可恢复分片</small></article>
              <article><span>正式规模方案</span><strong>20 × 2,500</strong><small>50,000 个候选需要单独确认预算</small></article>
            </div>
            <div className="ghost-progress"><span /><p>等待第5步确定唯一的可放大策略</p></div>
          </>
        ) : (
          <>
            <div className="candidate-preview">
              {(stageFive.tables.predictions || []).slice(0, 4).map((item, index) => (
                <article key={String(item.candidate_id)}>
                  <span>初步候选 {String(index + 1).padStart(2, "0")}</span>
                  <strong>{shortCandidate(String(item.candidate_id))}</strong>
                  <small>来自第5步 · 不是最终候选</small>
                </article>
              ))}
            </div>
            <button className="primary-button disabled" disabled title="当前运行没有最终候选包">
              生成湿实验候选草案
            </button>
            <p className="fine">只有文件完整性校验通过的第7步最终候选包才能解锁；软件仍不会自动向供应商下单。</p>
          </>
        )}
      </section>
    </div>
  );
}

function EvidenceList({ stage, limit = 12 }: { stage: Stage; limit?: number }) {
  return (
    <section className="panel evidence-panel">
      <div className="panel-header"><div><p className="section-label">本步骤输出</p><h3>结果文件与下载</h3></div><span>{stage.artifacts.length} 个文件</span></div>
      <div className="artifact-list">
        {stage.artifacts.slice(0, limit).map((artifact) => (
          <a key={artifact.artifact_id} href={`/api/v1/artifacts/${artifact.token}?download=true`}>
            <span className={`file-icon file-${artifact.file_format}`}>{artifact.file_format.slice(0, 3).toUpperCase()}</span>
            <div><strong>{artifactName(artifact.artifact_id)}</strong><small>{humanBytes(artifact.size_bytes)}</small></div>
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
  if (stage.stage_number === 5) return <FilterStageFive stage={stage} run={run} />;
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
  const [showTechnical, setShowTechnical] = useState(false);
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
      {replay && <div className="replay-banner"><strong>演示回放</strong><span>正在回放已保存的真实结果；不会启动 GPU，也不会修改科学结果。</span><b>{replay.frames.length} 个时间点</b></div>}
      <header className="run-header">
        <div>
          <div className="breadcrumbs"><span>我的项目</span><b>/</b><strong>{run.project_id}</strong></div>
          <h1>{run.project_id}</h1>
          <p>本次运行已进行到第 {Math.max(...run.stages.filter((item) => item.state !== "not-reached").map((item) => item.stage_number), 0)} 步 · 最近更新 {formatTime(run.updated_at)}</p>
        </div>
        <div className="run-actions">
          <button type="button" className="secondary-button" onClick={() => setShowTechnical((value) => !value)}>技术记录</button>
          <button type="button" className="secondary-button" onClick={onReplay}>▶ 演示回放</button>
          {run.stages.some((item) => item.state === "operational-failed") && <button type="button" className="secondary-button" onClick={onResume}>恢复未完成任务</button>}
          <button type="button" className="primary-button" onClick={clone}>按相同配置重新运行</button>
        </div>
      </header>
      {(cloneStatus || liveStatus) && <div className="inline-notice"><span>{cloneStatus || liveStatus}</span></div>}
      {showTechnical && (
        <section className="technical-record panel">
          <div className="panel-heading"><div><p className="section-label">专家信息</p><h3>运行技术记录</h3></div><span>文件完整性已验证</span></div>
          <dl>
            <div><dt>内部运行编号</dt><dd><code>{run.run_id}</code></dd></div>
            <div><dt>EasyDesign 版本</dt><dd>{run.code_version}</dd></div>
            <div><dt>源代码提交</dt><dd><code>{run.code_commit?.slice(0, 12) || "来自已安装的软件包"}</code></dd></div>
            <div><dt>运行配置</dt><dd>{run.profile_id || "未记录"}</dd></div>
          </dl>
          <div className="audit-chain">
            {run.stages.map((item) => (
              <div key={item.stage_number}>
                <span>{stageNames[item.stage_number - 1]}</span>
                <strong>{item.artifacts.length} 个输出文件</strong>
                <Status state={item.state} small />
              </div>
            ))}
          </div>
        </section>
      )}
      <StageRail stages={run.stages} selected={selected} onSelect={setSelected} />
      <div className="stage-title-row">
        <div><p className="section-label">设计流程</p><h2>{stageNames[stage.stage_number - 1]}</h2><p>{stateCopy[stage.state].description}</p></div>
        <div className="stage-state-block"><Status state={stage.state} /><span>{capabilityLabel(stage.capability.status)}</span></div>
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
  function runState(run: Run): StageState {
    if (run.stages.some((stage) => stage.state === "operational-failed")) return "operational-failed";
    if (run.stages.some((stage) => stage.state === "awaiting-human-approval")) return "awaiting-human-approval";
    if (run.stages.some((stage) => stage.state === "running")) return "running";
    if (run.stages.some((stage) => stage.state === "scientific-stop")) return "scientific-stop";
    return "succeeded";
  }
  return (
    <div className="dashboard-page">
      <header className="page-heading"><div><p className="section-label">EasyDesign 科研工作台</p><h1>我的项目</h1><p>查看每个设计项目当前得到的结论，以及下一步需要做什么。</p></div><button className="primary-button" onClick={onNew}>＋ 新建设计</button></header>
      <div className="project-cards">
        {projects.map((project) => {
          const run = project.latest_run;
          if (!run) return null;
          const state = runState(run);
          const lastStage = [...run.stages].reverse().find((item) => item.state !== "not-reached");
          const nextStep = state === "scientific-stop"
            ? "查看未通过原因，决定是否开展受控复核"
            : state === "awaiting-human-approval"
              ? "完成待确认事项后继续"
              : state === "running"
                ? "等待当前计算完成"
                : "查看结果或创建一次新运行";
          return (
            <article className="project-card" key={project.project_id}>
              <header>
                <span className="project-mark">{project.project_id.slice(0, 2).toUpperCase()}</span>
                <div><h2>{project.project_id}</h2><p>目标：{String(run.stages[0]?.highlights.target_id || project.project_id)}</p></div>
                <Status state={state} />
              </header>
              <div className="project-progress">
                {run.stages.map((stage) => <span key={stage.stage_number} className={`state-${stage.state}`} title={stageNames[stage.stage_number - 1]} />)}
              </div>
              <dl>
                <div><dt>当前进度</dt><dd>{lastStage ? stageNames[lastStage.stage_number - 1] : "尚未开始"}</dd></div>
                <div><dt>最近结论</dt><dd>{stateCopy[state].description}</dd></div>
                <div><dt>下一步建议</dt><dd>{nextStep}</dd></div>
              </dl>
              <footer><span>{project.run_count} 次历史运行 · 更新于 {formatTime(run.updated_at)}</span><button type="button" onClick={() => onOpen(run)}>查看项目 →</button></footer>
            </article>
          );
        })}
        {projects.length === 0 && <div className="empty-state large"><strong>还没有设计项目</strong><span>点击“新建设计”，从目标结构或序列开始。</span><button className="primary-button" onClick={onNew}>创建第一个项目</button></div>}
      </div>
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
    setActionStatus("正在上传输入并生成标准配置…");
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
        if (!selectedRun || !bundle) throw new Error("所选运行没有正式目标结构包");
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
    setActionStatus("正在检查配置和运行环境…");
    try {
      await api.updateConfig(createdProject, generatedYaml);
      const result = await api.preflight(createdProject);
      const diagnostic = result.diagnostic as { ok?: boolean };
      setActionStatus(
        diagnostic.ok
          ? "配置和所需工具检查通过，可以确认后开始真实运行。"
          : "配置有效，但当前运行所需工具尚未就绪。",
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
    setActionStatus("正在完成启动前检查并创建独立任务…");
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
      <header className="page-heading compact"><div><p className="section-label">开始新的蛋白设计</p><h1>新建设计</h1><p>选择目标来源、结合区域方法和运行范围，系统会同步生成标准配置。</p></div></header>
      <div className="wizard">
        <div className="wizard-steps">
          {["目标输入", "设计意图", "区域策略", "预算与资源", "检查并启动"].map((item, i) => <div className={i === 0 ? "active" : ""} key={item}><span>{i + 1}</span><strong>{item}</strong></div>)}
        </div>
        <section className="wizard-form">
          <p className="section-label">第一项 · 目标来源</p>
          <h2>你的目标蛋白从哪里来？</h2>
          <p>六种入口最终都会得到同一种规范目标结构包和 chain A 的 target.cif。</p>
          <div className="two-field-row">
            <label><span>项目名称</span><input value={projectId} onChange={(event) => setProjectId(event.target.value)} /></label>
            <label><span>运行方式</span><select value={executionMode} onChange={(event) => setExecutionMode(event.target.value)}><option value="review-gated">遇到科学选择时等待确认（推荐）</option><option value="unattended">按预设规则连续运行</option></select></label>
          </div>
          <div className="source-grid">
            {[
              ["pse", "PyMOL PSE", "读取单个目标和红、蓝、黄区域标注"],
              ["local-file", "PDB / mmCIF", "本地实验结构与编号映射"],
              ["sequence", "FASTA / 序列", "检索实验结构或使用 MSA 进行预测"],
              ["pdb-id", "RCSB PDB ID", "下载指定实验结构"],
              ["uniprot", "UniProt", "读取蛋白身份、注释和候选结构"],
              ["target-bundle", "目标结构包", "复用已验证的上游结果"],
            ].map(([id, title, copy]) => (
              <button type="button" className={source === id ? "selected" : ""} onClick={() => setSource(id)} key={id}><span className="source-icon">{title.slice(0, 1)}</span><strong>{title}</strong><small>{copy}</small></button>
            ))}
          </div>
          <label className="upload-field">
            <span>输入文件、UniProt accession 或来源运行</span>
            {["pse", "local-file", "sequence"].includes(source) ? (
              <div><input type="text" readOnly value={inputFile?.name || ""} placeholder="尚未选择文件" /><label className="file-button">浏览…<input type="file" onChange={(event) => setInputFile(event.target.files?.[0])} /></label></div>
            ) : source === "target-bundle" ? (
              <select value={sourceValue} onChange={(event) => setSourceValue(event.target.value)}>
                <option value="">选择一次已有运行</option>
                {availableRuns.map((run) => <option key={run.run_key} value={run.run_key}>{run.project_id} / {run.run_id}</option>)}
              </select>
            ) : (
              <div><input value={sourceValue} onChange={(event) => setSourceValue(event.target.value)} placeholder={source === "pdb-id" ? "例如 1UBQ" : uniprotMode === "search" ? "例如 EGFR" : "例如 P00533"} /></div>
            )}
          </label>
          {source === "uniprot" && <div className="two-field-row"><label><span>UniProt 查找方式</span><select value={uniprotMode} onChange={(event) => setUniprotMode(event.target.value)}><option value="accession">精确 accession</option><option value="search">按名称或基因名搜索</option></select></label>{uniprotMode === "search" && <label><span>物种编号</span><input value={taxonId} onChange={(event) => setTaxonId(event.target.value)} /></label>}</div>}
          <label className="upload-field"><span>第2步区域选择方法</span><select value={stage02Method} onChange={(event) => setStage02Method(event.target.value)}><option value="both">SASA + ScanNet（分别比较）</option><option value="sasa">SASA</option><option value="scannet">ScanNet</option></select></label>
          <div className="stage-budget"><span>运行到第几步</span>{[1,2,3,4,5,6,7].map((value) => <button className={stage === value ? "active" : ""} type="button" onClick={() => setStage(value)} key={value}>{value}</button>)}</div>
          {actionStatus && <div className="form-status">{actionStatus}</div>}
          <div className="wizard-actions">
            <button className="secondary-button" onClick={createDraft} disabled={busy || Boolean(createdProject)}>生成项目草稿</button>
            <button className="secondary-button" onClick={validateDraft} disabled={busy || !createdProject}>检查配置与环境</button>
            <button className="primary-button" onClick={launch} disabled={busy || !createdProject}>确认并真实启动 →</button>
          </div>
        </section>
        <aside className="yaml-preview">
          <div><span>标准 YAML 配置预览</span><b>schema 0.7</b></div>
          {createdProject
            ? <textarea aria-label="Canonical YAML" value={generatedYaml} onChange={(event) => setGeneratedYaml(event.target.value)} />
            : <pre>{yaml}</pre>}
          <p>最终配置由 EasyDesign 生成并再次检查；右侧为专家可编辑视图。</p>
        </aside>
      </div>
    </div>
  );
}

function TasksPage({
  projects,
  onOpen,
}: {
  projects: Project[];
  onOpen: (run: Run) => void;
}) {
  const runs = projects
    .flatMap((project) => project.runs)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  function stateForRun(run: Run): StageState {
    for (const state of ["operational-failed", "awaiting-human-approval", "running", "scientific-stop"] as StageState[]) {
      if (run.stages.some((stage) => stage.state === state)) return state;
    }
    return "succeeded";
  }
  return (
    <div className="tasks-page">
      <header className="page-heading compact">
        <div><p className="section-label">所有计算与确认事项</p><h1>运行任务</h1><p>查看正在运行、等待确认、已完成或未达到继续条件的任务。</p></div>
      </header>
      <section className="panel task-list">
        <div className="panel-heading"><div><p className="section-label">最近更新</p><h3>全部运行</h3></div><span>{runs.length} 个任务</span></div>
        {runs.map((run) => {
          const state = stateForRun(run);
          const active = [...run.stages].reverse().find((stage) => stage.state !== "not-reached");
          return (
            <button type="button" key={run.run_key} onClick={() => onOpen(run)}>
              <span className="project-mark">{run.project_id.slice(0, 2).toUpperCase()}</span>
              <div className="task-main"><strong>{run.project_id}</strong><small>{active ? stageNames[active.stage_number - 1] : "尚未开始"} · 更新于 {formatTime(run.updated_at)}</small></div>
              <div className="mini-rail">{run.stages.map((stage) => <span key={stage.stage_number} className={`state-${stage.state}`} />)}</div>
              <Status state={state} />
              <b>→</b>
            </button>
          );
        })}
        {runs.length === 0 && <div className="empty-state large"><strong>还没有运行任务</strong><span>从“新建设计”创建第一个任务。</span></div>}
      </section>
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
  const [hotspotYaml, setHotspotYaml] = useState("");
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
      .catch(async () => {
        try {
          const result = await api.hotspotReview(approvalRunKey);
          setHotspotYaml(result.yaml);
          setMessage("这是 Stage 02 hotspot 审批模板；请补全批准人、理由与 acknowledgement。");
        } catch (value) {
          setMessage(value instanceof Error ? value.message : "无法读取待审批请求");
        }
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
    async function approveHotspotPending() {
      if (!approvalRunKey || !hotspotYaml.trim()) return;
      setMessage("正在验证区域、编号、证据限制并发布不可变 hotspots.yaml…");
      try {
        await api.approveHotspots(approvalRunKey, hotspotYaml);
        setMessage("Hotspot 已批准；请返回 run 工作台使用“恢复未完成任务”继续后续 Stage。");
      } catch (value) {
        setMessage(value instanceof Error ? value.message : "Hotspot 审批失败");
      }
    }
    const options = decision?.options as Array<Record<string, unknown>> | undefined;
    return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">DECISION AUTHORITY</p><h1>待审批</h1><p>身份、结构、hotspot 与高成本预算均保留人工 authority。</p></div></header><section className="panel utility-panel">{approvals.length ? <>{approvals.map(({ run, stage }) => <div className="utility-row" key={`${run.run_key}-${stage.stage_number}`}><div><strong>{run.project_id} · Stage {stage.stage_number}</strong><small>{stage.summary}</small></div><Status state={stage.state} /></div>)}{decision && <div className="decision-form"><p>{String(decision.message || "请选择经过验证的 option")}</p><div className="option-list">{(options || []).map((option) => <label key={String(option.option_id)} className={option.eligible === false ? "ineligible" : ""}><input type="radio" name="decision-option" value={String(option.option_id)} checked={selectedOption === String(option.option_id)} disabled={option.eligible === false} onChange={(event) => setSelectedOption(event.target.value)} /><span><strong>{String(option.label)}</strong><small>{String(option.description || "")}</small></span></label>)}</div><div className="two-field-row"><label><span>批准人</span><input value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} placeholder="真实姓名或稳定 ID" /></label><button className="primary-button" onClick={approvePending} disabled={!selectedOption || !approvedBy.trim()}>确认并继续</button></div></div>}{hotspotYaml && <div className="decision-form"><p>Stage 02 Hotspot 审批文件</p><textarea aria-label="Hotspot approval YAML" value={hotspotYaml} onChange={(event) => setHotspotYaml(event.target.value)} /><button className="primary-button" onClick={approveHotspotPending}>验证并批准 hotspots.yaml</button></div>}{message && <div className="form-status">{message}</div>}</> : <div className="empty-state"><strong>当前没有待审批事项</strong><span>审批不会被 UI 自动跳过。</span></div>}</section></div>;
  }
  if (type === "environment") {
    async function diagnose() {
      setMessage("正在检查当前配置需要的运行工具…");
      try {
        const result = await api.preflight(selectedProject);
        setDiagnostic(result.diagnostic);
        setMessage("检查完成；这里只检查所选配置真正需要的工具。");
      } catch (value) {
        setMessage(value instanceof Error ? value.message : "环境检查失败");
      }
    }
    return <div className="utility-page"><header className="page-heading compact"><div><p className="section-label">设置</p><h1>运行环境</h1><p>检查 Protenix、BoltzGen、PyMOL、ScanNet、TNP、GPU 和模型是否满足所选任务。</p></div></header><section className="panel utility-panel"><div className="two-field-row"><label><span>选择一个项目配置</span><select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)}><option value="">请选择项目</option>{editableProjects.map((project) => <option key={project}>{project}</option>)}</select></label><button className="primary-button" onClick={diagnose} disabled={!selectedProject}>检查运行环境</button></div>{!editableProjects.length && <div className="notice"><strong>当前没有可编辑项目</strong><span>你仍可查看已有运行；新建项目后才能按配置检查环境。</span></div>}{message && <div className="form-status">{message}</div>}{diagnostic && <pre className="audit-json">{JSON.stringify(diagnostic, null, 2)}</pre>}</section><section className="panel software-info"><p className="section-label">软件信息</p><h3>EasyDesign 本地科研工作台</h3><p>工作台只监听 127.0.0.1。科研结果继续由不可变运行记录和文件完整性校验保护。</p></section></div>;
  }
  return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">EVIDENCE CHAIN</p><h1>证据审计</h1><p>所有内容来自当前 manifest 声明并通过 checksum 的 artifact。</p></div></header>{audited ? <><div className="metric-row"><Metric label="Run" value={audited.run_id} /><Metric label="代码版本" value={audited.code_version} /><Metric label="Commit" value={audited.code_commit?.slice(0, 10) || "installed package"} /><Metric label="完整性" value={audited.integrity_status} /></div><section className="panel utility-panel"><div className="audit-chain">{audited.stages.map((stage) => <div key={stage.stage_number}><span>Stage {stage.stage_number}</span><strong>{stage.artifacts.length} artifacts</strong><Status state={stage.state} small /></div>)}</div></section></> : <div className="empty-state"><strong>暂无 run 可审计</strong></div>}</div>;
}

function App() {
  const [data, setData] = useState<ProjectResponse>({ projects: [], editable_projects: [] });
  const [page, setPage] = useState("projects");
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
  const pendingCount = data.projects
    .flatMap((project) => project.runs)
    .flatMap((run) => run.stages)
    .filter((stage) => stage.state === "awaiting-human-approval").length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark"><i /><i /><i /></span><div><strong>EasyDesign</strong><small>蛋白设计工作台</small></div></div>
        <nav>{nav.map(([id, label, icon]) => <button type="button" key={id} onClick={() => setPage(id)} className={page === id || (id === "tasks" && page === "run") ? "active" : ""}><span>{icon}</span>{label}</button>)}</nav>
        <div className="sidebar-footer">
          <div className="profile-avatar">K</div>
          <div><strong>本地科研工作区</strong><small>仅在当前电脑访问</small></div>
          <span className="online-dot" />
        </div>
      </aside>
      <main className="main-shell">
        <div className="topbar">
          <div className="search"><span>⌕</span><input aria-label="搜索项目和运行" placeholder="搜索项目、运行或候选…" /><kbd>⌘ K</kbd></div>
          <div className="top-status">
            <button type="button" className="notification-button" onClick={() => setPage("tasks")}>待确认 {pendingCount > 0 && <b>{pendingCount}</b>}</button>
            <button type="button" onClick={() => setPage("settings")}>设置</button>
          </div>
        </div>
        {error && <div className="api-error"><strong>本地 API 暂不可用</strong><span>{error}</span></div>}
        {loading ? <div className="loading-screen"><span /><strong>正在读取运行记录…</strong></div> :
          page === "projects" ? <Dashboard projects={data.projects} onOpen={openRun} onNew={() => setPage("new")} /> :
          page === "new" ? <NewDesign projects={data.projects} onCreated={refreshProjects} /> :
          page === "tasks" ? <TasksPage projects={data.projects} onOpen={openRun} /> :
          page === "run" && selectedRun ? <RunWorkspace run={selectedRun} onReplay={startReplay} onClone={cloneSelectedRun} onResume={resumeSelectedRun} replay={replay} /> :
          page === "settings" ? <OperationsPage type="environment" projects={data.projects} editableProjects={data.editable_projects} selectedRun={selectedRun} /> :
          <TasksPage projects={data.projects} onOpen={openRun} />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
