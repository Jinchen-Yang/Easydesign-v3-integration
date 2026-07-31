import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { NativePyMOLViewer } from "./chatpymol-port/NativePyMOLViewer";
import { MolViewer } from "./MolViewer";
import type {
  AssistantServiceStatus,
  RegionEditorProjection,
  SceneVersion,
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

type AssistantMessageView = StructureInteractionSession["messages"][number] & {
  pending?: boolean;
  failed?: boolean;
};

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

function regionOverlayPml(
  projection: RegionEditorProjection,
  regions: Region[],
): string {
  const lines: string[] = [];
  for (const region of regions) {
    if (!(region.id in REGION_COLORS) || !region.label_seq_ids.length) continue;
    const regionId = region.id as keyof typeof REGION_COLORS;
    const selection = `ed_region_${regionId}`;
    lines.push(
      `select ${selection}, ${authorSelector(projection, region.label_seq_ids)}`,
      `color ${REGION_COLORS[regionId]}, ${selection}`,
      `show sticks, ${selection}`,
    );
  }
  return lines.length ? `${lines.join("\n")}\ndeselect\n` : "";
}

function basePml(
  projection: RegionEditorProjection,
  regions: Region[],
): string {
  return [
    "hide everything, all",
    "show cartoon, all",
    "color gray70, all",
    regionOverlayPml(projection, regions).trimEnd(),
    "deselect",
  ].filter(Boolean).join("\n") + "\n";
}

function withRegionOverlay(
  pml: string,
  projection: RegionEditorProjection,
  regions: Region[],
): string {
  const overlay = regionOverlayPml(projection, regions).trim();
  if (!overlay) return pml;
  return `${pml.trimEnd()}\n\n# @easydesign live region overlay\n${overlay}\n`;
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

function activeSceneVersion(session?: StructureInteractionSession): SceneVersion | undefined {
  if (!session?.scene_versions?.length) return undefined;
  return session.scene_versions.find(
    (item) => item.version_id === session.active_scene_version_id,
  ) || session.scene_versions.at(-1);
}

function pmlToCommonViewerActions(pml: string): ViewerAction[] {
  const actions: ViewerAction[] = [];
  for (const rawLine of pml.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const [verb, ...restParts] = line.split(/\s+/);
    const rest = restParts.join(" ");
    const lower = verb.toLowerCase();
    if (lower === "bg_color") {
      actions.push({ action: "background", target: "all", value: rest.trim() });
    } else if (lower === "color") {
      const [value, target = "all"] = rest.split(",", 2).map((item) => item.trim());
      actions.push({ action: "color", target: target || "all", value });
    } else if (lower === "show") {
      const [value, target = "all"] = rest.split(",", 2).map((item) => item.trim());
      if (["cartoon", "surface", "sticks", "stick", "spheres", "lines"].includes(value)) {
        actions.push({ action: "representation", target: target || "all", value });
      }
    } else if (lower === "zoom") {
      actions.push({ action: "focus", target: rest.trim() || "all" });
    } else if (lower === "center") {
      actions.push({ action: "center", target: rest.trim() || "all" });
    } else if (lower === "orient") {
      actions.push({ action: "orient", target: rest.trim() || "all" });
    }
  }
  return actions.filter((item) => item.target === "all" || item.target === "target");
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
  const [pendingMessages, setPendingMessages] = useState<AssistantMessageView[]>([]);
  const [status, setStatus] = useState("");
  const [pmlEditorOpen, setPmlEditorOpen] = useState(false);
  const assistantMessagesRef = useRef<HTMLDivElement | null>(null);
  const [pmlDraft, setPmlDraft] = useState("");
  const [referenceBusy, setReferenceBusy] = useState(false);
  const [referenceRcsbId, setReferenceRcsbId] = useState("");
  const pendingPmlSession = useRef<StructureInteractionSession | undefined>(undefined);

  const structureUrl = `/api/v1/artifacts/${projection.structure.token}`;
  const referenceStructures = useMemo(
    () => session?.reference_structures?.filter((item) => item.role === "reference") || [],
    [session?.reference_structures],
  );
  const nativeStructures = useMemo(
    () => [{
      id: projection.structure.sha256,
      sha256: projection.structure.sha256,
      filename: "target.cif",
      objectName: "target",
    }, ...referenceStructures.map((item) => ({
      id: item.object_id,
      sha256: item.sha256,
      filename: item.filename,
      objectName: item.object_name,
      referenceUrl: `/api/v1/structure-sessions/${encodeURIComponent(session?.session_id || "")}/references/${encodeURIComponent(item.object_id)}/file`,
    }))],
    [projection.structure.sha256, referenceStructures, session?.session_id],
  );
  const activeVersion = useMemo(() => activeSceneVersion(session), [session]);
  const legacyScenePml = useMemo(
    () => combinedPml(projection, regions, session),
    [projection, regions, session],
  );
  const scenePml = useMemo(
    () => withRegionOverlay(activeVersion?.pml || legacyScenePml, projection, regions),
    [activeVersion?.pml, legacyScenePml, projection, regions],
  );
  const sceneVersions = session?.scene_versions || [];
  const commonViewActions = useMemo(
    () => pmlToCommonViewerActions(scenePml),
    [scenePml],
  );
  const assistantMessages = useMemo<AssistantMessageView[]>(
    () => [...(session?.messages || []), ...pendingMessages],
    [pendingMessages, session?.messages],
  );
  useEffect(() => {
    setPmlDraft(scenePml);
  }, [scenePml]);
  useEffect(() => {
    setPendingMessages([]);
  }, [session?.session_id]);
  useEffect(() => {
    const element = assistantMessagesRef.current;
    if (!element) return;
    element.scrollTop = element.scrollHeight;
  }, [assistantMessages.length, busy]);

  const nativeApi = useMemo(
    () => ({
      structureBytes: async (_projectId?: string, structure?: unknown, signal?: AbortSignal) => {
        async function fetchBytes(url: string, label: string) {
          const response = await fetch(url, { cache: "no-store", signal });
          if (!response.ok) {
            throw new Error(`${label} 下载失败（HTTP ${response.status}）`);
          }
          return new Uint8Array(await response.arrayBuffer());
        }
        const referenceUrl = (structure as { referenceUrl?: string } | undefined)?.referenceUrl;
        if (referenceUrl) {
          return fetchBytes(referenceUrl, "参考结构");
        }
        try {
          return await fetchBytes(structureUrl, "目标结构");
        } catch (error) {
          if (signal?.aborted) throw error;
          const refreshed = await api.regionEditor(runKey);
          return fetchBytes(`/api/v1/artifacts/${refreshed.structure.token}`, "目标结构");
        }
      },
    }),
    [runKey, structureUrl],
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

  const nativeCommandsApplied = useCallback((commands?: string) => {
    if (pendingPmlSession.current) {
      setSession(pendingPmlSession.current);
      pendingPmlSession.current = undefined;
      return;
    }
    if (!commands?.trim() || !session) return;
    api.appendStructurePml(session.session_id, commands, "viewer")
      .then((updated) => {
        setSession(updated);
        setStatus("原生 PyMOL 操作已保存为 PML 版本。");
      })
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : "原生 PyMOL 操作保存失败");
      });
  }, [session]);
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
    const text = message.trim();
    const createdAt = new Date().toISOString();
    const optimisticUser: AssistantMessageView = {
      message_id: `local-user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: createdAt,
    };
    const optimisticAssistant: AssistantMessageView = {
      message_id: `local-assistant-${Date.now()}`,
      role: "assistant",
      content: "正在生成建议…",
      created_at: createdAt,
      pending: true,
    };
    setPendingMessages([optimisticUser, optimisticAssistant]);
    setMessage("");
    setBusy(true);
    setStatus("正在请求结构助手…");
    try {
      const updated = await api.assistantMessage(
        session.session_id,
        text,
      );
      setPendingMessages([]);
      setSession(updated);
      const latest = updated.messages.at(-1);
      setStatus(latest?.version_id ? "助手已更新 PML 场景并保存版本。" : "助手已生成待确认建议。");
    } catch (error) {
      setPendingMessages([
        optimisticUser,
        {
          ...optimisticAssistant,
          content: "请求失败，请查看下方状态后重试。",
          pending: false,
          failed: true,
        },
      ]);
      setStatus(error instanceof Error ? error.message : "结构助手请求失败");
    } finally {
      setBusy(false);
    }
  }

  async function savePmlDraft() {
    if (!session || !pmlDraft.trim()) return;
    setBusy(true);
    try {
      const response = await api.saveScenePml(
        session.session_id,
        pmlDraft,
        "expert-console",
      );
      setSession(response.session);
      setStatus(`PML 已保存为版本 ${response.version.revision}。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "PML 保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function restoreVersion(versionId: string) {
    if (!session) return;
    setBusy(true);
    try {
      const response = await api.restoreSceneVersion(
        session.session_id,
        versionId,
        session.active_scene_version_id,
      );
      setSession(response.session);
      setStatus(`已恢复为新版本 ${response.version.revision}。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "恢复 PML 版本失败");
    } finally {
      setBusy(false);
    }
  }

  async function addReferenceFile(file?: File) {
    if (!session || !file) return;
    setReferenceBusy(true);
    setStatus("正在上传参考结构…");
    try {
      const receipt = await api.upload(file);
      const response = await api.addUploadedStructureReference(
        session.session_id,
        receipt.upload_token,
      );
      setSession(response.session);
      setStatus(`参考结构 ${response.reference.object_name} 已加入 Stage 2 场景。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "参考结构上传失败");
    } finally {
      setReferenceBusy(false);
    }
  }

  async function addRcsbReference() {
    if (!session || !referenceRcsbId.trim()) return;
    setReferenceBusy(true);
    setStatus("正在从 RCSB 拉取参考结构…");
    try {
      const response = await api.addRcsbStructureReference(
        session.session_id,
        referenceRcsbId.trim(),
      );
      setSession(response.session);
      setReferenceRcsbId("");
      setStatus(`参考结构 ${response.reference.object_name} 已加入 Stage 2 场景。`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "RCSB 参考结构拉取失败");
    } finally {
      setReferenceBusy(false);
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
          : response.result === "scene-version-restored"
            ? "已恢复到历史 PML 场景。"
            : response.result === "pml-edit-applied"
              ? "PML 场景建议已保存为新版本。"
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
                  versionId={activeVersion?.version_id || "current"}
                  revision={activeVersion?.revision || (
                    (session?.pml_revisions.length || 0)
                    + (session?.view_state_revisions?.length || 0)
                  )}
                  exportName={`${projection.target_id}-visualization`}
                  readOnly={false}
                  canUndo={sceneVersions.length > 1}
                  canRedo={false}
                  onUndo={() => {
                    const previous = sceneVersions.at(-2);
                    if (previous) restoreVersion(previous.version_id);
                  }}
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
        <section className="scene-version-panel">
          <div className="scene-version-toolbar">
            <div>
              <strong>PML 场景版本</strong>
              <span>{activeVersion ? `当前版本 ${activeVersion.revision}` : "尚未建立版本"}</span>
            </div>
            <button type="button" onClick={() => setPmlEditorOpen((value) => !value)}>
              {pmlEditorOpen ? "收起 PML" : "编辑 PML"}
            </button>
          </div>
          <div className="reference-controls">
            <div>
              <strong>参考结构</strong>
              <span>仅用于 Stage 2 可视化/比对，不改变下游 target bundle。</span>
            </div>
            <label>
              <span>上传 PDB/mmCIF</span>
              <input
                type="file"
                accept=".cif,.mmcif,.pdb,.ent"
                disabled={!session || referenceBusy || busy}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  addReferenceFile(file);
                }}
              />
            </label>
            <label>
              <span>RCSB ID</span>
              <input
                value={referenceRcsbId}
                placeholder="例如 1UBQ"
                maxLength={4}
                disabled={!session || referenceBusy || busy}
                onChange={(event) => setReferenceRcsbId(event.target.value.toUpperCase())}
                onKeyDown={(event) => {
                  if (event.key === "Enter") addRcsbReference();
                }}
              />
            </label>
            <button
              type="button"
              disabled={!session || referenceBusy || busy || !referenceRcsbId.trim()}
              onClick={addRcsbReference}
            >
              加入 RCSB
            </button>
            {referenceStructures.length > 0 && (
              <ul>
                {referenceStructures.map((item) => (
                  <li key={item.object_id}>
                    <code>{item.object_name}</code>
                    <span>{item.filename}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {pmlEditorOpen && (
            <div className="scene-pml-editor">
              <textarea
                value={pmlDraft}
                onChange={(event) => setPmlDraft(event.target.value)}
                spellCheck={false}
              />
              <div>
                <button type="button" disabled={busy || pmlDraft === scenePml} onClick={savePmlDraft}>
                  保存为新版本
                </button>
                <button type="button" disabled={busy} onClick={() => setPmlDraft(scenePml)}>
                  放弃草稿
                </button>
              </div>
            </div>
          )}
          {sceneVersions.length > 0 && (
            <div className="scene-version-list">
              {sceneVersions.slice(-6).reverse().map((version) => (
                <button
                  type="button"
                  key={version.version_id}
                  className={version.version_id === session?.active_scene_version_id ? "active" : ""}
                  disabled={busy || version.version_id === session?.active_scene_version_id}
                  onClick={() => restoreVersion(version.version_id)}
                >
                  <strong>v{version.revision}</strong>
                  <span>{version.summary}</span>
                  <small>{version.actor} · {version.source}</small>
                </button>
              ))}
            </div>
          )}
        </section>
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
          <div className="assistant-messages" aria-live="polite" aria-busy={busy} ref={assistantMessagesRef}>
            {!assistantMessages.length && (
              <p>
                例如：“将32、36加入A区”或“把结构显示为表面”。
                “寻找最佳区域”只会产生待确认的算法计划。
              </p>
            )}
            {assistantMessages.map((item) => (
              <article
                className={`assistant-message ${item.role}${item.pending ? " pending" : ""}${item.failed ? " failed" : ""}`}
                key={item.message_id}
              >
                <span>{item.role === "user" ? "你" : "助手"}</span>
                <p>{item.content}</p>
                {item.pending && <small className="assistant-thinking">等待平台模型返回</small>}
                {item.proposal && !item.pending && !item.failed && item.proposal.kind !== "explanation" && (
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
            会发送当前 PML 场景、对象/链/区域元数据和最近对话；不会上传坐标、MSA 或完整序列。
          </footer>
        </aside>
      )}
    </div>
  );
}
