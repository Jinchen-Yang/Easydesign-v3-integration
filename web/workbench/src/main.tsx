import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { MolViewer } from "./MolViewer";
import { artifactName, capabilityLabel, stageNames, stageShortNames, stateCopy } from "./product";
import { StageFive as FilterStageFive } from "./StageFive";
import type {
  Artifact,
  ExecutionProgress,
  Project,
  ProjectResponse,
  RemoteExecutor,
  RemoteJob,
  Replay,
  Run,
  Stage,
  StageState,
} from "./types";
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

function ExecutionStage({ stage, run }: { stage: Stage; run: Run }) {
  const [execution, setExecution] = useState<ExecutionProgress>();
  const [executionError, setExecutionError] = useState("");
  const isScale = stage.stage_number === 6;

  useEffect(() => {
    let disposed = false;
    api.execution(run.run_key, stage.stage_number as 4 | 6)
      .then((value) => {
        if (!disposed) setExecution(value);
      })
      .catch((error: unknown) => {
        if (!disposed) {
          setExecutionError(error instanceof Error ? error.message : "执行记录读取失败");
        }
      });
    if (stage.state !== "running") {
      return () => { disposed = true; };
    }
    const source = new EventSource(`/api/v1/runs/${run.run_key}/events`);
    source.addEventListener("progress", (event) => {
      try {
        const value = JSON.parse((event as MessageEvent).data) as ExecutionProgress;
        if (value.stage_id === stage.stage_id && Array.isArray(value.devices)) {
          setExecution(value);
          setExecutionError("");
        }
      } catch {
        setExecutionError("收到的实时进度格式无效；刷新页面可重新读取运行记录");
      }
    });
    source.onerror = () => {
      setExecutionError("实时连接已断开；页面仍保留最近一次结构化进度");
    };
    return () => {
      disposed = true;
      source.close();
    };
  }, [run.run_key, stage.stage_id, stage.stage_number, stage.state]);

  const h = stage.highlights;
  const planned = execution?.planned_candidates
    ?? Number(h.planned_candidates || h.requested_candidates || 0);
  const collected = execution?.collected_candidates
    ?? Number(h.collected_candidates || 0);
  const percentage = planned ? Math.min(100, (collected / planned) * 100) : 0;
  const devices = execution?.devices || [];
  return (
    <div className="content-stack">
      <section className="progress-hero panel">
        <div className="progress-copy">
          <p className="section-label">多 GPU · 可恢复运行</p>
          <h3>
            {collected === planned
              ? `${isScale ? "规模化" : "小规模"}候选已全部生成`
              : `正在进行${isScale ? "规模化" : "小规模"}生成`}
          </h3>
          <p>
            每个{isScale ? "分片" : "设计方案"}独立执行；已完成候选、失败原因和重试记录都会保留。
          </p>
        </div>
        <div className="progress-number"><strong>{percentage.toFixed(0)}%</strong><span>{collected} / {planned}</span></div>
        <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
      </section>
      <div className="metric-row">
        <Metric label={isScale ? "计算分片" : "设计方案"} value={formatNumber(execution?.total_tasks ?? h.strategy_count ?? h.shard_count, 0)} />
        <Metric label="完成任务" value={formatNumber(execution?.succeeded_tasks ?? h.succeeded_tasks, 0)} />
        <Metric label="运行时长" value={`${formatNumber((execution?.elapsed_seconds ?? Number(h.elapsed_seconds || 0)) / 3600, 2)} h`} />
        <Metric label="生成速度" value={formatNumber(execution?.throughput_candidates_per_hour ?? h.throughput_candidates_per_hour, 1)} note="候选 / 小时" />
      </div>
      <section className="panel gpu-panel">
        <div className="panel-header"><div><p className="section-label">运行进度</p><h3>每张 GPU 的任务分配</h3></div><Status state={stage.state} /></div>
        {executionError && <div className="inline-notice execution-warning"><span>{executionError}</span></div>}
        <div className="gpu-lanes">
          {devices.map((device) => (
            <article className="gpu-lane" key={String(device.device)}>
              <div className="gpu-identity">
                <strong>GPU {device.device}</strong>
                <small>
                  {device.current_strategy_id
                    ? `正在运行：${device.current_strategy_id}`
                    : "当前空闲 · 显示历史任务"}
                </small>
                {device.latest_heartbeat_at && (
                  <small>
                    最近心跳：{formatTime(device.latest_heartbeat_at)}
                    {device.heartbeat_elapsed_seconds != null
                      ? ` · 本次任务已运行 ${formatNumber(device.heartbeat_elapsed_seconds / 60, 1)} 分钟`
                      : ""}
                  </small>
                )}
              </div>
              <div className="lane-track">
                {Array.from({ length: Math.max(1, device.assigned_task_count) }).map((_, item) => (
                  <span
                    className={item < device.succeeded_task_count ? "succeeded" : ""}
                    key={item}
                  />
                ))}
              </div>
              <dl className="gpu-stat-grid">
                <div><dt>分配任务</dt><dd>{device.assigned_task_count}</dd></div>
                <div><dt>完成任务</dt><dd>{device.succeeded_task_count}</dd></div>
                <div><dt>执行次数</dt><dd>{device.attempt_count}</dd></div>
                <div><dt>收集候选</dt><dd>{device.collected_candidates}</dd></div>
                <div><dt>重试/失败</dt><dd>{device.failed_attempt_count}</dd></div>
                <div><dt>累计计算</dt><dd>{formatNumber(device.busy_seconds / 3600, 2)} h</dd></div>
              </dl>
            </article>
          ))}
          {!devices.length && execution && (
            <div className="empty-state">
              <strong>此运行未记录历史设备分配</strong>
              <span>总体候选和任务数量仍来自正式进度记录；页面不会扫描目录或解析终端文本补猜。</span>
            </div>
          )}
          {!devices.length && !execution && !executionError && (
            <div className="loading-block">正在验证执行记录…</div>
          )}
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
  if (stage.stage_number === 4) return <ExecutionStage stage={stage} run={run} />;
  if (stage.stage_number === 5) return <FilterStageFive stage={stage} run={run} />;
  if (stage.stage_number === 6 && stage.state !== "not-reached") {
    return <ExecutionStage stage={stage} run={run} />;
  }
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
  const [showTechnical, setShowTechnical] = useState(false);
  const stage = run.stages[selected - 1];

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
      {cloneStatus && <div className="inline-notice"><span>{cloneStatus}</span></div>}
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
  const wizardSteps = ["目标输入", "设计意图", "区域策略", "预算与资源", "检查并启动"];
  const [activeStep, setActiveStep] = useState(1);
  const [source, setSource] = useState("pse");
  const [stage, setStage] = useState(2);
  const [projectId, setProjectId] = useState("new-design");
  const [sourceValue, setSourceValue] = useState("");
  const [inputFile, setInputFile] = useState<File>();
  const [uploadReceipt, setUploadReceipt] = useState<{
    upload_token: string;
    filename: string;
    size_bytes: number;
    sha256: string;
  }>();
  const [uploadState, setUploadState] = useState<
    "idle" | "uploading" | "uploaded" | "failed"
  >("idle");
  const [uploadMessage, setUploadMessage] = useState("");
  const uploadSequence = useRef(0);
  const [taxonId, setTaxonId] = useState("9606");
  const [uniprotMode, setUniprotMode] = useState("accession");
  const [executionMode, setExecutionMode] = useState("review-gated");
  const [designIntent, setDesignIntent] = useState("exploratory");
  const [stage02Method, setStage02Method] = useState("both");
  const [executors, setExecutors] = useState<RemoteExecutor[]>([]);
  const [executorId, setExecutorId] = useState("local");
  const [generatedYaml, setGeneratedYaml] = useState("");
  const [createdProject, setCreatedProject] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [preflightState, setPreflightState] = useState<
    "idle" | "checking" | "passed" | "blocked" | "failed"
  >("idle");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.remoteExecutors()
      .then((value) => setExecutors(value.executors))
      .catch(() => setExecutors([]));
  }, []);
  const availableRuns = projects.flatMap((project) => project.runs);
  const isLocalSource = ["pse", "local-file", "sequence"].includes(source);
  const sourceReady = isLocalSource
    ? uploadState === "uploaded" && Boolean(uploadReceipt)
    : Boolean(sourceValue.trim());
  const projectReady = Boolean(projectId.trim());
  const intentNames: Record<string, string> = {
    exploratory: "探索性设计",
    blocking: "阻断",
    nonblocking: "非阻断",
    detection: "检测",
    imaging: "成像",
  };
  const methodNames: Record<string, string> = {
    both: "SASA 与 ScanNet 分别比较",
    sasa: "SASA 表面区域",
    scannet: "ScanNet 区域",
  };
  const stepStates = [
    sourceReady && projectReady
      ? "已填写"
      : uploadState === "uploading"
        ? "正在接收"
        : "待填写",
    "已设置",
    stage < 2 ? "不运行" : "已设置",
    "已设置",
    preflightState === "passed"
      ? "检查通过"
      : createdProject
        ? "等待检查"
        : "等待生成草稿",
  ];
  const previewYaml = useMemo(() => `schema_version: "0.7"
project_id: ${projectId || "new-design"}
design:
  binder_profile: vhh
  intent: ${designIntent}
workflow:
  execution_mode: ${executionMode}
  stop_after_stage: ${stage}
stage01:
  target:
    source:
      type: ${isLocalSource ? "local-file" : source}
      ${isLocalSource
    ? `path: "inputs/${inputFile?.name || "尚未选择文件"}"\n      format: ${source === "pse" ? "pse" : "auto"}`
    : `value: "${sourceValue}"`}
stage02: ${stage < 2 ? "null" : `
  mode: ${source === "pse" ? "detect" : "automatic"}
  methods: [${stage02Method === "both" ? "sasa, scannet" : stage02Method}]`}
stage03: ${stage >= 3 ? "{profile: boltzgen-vhh-basic-v1}" : "null"}
stage04: ${stage >= 4 ? "{backend: boltzgen-0.3.2}" : "null"}
stage05: ${stage >= 5 ? "{filter_profile: nanobody-filter-standard-v1.5}" : "null"}
stage06: ${stage >= 6 ? "{scale_profile: smoke-1000}" : "null"}
stage07: ${stage >= 7 ? "{final_filter_profile: nanobody-final-v1.5}" : "null"}
`, [
    designIntent,
    executionMode,
    inputFile?.name,
    isLocalSource,
    projectId,
    source,
    sourceValue,
    stage,
    stage02Method,
  ]);
  const yaml = generatedYaml || previewYaml;

  function selectSource(nextSource: string) {
    if (createdProject) return;
    setSource(nextSource);
    setSourceValue("");
    setInputFile(undefined);
    setUploadReceipt(undefined);
    setUploadState("idle");
    setUploadMessage("");
    uploadSequence.current += 1;
  }

  async function receiveInputFile(file?: File) {
    const requestSequence = uploadSequence.current + 1;
    uploadSequence.current = requestSequence;
    setInputFile(file);
    setUploadReceipt(undefined);
    setUploadMessage("");
    if (!file) {
      setUploadState("idle");
      return;
    }
    if (file.size > 64 * 1024 * 1024) {
      setUploadState("failed");
      setUploadMessage("文件超过 64 MiB 上限，请选择更小的输入文件。");
      return;
    }
    setUploadState("uploading");
    setUploadMessage("正在安全接收文件…");
    try {
      const receipt = await api.upload(file.name, await fileAsBase64(file));
      if (uploadSequence.current !== requestSequence) return;
      setUploadReceipt(receipt);
      setUploadState("uploaded");
      setUploadMessage(
        `后端已接收 ${receipt.filename}（${humanBytes(receipt.size_bytes)}），可以继续查看或配置其他步骤。`,
      );
    } catch (value) {
      if (uploadSequence.current !== requestSequence) return;
      setUploadState("failed");
      setUploadMessage(value instanceof Error ? value.message : "文件接收失败");
    }
  }

  async function createDraft() {
    setBusy(true);
    setActionStatus("正在生成标准项目配置…");
    try {
      let selectedValue = sourceValue.trim();
      let sourceType = source;
      let sourceRunKey: string | undefined;
      if (isLocalSource) {
        if (uploadState === "uploading") throw new Error("文件仍在接收，请稍候");
        if (!uploadReceipt) throw new Error("请先选择文件，并等待“后端已接收”的提示");
        selectedValue = uploadReceipt.upload_token;
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
        design_intent: designIntent,
        stop_after_stage: stage,
        stage02_method: stage02Method,
        source_run_key: sourceRunKey,
      });
      setCreatedProject(result.project_id);
      setGeneratedYaml(result.config);
      setActionStatus("草稿已创建。下一步先校验配置和本机运行环境。");
      setPreflightState("idle");
      setActiveStep(5);
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
    setPreflightState("checking");
    setActionStatus("正在检查配置和运行环境…");
    try {
      await api.updateConfig(createdProject, generatedYaml);
      const selectedExecutor = executorId === "local" ? undefined : executorId;
      const result = await api.preflight(createdProject, selectedExecutor);
      const diagnostic = result.diagnostic as { ok?: boolean; status?: string };
      const passed = diagnostic.ok === true || diagnostic.status === "remote-reachable";
      setActionStatus(
        passed
          ? selectedExecutor
            ? `配置有效，远程执行服务器 ${selectedExecutor} 可连接，可以确认后提交。`
            : "配置和所需工具检查通过，可以确认后开始真实运行。"
          : "配置有效，但当前运行所需工具尚未就绪。",
      );
      setPreflightState(passed ? "passed" : "blocked");
    } catch (value) {
      setPreflightState("failed");
      setActionStatus(value instanceof Error ? value.message : "校验失败");
    } finally {
      setBusy(false);
    }
  }

  async function launch() {
    if (!createdProject || preflightState !== "passed") return;
    setBusy(true);
    setActionStatus("正在完成启动前检查并创建独立任务…");
    try {
      const selectedExecutor = executorId === "local" ? undefined : executorId;
      await api.preflight(createdProject, selectedExecutor);
      const job = await api.launch(createdProject, undefined, selectedExecutor);
      setActionStatus(
        selectedExecutor
          ? `任务已提交到 ${selectedExecutor}：${String(job.job_id || "job")}。可在“运行任务”同步进度和结果。`
          : `真实任务已创建：${String(job.job_id || "job")}。`,
      );
    } catch (value) {
      setActionStatus(value instanceof Error ? value.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="new-page">
      <header className="page-heading compact"><div><p className="section-label">开始新的蛋白设计</p><h1>新建设计</h1><p>可以先查看任意步骤；只有最终检查和真实启动需要完整填写。</p></div></header>
      <div className="wizard">
        <div className="wizard-steps" aria-label="新建设计步骤">
          {wizardSteps.map((item, index) => (
            <button
              type="button"
              className={`${activeStep === index + 1 ? "active" : ""} ${
                ["已填写", "已设置", "检查通过"].includes(stepStates[index])
                  ? "complete"
                  : ""
              }`}
              key={item}
              onClick={() => setActiveStep(index + 1)}
              aria-current={activeStep === index + 1 ? "step" : undefined}
            >
              <span>{index + 1}</span>
              <span><strong>{item}</strong><small>{stepStates[index]}</small></span>
            </button>
          ))}
        </div>
        <section className="wizard-form">
          {activeStep === 1 && (
            <>
              <p className="section-label">第一项 · 目标来源</p>
              <h2>你的目标蛋白从哪里来？</h2>
              <p>六种入口最终都会得到同一种规范目标结构包和 chain A 的 target.cif。</p>
              <label className="wide-field"><span>项目名称</span><input value={projectId} disabled={Boolean(createdProject)} onChange={(event) => setProjectId(event.target.value)} /></label>
              <div className="source-grid">
                {[
                  ["pse", "PyMOL PSE", "读取单个目标和红、蓝、黄区域标注"],
                  ["local-file", "PDB / mmCIF", "本地实验结构与编号映射"],
                  ["sequence", "FASTA / 序列", "检索实验结构或使用 MSA 进行预测"],
                  ["pdb-id", "RCSB PDB ID", "下载指定实验结构"],
                  ["uniprot", "UniProt", "读取蛋白身份、注释和候选结构"],
                  ["target-bundle", "目标结构包", "复用已验证的上游结果"],
                ].map(([id, title, copy]) => (
                  <button type="button" disabled={Boolean(createdProject)} className={source === id ? "selected" : ""} onClick={() => selectSource(id)} key={id}><span className="source-icon">{title.slice(0, 1)}</span><strong>{title}</strong><small>{copy}</small></button>
                ))}
              </div>
              <label className="upload-field">
                <span>目标输入</span>
                {isLocalSource ? (
                  <>
                    <div><input type="text" readOnly value={inputFile?.name || ""} placeholder="尚未选择文件" /><label className={`file-button ${createdProject ? "disabled" : ""}`}>浏览…<input aria-label="选择本地文件" type="file" disabled={Boolean(createdProject)} onChange={(event) => void receiveInputFile(event.target.files?.[0])} /></label></div>
                    <div className={`upload-receipt upload-${uploadState}`} role="status">
                      <span className="upload-state-mark" />
                      <div>
                        <strong>{uploadState === "uploaded" ? "文件已接收" : uploadState === "uploading" ? "正在接收文件" : uploadState === "failed" ? "文件接收失败" : "尚未选择文件"}</strong>
                        <small>{uploadMessage || "选择文件后会立即传给本地 EasyDesign 服务，并显示大小和完整性摘要。"}</small>
                        {uploadReceipt && <code>SHA-256 {uploadReceipt.sha256.slice(0, 12)}…</code>}
                      </div>
                    </div>
                  </>
                ) : source === "target-bundle" ? (
                  <select value={sourceValue} disabled={Boolean(createdProject)} onChange={(event) => setSourceValue(event.target.value)}>
                    <option value="">选择一次已有运行</option>
                    {availableRuns.map((run) => <option key={run.run_key} value={run.run_key}>{run.project_id} / {run.run_id}</option>)}
                  </select>
                ) : (
                  <div><input value={sourceValue} disabled={Boolean(createdProject)} onChange={(event) => setSourceValue(event.target.value)} placeholder={source === "pdb-id" ? "例如 1UBQ" : uniprotMode === "search" ? "例如 EGFR" : "例如 P00533"} /></div>
                )}
              </label>
              {source === "uniprot" && <div className="two-field-row"><label><span>UniProt 查找方式</span><select value={uniprotMode} disabled={Boolean(createdProject)} onChange={(event) => setUniprotMode(event.target.value)}><option value="accession">精确 accession</option><option value="search">按名称或基因名搜索</option></select></label>{uniprotMode === "search" && <label><span>物种编号</span><input value={taxonId} disabled={Boolean(createdProject)} onChange={(event) => setTaxonId(event.target.value)} /></label>}</div>}
            </>
          )}
          {activeStep === 2 && (
            <>
              <p className="section-label">第二项 · 设计目标</p>
              <h2>你希望这个 binder 做什么？</h2>
              <p>这里描述设计意图，不会替代后续科学筛选。EasyDesign 1.0 先提供 VHH 主线。</p>
              <div className="binder-choice">
                <button type="button" className="selected"><strong>VHH / Nanobody</strong><small>1.0 已实现的参考主线</small></button>
                <button type="button" disabled><strong>蛋白 Binder</strong><small>后续版本</small></button>
                <button type="button" disabled><strong>肽 Binder</strong><small>后续版本</small></button>
              </div>
              <label className="wide-field"><span>设计意图</span><select value={designIntent} disabled={Boolean(createdProject)} onChange={(event) => setDesignIntent(event.target.value)}><option value="exploratory">探索性设计</option><option value="blocking">阻断</option><option value="nonblocking">非阻断</option><option value="detection">检测</option><option value="imaging">成像</option></select></label>
              <label className="wide-field"><span>遇到科学选择时</span><select value={executionMode} disabled={Boolean(createdProject)} onChange={(event) => setExecutionMode(event.target.value)}><option value="review-gated">暂停并等待人工确认（推荐）</option><option value="unattended">按已配置的确定规则连续运行</option></select></label>
              <div className="notice"><strong>当前选择</strong><span>VHH · {intentNames[designIntent]} · {executionMode === "review-gated" ? "需要时等待确认" : "连续运行"}</span></div>
            </>
          )}
          {activeStep === 3 && (
            <>
              <p className="section-label">第三项 · 结合区域</p>
              <h2>第2步怎样得到设计区域？</h2>
              <p>区域来源会保留证据和编号映射。自动方法彼此独立，不会生成隐藏的融合赢家。</p>
              {source === "pse" && <div className="notice"><strong>先检查 PSE 染色</strong><span>发现标准红、蓝、黄色时作为用户区域；没有标准色时再运行下面选择的自动方法。</span></div>}
              <div className="method-choice">
                {[
                  ["both", "SASA 与 ScanNet", "分别计算和比较，等待人工选择"],
                  ["sasa", "SASA", "表面暴露度和三维连通区域"],
                  ["scannet", "ScanNet", "独立的逐残基 epitope 分数"],
                ].map(([id, title, copy]) => <button type="button" disabled={Boolean(createdProject)} className={stage02Method === id ? "selected" : ""} onClick={() => setStage02Method(id)} key={id}><strong>{title}</strong><small>{copy}</small></button>)}
              </div>
              {executionMode === "unattended" && stage02Method === "both" && <div className="notice error"><strong>需要调整</strong><span>连续运行必须选择一种区域方法；两种方法比较需要人工确认。</span></div>}
            </>
          )}
          {activeStep === 4 && (
            <>
              <p className="section-label">第四项 · 运行范围</p>
              <h2>这次准备运行到哪一步？</h2>
              <p>可以先查看全部范围。真正启动前，系统会按所选步骤检查环境、GPU、模型和磁盘。</p>
              <div className="stage-budget"><span>运行到第几步</span>{[1,2,3,4,5,6,7].map((value) => <button className={stage === value ? "active" : ""} disabled={Boolean(createdProject)} type="button" onClick={() => setStage(value)} key={value}>{value}</button>)}</div>
              <label className="executor-selector">
                <span>在哪里运行</span>
                <select
                  value={executorId}
                  disabled={Boolean(createdProject)}
                  onChange={(event) => {
                    setExecutorId(event.target.value);
                    setPreflightState("idle");
                  }}
                >
                  <option value="local">当前服务器</option>
                  {executors.map((executor) => (
                    <option key={executor.executor_id} value={executor.executor_id}>
                      远程服务器 · {executor.label}
                    </option>
                  ))}
                </select>
                <small>远程任务通过 SSH 提交；输入、配置、版本和结果仍按运行记录校验。</small>
              </label>
              <div className="budget-summary">
                <article><span>第3步基础方案</span><strong>区域 × 7 个 VHH scaffold</strong><small>每个策略 40 个小规模候选</small></article>
                <article><span>第4步小规模生成</span><strong>双 GPU 可恢复运行</strong><small>实际任务量由区域数量决定</small></article>
                <article><span>第6步规模化</span><strong>smoke-1000</strong><small>只有第5步选出唯一策略后才会到达</small></article>
              </div>
              <div className="notice"><strong>本次范围</strong><span>运行到第 {stage} 步：{stageNames[stage - 1]}</span></div>
            </>
          )}
          {activeStep === 5 && (
            <>
              <p className="section-label">第五项 · 启动前检查</p>
              <h2>确认输入、配置和运行环境</h2>
              <p>浏览步骤不需要提前填完；从这里开始才统一判断哪些内容会阻止创建或启动。</p>
              <div className="readiness-list">
                <div className={sourceReady && projectReady ? "ready" : "missing"}><span>{sourceReady && projectReady ? "✓" : "!"}</span><div><strong>目标输入</strong><small>{sourceReady ? (uploadReceipt?.filename || sourceValue || "来源运行已选择") : "尚未形成可用输入"}{!projectReady ? "；项目名称为空" : ""}</small></div><button type="button" onClick={() => setActiveStep(1)}>查看</button></div>
                <div className="ready"><span>✓</span><div><strong>设计意图</strong><small>VHH · {intentNames[designIntent]} · {executionMode === "review-gated" ? "等待确认模式" : "连续运行模式"}</small></div><button type="button" onClick={() => setActiveStep(2)}>查看</button></div>
                <div className={executionMode === "unattended" && stage02Method === "both" ? "missing" : "ready"}><span>{executionMode === "unattended" && stage02Method === "both" ? "!" : "✓"}</span><div><strong>区域策略</strong><small>{methodNames[stage02Method]}</small></div><button type="button" onClick={() => setActiveStep(3)}>查看</button></div>
                <div className="ready"><span>✓</span><div><strong>运行范围</strong><small>运行到第 {stage} 步 · {executorId === "local" ? "当前服务器" : executorId}</small></div><button type="button" onClick={() => setActiveStep(4)}>查看</button></div>
              </div>
              {createdProject && <div className="notice"><strong>项目草稿已创建</strong><span>{createdProject}。目标输入已复制到项目，若要更换目标请新建另一个设计。</span></div>}
              {actionStatus && <div className={`form-status ${preflightState === "failed" || preflightState === "blocked" ? "error" : ""}`}>{actionStatus}</div>}
              <div className="launch-actions">
                <button className="secondary-button" onClick={createDraft} disabled={busy || Boolean(createdProject) || !sourceReady || !projectReady || (executionMode === "unattended" && stage02Method === "both")}>{busy && !createdProject ? "正在生成…" : "1. 生成项目草稿"}</button>
                <button className="secondary-button" onClick={validateDraft} disabled={busy || !createdProject}>{preflightState === "checking" ? "正在检查…" : "2. 检查配置与环境"}</button>
                <button className="primary-button" onClick={launch} disabled={busy || !createdProject || preflightState !== "passed"}>3. 确认并真实启动 →</button>
              </div>
              <p className="launch-help">{!sourceReady ? "请先在“目标输入”选择并等待文件接收完成。" : !createdProject ? "输入已就绪，可以生成项目草稿。" : preflightState !== "passed" ? "项目草稿已建立；检查通过后才会开放真实启动。" : "全部检查通过。点击启动会创建新的、可恢复的运行任务。"}</p>
            </>
          )}
          <div className="wizard-actions">
            <button className="secondary-button" type="button" disabled={activeStep === 1} onClick={() => setActiveStep((value) => Math.max(1, value - 1))}>← 上一步</button>
            <span>第 {activeStep} / 5 项</span>
            <button className="secondary-button" type="button" disabled={activeStep === 5} onClick={() => setActiveStep((value) => Math.min(5, value + 1))}>下一步 →</button>
          </div>
        </section>
        <aside className="yaml-preview">
          <div><span>标准 YAML 配置预览</span><b>schema 0.7</b></div>
          {createdProject
            ? <textarea aria-label="Canonical YAML" value={generatedYaml} onChange={(event) => { setGeneratedYaml(event.target.value); setPreflightState("idle"); }} />
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
  onRefresh,
}: {
  projects: Project[];
  onOpen: (run: Run) => void;
  onRefresh: () => Promise<void>;
}) {
  const [remoteJobs, setRemoteJobs] = useState<RemoteJob[]>([]);
  const [remoteStatus, setRemoteStatus] = useState<Record<string, string>>({});
  const [remoteMessage, setRemoteMessage] = useState("");
  const runs = projects
    .flatMap((project) => project.runs)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  useEffect(() => {
    api.remoteJobs()
      .then((value) => setRemoteJobs(value.jobs as unknown as RemoteJob[]))
      .catch(() => setRemoteJobs([]));
  }, []);
  function remoteKey(job: RemoteJob) {
    return `${job.executor_id}/${job.job_id}`;
  }
  async function observeRemote(job: RemoteJob) {
    const value = await api.remoteJob(job.executor_id, job.job_id);
    const worker = value.worker as { active_state?: string; sub_state?: string };
    const progress = value.progress as { status?: string; collected_candidates?: number; planned_candidates?: number } | undefined;
    setRemoteStatus((current) => ({
      ...current,
      [remoteKey(job)]: progress
        ? `${progress.status || "运行中"} · ${progress.collected_candidates || 0}/${progress.planned_candidates || 0}`
        : `${worker.active_state || "unknown"} / ${worker.sub_state || "unknown"}`,
    }));
  }
  async function syncRemote(job: RemoteJob) {
    setRemoteMessage(`正在从 ${job.executor_id} 同步运行记录…`);
    try {
      await api.syncRemoteJob(job.executor_id, job.job_id, "metadata");
      await onRefresh();
      setRemoteMessage("运行记录已同步；页面现在可以查看远端 manifest 声明的进度与证据。");
    } catch (value) {
      setRemoteMessage(value instanceof Error ? value.message : "远程同步失败");
    }
  }
  async function resumeRemote(job: RemoteJob) {
    setRemoteMessage(`正在请求 ${job.executor_id} 恢复未完成任务…`);
    try {
      await api.resumeRemoteJob(job.executor_id, job.job_id);
      await observeRemote(job);
      setRemoteMessage("恢复任务已提交；已完成分片不会重跑。");
    } catch (value) {
      setRemoteMessage(value instanceof Error ? value.message : "远程恢复失败");
    }
  }
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
      {remoteJobs.length > 0 && (
        <section className="panel remote-task-list">
          <div className="panel-heading"><div><p className="section-label">远程计算</p><h3>其他服务器上的任务</h3></div><span>{remoteJobs.length} 个任务</span></div>
          {remoteJobs.map((job) => (
            <article key={remoteKey(job)} className="remote-task-card">
              <div>
                <strong>{job.project_id} · {job.run_id}</strong>
                <small>{job.executor_id} · 提交于 {formatTime(job.submitted_at)}</small>
                <span>{remoteStatus[remoteKey(job)] || "点击“刷新状态”读取远端结构化进度"}</span>
              </div>
              <div className="remote-task-actions">
                <button type="button" onClick={() => void observeRemote(job)}>刷新状态</button>
                <button type="button" onClick={() => void syncRemote(job)}>同步运行记录</button>
                <button type="button" onClick={() => void resumeRemote(job)}>恢复未完成任务</button>
              </div>
            </article>
          ))}
          {remoteMessage && <div className="form-status">{remoteMessage}</div>}
        </section>
      )}
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
          page === "tasks" ? <TasksPage projects={data.projects} onOpen={openRun} onRefresh={refreshProjects} /> :
          page === "run" && selectedRun ? <RunWorkspace run={selectedRun} onReplay={startReplay} onClone={cloneSelectedRun} onResume={resumeSelectedRun} replay={replay} /> :
          page === "settings" ? <OperationsPage type="environment" projects={data.projects} editableProjects={data.editable_projects} selectedRun={selectedRun} /> :
          <TasksPage projects={data.projects} onOpen={openRun} onRefresh={refreshProjects} />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
