import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { NativePyMOLViewer } from "./chatpymol-port/NativePyMOLViewer";
import { MolViewer } from "./MolViewer";
import type {
  AssistantServiceStatus,
  RegionEditorProjection,
  StructureInteractionSession,
  ViewerAction,
} from "./types";
import "./StructureWorkbench.css";

interface Region {
  id: string;
  label_seq_ids: number[];
}

interface Props {
  runKey: string;
  stageNumber: 1 | 2;
  projection: RegionEditorProjection;
  regions?: Region[];
  onResidueClick?: (labelSeqId: number) => void;
  onRegionDraft?: (
    regions: Partial<Record<"A" | "B" | "C", number[]>>,
  ) => void;
  onAnalysisPlan?: (methods: Array<"sasa" | "scannet">) => void;
  compact?: boolean;
}

const REGION_COLORS = {
  A: "red",
  B: "blue",
  C: "yellow",
} as const;

const EMPTY_REGIONS: Region[] = [];

function authorSelector(
  projection: RegionEditorProjection,
  labels: number[],
): string {
  const requested = new Set(labels);
  const byChain = new Map<string, string[]>();
  for (const residue of projection.residues) {
    if (!requested.has(residue.label_seq_id)) continue;
    const chain = residue.auth_chain_id || "A";
    const values = byChain.get(chain) || [];
    values.push(
      `${residue.auth_residue_id}${residue.insertion_code || ""}`,
    );
    byChain.set(chain, values);
  }
  const clauses = [...byChain.entries()].map(
    ([chain, residues]) => (
      `(chain ${chain} and resi ${[...new Set(residues)].join("+")})`
    ),
  );
  return clauses.length ? clauses.join(" or ") : "none";
}

function basePml(
  projection: RegionEditorProjection,
  regions: Region[],
): string {
  const lines = [
    "hide everything, all",
    "show cartoon, all",
    "color gray70, all",
  ];
  for (const region of regions) {
    if (!(region.id in REGION_COLORS) || !region.label_seq_ids.length) continue;
    const regionId = region.id as keyof typeof REGION_COLORS;
    const selection = `ed_region_${regionId}`;
    lines.push(
      `select ${selection}, ${authorSelector(projection, region.label_seq_ids)}`,
      `color ${REGION_COLORS[regionId]}, ${selection}`,
    );
  }
  lines.push("deselect");
  return `${lines.join("\n")}\n`;
}

function combinedPml(
  projection: RegionEditorProjection,
  regions: Region[],
  session?: StructureInteractionSession,
): string {
  return [
    basePml(projection, regions).trimEnd(),
    ...(
      session?.view_state_revisions?.flatMap((item) => (
        compileCommonViewerActions(item.actions)
      )) || []
    ),
    ...(session?.pml_revisions.map((item) => item.pml.trimEnd()) || []),
  ].filter(Boolean).join("\n");
}

function compileCommonViewerActions(actions: ViewerAction[]): string[] {
  const lines: string[] = [];
  for (const action of actions) {
    const target = action.target || "all";
    if (action.action === "representation") {
      const representation = action.value === "stick" ? "sticks" : action.value;
      lines.push(`hide everything, ${target}`, `show ${representation}, ${target}`);
    } else if (action.action === "color") {
      lines.push(`color ${action.value}, ${target}`);
    } else if (action.action === "background") {
      lines.push(`bg_color ${action.value}`);
    } else if (action.action === "focus") {
      lines.push(`zoom ${target}`);
    } else if (action.action === "orient") {
      lines.push(`orient ${target}`);
    } else if (action.action === "center") {
      lines.push(`center ${target}`);
    }
  }
  return lines;
}

function downloadText(value: string, filename: string) {
  const href = URL.createObjectURL(
    new Blob([value], { type: "text/plain;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export function StructureWorkbench({
  runKey,
  stageNumber,
  projection,
  regions = EMPTY_REGIONS,
  onResidueClick,
  onRegionDraft,
  onAnalysisPlan,
  compact = false,
}: Props) {
  const [viewer, setViewer] = useState<"pymol" | "molstar">("pymol");
  const [molstarMounted, setMolstarMounted] = useState(false);
  const [pymolAvailable, setPymolAvailable] = useState<boolean>();
  const [session, setSession] = useState<StructureInteractionSession>();
  const [assistantService, setAssistantService] = useState<AssistantServiceStatus>();
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const pendingPmlSession = useRef<StructureInteractionSession | undefined>(undefined);

  const structureUrl = `/api/v1/artifacts/${projection.structure.token}`;
  const nativeStructures = useMemo(
    () => [{
      id: projection.structure.sha256,
      sha256: projection.structure.sha256,
      filename: "target.cif",
      objectName: "target",
    }],
    [projection.structure.sha256],
  );
  const scenePml = useMemo(
    () => combinedPml(projection, regions, session),
    [projection, regions, session],
  );
  const commonViewActions = useMemo(
    () => session?.view_state_revisions?.flatMap((item) => item.actions) || [],
    [session?.view_state_revisions],
  );
  const nativeApi = useMemo(
    () => ({
      structureBytes: async (_projectId?: string, _structure?: unknown, signal?: AbortSignal) => {
        const response = await fetch(structureUrl, { cache: "no-store", signal });
        if (!response.ok) throw new Error("目标结构下载失败");
        return new Uint8Array(await response.arrayBuffer());
      },
    }),
    [structureUrl],
  );

  useEffect(() => {
    let disposed = false;
    Promise.all([
      api.browserPymolStatus(),
      api.createStructureSession(runKey, stageNumber),
      api.assistantStatus(),
    ]).then(([pymol, activeSession, serviceStatus]) => {
      if (disposed) return;
      setPymolAvailable(pymol.available);
      if (!pymol.available) {
        setMolstarMounted(true);
        setViewer("molstar");
      }
      setSession(activeSession);
      setAssistantService(serviceStatus);
    }).catch((error: unknown) => {
      if (!disposed) {
        setPymolAvailable(false);
        setViewer("molstar");
        setStatus(error instanceof Error ? error.message : "结构工作区初始化失败");
      }
    });
    return () => {
      disposed = true;
    };
  }, [runKey, stageNumber]);

  const validatePml = useCallback(async (pml: string) => {
    if (!session) throw new Error("交互会话尚未就绪");
    const updated = await api.appendStructurePml(
      session.session_id,
      pml,
      "expert-console",
    );
    pendingPmlSession.current = updated;
    const last = updated.pml_revisions.at(-1);
    if (!last) throw new Error("安全 PML 没有生成 revision");
    return last.pml;
  }, [session]);

  const nativeCommandsApplied = useCallback(() => {
    if (pendingPmlSession.current) {
      setSession(pendingPmlSession.current);
      pendingPmlSession.current = undefined;
    }
  }, []);
  const nativeFailure = useCallback((failure: string) => {
    setStatus(failure);
  }, []);
  const switchToMolstar = useCallback(() => {
    setMolstarMounted(true);
    setViewer("molstar");
  }, []);

  const selectedAuthorResidue = useCallback((value: { chain: string; residueId: string }) => {
    const exact = projection.residues.filter(
      (item) => (
        item.auth_chain_id === value.chain
        && `${item.auth_residue_id}${item.insertion_code || ""}`
          === value.residueId
      ),
    );
    const fallback = projection.residues.filter(
      (item) => String(item.label_seq_id) === value.residueId,
    );
    const matches = exact.length ? exact : fallback;
    if (matches.length === 1) onResidueClick?.(matches[0].label_seq_id);
  }, [onResidueClick, projection.residues]);

  async function sendMessage() {
    if (!session || !assistantService?.available || !message.trim()) return;
    setBusy(true);
    setStatus("正在请求结构助手…");
    try {
      const updated = await api.assistantMessage(
        session.session_id,
        message.trim(),
      );
      setSession(updated);
      setMessage("");
      setStatus("助手已生成待确认建议。");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "结构助手请求失败");
    } finally {
      setBusy(false);
    }
  }

  async function applyProposal(proposalId: string) {
    if (!session) return;
    setBusy(true);
    try {
      const response = await api.applyAssistantProposal(
        session.session_id,
        proposalId,
      );
      setSession(response.session);
      if (response.result === "region-edit-applied-to-draft") {
        onRegionDraft?.(response.session.current_regions);
      }
      if (response.analysis_plan) {
        onAnalysisPlan?.(response.analysis_plan.methods);
      }
      setStatus(
        response.result === "analysis-plan-confirmed"
          ? "分析计划已确认；请在第2步启动对应算法。"
          : "建议已应用到当前交互草稿。",
      );
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "无法应用建议");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`structure-workbench ${assistantOpen ? "" : "assistant-collapsed"}`}>
      <section className="structure-viewer-column">
        <header className="structure-viewer-switcher">
          <div role="tablist" aria-label="结构查看器">
            <button
              type="button"
              role="tab"
              aria-selected={viewer === "pymol"}
              className={viewer === "pymol" ? "selected" : ""}
              disabled={pymolAvailable === false}
              onClick={() => setViewer("pymol")}
            >
              PyMOL
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewer === "molstar"}
              className={viewer === "molstar" ? "selected" : ""}
              onClick={() => {
                setMolstarMounted(true);
                setViewer("molstar");
              }}
            >
              Mol*
            </button>
          </div>
          <span>
            {pymolAvailable === false
              ? "浏览器 PyMOL 资源不可用，Mol* 仍可正常使用"
              : "两种查看器读取同一份已校验 target.cif"}
          </span>
          <button
            type="button"
            className="assistant-toggle"
            onClick={() => setAssistantOpen((value) => !value)}
          >
            {assistantOpen ? "收起助手" : "打开助手"}
          </button>
        </header>
        <div className="structure-viewer-surface">
          {pymolAvailable === true && (
            <div
              className={`structure-viewer-pane ${viewer === "pymol" ? "active" : "inactive"}`}
              aria-hidden={viewer !== "pymol"}
              inert={viewer !== "pymol" ? true : undefined}
            >
              <div className="easydesign-pymol">
                <NativePyMOLViewer
                  api={nativeApi}
                  projectId={projection.target_id}
                  active={viewer === "pymol"}
                  pml={scenePml}
                  structures={nativeStructures}
                  versionId="current"
                  revision={
                    (session?.pml_revisions.length || 0)
                    + (session?.view_state_revisions?.length || 0)
                  }
                  exportName={`${projection.target_id}-visualization`}
                  readOnly={false}
                  language="zh"
                  onValidatePml={validatePml}
                  onNativeCommands={nativeCommandsApplied}
                  onResidueSelect={selectedAuthorResidue}
                  onFailure={nativeFailure}
                  onSwitchViewer={switchToMolstar}
                  onDownloadStructure={() => window.open(`${structureUrl}?download=true`, "_blank")}
                  onDownloadPml={() => downloadText(scenePml, `${projection.target_id}.pml`)}
                />
              </div>
            </div>
          )}
          {(molstarMounted || viewer === "molstar") && (
            <div
              className={`structure-viewer-pane ${viewer === "molstar" ? "active" : "inactive"}`}
              aria-hidden={viewer !== "molstar"}
              inert={viewer !== "molstar" ? true : undefined}
            >
              <MolViewer
                structureUrl={structureUrl}
                regions={regions}
                compact={compact}
                onResidueClick={onResidueClick}
                viewActions={commonViewActions}
              />
            </div>
          )}
        </div>
      </section>
      {assistantOpen && (
        <aside className="structure-assistant">
          <header>
            <div>
              <strong>结构助手</strong>
              <span>显示操作同步到 PyMOL 与 Mol*</span>
            </div>
            <span className="assistant-safety">不会判断最佳 hotspot</span>
          </header>
          <div
            className={`assistant-service ${assistantService?.available ? "available" : "unavailable"}`}
          >
            <strong>{assistantService?.service_name || "EasyDesign 结构助手"}</strong>
            <span>
              {assistantService?.detail || "正在检查平台助手服务…"}
            </span>
          </div>
          <div className="assistant-messages" aria-live="polite">
            {!session?.messages.length && (
              <p>
                例如：“将32、36加入A区”或“把结构显示为表面”。
                “寻找最佳区域”只会产生待确认的算法计划。
              </p>
            )}
            {session?.messages.map((item) => (
              <article className={`assistant-message ${item.role}`} key={item.message_id}>
                <span>{item.role === "user" ? "你" : "助手"}</span>
                <p>{item.content}</p>
                {item.proposal && item.proposal.kind !== "explanation" && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => applyProposal(item.proposal!.proposal_id)}
                  >
                    {item.proposal.kind === "analysis-plan"
                      ? "确认分析计划"
                      : "确认并应用"}
                  </button>
                )}
              </article>
            ))}
          </div>
          <div className="assistant-composer">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="输入显示操作或明确的残基编号…"
              disabled={!assistantService?.available || busy}
            />
            <button
              type="button"
              disabled={!assistantService?.available || !message.trim() || busy}
              onClick={sendMessage}
            >
              {busy ? "处理中…" : "发送"}
            </button>
          </div>
          {status && <p className="assistant-status">{status}</p>}
          <footer>
            仅发送文字、阶段、链和当前区域数量；不会上传坐标、MSA 或完整序列。
          </footer>
        </aside>
      )}
    </div>
  );
}
