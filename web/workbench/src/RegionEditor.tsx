import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { api } from "./api";
import { MolViewer } from "./MolViewer";
import type { DesignSession, RegionEditorProjection, Run } from "./types";

type RegionId = "A" | "B" | "C";
type Tool = RegionId | "erase";
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
}: {
  run: Run;
  onClose: () => void;
  onSubmitted: (message: string) => void;
}) {
  const [projection, setProjection] = useState<RegionEditorProjection>();
  const [loadingError, setLoadingError] = useState("");
  const [selection, setSelection] = useState<Map<number, RegionId>>(new Map());
  const [tool, setTool] = useState<Tool>("A");
  const [showSource, setShowSource] = useState(true);
  const [showCurrent, setShowCurrent] = useState(true);
  const [pasteValue, setPasteValue] = useState("");
  const [approvedBy, setApprovedBy] = useState("");
  const [executionMode, setExecutionMode] = useState<"review-gated" | "unattended">("review-gated");
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("manual");
  const [allowStructuralOnly, setAllowStructuralOnly] = useState(false);
  const [acknowledge, setAcknowledge] = useState(false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const lastSelected = useRef<number | undefined>(undefined);

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
    setSelection((current) => {
      const next = new Map(current);
      for (const label of targets) {
        if (!available.has(label)) continue;
        if (tool === "erase") next.delete(label);
        else next.set(label, tool);
      }
      return next;
    });
    lastSelected.current = labelSeqId;
    setStatus(
      tool === "erase"
        ? `已将规范残基 ${labelSeqId} 移出本次编辑区域。`
        : `已将规范残基 ${labelSeqId} 设为区域 ${tool}。`,
    );
  }

  function loadUpstream() {
    if (!projection) return;
    const restored = upstreamSelection(projection);
    setSelection(restored);
    setShowSource(true);
    setShowCurrent(true);
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

  function chooseTool(nextTool: Tool) {
    setTool(nextTool);
    setStatus(
      nextTool === "erase"
        ? "已切换到橡皮擦；请点击结构或下方序列中的残基。"
        : `已切换到区域 ${nextTool} 画笔；请继续点击结构或下方序列中的残基。`,
    );
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
        for (const value of values) {
          if (tool === "erase") next.delete(value);
          else next.set(value, tool);
        }
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
    if (!approvedBy.trim()) {
      setStatus("请填写批准人；用户选区必须保留明确的人类责任记录。");
      return;
    }
    if (!acknowledge) {
      setStatus("请确认：用户标注区域不等同于已经验证的真实结合位点。");
      return;
    }
    setBusy(true);
    setStatus("正在创建新的 Stage 02 分支…");
    try {
      const sessions = await api.designSessions();
      let session: DesignSession | undefined = sessions.find(
        (item) => item.project_id === run.project_id && item.design_mode === "stepwise",
      );
      if (!session) {
        session = await api.createDesignSession(
          run.project_id,
          "stepwise",
          executionMode,
        );
      }
      const regions = populated.map(({ id }) => ({
        id,
        label_seq_ids: [...selection.entries()]
          .filter(([, region]) => region === id)
          .map(([label]) => label)
          .sort((left, right) => left - right),
      }));
      await api.reviseRegions(run.run_key, {
        session_id: session.session_id,
        execution_mode: executionMode,
        regions,
        approved_by: approvedBy.trim(),
        acknowledge_user_provided_regions: true,
        acknowledge_evidence_limitations: true,
      });
      const message = executionMode === "review-gated"
        ? "新的 Stage 02 分支已启动；完成后会进入“等待你的确认”。"
        : "新的 Stage 02 分支已启动；本次明确提交记录为人工批准。";
      setStatus(message);
      onSubmitted(message);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "保存区域失败");
    } finally {
      setBusy(false);
    }
  }

  async function startAutomaticSelection() {
    if (selectionMode === "manual") return;
    if (executionMode === "unattended" && selectionMode === "both") {
      setStatus("连续运行时必须选择 SASA 或 ScanNet 中的一种；两种方法比较需要人工确认。");
      return;
    }
    setBusy(true);
    setStatus("正在建立自动选区的第2步运行…");
    try {
      const sessions = await api.designSessions();
      let session: DesignSession | undefined = sessions.find(
        (item) => item.project_id === run.project_id && item.design_mode === "stepwise",
      );
      if (!session) {
        session = await api.createDesignSession(
          run.project_id,
          "stepwise",
          executionMode,
        );
      }
      await api.continueRun(run.run_key, 2, {
        session_id: session.session_id,
        execution_mode: executionMode,
        options: {
          method: selectionMode,
          allow_structural_only: allowStructuralOnly,
        },
      });
      const message = selectionMode === "both"
        ? "新的第2步已启动；SASA 与 ScanNet 会独立运行，完成后等待你比较确认。"
        : `新的第2步已启动；将使用 ${selectionMode === "sasa" ? "SASA" : "ScanNet"} 选择区域。`;
      setStatus(message);
      onSubmitted(message);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "启动自动选区失败");
    } finally {
      setBusy(false);
    }
  }

  if (loadingError) {
    return (
      <div className="region-editor-overlay" role="dialog" aria-modal="true">
        <section className="region-editor-shell compact-dialog">
          <h2>无法打开区域编辑器</h2>
          <p>{loadingError}</p>
          <button type="button" className="primary-button" onClick={onClose}>关闭</button>
        </section>
      </div>
    );
  }
  if (!projection) {
    return (
      <div className="region-editor-overlay" role="dialog" aria-modal="true">
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
    <div className="region-editor-overlay" role="dialog" aria-modal="true" aria-label="重新选择结合区域">
      <section className="region-editor-shell">
        <header className="region-editor-header">
          <div>
            <p className="section-label">第2步 · 建立新分支</p>
            <h2>重新选择结合区域</h2>
            <p>编辑层与 PSE 来源颜色、已批准区域相互独立；保存不会追溯修改旧运行。</p>
          </div>
          <button type="button" className="dialog-close" onClick={onClose}>关闭</button>
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
              <label>
                <span>后续运行方式</span>
                <select value={executionMode} onChange={(event) => setExecutionMode(event.target.value as typeof executionMode)}>
                  <option value="review-gated">遇到科学选择时暂停确认</option>
                  <option value="unattended">连续运行</option>
                </select>
              </label>
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
                disabled={busy || (executionMode === "unattended" && selectionMode === "both")}
                onClick={startAutomaticSelection}
              >
                {busy ? "正在建立运行…" : "启动第2步"}
              </button>
              {executionMode === "unattended" && selectionMode === "both" && (
                <p className="field-error">连续运行不能替你决定两种方法的赢家，请改为单一方法或暂停确认。</p>
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
              <button type="button" className={tool === "erase" ? "selected" : ""} onClick={() => chooseTool("erase")}>
                橡皮擦
                <small>移出编辑区域</small>
              </button>
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
            <p className="fine">区域 A/B/C 按钮只是切换画笔；还需要点击右侧结构或下方序列中的残基。重新着色会自动把残基从旧区域移动到新区域。</p>
            {status && <div className="region-editor-feedback">{status}</div>}
          </aside>
          <div className="region-editor-structure">
            <MolViewer
              structureUrl={`/api/v1/artifacts/${projection.structure.token}`}
              regions={displayRegions}
              onResidueClick={(label) => colorResidue(label)}
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
                <small>{residue.label_seq_id}</small>
              </button>
            );
          })}
        </div>
        <div className="region-editor-approval">
          <p className="approval-summary">
            EasyDesign 会沿用本项目的设计意图，并记录已完成的编号映射与坐标验证；
            无需为 A、B、C 分别重复填写目的和理由。
          </p>
          <div className="approval-footer">
            <label><span>批准人</span><input value={approvedBy} onChange={(event) => setApprovedBy(event.target.value)} placeholder="真实姓名或稳定 ID" /></label>
            <label><span>后续运行方式</span><select value={executionMode} onChange={(event) => setExecutionMode(event.target.value as typeof executionMode)}><option value="review-gated">保存后等待再次确认</option><option value="unattended">按本次人工提交连续运行</option></select></label>
            <label className="acknowledgement"><input type="checkbox" checked={acknowledge} onChange={(event) => setAcknowledge(event.target.checked)} /><span>我确认这些是用户提供的设计区域，并不代表已经验证的真实结合位点。</span></label>
            <button type="button" className="primary-button" disabled={busy} onClick={save}>{busy ? "正在建立新分支…" : "保存并建立新的第2步分支"}</button>
          </div>
          {status && <div className="form-status">{status}</div>}
        </div>
          </>
        )}
      </section>
    </div>
  );
}
