import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "./api";
import { StructureWorkbench } from "./StructureWorkbench";
import type { DesignSession, RegionEditorProjection, Run } from "./types";

type RegionId = "A" | "B" | "C";
type SelectionMode = "manual" | "sasa" | "scannet" | "both";

const REGION_COLORS: Record<RegionId, string> = {
  A: "#FF4D55",
  B: "#3F7CF7",
  C: "#FFD447",
};

function sourceRegion(color?: string): RegionId | undefined {
  if (color?.toUpperCase() === "#FF0000") return "A";
  if (color?.toUpperCase() === "#0000FF") return "B";
  if (color?.toUpperCase() === "#FFFF00") return "C";
  return undefined;
}

function parseResidueList(value: string): number[] {
  const result = new Set<number>();
  for (const raw of value.split(/[\s,，;；]+/)) {
    const token = raw.trim();
    if (!token) continue;
    const range = token.match(/^(\d+)(?:\.\.|-)(\d+)$/);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      if (end < start || end - start > 10_000) {
        throw new Error(`无效残基范围：${token}`);
      }
      for (let value = start; value <= end; value += 1) result.add(value);
      continue;
    }
    if (!/^\d+$/.test(token)) throw new Error(`无法识别残基编号：${token}`);
    result.add(Number(token));
  }
  return [...result].sort((left, right) => left - right);
}

function regionCounts(selection: Map<number, RegionId>) {
  return (["A", "B", "C"] as RegionId[]).map((id) => ({
    id,
    count: [...selection.values()].filter((value) => value === id).length,
  }));
}

function upstreamSelection(projection: RegionEditorProjection) {
  const current = new Map<number, RegionId>();
  const source = new Map<number, RegionId>();
  for (const residue of projection.residues) {
    const sourceId = sourceRegion(residue.source_color);
    if (sourceId) source.set(residue.label_seq_id, sourceId);
    if (residue.current_region) {
      current.set(residue.label_seq_id, residue.current_region);
    }
  }
  return current.size > 0 ? current : source;
}

export function RegionEditor({
  run,
  onClose,
  onSubmitted,
  presentation = "dialog",
}: {
  run: Run;
  onClose: () => void;
  onSubmitted: (message: string, runKey?: string, destinationStage?: number) => void;
  presentation?: "dialog" | "embedded";
}) {
  const embedded = presentation === "embedded";
  const [projection, setProjection] = useState<RegionEditorProjection>();
  const [loadingError, setLoadingError] = useState("");
  const [selection, setSelection] = useState<Map<number, RegionId>>(new Map());
  const [tool, setTool] = useState<RegionId>("A");
  const [showSource, setShowSource] = useState(false);
  const [showCurrent, setShowCurrent] = useState(false);
  const [pasteValue, setPasteValue] = useState("");
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("manual");
  const [allowStructuralOnly, setAllowStructuralOnly] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeJobId, setActiveJobId] = useState("");
  const lastSelected = useRef<number | undefined>(undefined);
  const completionMessage = useRef("");
  const submittedCallback = useRef(onSubmitted);

  useEffect(() => {
    submittedCallback.current = onSubmitted;
  }, [onSubmitted]);

  useEffect(() => {
    if (!activeJobId) return;
    let disposed = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const record = await api.job(activeJobId);
        if (disposed) return;
        const jobStatus = String(record.status || "");
        if (jobStatus === "queued" || jobStatus === "running") {
          setBusy(true);
          setStatus(
            jobStatus === "queued"
              ? "第2步任务已排队，正在等待执行资源…"
              : "第2步正在运行；页面会自动更新，无需重复提交。",
          );
          timer = window.setTimeout(() => void poll(), 1000);
          return;
        }
        setBusy(false);
        setActiveJobId("");
        if (jobStatus === "succeeded") {
          const message = completionMessage.current
            || "第2步已完成，现在可以配置下一阶段。";
          setStatus(message);
          const runKey = String(record.run_key || "");
          submittedCallback.current(message, runKey || undefined, 3);
          return;
        }
        if (jobStatus === "awaiting-human-approval") {
          const message = "自动候选区域已生成，等待你比较并确认后再进入下一阶段。";
          setStatus(message);
          const runKey = String(record.run_key || "");
          submittedCallback.current(message, runKey || undefined, 2);
          return;
        }
        const error = String(record.error || "");
        setStatus(
          error
            ? `第2步运行失败：${error}`
            : `第2步没有完成，任务状态：${jobStatus || "未知"}`,
        );
      } catch (error) {
        if (!disposed) {
          setBusy(false);
          setActiveJobId("");
          setStatus(error instanceof Error ? error.message : "无法读取第2步任务进度");
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [activeJobId]);

  useEffect(() => {
    let disposed = false;
    api.regionEditor(run.run_key)
      .then((value) => {
        if (!disposed) {
          const initial = upstreamSelection(value);
          setProjection(value);
          setSelection(initial);
          if (initial.size > 0) {
            setStatus(
              `已将上游的 ${initial.size} 个区域残基复制到本次可编辑层；可直接修改，或选择“从空白开始”。`,
            );
          }
        }
      })
      .catch((error: unknown) => {
        if (!disposed) {
          setLoadingError(error instanceof Error ? error.message : "无法读取区域编辑数据");
        }
      });
    return () => { disposed = true; };
  }, [run.run_key]);

  const displayRegions = useMemo(() => {
    if (!projection) return [];
    const displayed = new Map<number, RegionId>();
    if (showSource) {
      for (const residue of projection.residues) {
        const region = sourceRegion(residue.source_color);
        if (region) displayed.set(residue.label_seq_id, region);
      }
    }
    if (showCurrent) {
      for (const residue of projection.residues) {
        if (residue.current_region) {
          displayed.set(residue.label_seq_id, residue.current_region);
        }
      }
    }
    for (const [label, region] of selection) displayed.set(label, region);
    return (["A", "B", "C"] as RegionId[]).map((id) => ({
      id,
      label_seq_ids: [...displayed.entries()]
        .filter(([, region]) => region === id)
        .map(([label]) => label)
        .sort((left, right) => left - right),
    }));
  }, [projection, selection, showCurrent, showSource]);
  const editableRegions = useMemo(
    () => (["A", "B", "C"] as RegionId[]).map((id) => ({
      id,
      label_seq_ids: [...selection.entries()]
        .filter(([, region]) => region === id)
        .map(([label]) => label)
        .sort((left, right) => left - right),
    })),
    [selection],
  );

  function colorResidue(labelSeqId: number, shift = false) {
    if (!projection) return;
    const available = new Set(projection.residues.map((item) => item.label_seq_id));
    const targets = new Set([labelSeqId]);
    if (shift && lastSelected.current != null) {
      const minimum = Math.min(lastSelected.current, labelSeqId);
      const maximum = Math.max(lastSelected.current, labelSeqId);
      for (const residue of projection.residues) {
        if (residue.label_seq_id >= minimum && residue.label_seq_id <= maximum) {
          targets.add(residue.label_seq_id);
        }
      }
    }
    const removeFromCurrentRegion = selection.get(labelSeqId) === tool;
    setSelection((current) => {
      const next = new Map(current);
      for (const label of targets) {
        if (!available.has(label)) continue;
        if (next.get(label) === tool) next.delete(label);
        else next.set(label, tool);
      }
      return next;
    });
    lastSelected.current = labelSeqId;
    setStatus(
      removeFromCurrentRegion
        ? `已取消规范残基 ${labelSeqId} 的区域 ${tool} 选择。`
        : `已将规范残基 ${labelSeqId} 设为区域 ${tool}。`,
    );
  }

  function loadUpstream() {
    if (!projection) return;
    const restored = upstreamSelection(projection);
    setSelection(restored);
    setShowSource(false);
    setShowCurrent(false);
    setStatus(
      restored.size > 0
        ? `已恢复上游的 ${restored.size} 个区域残基；原始运行没有被修改。`
        : "当前上游没有 PSE 标注或已批准区域，本次编辑层保持为空。",
    );
  }

  function startBlank() {
    setSelection(new Map());
    setShowSource(false);
    setShowCurrent(false);
    lastSelected.current = undefined;
    setStatus("已隐藏上游颜色并清空本次编辑层；现在可以从空白结构重新选择。");
  }

  function chooseTool(nextTool: RegionId) {
    setTool(nextTool);
    setStatus(`已切换到区域 ${nextTool}；再次点击同一区域的残基即可取消选择。`);
  }

  function pasteSelection() {
    if (!projection) return;
    try {
      const values = parseResidueList(pasteValue);
      const available = new Set(projection.residues.map((item) => item.label_seq_id));
      const missing = values.filter((value) => !available.has(value));
      if (missing.length) throw new Error(`结构中不存在编号：${missing.join(", ")}`);
      setSelection((current) => {
        const next = new Map(current);
        for (const value of values) next.set(value, tool);
        return next;
      });
      setPasteValue("");
      setStatus(`已处理 ${values.length} 个规范残基编号。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "残基列表无效");
    }
  }

  async function save() {
    const populated = regionCounts(selection).filter((item) => item.count > 0);
    if (!populated.length) {
      setStatus("请至少为 A、B、C 中的一个区域选择残基。");
      return;
    }
    setBusy(true);
    setStatus("正在发布第2步正式结果…");
    try {
      const sessions = await api.designSessions();
      let session: DesignSession | undefined = sessions.find(
        (item) => item.project_id === run.project_id
          && item.design_mode === "stepwise"
          && item.execution_mode === "review-gated",
      );
      if (!session) {
        session = await api.createDesignSession(
          run.project_id,
          "stepwise",
          "review-gated",
        );
      }
      const regions = populated.map(({ id }) => ({
        id,
        label_seq_ids: [...selection.entries()]
          .filter(([, region]) => region === id)
          .map(([label]) => label)
          .sort((left, right) => left - right),
      }));
      const response = await api.reviseRegions(run.run_key, {
        session_id: session.session_id,
        regions,
      });
      const jobId = String(response.job.job_id || "");
      if (!jobId) throw new Error("第2步任务没有返回可跟踪的 job_id");
      completionMessage.current = (
        "人工选区已保存并完成确认；第2步已完成，现在可以配置下一阶段。"
      );
      setActiveJobId(jobId);
      setStatus("人工选区已提交，正在验证编号、坐标和运行记录…");
    } catch (error) {
      setBusy(false);
      setStatus(error instanceof Error ? error.message : "保存区域失败");
    }
  }

  async function startAutomaticSelection() {
    if (selectionMode === "manual") return;
    setBusy(true);
    setStatus("正在建立自动选区的第2步运行…");
    try {
      const sessions = await api.designSessions();
      let session: DesignSession | undefined = sessions.find(
        (item) => item.project_id === run.project_id
          && item.design_mode === "stepwise"
          && item.execution_mode === "review-gated",
      );
      if (!session) {
        session = await api.createDesignSession(
          run.project_id,
          "stepwise",
          "review-gated",
        );
      }
      const response = await api.continueRun(run.run_key, 2, {
        session_id: session.session_id,
        execution_mode: "review-gated",
        options: {
          method: selectionMode,
          allow_structural_only: allowStructuralOnly,
        },
      });
      const jobId = String(response.job.job_id || "");
      if (!jobId) throw new Error("第2步任务没有返回可跟踪的 job_id");
      completionMessage.current = selectionMode === "both"
        ? "SASA 与 ScanNet 已分别完成，等待你比较并确认区域。"
        : `第2步已使用 ${selectionMode === "sasa" ? "SASA" : "ScanNet"} 生成候选，等待你确认区域。`;
      setActiveJobId(jobId);
      setStatus("第2步任务已创建，正在读取运行进度…");
    } catch (error) {
      setBusy(false);
      setStatus(error instanceof Error ? error.message : "启动自动选区失败");
    }
  }

  if (loadingError) {
    return (
      <div
        className={embedded ? "region-editor-embedded" : "region-editor-overlay"}
        role={embedded ? "region" : "dialog"}
        aria-modal={embedded ? undefined : true}
      >
        <section className="region-editor-shell compact-dialog">
          <h2>无法打开区域编辑器</h2>
          <p>{loadingError}</p>
          <button type="button" className="primary-button" onClick={onClose}>
            {embedded ? "返回上一步" : "关闭"}
          </button>
        </section>
      </div>
    );
  }
  if (!projection) {
    return (
      <div
        className={embedded ? "region-editor-embedded" : "region-editor-overlay"}
        role={embedded ? "region" : "dialog"}
        aria-modal={embedded ? undefined : true}
      >
        <section className="region-editor-shell compact-dialog">
          <div className="loading-block">正在验证目标结构、编号映射和区域来源…</div>
        </section>
      </div>
    );
  }

  const counts = regionCounts(selection);
  const stageTwoNotReached = run.stages.find(
    (item) => item.stage_number === 2,
  )?.state === "not-reached";
  return (
    <div
      className={embedded ? "region-editor-embedded" : "region-editor-overlay"}
      role={embedded ? "region" : "dialog"}
      aria-modal={embedded ? undefined : true}
      aria-label="选择结合区域"
    >
      <section className="region-editor-shell">
        <header className="region-editor-header">
          <div>
            <p className="section-label">
              第2步 · 配置结合区域
            </p>
            <h2>选择结合区域</h2>
            <p>
              {stageTwoNotReached
                ? "完成本步后会继续到设计方案；来源颜色、自动方法和人工编辑始终保留各自证据。"
                : "编辑层与 PSE 来源颜色、已批准区域相互独立；保存不会追溯修改旧运行。"}
            </p>
          </div>
          {(!embedded || !stageTwoNotReached) && (
            <button type="button" className="dialog-close" onClick={onClose}>
              {embedded ? "返回已完成结果" : "关闭"}
            </button>
          )}
        </header>
        {stageTwoNotReached && (
          <section className="stage-two-route-picker">
            <div>
              <p className="section-label">先选择第2步路线</p>
              <h3>这一步如何确定结合区域？</h3>
              <p>你可以手工涂选，也可以让 SASA 或 ScanNet 自动提出候选。两种自动方法比较时不会融合分数。</p>
            </div>
            <div className="stage-two-route-options">
              {([
                ["manual", "手工选择", "在结构或序列上涂选 A、B、C"],
                ["sasa", "SASA", "按表面暴露与三维几何选区"],
                ["scannet", "ScanNet", "使用独立模型提出区域"],
                ["both", "两种方法比较", "分别计算，完成后人工选择"],
              ] as Array<[SelectionMode, string, string]>).map(([value, title, description]) => (
                <button
                  type="button"
                  className={selectionMode === value ? "selected" : ""}
                  onClick={() => setSelectionMode(value)}
                  key={value}
                >
                  <strong>{title}</strong>
                  <span>{description}</span>
                </button>
              ))}
            </div>
          </section>
        )}
        {selectionMode !== "manual" ? (
          <section className="automatic-region-setup">
            <div className="automatic-region-summary">
              <p className="section-label">自动选区</p>
              <h3>
                {selectionMode === "both"
                  ? "独立运行 SASA 与 ScanNet"
                  : `使用 ${selectionMode === "sasa" ? "SASA" : "ScanNet"}`}
              </h3>
              <p>
                自动方法只提出可设计的表面区域，不把成员宣称为真实结合位点。
                原始 PSE 颜色不会影响自动排名。
              </p>
            </div>
            <div className="automatic-region-form">
              <label className="acknowledgement">
                <input
                  type="checkbox"
                  checked={allowStructuralOnly}
                  onChange={(event) => setAllowStructuralOnly(event.target.checked)}
                />
                <span>目标没有可靠 UniProt 注释时，允许仅凭结构证据继续。</span>
              </label>
              <button
                type="button"
                className="primary-button"
                disabled={busy}
                onClick={startAutomaticSelection}
              >
                {busy ? "正在建立运行…" : "启动第2步"}
              </button>
              {busy && (
                <div className="region-editor-job-progress" role="progressbar" aria-label="第2步正在运行">
                  <span />
                </div>
              )}
              {status && <div className="form-status">{status}</div>}
            </div>
          </section>
        ) : (
          <>
        <div className="region-editor-workspace">
          <aside className="region-editor-controls">
            <div className="editor-layer-controls">
              <label>
                <input type="checkbox" checked={showSource} onChange={(event) => setShowSource(event.target.checked)} />
                显示 PSE 来源颜色
              </label>
              <label>
                <input type="checkbox" checked={showCurrent} onChange={(event) => setShowCurrent(event.target.checked)} />
                显示当前批准区域
              </label>
            </div>
            <div className="paint-tools" aria-label="区域画笔">
              {(["A", "B", "C"] as RegionId[]).map((id) => (
                <button
                  type="button"
                  className={tool === id ? "selected" : ""}
                  style={{ "--region-color": REGION_COLORS[id] } as CSSProperties}
                  onClick={() => chooseTool(id)}
                  key={id}
                >
                  <i />
                  区域 {id}
                  <small>本次可编辑 {counts.find((item) => item.id === id)?.count || 0} 个残基</small>
                </button>
              ))}
            </div>
            <div className="editor-actions-row">
              <button type="button" onClick={loadUpstream}>恢复上游区域</button>
              <button type="button" onClick={startBlank}>从空白开始</button>
            </div>
            <div className="paste-residues">
              <label>
                <span>粘贴规范残基编号</span>
                <textarea
                  value={pasteValue}
                  onChange={(event) => setPasteValue(event.target.value)}
                  placeholder="例如 32, 36, 39 或 61..69"
                />
              </label>
              <button type="button" onClick={pasteSelection} disabled={!pasteValue.trim()}>
                应用到当前画笔
              </button>
            </div>
            <p className="fine">选择区域 A/B/C 后，点击结构或序列中的残基进行标记；再次点击同一区域的残基即可取消。切换区域后点击会把残基移动到新区域。</p>
            {status && <div className="region-editor-feedback">{status}</div>}
          </aside>
          <div className="region-editor-structure">
            <StructureWorkbench
              runKey={run.run_key}
              stageNumber={2}
              projection={projection}
              regions={displayRegions}
              editableRegions={editableRegions}
              onResidueClick={(label) => colorResidue(label)}
              onRegionDraft={(regions) => {
                const next = new Map<number, RegionId>();
                for (const id of ["A", "B", "C"] as RegionId[]) {
                  for (const label of regions[id] || []) next.set(label, id);
                }
                const added = [...next].filter(
                  ([label, regionId]) => selection.get(label) !== regionId,
                ).length;
                const removed = [...selection].filter(
                  ([label, regionId]) => next.get(label) !== regionId,
                ).length;
                setSelection(next);
                setStatus(
                  `助手建议已应用到本次可编辑层：新增或移动 ${added} 个，移出 ${removed} 个。`
                  + "旧运行与原始 PSE 标注保持不变。",
                );
              }}
              onAnalysisPlan={(methods) => {
                setSelectionMode(
                  methods.length === 2
                    ? "both"
                    : methods[0] === "scannet"
                      ? "scannet"
                      : "sasa",
                );
                setStatus("分析计划已确认；请检查路线与运行方式，再点击启动第2步算法。");
              }}
            />
          </div>
        </div>
        <div className="sequence-editor" aria-label="目标序列选择">
          {projection.residues.map((residue) => {
            const selected = selection.get(residue.label_seq_id);
            return (
              <button
                type="button"
                key={residue.label_seq_id}
                className={selected ? `selected region-${selected.toLowerCase()}` : ""}
                title={`label ${residue.label_seq_id} · auth ${residue.auth_chain_id}:${residue.auth_residue_id}${residue.insertion_code || ""}`}
                onClick={(event) => colorResidue(residue.label_seq_id, event.shiftKey)}
              >
                <strong>{residue.amino_acid}</strong>
                <small>规范 {residue.label_seq_id}</small>
                <span className="source-residue-number">
                  原始 {residue.auth_chain_id}:{residue.auth_residue_id}{residue.insertion_code || ""}
                </span>
              </button>
            );
          })}
        </div>
        <div className="region-editor-approval">
          <p className="approval-summary">
            EasyDesign 会沿用本项目的设计意图，并记录已完成的编号映射与坐标验证；
            无需为 A、B、C 分别重复填写目的和理由。本次区域是你的设计输入，
            不会被表述为已经实验验证的真实结合位点。保存后会完成第2步并暂停，
            由你继续配置下一步。
          </p>
          <div className="approval-footer">
            <button type="button" className="primary-button" disabled={busy} onClick={save}>
              {busy ? "正在发布第2步…" : "保存并完成第2步"}
            </button>
          </div>
          {busy && (
            <div className="region-editor-job-progress" role="progressbar" aria-label="第2步正在运行">
              <span />
            </div>
          )}
          {status && (
            <div className="form-status">
              {status}
            </div>
          )}
        </div>
          </>
        )}
      </section>
    </div>
  );
}
