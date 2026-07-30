import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { artifactName, capabilityLabel, stageNames, stageShortNames, stateCopy } from "./product";
import { RegionEditor } from "./RegionEditor";
import { StageFive as FilterStageFive } from "./StageFive";
import { StructureWorkbench } from "./StructureWorkbench";
import type {
  AssistantProviderId,
  AssistantProviderStatus,
  Artifact,
  DesignSession,
  ExecutionProgress,
  InstallStatus,
  Project,
  ProjectDraft,
  ProjectCatalogEntry,
  ProjectResponse,
  RemoteExecutor,
  RemoteJob,
  Replay,
  RegionEditorProjection,
  Run,
  SelfTestRecord,
  Stage,
  StageFormDefinition,
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

const projectIdPattern = /^[a-z0-9][a-z0-9._-]{0,127}$/;

function suggestProjectId(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "")
    .slice(0, 128) || "new-design";
}

type UploadReceipt = {
  schema_version: "0.2";
  upload_token: string;
  filename: string;
  size_bytes: number;
  sha256: string;
  status: string;
  relative_path: string;
};

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
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
  const rail = useRef<HTMLDivElement>(null);
  const buttons = useRef(new Map<number, HTMLButtonElement>());

  useEffect(() => {
    buttons.current.get(selected)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    });
  }, [selected]);

  return (
    <div className="stage-rail" aria-label="七阶段进度" ref={rail}>
      {stages.map((stage) => (
        <button
          key={stage.stage_number}
          ref={(element) => {
            if (element) buttons.current.set(stage.stage_number, element);
            else buttons.current.delete(stage.stage_number);
          }}
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

function completedPrefix(run: Run, stageNumber: number) {
  return run.stages
    .filter((item) => item.stage_number < stageNumber)
    .every((item) => item.state === "succeeded");
}

function stageAccess(stage?: Stage, run?: Run): NonNullable<Stage["access"]> {
  if (stage?.access) return stage.access;
  const reachedStages = run?.stages.filter((item) => item.state !== "not-reached") || [];
  const highestReached = Math.max(
    ...reachedStages.map((item) => item.stage_number),
    0,
  );
  const reached = Boolean(stage && stage.stage_number <= highestReached);
  const isNextConfigurable = Boolean(
    run
    && stage
    && stage.stage_number === highestReached + 1
    && completedPrefix(run, stage.stage_number),
  );
  return {
    stage_number: stage?.stage_number || 0,
    access: reached ? "view-only" : isNextConfigurable ? "configure" : "not-reached",
    locked_by_stage: reached ? stage?.stage_number : undefined,
    reason: reached
      ? "此历史运行没有阶段访问记录，按只读方式安全展示。"
      : isNextConfigurable
        ? "上游步骤已完成，可以配置本步骤。"
        : "本次运行尚未到达此步骤。",
    allowed_actions: reached
      ? ["view", "download"]
      : isNextConfigurable
        ? ["configure"]
        : [],
  };
}

function stageRegionCount(run: Run) {
  const stageTwo = run.stages[1];
  const highlighted = Number(stageTwo?.highlights.region_count || 0);
  return highlighted || (stageTwo?.tables.regions || []).length;
}

function chooseContinuationSession(
  sessions: DesignSession[],
  run: Run,
) {
  const candidates = [...sessions].reverse();
  return candidates.find(
    (item) => item.design_mode === "stepwise"
      && item.run_lineage.includes(run.run_key),
  ) || candidates.find(
    (item) => item.design_mode === "stepwise"
      && item.project_id === run.project_id,
  );
}

function StageContinuationSetup({
  stage,
  run,
  onCompleted,
}: {
  stage: Stage;
  run: Run;
  onCompleted: (runKey: string, destinationStage: number) => Promise<void>;
}) {
  const [definition, setDefinition] = useState<StageFormDefinition>();
  const [loadError, setLoadError] = useState("");
  const [status, setStatus] = useState("");
  const [jobId, setJobId] = useState("");
  const [resourceConfirmed, setResourceConfirmed] = useState(false);
  const expensive = stage.stage_number === 4 || stage.stage_number === 6;

  useEffect(() => {
    const requestedStage = stage.stage_number;
    setDefinition(undefined);
    setLoadError("");
    api.configForm(requestedStage)
      .then((value) => {
        if (value.stage_number !== requestedStage) {
          throw new Error(
            `配置阶段不匹配：请求第${requestedStage}步，实际返回第${value.stage_number}步`,
          );
        }
        setDefinition(value);
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof Error ? error.message : "无法读取本步骤配置");
      });
  }, [stage.stage_number]);

  useEffect(() => {
    if (!jobId) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const record = await api.job(jobId);
        if (disposed) return;
        if (record.status === "queued" || record.status === "running") {
          setStatus(
            record.status === "queued"
              ? `第${stage.stage_number}步已排队，正在等待运行资源…`
              : `第${stage.stage_number}步正在运行；页面会在完成后自动前进。`,
          );
          timer = window.setTimeout(() => void poll(), 1000);
          return;
        }
        setJobId("");
        if (record.status === "succeeded") {
          setStatus(`第${stage.stage_number}步已完成，正在打开下一步…`);
          if (record.run_key) {
            await onCompleted(
              record.run_key,
              Math.min(7, stage.stage_number + 1),
            );
          }
          return;
        }
        if (record.status === "awaiting-human-approval") {
          setStatus(`第${stage.stage_number}步已生成候选，正在打开待确认结果…`);
          if (record.run_key) await onCompleted(record.run_key, stage.stage_number);
          return;
        }
        setStatus(
          record.error
            ? `第${stage.stage_number}步运行失败：${record.error}`
            : `第${stage.stage_number}步没有完成，任务状态：${record.status}`,
        );
      } catch (error) {
        if (!disposed) {
          setJobId("");
          setStatus(error instanceof Error ? error.message : "无法读取任务状态");
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [jobId, onCompleted, stage.stage_number]);

  async function start() {
    if (!definition || jobId || (expensive && !resourceConfirmed)) return;
    setStatus(`正在验证第${stage.stage_number}步配置和运行环境…`);
    try {
      const sessions = await api.designSessions();
      let session = chooseContinuationSession(sessions, run);
      if (!session) {
        session = await api.createDesignSession(
          run.project_id,
          "stepwise",
          "review-gated",
        );
      }
      const response = await api.continueRun(run.run_key, stage.stage_number, {
        session_id: session.session_id,
        execution_mode: session.execution_mode,
        options: definition.defaults,
      });
      setJobId(response.job.job_id);
      setStatus(`第${stage.stage_number}步任务已创建，正在读取真实运行状态…`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "无法启动本步骤");
    }
  }

  if (loadError) {
    return <div className="notice error"><strong>无法配置本步骤</strong><span>{loadError}</span></div>;
  }
  if (!definition) {
    return <div className="loading-block">正在读取第{stage.stage_number}步的版本化配置…</div>;
  }

  const facts = [...definition.presentation.facts];
  if (stage.stage_number === 3) {
    const regionCount = stageRegionCount(run);
    const scaffoldCount = Number(
      facts.find((item) => item.label === "VHH 骨架")?.value || 0,
    );
    const perStrategy = Number(definition.defaults.candidates_per_strategy || 0);
    facts.unshift({
      label: "已批准区域",
      value: regionCount,
      note: "来自第2步正式结果",
    });
    facts.push({
      label: "设计方案",
      value: regionCount * scaffoldCount,
      note: `${regionCount} 个区域 × ${scaffoldCount} 个骨架`,
    });
    facts.push({
      label: "第4步候选预算",
      value: regionCount * scaffoldCount * perStrategy,
      note: "第3步只生成和验证设计文件",
    });
  }

  return (
    <section className="stage-setup panel">
      <div className="stage-setup-copy">
        <p className="section-label">已具备开始条件</p>
        <h3>配置第{stage.stage_number}步：{definition.title}</h3>
        <p>{definition.presentation.description}</p>
      </div>
      <div className="stage-setup-facts">
        {facts.map((fact) => (
          <article key={`${fact.label}-${String(fact.value)}`}>
            <span>{fact.label}</span>
            <strong>{String(fact.value)}</strong>
            {fact.note && <small>{fact.note}</small>}
          </article>
        ))}
      </div>
      {stage.stage_number === 3 && (
        <div className="stage-setup-note">
          <strong>本步不会启动候选生成</strong>
          <span>只把已批准区域写为正向结合约束；其他残基保持中性，并使用固定 BoltzGen 版本验证 YAML。</span>
        </div>
      )}
      {expensive && (
        <label className="stage-resource-confirmation">
          <input
            type="checkbox"
            checked={resourceConfirmed}
            onChange={(event) => setResourceConfirmed(event.target.checked)}
          />
          <span>我确认本步骤会调用真实计算后端；EasyDesign 将先检查 GPU、磁盘和运行环境。</span>
        </label>
      )}
      <div className="stage-setup-actions">
        <button
          type="button"
          className="primary-button"
          disabled={Boolean(jobId) || (expensive && !resourceConfirmed)}
          onClick={() => void start()}
        >
          {jobId ? `第${stage.stage_number}步正在运行…` : definition.presentation.action_label}
        </button>
        <span>配置来自 EasyDesign Python 契约；页面不会自行改写科学参数。</span>
      </div>
      {jobId && (
        <div className="stage-continuation-progress" role="progressbar" aria-label={`第${stage.stage_number}步正在运行`}>
          <span />
        </div>
      )}
      {status && <div className="form-status">{status}</div>}
    </section>
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

function projectionSourceRegions(projection: RegionEditorProjection) {
  const sourceColors: Record<string, "A" | "B" | "C"> = {
    "#FF0000": "A",
    "#0000FF": "B",
    "#FFFF00": "C",
  };
  const selected: Record<"A" | "B" | "C", number[]> = {
    A: [],
    B: [],
    C: [],
  };
  for (const residue of projection.residues) {
    const region = sourceColors[String(residue.source_color || "").toUpperCase()];
    if (region) selected[region].push(residue.label_seq_id);
  }
  return (["A", "B", "C"] as const)
    .map((id) => ({ id, label_seq_ids: selected[id] }))
    .filter((region) => region.label_seq_ids.length > 0);
}

function RunStructureWorkbench({
  run,
  stageNumber,
  regions,
  useSourceColors = false,
}: {
  run: Run;
  stageNumber: 1 | 2;
  regions?: Array<{ id: string; label_seq_ids: number[] }>;
  useSourceColors?: boolean;
}) {
  const [projection, setProjection] = useState<RegionEditorProjection>();
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    setProjection(undefined);
    setError("");
    api.regionEditor(run.run_key)
      .then((value) => {
        if (!disposed) setProjection(value);
      })
      .catch((value: unknown) => {
        if (!disposed) {
          setError(value instanceof Error ? value.message : "无法读取结构与编号映射");
        }
      });
    return () => {
      disposed = true;
    };
  }, [run.run_key]);

  if (error) {
    return <div className="structure-workbench-loading error"><strong>结构工作区不可用</strong><span>{error}</span></div>;
  }
  if (!projection) {
    return <div className="structure-workbench-loading"><span /><strong>正在验证结构与编号映射…</strong></div>;
  }
  const displayedRegions = useSourceColors
    ? projectionSourceRegions(projection)
    : (regions || []);
  return (
    <StructureWorkbench
      runKey={run.run_key}
      stageNumber={stageNumber}
      projection={projection}
      regions={displayedRegions}
    />
  );
}

function StageOne({
  stage,
  run,
  onConfigureNext,
}: {
  stage: Stage;
  run: Run;
  onConfigureNext: () => void;
}) {
  const h = stage.highlights;
  const nextStage = run.stages[1];
  const currentAccess = stageAccess(stage, run);
  const canConfigureNext = stageAccess(nextStage, run).access === "configure";
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
          {canConfigureNext && (
            <button type="button" className="primary-button region-reselect-button" onClick={onConfigureNext}>
              配置下一步：选择结合区域
            </button>
          )}
          {!canConfigureNext && currentAccess.access === "view-only" && (
            <p className="stage-lock-note">🔒 {currentAccess.reason}</p>
          )}
        </section>
        <EvidenceList stage={stage} limit={8} />
      </aside>
      <RunStructureWorkbench run={run} stageNumber={1} useSourceColors />
    </div>
  );
}

function StageTwo({
  stage,
  run,
}: {
  stage: Stage;
  run: Run;
}) {
  const regions = (stage.tables.regions || []).map((item) => ({
    id: String(item.id),
    label_seq_ids: parseLabelRanges(item.label_ranges),
  }));
  const access = stageAccess(stage, run);
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
          <p className="stage-lock-note">🔒 {access.reason}</p>
        </section>
        <EvidenceList stage={stage} />
      </aside>
      <RunStructureWorkbench run={run} stageNumber={2} regions={regions} />
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

function StageContent({
  stage,
  run,
  editingRegions,
  onReselectRegions,
  onCancelRegionEditing,
  onRegionSubmitted,
  onContinuationCompleted,
}: {
  stage: Stage;
  run: Run;
  editingRegions: boolean;
  onReselectRegions: () => void;
  onCancelRegionEditing: () => void;
  onRegionSubmitted: (
    message: string,
    runKey?: string,
    destinationStage?: number,
  ) => void;
  onContinuationCompleted: (
    runKey: string,
    destinationStage: number,
  ) => Promise<void>;
}) {
  if (stage.stage_number === 1) {
    return <StageOne stage={stage} run={run} onConfigureNext={onReselectRegions} />;
  }
  if (stage.stage_number === 2) {
    if (
      (stage.state === "not-reached" || editingRegions)
      && stageAccess(stage, run).access === "configure"
    ) {
      return (
        <RegionEditor
          run={run}
          presentation="embedded"
          onClose={onCancelRegionEditing}
          onSubmitted={onRegionSubmitted}
        />
      );
    }
    return <StageTwo stage={stage} run={run} />;
  }
  if (
    stage.state === "not-reached"
    && completedPrefix(run, stage.stage_number)
    && stageAccess(stage, run).access === "configure"
  ) {
    return (
      <StageContinuationSetup
        stage={stage}
        run={run}
        onCompleted={onContinuationCompleted}
      />
    );
  }
  if (stage.stage_number === 3) {
    return stage.state === "not-reached"
      ? <FutureStage stage={stage} run={run} />
      : <StageThree stage={stage} />;
  }
  if (stage.stage_number === 4) {
    return stage.state === "not-reached"
      ? <FutureStage stage={stage} run={run} />
      : <ExecutionStage stage={stage} run={run} />;
  }
  if (stage.stage_number === 5) {
    return stage.state === "not-reached"
      ? <FutureStage stage={stage} run={run} />
      : <FilterStageFive stage={stage} run={run} />;
  }
  if (stage.stage_number === 6 && stage.state !== "not-reached") {
    return <ExecutionStage stage={stage} run={run} />;
  }
  return <FutureStage stage={stage} run={run} />;
}

function RunWorkspace({
  run,
  onReplay,
  onResume,
  onOpenRun,
  initialStage,
  replay,
}: {
  run: Run;
  onReplay: () => void;
  onResume: () => Promise<void>;
  onOpenRun: (runKey: string, destinationStage?: number) => Promise<void>;
  initialStage?: number;
  replay?: Replay;
}) {
  const latestReachedStage = (
    [...run.stages].reverse().find((item) => item.state !== "not-reached")
      ?.stage_number || 1
  );
  const [selected, setSelected] = useState(initialStage || latestReachedStage);
  const [slideDirection, setSlideDirection] = useState<"forward" | "backward">("forward");
  const [cloneStatus, setCloneStatus] = useState("");
  const [showTechnical, setShowTechnical] = useState(false);
  const [editingRegions, setEditingRegions] = useState(false);
  const stage = run.stages[selected - 1];
  const access = stageAccess(stage, run);

  useEffect(() => {
    setSelected(initialStage || latestReachedStage);
    setEditingRegions(false);
  }, [initialStage, latestReachedStage, run.run_key]);

  function selectStage(next: number) {
    setSlideDirection(next >= selected ? "forward" : "backward");
    setSelected(next);
    setEditingRegions(false);
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
      <StageRail stages={run.stages} selected={selected} onSelect={selectStage} />
      <div className="stage-title-row">
        <div><p className="section-label">设计流程</p><h2>{stageNames[stage.stage_number - 1]}</h2><p>{stateCopy[stage.state].description}</p></div>
        <div className="stage-state-block"><Status state={stage.state} /><span>{capabilityLabel(stage.capability.status)}</span></div>
      </div>
      {access.access === "view-only" && (
        <div className="stage-access-banner">
          <strong>🔒 本步骤仅供查看</strong>
          <span>{access.reason}</span>
        </div>
      )}
      <div
        className={`stage-slide stage-slide-${slideDirection}`}
        key={`${run.run_key}-${selected}-${editingRegions ? "edit" : "view"}`}
      >
        <StageContent
          stage={stage}
          run={run}
          editingRegions={editingRegions}
          onReselectRegions={() => {
            if (stage.stage_number === 1) {
              selectStage(2);
              return;
            }
            setEditingRegions(true);
          }}
          onCancelRegionEditing={() => {
            if (stage.state === "not-reached") selectStage(1);
            else setEditingRegions(false);
          }}
          onRegionSubmitted={(message, runKey, destinationStage) => {
            setCloneStatus(message);
            if (runKey) {
              setEditingRegions(false);
              void onOpenRun(runKey, destinationStage);
            }
          }}
          onContinuationCompleted={onOpenRun}
        />
      </div>
    </div>
  );
}

function Dashboard({
  projects,
  drafts = [],
  onOpen,
  onContinueDraft,
  onNew,
}: {
  projects: Project[];
  drafts: ProjectDraft[];
  onOpen: (run: Run) => void;
  onContinueDraft: (draft: ProjectDraft) => void;
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
        {drafts.map((draft) => (
          <article className="project-card project-draft-card" key={draft.project_id}>
            <header>
              <span className="project-mark">{draft.project_id.slice(0, 2).toUpperCase()}</span>
              <div><h2>{draft.project_id}</h2><p>目标：{draft.target_id}</p></div>
              <span className="status status-draft"><span className="status-mark" />草稿 · 尚未运行</span>
            </header>
            <div className="project-progress">
              {Array.from({ length: 7 }, (_, index) => (
                <span
                  key={index}
                  className={index < draft.configured_through_stage ? "state-ready" : "state-not-reached"}
                />
              ))}
            </div>
            <dl>
              <div><dt>目标输入</dt><dd>{draft.input_type}</dd></div>
              <div><dt>已配置到</dt><dd>第 {draft.configured_through_stage} 步</dd></div>
              <div><dt>下一步建议</dt><dd>继续检查配置并启动首次运行</dd></div>
            </dl>
            <footer>
              <span>更新于 {formatTime(draft.updated_at)}</span>
              <button type="button" onClick={() => onContinueDraft(draft)}>继续设计 →</button>
            </footer>
          </article>
        ))}
        {projects.length === 0 && drafts.length === 0 && <div className="empty-state large"><strong>还没有设计项目</strong><span>点击“新建设计”，从目标结构或序列开始。</span><button className="primary-button" onClick={onNew}>创建第一个项目</button></div>}
      </div>
    </div>
  );
}

function DeveloperSmoke({ onBack }: { onBack: () => void }) {
  const [records, setRecords] = useState<SelfTestRecord[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState<"deterministic-seven-stage" | "real-backend-micro">();
  const [active, setActive] = useState<SelfTestRecord>();
  const [selectedStage, setSelectedStage] = useState(1);
  const [stageJobId, setStageJobId] = useState("");

  async function refresh() {
    try {
      const latest = await api.selfTests();
      setRecords(latest);
      if (active) {
        const updated = latest.find((item) => item.self_test_id === active.self_test_id);
        if (updated) setActive(updated);
      }
      return latest;
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "无法读取自检历史");
      return [];
    }
  }
  useEffect(() => {
    void refresh();
  }, []);

  async function run(mode: SelfTestRecord["mode"]) {
    setBusy(mode);
    setStatus(
      mode === "deterministic-seven-stage"
        ? "正在建立七阶段确定性 manifest 链…"
        : "正在登记真实后端微型自检，并冻结环境预检要求…",
    );
    try {
      const record = await api.runSelfTest(mode);
      setStatus(record.message);
      if (mode === "real-backend-micro") {
        setActive(record);
        setSelectedStage(record.next_stage || 1);
      }
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "开发者自检失败");
    } finally {
      setBusy(undefined);
    }
  }

  useEffect(() => {
    if (!stageJobId) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const job = await api.job(stageJobId);
        if (disposed) return;
        if (job.status === "queued" || job.status === "running") {
          setStatus(
            job.status === "queued"
              ? `第${selectedStage}步已排队，正在等待运行资源…`
              : `第${selectedStage}步正在调用真实后端…`,
          );
          timer = window.setTimeout(() => void poll(), 1200);
          return;
        }
        setStageJobId("");
        const latest = await refresh();
        const updated = latest.find((item) => item.self_test_id === active?.self_test_id);
        if (updated) {
          setActive(updated);
          setSelectedStage(updated.next_stage || updated.current_stage || selectedStage);
          setStatus(updated.message);
        } else {
          setStatus(job.error || `第${selectedStage}步已结束`);
        }
      } catch (error) {
        if (!disposed) {
          setStageJobId("");
          setStatus(error instanceof Error ? error.message : "无法读取自检进度");
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [stageJobId, selectedStage, active?.self_test_id]);

  async function runRealStage() {
    if (!active) return;
    const stage = active.next_stage;
    if (!stage) {
      setStatus("真实后端七阶段微型自检已经结束。");
      return;
    }
    setSelectedStage(stage);
    setStatus(`正在启动第${stage}步真实后端自检…`);
    try {
      const outcome = await api.runSelfTestStage(active.self_test_id, stage);
      setActive(outcome.record);
      if (outcome.job) {
        setStageJobId(outcome.job.job_id);
      } else {
        setSelectedStage(outcome.record.next_stage || stage);
        setStatus(outcome.record.message);
        await refresh();
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "真实后端自检启动失败");
    }
  }

  const selfTestStates = active
    ? Array.from({ length: 7 }, (_, index) => {
        const number = index + 1;
        const value = active.stage_statuses[`stage${String(number).padStart(2, "0")}`];
        return value === "passed"
          ? "succeeded"
          : value === "running"
            ? "running"
            : value === "scientific-stop"
              ? "scientific-stop"
              : value === "operational-failed"
                ? "operational-failed"
                : active.next_stage === number
                  ? "ready"
                  : "not-reached";
      })
    : [];

  return (
    <div className="developer-smoke-page">
      <header className="page-heading compact">
        <div>
          <p className="section-label">与科研项目隔离</p>
          <h1>开发者全阶段自检</h1>
          <p>工程自检验证软件链路；真实后端自检验证外部工具。两者都不能作为科学结果或下单依据。</p>
        </div>
        <button type="button" className="secondary-button" onClick={onBack}>返回设计路线</button>
      </header>
      <div className="self-test-cards">
        <article>
          <span className="self-test-number">第一层</span>
          <h2>快速确定性七步自检</h2>
          <p>不使用网络、GPU 或重型工具，真实创建七个阶段的 attempt、输出引用和运行记录。</p>
          <ul>
            <li>验证 Stage 01–07 工程串联</li>
            <li>验证不可变运行记录和文件完整性</li>
            <li>显式标记为 synthetic-engineering-smoke</li>
          </ul>
          <button type="button" className="primary-button" disabled={Boolean(busy)} onClick={() => void run("deterministic-seven-stage")}>
            {busy === "deterministic-seven-stage" ? "正在运行…" : "运行快速七步自检"}
          </button>
        </article>
        <article>
          <span className="self-test-number">第二层</span>
          <h2>真实后端微型自检</h2>
          <p>使用固定非 APOE 案例调用真实后端；科学停止不算失败，后端崩溃或产物损坏才算失败。</p>
          <ul>
            <li>先检查环境、GPU、磁盘与模型</li>
            <li>Stage 01–05 使用极小预算</li>
            <li>Stage 06/07 使用独立 adapter probe</li>
          </ul>
          <button type="button" className="secondary-button" disabled={Boolean(busy)} onClick={() => void run("real-backend-micro")}>
            {busy === "real-backend-micro" ? "正在登记…" : "准备真实后端自检"}
          </button>
          <small>准备完成后会出现七步滑动工作区；每一步都由你明确点击，采用极小真实预算。</small>
        </article>
      </div>
      {status && <div className="form-status">{status}</div>}
      {active && active.mode === "real-backend-micro" && (
        <section className="panel real-self-test-workspace">
          <div className="panel-heading">
            <div>
              <p className="section-label">固定非 APOE 案例 · 1UBQ</p>
              <h3>真实后端逐阶段微型自检</h3>
              <p>第1–5步运行真实流程；第6、7步各执行一次真实 adapter 探针。</p>
            </div>
            <span>{active.status}</span>
          </div>
          <div className="stage-rail self-test-stage-rail" aria-label="真实后端七阶段自检">
            {selfTestStates.map((stageState, index) => {
              const stage = index + 1;
              return (
                <button
                  key={stage}
                  type="button"
                  className={`stage-node ${selectedStage === stage ? "selected" : ""}`}
                  onClick={() => setSelectedStage(stage)}
                >
                  <span className={`stage-orb state-${stageState}`}>{String(stage).padStart(2, "0")}</span>
                  <span className="stage-name">{stageShortNames[index]}</span>
                  <span className="stage-mini-state">
                    {stageState === "succeeded"
                      ? "已通过"
                      : stageState === "running"
                        ? "正在运行"
                        : stageState === "scientific-stop"
                          ? "科学停止"
                          : stageState === "operational-failed"
                            ? "后端失败"
                            : stageState === "ready"
                              ? "可以开始"
                              : "尚未开始"}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="self-test-stage-detail">
            <div>
              <p className="section-label">第{selectedStage}步</p>
              <h3>{stageNames[selectedStage - 1]}</h3>
              <p>
                {selectedStage <= 5
                  ? "使用一个区域、一个 VHH 骨架和极小候选预算调用真实后端。"
                  : "只执行一个真实 adapter probe，不启动 1,000 或 50,000 规模任务。"}
              </p>
            </div>
            <button
              type="button"
              className="primary-button"
              disabled={
                Boolean(stageJobId)
                || active.status === "blocked"
                || active.next_stage !== selectedStage
              }
              onClick={() => void runRealStage()}
            >
              {stageJobId
                ? `第${selectedStage}步正在运行…`
                : active.next_stage === selectedStage
                  ? `运行第${selectedStage}步`
                  : selfTestStates[selectedStage - 1] === "succeeded"
                    ? "本步骤已通过"
                    : "请先完成前一步"}
            </button>
          </div>
          {active.status === "blocked" && (
            <div className="inline-notice execution-warning">
              请先进入“设置 → 安装与环境”，完成所有环境、许可和模型资产。
            </div>
          )}
          {stageJobId && (
            <div className="stage-continuation-progress" role="progressbar" aria-label="真实后端自检正在运行">
              <span />
            </div>
          )}
        </section>
      )}
      <section className="panel self-test-history">
        <div className="panel-heading">
          <div><p className="section-label">设置中的独立历史</p><h3>最近自检</h3></div>
          <span>{records.length} 条</span>
        </div>
        {records.map((record) => (
          <button
            type="button"
            className="self-test-record"
            key={record.self_test_id}
            onClick={() => {
              if (record.mode === "real-backend-micro") {
                setActive(record);
                setSelectedStage(record.next_stage || record.current_stage || 1);
              }
            }}
          >
            <div>
              <strong>{record.mode === "deterministic-seven-stage" ? "快速确定性七步自检" : "真实后端微型自检"}</strong>
              <small>{formatTime(record.updated_at)} · {record.self_test_id}</small>
              <p>{record.message}</p>
            </div>
            <div>
              <span>工程：{record.engineering_status}</span>
              <span>后端：{record.backend_status}</span>
              <span>科学：{record.scientific_status}</span>
            </div>
          </button>
        ))}
        {!records.length && <div className="empty-state"><strong>还没有自检记录</strong><span>快速自检通常在数秒内完成。</span></div>}
      </section>
    </div>
  );
}

function NewDesign({
  projects,
  initialDraft,
  onCreated,
  onRunReady,
}: {
  projects: Project[];
  initialDraft?: ProjectDraft;
  onCreated: (projectId: string) => Promise<void>;
  onRunReady: (runKey: string) => Promise<void>;
}) {
  const wizardSteps = ["目标输入", "设计意图", "区域策略", "预算与资源", "检查并启动"];
  const [designMode, setDesignMode] = useState<
    "full-workflow" | "stepwise" | "developer-smoke" | undefined
  >();
  const [browsedStage, setBrowsedStage] = useState(1);
  const [activeStep, setActiveStep] = useState(1);
  const [source, setSource] = useState("pse");
  const [stage, setStage] = useState(2);
  const [projectId, setProjectId] = useState("new-design");
  const [sourceValue, setSourceValue] = useState("");
  const [inputFile, setInputFile] = useState<File>();
  const [uploadReceipt, setUploadReceipt] = useState<UploadReceipt>();
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
  const [sessionId, setSessionId] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [preflightState, setPreflightState] = useState<
    "idle" | "checking" | "passed" | "blocked" | "failed"
  >("idle");
  const [stepwisePhase, setStepwisePhase] = useState<
    "idle" | "preparing" | "checking" | "running" | "failed"
  >("idle");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.remoteExecutors()
      .then((value) => setExecutors(value.executors))
      .catch(() => setExecutors([]));
  }, []);
  useEffect(() => {
    if (!initialDraft) return;
    setDesignMode("full-workflow");
    setProjectId(initialDraft.project_id);
    setCreatedProject(initialDraft.project_id);
    setSessionId(initialDraft.session_id || "");
    setStage(initialDraft.configured_through_stage);
    setActiveStep(5);
    setBrowsedStage(initialDraft.configured_through_stage);
    setActionStatus("已恢复上次保存的项目草稿；可继续检查配置和运行环境。");
    api.config(initialDraft.project_id)
      .then((value) => setGeneratedYaml(value.yaml))
      .catch((error: unknown) => {
        setActionStatus(error instanceof Error ? error.message : "无法读取项目草稿配置");
      });
  }, [initialDraft]);
  const availableRuns = projects.flatMap((project) => project.runs);
  const isLocalSource = ["pse", "local-file", "sequence"].includes(source);
  const normalizedProjectId = projectId.trim();
  const projectIdValid = projectIdPattern.test(normalizedProjectId);
  const suggestedProjectId = suggestProjectId(projectId);
  const projectIdGuidance = projectIdValid
    ? ""
    : `项目名称只能使用小写字母、数字、点、下划线和连字符。建议使用 ${suggestedProjectId}。`;
  const sourceReady = isLocalSource
    ? uploadState === "uploaded" && Boolean(uploadReceipt)
    : Boolean(sourceValue.trim());
  const projectReady = projectIdValid;
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

  function selectDesignMode(
    selected: "full-workflow" | "stepwise" | "developer-smoke",
  ) {
    setDesignMode(selected);
    setCreatedProject("");
    setSessionId("");
    setGeneratedYaml("");
    setActionStatus("");
    setPreflightState("idle");
    setStepwisePhase("idle");
    if (selected === "stepwise") {
      setStage(1);
      setActiveStep(1);
      setBrowsedStage(1);
    }
  }

  function selectSource(nextSource: string) {
    if (createdProject) return;
    setSource(nextSource);
    setSourceValue("");
    setInputFile(undefined);
    setUploadReceipt(undefined);
    setUploadState("idle");
    setUploadMessage("");
    setStepwisePhase("idle");
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
    if (!projectIdValid) {
      setUploadState("failed");
      setUploadMessage(projectIdGuidance);
      return;
    }
    if (file.size > 64 * 1024 * 1024) {
      setUploadState("failed");
      setUploadMessage("文件超过 64 MiB 上限，请选择更小的输入文件。");
      return;
    }
    setUploadState("uploading");
    setUploadMessage("正在检查项目名称并计算文件 SHA-256…");
    let received = false;
    try {
      const projectCheck = await api.projectPreflight(projectId.trim());
      if (!projectCheck.available) {
        throw new Error(
          `${projectCheck.reason}。建议名称：${projectCheck.suggested_project_id || "请修改项目名称"}`,
        );
      }
      setUploadMessage("项目名称可用，正在安全接收文件…");
      const receipt = await api.upload(file);
      if (uploadSequence.current !== requestSequence) return;
      received = true;
      setUploadReceipt(receipt);
      setUploadState("uploaded");
      setUploadMessage(
        `本地服务已接收 ${receipt.filename}（${humanBytes(receipt.size_bytes)}），文件完整性已记录。`,
      );
      if (designMode === "stepwise" && source === "pse") {
        await startStepwiseStageOne(receipt);
      }
    } catch (value) {
      if (uploadSequence.current !== requestSequence) return;
      if (!received) {
        setUploadState("failed");
        setUploadMessage(value instanceof Error ? value.message : "文件接收失败");
      }
    }
  }

  async function initializeDraft(receiptOverride?: UploadReceipt) {
      if (!projectIdValid) {
        throw new Error(projectIdGuidance);
      }
      let selectedValue = sourceValue.trim();
      let sourceType = source;
      let sourceRunKey: string | undefined;
      if (isLocalSource) {
        if (uploadState === "uploading") throw new Error("文件仍在接收，请稍候");
        const selectedReceipt = receiptOverride || uploadReceipt;
        if (!selectedReceipt) throw new Error("请先选择文件，并等待“文件已接收”的提示");
        selectedValue = selectedReceipt.upload_token;
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
        project_id: normalizedProjectId,
        source_type: sourceType,
        source_value: selectedValue,
        taxon_id: sourceType === "uniprot-search" ? Number(taxonId) : undefined,
        execution_mode: executionMode,
        design_intent: designIntent,
        stop_after_stage: stage,
        stage02_method: stage02Method,
        source_run_key: sourceRunKey,
        design_mode: designMode || "full-workflow",
      });
      setCreatedProject(result.project_id);
      setSessionId(result.session.session_id);
      setGeneratedYaml(result.config);
      setPreflightState("idle");
      if (designMode === "full-workflow") setActiveStep(5);
      await onCreated(result.project_id);
      return result;
  }

  async function createDraft() {
    setBusy(true);
    setActionStatus("正在生成标准项目配置…");
    try {
      await initializeDraft();
      setActionStatus("草稿已创建。下一步先校验配置和本机运行环境。");
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
      const job = await api.launch(
        createdProject,
        undefined,
        selectedExecutor,
        sessionId || undefined,
        sessionId ? stage : undefined,
      );
      setActionStatus(
        selectedExecutor
          ? `任务已提交到 ${selectedExecutor}：${String(job.job_id || "job")}。可在“运行任务”同步进度和结果。`
          : `真实任务已创建：${String(job.job_id || "job")}。`,
      );
      if (designMode === "stepwise") {
        setActionStatus(
          `第1步任务已创建：${String(job.job_id || "job")}。完成后请在“运行任务”打开结果，`
          + "结构页面会提供“配置下一步：选择结合区域”。"
          + (sessionId ? ` 产品会话：${sessionId}` : ""),
        );
      }
    } catch (value) {
      setActionStatus(value instanceof Error ? value.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }

  async function waitForStageOneJob(jobId: string) {
    for (let attempt = 0; attempt < 1800; attempt += 1) {
      const record = await api.job(jobId);
      const status = String(record.status || "");
      if (!["queued", "running"].includes(status)) return record;
      await wait(1000);
    }
    throw new Error("第1步仍在服务器运行，请到“运行任务”继续查看进度");
  }

  async function startStepwiseStageOne(receiptOverride?: UploadReceipt) {
    if (designMode !== "stepwise" || busy) return;
    setBusy(true);
    setStepwisePhase("preparing");
    setActionStatus("文件已接收，正在建立第1步项目配置…");
    try {
      let activeProject = createdProject;
      let activeConfig = generatedYaml;
      let activeSessionId = sessionId;
      if (!activeProject) {
        const result = await initializeDraft(receiptOverride);
        activeProject = result.project_id;
        activeConfig = result.config;
        activeSessionId = result.session.session_id;
      }
      setStepwisePhase("checking");
      setPreflightState("checking");
      setActionStatus("正在检查第1步需要的 PyMOL 环境和输入配置…");
      await api.updateConfig(activeProject, activeConfig);
      const result = await api.preflight(activeProject);
      const diagnostic = result.diagnostic as { ok?: boolean; status?: string };
      const passed = diagnostic.ok === true || diagnostic.status === "remote-reachable";
      if (!passed) {
        throw new Error("第1步运行环境未通过检查，请在“设置”中修复后重试");
      }
      setPreflightState("passed");
      setStepwisePhase("running");
      setActionStatus("检查通过，正在准备目标结构。完成后会自动进入结构审查…");
      const launched = await api.launch(
        activeProject,
        undefined,
        undefined,
        activeSessionId || undefined,
        activeSessionId ? 1 : undefined,
      );
      const jobId = String(launched.job_id || "");
      if (!jobId) throw new Error("服务器没有返回第1步任务编号");
      const completed = await waitForStageOneJob(jobId);
      const status = String(completed.status || "");
      const runKey = String(completed.run_key || "");
      if (status === "operational-failed") {
        throw new Error(String(completed.error || "第1步运行失败"));
      }
      if (!runKey) {
        throw new Error(`第1步结束状态为 ${status || "unknown"}，但没有可审查的运行记录`);
      }
      setActionStatus("第1步已完成，正在打开目标结构审查…");
      await onCreated(activeProject);
      await onRunReady(runKey);
    } catch (value) {
      setStepwisePhase("failed");
      setPreflightState("failed");
      setActionStatus(value instanceof Error ? value.message : "第1步未能完成");
    } finally {
      setBusy(false);
    }
  }

  if (!designMode) {
    return (
      <div className="new-page">
        <header className="page-heading compact">
          <div>
            <p className="section-label">开始新的蛋白设计</p>
            <h1>选择设计路线</h1>
            <p>三条路线使用相同的科学实现；区别只在于什么时候配置、什么时候暂停。</p>
          </div>
        </header>
        <div className="design-route-grid">
          <button type="button" onClick={() => selectDesignMode("full-workflow")}>
            <span>01</span>
            <div>
              <h2>全流程设计</h2>
              <p>开始前查看并配置第1–7步，然后选择连续运行，或在科学选择处暂停确认。</p>
              <strong>适合：已经明确整体方案和预算</strong>
            </div>
            <b>进入 →</b>
          </button>
          <button type="button" onClick={() => selectDesignMode("stepwise")}>
            <span>02</span>
            <div>
              <h2>按步骤设计</h2>
              <p>现在只提交第1步。结构完成后直接查看 Mol* 结果，再配置第2步。</p>
              <strong>适合：边看结果边做科学决策</strong>
            </div>
            <b>进入 →</b>
          </button>
          <button type="button" onClick={() => selectDesignMode("developer-smoke")}>
            <span>03</span>
            <div>
              <h2>开发者自检</h2>
              <p>先跑快速确定性七步工程自检；需要时再运行真实后端微型检查。</p>
              <strong>结果与科研项目隔离</strong>
            </div>
            <b>进入 →</b>
          </button>
        </div>
      </div>
    );
  }

  if (designMode === "developer-smoke") {
    return (
      <DeveloperSmoke
        onBack={() => setDesignMode(undefined)}
      />
    );
  }

  const visibleWizardSteps = designMode === "stepwise"
    ? [
      {
        step: 1,
        label: "第1步：准备目标结构",
        state: stepwisePhase === "running"
          ? "正在运行"
          : stepwisePhase === "checking" || stepwisePhase === "preparing"
            ? "正在准备"
            : stepwisePhase === "failed"
              ? "需要处理"
              : stepStates[0],
      },
    ]
    : wizardSteps.map((label, index) => ({
      step: index + 1,
      label,
      state: stepStates[index],
    }));

  return (
    <div className="new-page">
      <header className="page-heading compact">
        <div>
          <p className="section-label">开始新的蛋白设计</p>
          <h1>{designMode === "stepwise" ? "按步骤设计" : "全流程设计"}</h1>
          <p>{designMode === "stepwise" ? "本次只要求完成第1步；得到结构后再配置下一步。" : "可以先查看任意科学阶段；只有最终检查和真实启动需要完整填写。"}</p>
        </div>
        <button type="button" className="secondary-button" onClick={() => setDesignMode(undefined)}>更换设计路线</button>
      </header>
      {designMode === "full-workflow" && (
        <div className="scientific-stage-browser" aria-label="七阶段配置浏览">
          {[1,2,3,4,5,6,7].map((value) => (
            <button
              type="button"
              key={value}
              className={browsedStage === value ? "active" : ""}
              onClick={() => {
                setBrowsedStage(value);
                if (value === 1) setActiveStep(1);
                else if (value === 2) setActiveStep(3);
                else setActiveStep(4);
              }}
            >
              <span>{value}</span>
              <strong>{stageShortNames[value - 1]}</strong>
              <small>{value <= stage ? "已纳入本次运行" : "可查看，尚未纳入"}</small>
            </button>
          ))}
        </div>
      )}
      <div className={`wizard ${designMode === "stepwise" ? "wizard-stepwise" : ""}`}>
        <div className="wizard-steps" aria-label="新建设计步骤">
          {visibleWizardSteps.map((item, index) => (
            <button
              type="button"
              className={`${activeStep === item.step ? "active" : ""} ${
                ["已填写", "已设置", "检查通过"].includes(item.state)
                  ? "complete"
                  : ""
              }`}
              key={item.step}
              onClick={() => setActiveStep(item.step)}
              aria-current={activeStep === item.step ? "step" : undefined}
            >
              <span>{index + 1}</span>
              <span><strong>{item.label}</strong><small>{item.state}</small></span>
            </button>
          ))}
        </div>
        <section className="wizard-form">
          {activeStep === 1 && (
            <>
              <p className="section-label">第一项 · 目标来源</p>
              <h2>你的目标蛋白从哪里来？</h2>
              <p>六种入口最终都会得到同一种规范目标结构包和 chain A 的 target.cif。</p>
              <label className="wide-field">
                <span>项目名称</span>
                <input
                  value={projectId}
                  disabled={Boolean(createdProject)}
                  aria-invalid={!projectIdValid}
                  aria-describedby="project-id-guidance"
                  onChange={(event) => {
                    setProjectId(event.target.value);
                    setPreflightState("idle");
                    setActionStatus("");
                  }}
                />
                <small id="project-id-guidance">
                  使用小写字母、数字、点、下划线或连字符；这是项目目录和运行记录的稳定标识。
                </small>
              </label>
              {!projectIdValid && (
                <div className="project-id-warning" role="alert">
                  <span>{projectIdGuidance}</span>
                  <button type="button" onClick={() => setProjectId(suggestedProjectId)}>
                    使用 {suggestedProjectId}
                  </button>
                </div>
              )}
              <div className="source-grid">
                {[
                  ["pse", "PyMOL PSE", "读取单个目标和红、蓝、黄区域标注"],
                  ["local-file", "PDB / mmCIF", "本地实验结构与编号映射"],
                  ["sequence", "FASTA / 序列", "检索实验结构或使用 MSA 进行预测"],
                  ["pdb-id", "RCSB PDB ID", "下载指定实验结构"],
                  ["uniprot", "UniProt", "读取蛋白身份、注释和候选结构"],
                  ["target-bundle", "目标结构包", "复用已验证的上游结果"],
                ].map(([id, title, copy]) => (
                  <button type="button" disabled={Boolean(createdProject) || busy} className={source === id ? "selected" : ""} onClick={() => selectSource(id)} key={id}><span className="source-icon">{title.slice(0, 1)}</span><strong>{title}</strong><small>{copy}</small></button>
                ))}
              </div>
              <label className="upload-field">
                <span>目标输入</span>
                {isLocalSource ? (
                  <>
                    <div><input type="text" readOnly value={inputFile?.name || ""} placeholder="尚未选择文件" /><label className={`file-button ${createdProject || busy || !projectIdValid ? "disabled" : ""}`}>浏览…<input aria-label="选择本地文件" type="file" disabled={Boolean(createdProject) || busy || !projectIdValid} onChange={(event) => void receiveInputFile(event.target.files?.[0])} /></label></div>
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
              {designMode === "stepwise" && (
                <div className={`stepwise-stage-one-status phase-${stepwisePhase}`} role="status">
                  <div>
                    <strong>
                      {stepwisePhase === "preparing" && "正在建立第1步配置"}
                      {stepwisePhase === "checking" && "正在检查输入和运行环境"}
                      {stepwisePhase === "running" && "正在准备目标结构"}
                      {stepwisePhase === "failed" && "第1步需要处理"}
                      {stepwisePhase === "idle" && (source === "pse"
                        ? "上传 PSE 后将自动准备结构"
                        : "输入就绪后开始准备结构")}
                    </strong>
                    <small>
                      {actionStatus || (
                        source === "pse"
                          ? "文件接收成功后，系统会自动完成检查和第1步运行，并直接打开结构审查。"
                          : "所有检查都在当前页面完成，不会再跳到单独的“启动前检查”页面。"
                      )}
                    </small>
                  </div>
                  {sourceReady && source !== "pse" && !createdProject && stepwisePhase === "idle" && (
                    <button
                      className="primary-button"
                      type="button"
                      disabled={busy}
                      onClick={() => void startStepwiseStageOne()}
                    >
                      开始准备结构 →
                    </button>
                  )}
                  {stepwisePhase === "failed" && (
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={busy || (!createdProject && !sourceReady)}
                      onClick={() => void startStepwiseStageOne()}
                    >
                      重新执行第1步
                    </button>
                  )}
                </div>
              )}
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
              <p className="section-label">第 {browsedStage} 步 · 配置要求</p>
              <h2>{stageNames[browsedStage - 1]}</h2>
              <p>可以先查看全部范围。真正启动前，系统会按所选步骤检查环境、GPU、模型和磁盘。</p>
              {browsedStage >= 3 && (
                <div className="stage-requirement-preview">
                  <strong>{browsedStage <= stage ? "已使用标准配置纳入本次运行" : "当前只查看，不会自动改变运行范围"}</strong>
                  <p>
                    {browsedStage === 3 && "把已批准结合区域编译为 BoltzGen 基础方案；非结合区域保持中性。"}
                    {browsedStage === 4 && "对每个设计方案进行小规模、多 GPU、可恢复生成。"}
                    {browsedStage === 5 && "按版本化门槛筛选，并决定是否存在可放大的唯一策略。"}
                    {browsedStage === 6 && "对胜出策略执行分片式规模化生成；高成本预算需要明确授权。"}
                    {browsedStage === 7 && "深度复核、聚类和多样性选择，输出主候选与备选草案。"}
                  </p>
                  {browsedStage > stage && (
                    <button type="button" className="secondary-button" onClick={() => setStage(browsedStage)}>
                      将本次运行范围扩展到第 {browsedStage} 步
                    </button>
                  )}
                </div>
              )}
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
          {designMode === "full-workflow" && activeStep === 5 && (
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
                <button className="secondary-button" onClick={createDraft} disabled={busy || Boolean(createdProject) || !sourceReady || !projectReady || (stage >= 2 && executionMode === "unattended" && stage02Method === "both")}>{busy && !createdProject ? "正在生成…" : "1. 生成项目草稿"}</button>
                <button className="secondary-button" onClick={validateDraft} disabled={busy || !createdProject}>{preflightState === "checking" ? "正在检查…" : "2. 检查配置与环境"}</button>
                <button className="primary-button" onClick={launch} disabled={busy || !createdProject || preflightState !== "passed"}>3. 确认并真实启动 →</button>
              </div>
              <p className="launch-help">{!sourceReady ? "请先在“目标输入”选择并等待文件接收完成。" : !createdProject ? "输入已就绪，可以生成项目草稿。" : preflightState !== "passed" ? "项目草稿已建立；检查通过后才会开放真实启动。" : "全部检查通过。点击启动会创建新的、可恢复的运行任务。"}</p>
            </>
          )}
          {designMode === "full-workflow" && (
            <div className="wizard-actions">
              <button className="secondary-button" type="button" disabled={activeStep === 1} onClick={() => setActiveStep(Math.max(1, activeStep - 1))}>← 上一步</button>
              <span>第 {activeStep} / 5 项</span>
              <button className="secondary-button" type="button" disabled={activeStep === 5} onClick={() => setActiveStep(Math.min(5, activeStep + 1))}>下一步 →</button>
            </div>
          )}
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

function AssistantProviderSettings() {
  const [providers, setProviders] = useState<AssistantProviderStatus[]>([]);
  const [provider, setProvider] = useState<AssistantProviderId>("deepseek");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const response = await api.assistantProviders();
    setProviders(response.providers);
    return response.providers;
  }

  useEffect(() => {
    refresh().catch(() => setProviders([]));
  }, []);

  useEffect(() => {
    const current = providers.find((item) => item.provider === provider);
    setModel(current?.model || "");
    setBaseUrl(current?.base_url || "");
    setApiKey("");
  }, [provider, providers]);

  async function save() {
    if (!model.trim() || !baseUrl.trim() || !apiKey.trim()) {
      setMessage("请明确填写模型 ID、HTTPS endpoint 和 API key；EasyDesign 不设置隐式默认值。");
      return;
    }
    setBusy(true);
    setMessage("正在把密钥写入当前仓库 runtime/secrets 的新 revision…");
    try {
      const status = await api.configureAssistantProvider(provider, {
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey,
      });
      setProviders((current) => [
        ...current.filter((item) => item.provider !== provider),
        status,
      ]);
      setApiKey("");
      setMessage("配置已保存。密钥只显示掩码；两家提供方之间不会自动切换。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "模型 API 配置保存失败");
    } finally {
      setBusy(false);
    }
  }

  const selected = providers.find((item) => item.provider === provider);
  return (
    <section className="panel assistant-provider-settings">
      <div className="panel-heading">
        <div>
          <p className="section-label">可选结构助手</p>
          <h3>DeepSeek / 智谱 GLM</h3>
        </div>
        <span>{selected?.configured ? `已配置 · ${selected.api_key_masked}` : "未配置"}</span>
      </div>
      <p>
        助手只接收文字、阶段、链和当前区域摘要，不上传坐标、MSA 或完整序列。
        未配置时，PyMOL、Mol*、手工选区、SASA 与 ScanNet 仍可正常使用。
      </p>
      <div className="assistant-provider-form">
        <label>
          <span>提供方</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value as AssistantProviderId)}>
            <option value="deepseek">DeepSeek</option>
            <option value="zhipu-glm">智谱 GLM</option>
          </select>
        </label>
        <label>
          <span>模型 ID</span>
          <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="必须显式填写" />
        </label>
        <label>
          <span>HTTPS endpoint</span>
          <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://…/v1" />
        </label>
        <label>
          <span>API key</span>
          <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={selected?.configured ? "填写新值会创建新 revision" : "只写入 runtime/secrets"} />
        </label>
        <button type="button" className="primary-button" disabled={busy} onClick={() => void save()}>
          {busy ? "正在保存…" : "保存提供方配置"}
        </button>
      </div>
      <div className="provider-status-row">
        {providers.map((item) => (
          <span key={item.provider} data-configured={item.configured}>
            {item.provider === "deepseek" ? "DeepSeek" : "智谱 GLM"}：
            {item.configured ? `${item.model} · ${item.api_key_masked}` : "未配置"}
          </span>
        ))}
      </div>
      {message && <div className="form-status">{message}</div>}
    </section>
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
  const [catalog, setCatalog] = useState<ProjectCatalogEntry[]>([]);
  const [selfTests, setSelfTests] = useState<SelfTestRecord[]>([]);
  const [installStatus, setInstallStatus] = useState<InstallStatus>();
  const [acceptedLicenses, setAcceptedLicenses] = useState<string[]>([]);
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
  useEffect(() => {
    if (type !== "environment") return;
    api.projectCatalog().then((value) => setCatalog(value.entries)).catch(() => setCatalog([]));
    api.selfTests().then(setSelfTests).catch(() => setSelfTests([]));
    api.installStatus().then(setInstallStatus).catch(() => setInstallStatus(undefined));
  }, [type]);
  useEffect(() => {
    if (
      type !== "environment"
      || !installStatus?.jobs.some((job) => job.status === "running")
    ) return;
    const timer = window.setInterval(() => {
      api.installStatus().then(setInstallStatus).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [installStatus?.jobs, type]);

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
    async function refreshInstallStatus() {
      setInstallStatus(await api.installStatus());
    }
    async function launchSetup(minimal: boolean, component?: string) {
      const componentLabels: Record<string, string> = {
        "core-ui": "core 与界面",
        "pymol-pse": "PyMOL / PSE",
        "protenix-v2": "Protenix-v2",
        "scannet-epitope": "ScanNet",
        boltzgen: "BoltzGen",
        tnp: "TNP",
      };
      setMessage(
        component
          ? `正在启动 ${componentLabels[component] || component} 安装…`
          : (minimal ? "正在启动 core/UI 安装…" : "正在启动完整仓库内安装…"),
      );
      try {
        const result = await api.launchSetup(minimal, component, acceptedLicenses);
        setMessage(`安装任务 ${result.job_id} 已启动；状态会从结构化注册表更新。`);
        await refreshInstallStatus();
      } catch (value) {
        setMessage(value instanceof Error ? value.message : "安装任务启动失败");
      }
    }
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
    async function changeArchive(entry: ProjectCatalogEntry) {
      setMessage(entry.category === "archived-project-run" ? "正在恢复项目…" : "正在归档项目…");
      try {
        if (entry.category === "archived-project-run") {
          await api.restoreProject(entry.project_id);
        } else {
          await api.archiveProject(entry.project_id);
        }
        const value = await api.projectCatalog();
        setCatalog(value.entries);
        setMessage("项目目录已更新；科学文件和校验值没有被改写。");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "项目目录操作失败");
      }
    }
    const archiveEntries = catalog.filter((entry) => entry.category === "archived-project-run");
    const activeEntries = catalog.filter((entry) => entry.category === "project-run");
    const componentLabels: Record<string, string> = {
      "pymol-pse": "安装 PyMOL / PSE",
      "protenix-v2": "安装 Protenix-v2",
      "scannet-epitope": "安装 ScanNet",
      boltzgen: "安装 BoltzGen",
      tnp: "安装 TNP",
    };
    const installLabel = (status: string) => ({
      "not-installed": "未安装",
      available: "可用",
      failed: "失败",
      "awaiting-approval": "待许可确认",
      "unsupported-platform": "当前平台不支持",
      running: "安装中",
      succeeded: "已完成",
      incomplete: "未完整完成",
      interrupted: "安装中断，可安全重试",
    }[status] || status);
    return <div className="utility-page">
      <header className="page-heading compact"><div><p className="section-label">设置</p><h1>运行环境</h1><p>检查 Protenix、BoltzGen、PyMOL、ScanNet、TNP、GPU 和模型是否满足所选任务。</p></div></header>
      <section className="panel install-center">
        <div className="panel-heading">
          <div><p className="section-label">仓库内自包含运行工作区</p><h3>安装与环境</h3></div>
          <span>{installStatus?.workspace || "正在读取工作区"}</span>
        </div>
        <p className="install-note">环境、模型、缓存和安装日志只写入当前 EasyDesign 仓库的 runtime/。系统代理、Shell 配置、Git 全局配置和 base Conda 不会被修改。</p>
        {installStatus?.plan && <div className={`disk-preflight ${installStatus.plan.disk.sufficient ? "available" : "failed"}`}>
          <strong>{installStatus.plan.disk.sufficient ? "工作区磁盘满足完整安装要求" : "工作区磁盘不足，完整安装会在写入前停止"}</strong>
          <span>
            可用 {humanBytes(installStatus.plan.disk.free_bytes)}
            {" · "}增量峰值约 {humanBytes(installStatus.plan.disk.incremental_peak_bytes)}
            {" · "}安全保留 {humanBytes(installStatus.plan.disk.reserve_bytes)}
          </span>
        </div>}
        <div className="install-actions">
          <button type="button" onClick={() => void launchSetup(true)}>仅安装 core 与界面</button>
          <button className="primary-button" type="button" onClick={() => void launchSetup(false)}>安装全部已确认组件</button>
          <button type="button" onClick={() => void refreshInstallStatus()}>刷新状态</button>
        </div>
        <div className="component-install-grid">
          {Object.entries(componentLabels).map(([component, label]) => {
            const componentPlan = installStatus?.component_plans?.[component];
            const sufficient = componentPlan?.disk.sufficient ?? false;
            return <article key={component}>
              <div>
                <strong>{label}</strong>
                <small>
                  {componentPlan
                    ? `本次峰值约 ${humanBytes(componentPlan.disk.incremental_peak_bytes)}`
                    : "正在计算组件计划"}
                </small>
              </div>
              <button
                type="button"
                disabled={!sufficient}
                onClick={() => void launchSetup(false, component)}
              >
                {sufficient ? "单独安装" : "空间不足"}
              </button>
            </article>;
          })}
        </div>
        <div className="install-grid">
          <div>
            <h4>运行环境</h4>
            {(installStatus?.environments || []).map((item) => <div className="install-row" key={item.environment_id}>
              <strong>{item.environment_id}</strong>
              <span data-status={item.status}>{installLabel(item.status)}</span>
            </div>)}
          </div>
          <div>
            <h4>模型与运行资产</h4>
            {(installStatus?.assets || []).map((item) => {
              const id = item.asset_id || "";
              const checked = acceptedLicenses.includes(id);
              return <div className="install-row asset" key={id}>
                <label>
                  {item.license_confirmation_required && <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => setAcceptedLicenses((current) =>
                      event.target.checked
                        ? [...new Set([...current, id])]
                        : current.filter((value) => value !== id),
                    )}
                  />}
                  <span><strong>{id}</strong><small>{item.license || "未声明许可"}</small></span>
                </label>
                <span data-status={item.status}>{installLabel(item.status)}</span>
              </div>;
            })}
          </div>
        </div>
        {!!installStatus?.jobs.length && <div className="setup-jobs">
          <h4>最近安装任务</h4>
          {installStatus.jobs.slice(0, 4).map((job) => <div className="install-row" key={job.job_id}>
            <span><strong>{job.job_id}</strong><small>{formatTime(job.started_at)}</small></span>
            <span data-status={job.status}>{installLabel(job.status)}</span>
          </div>)}
        </div>}
        <div className="quarantine-summary">隔离区：{installStatus?.quarantine.entries || 0} 项。EasyDesign 不会自动清理；任何清理都需要对精确路径另行批准。</div>
      </section>
      <section className="panel utility-panel"><div className="two-field-row"><label><span>选择一个项目配置</span><select value={selectedProject} onChange={(event) => setSelectedProject(event.target.value)}><option value="">请选择项目</option>{editableProjects.map((project) => <option key={project}>{project}</option>)}</select></label><button className="primary-button" onClick={diagnose} disabled={!selectedProject}>检查运行环境</button></div>{!editableProjects.length && <div className="notice"><strong>当前没有可编辑项目</strong><span>你仍可查看已有运行；新建项目后才能按配置检查环境。</span></div>}{message && <div className="form-status">{message}</div>}{diagnostic && <pre className="audit-json">{JSON.stringify(diagnostic, null, 2)}</pre>}</section>
      <AssistantProviderSettings />
      <section className="panel settings-catalog">
        <div className="panel-heading"><div><p className="section-label">可恢复项目目录</p><h3>活跃项目与归档项目</h3></div><span>{activeEntries.length} 个活跃 · {archiveEntries.length} 个归档</span></div>
        {[...activeEntries, ...archiveEntries].map((entry) => <div className="catalog-row" key={`${entry.category}-${entry.project_id}`}><div><strong>{entry.project_id}</strong><small>{entry.run_count} 次运行 · {entry.category === "project-run" ? "我的项目中可见" : "已从默认列表隐藏"}</small></div><button type="button" onClick={() => void changeArchive(entry)}>{entry.category === "project-run" ? "归档" : "恢复"}</button></div>)}
      </section>
      <section className="panel settings-catalog">
        <div className="panel-heading"><div><p className="section-label">开发者工具</p><h3>自检历史</h3></div><span>{selfTests.length} 条</span></div>
        {selfTests.map((record) => <div className="catalog-row" key={record.self_test_id}><div><strong>{record.mode === "deterministic-seven-stage" ? "快速确定性七步自检" : "真实后端微型自检"}</strong><small>{formatTime(record.updated_at)} · 工程 {record.engineering_status} · 后端 {record.backend_status}</small></div><span>{record.status}</span></div>)}
        {!selfTests.length && <div className="empty-state"><strong>还没有开发者自检记录</strong></div>}
      </section>
      <section className="panel software-info"><p className="section-label">软件信息</p><h3>EasyDesign 本地科研工作台</h3><p>工作台只监听 127.0.0.1。科研结果继续由不可变运行记录和文件完整性校验保护。</p></section>
    </div>;
  }
  return <div className="utility-page"><header className="page-heading compact"><div><p className="eyebrow">EVIDENCE CHAIN</p><h1>证据审计</h1><p>所有内容来自当前 manifest 声明并通过 checksum 的 artifact。</p></div></header>{audited ? <><div className="metric-row"><Metric label="Run" value={audited.run_id} /><Metric label="代码版本" value={audited.code_version} /><Metric label="Commit" value={audited.code_commit?.slice(0, 10) || "installed package"} /><Metric label="完整性" value={audited.integrity_status} /></div><section className="panel utility-panel"><div className="audit-chain">{audited.stages.map((stage) => <div key={stage.stage_number}><span>Stage {stage.stage_number}</span><strong>{stage.artifacts.length} artifacts</strong><Status state={stage.state} small /></div>)}</div></section></> : <div className="empty-state"><strong>暂无 run 可审计</strong></div>}</div>;
}

function App() {
  const [data, setData] = useState<ProjectResponse>({ projects: [], drafts: [], editable_projects: [] });
  const [page, setPage] = useState("projects");
  const [selectedRun, setSelectedRun] = useState<Run>();
  const [selectedRunStage, setSelectedRunStage] = useState<number>();
  const [replay, setReplay] = useState<Replay>();
  const [draftToResume, setDraftToResume] = useState<ProjectDraft>();
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

  async function openCompletedRun(runKey: string, destinationStage?: number) {
    const completedRun = await api.run(runKey);
    openRun(completedRun, destinationStage);
    await refreshProjects();
  }

  useEffect(() => {
    void refreshProjects();
  }, []);

  function openRun(run: Run, destinationStage?: number) {
    setSelectedRun(run);
    setSelectedRunStage(destinationStage);
    setReplay(undefined);
    setPage("run");
  }

  async function startReplay() {
    if (!selectedRun) return;
    setReplay(await api.replay(selectedRun.run_key));
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
          page === "projects" ? <Dashboard
            projects={data.projects}
            drafts={data.drafts}
            onOpen={openRun}
            onContinueDraft={(draft) => {
              setDraftToResume(draft);
              setPage("new");
            }}
            onNew={() => {
              setDraftToResume(undefined);
              setPage("new");
            }}
          /> :
          page === "new" ? (
            <NewDesign
              projects={data.projects}
              initialDraft={draftToResume}
              onCreated={refreshProjects}
              onRunReady={openCompletedRun}
            />
          ) :
          page === "tasks" ? <TasksPage projects={data.projects} onOpen={openRun} onRefresh={refreshProjects} /> :
          page === "run" && selectedRun ? (
            <RunWorkspace
              key={`${selectedRun.run_key}-${selectedRunStage ?? "latest"}`}
              run={selectedRun}
              initialStage={selectedRunStage}
              onReplay={startReplay}
              onResume={resumeSelectedRun}
              onOpenRun={openCompletedRun}
              replay={replay}
            />
          ) :
          page === "settings" ? <OperationsPage type="environment" projects={data.projects} editableProjects={data.editable_projects} selectedRun={selectedRun} /> :
          <TasksPage projects={data.projects} onOpen={openRun} onRefresh={refreshProjects} />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
