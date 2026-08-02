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
  editableRegions?: Region[];
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
const REGION_OVERLAY_COMMENT = "# EasyDesign live region overlay";
const LEGACY_REGION_OVERLAY_COMMENT = "# @easydesign live region overlay";

function regionArrayKey(regions?: Region[]): string {
  return (["A", "B", "C"] as const).map((regionId) => {
    const values = regions
      ?.find((region) => region.id === regionId)
      ?.label_seq_ids || [];
    return `${regionId}:${[...new Set(values)].sort((a, b) => a - b).join(",")}`;
  }).join("|");
}

function regionRecordKey(
  regions: Partial<Record<"A" | "B" | "C", number[]>>,
): string {
  return (["A", "B", "C"] as const).map((regionId) => (
    `${regionId}:${[...new Set(regions[regionId] || [])].sort((a, b) => a - b).join(",")}`
  )).join("|");
}

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
  const byRegion = new Map(
    regions.map((region) => [region.id, region.label_seq_ids] as const),
  );
  for (const regionId of ["A", "B", "C"] as const) {
    const selection = `ed_region_${regionId}`;
    const labels = byRegion.get(regionId) || [];
    lines.push(
      `select ${selection}, ${authorSelector(projection, labels)}`,
      `color ${REGION_COLORS[regionId]}, ${selection}`,
      `show sticks, ${selection}`,
    );
  }
  return `${lines.join("\n")}\ndeselect\n`;
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
  return `${pml.trimEnd()}\n\n${REGION_OVERLAY_COMMENT}\n${overlay}\n`;
}

function replaceManagedRegionSelections(
  pml: string,
  projection: RegionEditorProjection,
  regions: Region[],
): string {
  const reserved = /^ed_region_[ABC]$/i;
  const retained = pml.split(/\r?\n/).filter((rawLine) => {
    const line = rawLine.trim();
    if (
      line === REGION_OVERLAY_COMMENT
      || line === LEGACY_REGION_OVERLAY_COMMENT
    ) return false;
    if (!line || line.startsWith("#")) return true;
    const [verb, ...parts] = line.split(/\s+/);
    const rest = parts.join(" ");
    if (verb.toLowerCase() === "deselect" && !rest) return false;
    if (verb.toLowerCase() === "select") {
      return !reserved.test(rest.split(",", 1)[0]?.trim() || "");
    }
    if (["color", "show", "hide"].includes(verb.toLowerCase())) {
      const target = rest.split(",", 2)[1]?.trim() || "";
      return !reserved.test(target);
    }
    return true;
  });
  const overlay = regionOverlayPml(projection, regions).trimEnd();
  return `${retained.join("\n").replace(/\n{3,}/g, "\n\n").trim()}\n\n`
    + `${REGION_OVERLAY_COMMENT}\n${overlay}\n`;
}

function combinedPml(
  projection: RegionEditorProjection,
  regions: Region[],
  session?: StructureInteractionSession,
): string {
  const latestViewState = session?.view_state_revisions?.at(-1);
  const latestPml = session?.pml_revisions?.at(-1);
  return [
    basePml(projection, regions).trimEnd(),
    ...(latestViewState ? compileCommonViewerActions(latestViewState.actions) : []),
    latestPml?.pml.trimEnd() || "",
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

function pmlToMolstarProjection(pml: string): {
  actions: ViewerAction[];
  unsupported: string[];
} {
  const actions: ViewerAction[] = [];
  const unsupported: string[] = [];
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
    } else if (lower === "hide") {
      const [representation, target = "all"] = rest
        .split(",", 2)
        .map((item) => item.trim().toLowerCase());
      if (!(representation === "everything" && ["all", "target"].includes(target))) {
        unsupported.push(line);
      }
    } else if (lower === "select") {
      const selectionName = rest.split(",", 1)[0]?.trim();
      if (!["ed_region_A", "ed_region_B", "ed_region_C"].includes(selectionName)) {
        unsupported.push(line);
      }
    } else if (lower !== "deselect") {
      unsupported.push(line);
    }
  }
  return {
    actions: actions.filter((item) => item.target === "all" || item.target === "target"),
    unsupported,
  };
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
  editableRegions,
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
  const sessionRef = useRef<StructureInteractionSession | undefined>(undefined);
  const desiredScenePml = useRef("");
  const sceneSyncPromise = useRef<Promise<void> | null>(null);
  const sceneSyncTimer = useRef<number | undefined>(undefined);
  const pendingAssistantRegionKey = useRef<string | undefined>(undefined);

  const structureUrl = `/api/v1/artifacts/${projection.structure.token}`;
  const referenceStructures = useMemo(
    () => stageNumber === 2
      ? (session?.reference_structures?.filter((item) => item.role === "reference") || [])
      : [],
    [session?.reference_structures, stageNumber],
  );
  const nativeStructures = useMemo(
    () => [{
      id: projection.structure.sha256,
      sha256: projection.structure.sha256,
      filename: "target.cif",
      objectName: "target",
      required: true,
    }, ...referenceStructures.map((item) => ({
      id: item.object_id,
      sha256: item.sha256,
      filename: item.filename,
      objectName: item.object_name,
      required: false,
      referenceUrl: `/api/v1/structure-sessions/${encodeURIComponent(session?.session_id || "")}/references/${encodeURIComponent(item.object_id)}/file`,
    }))],
    [projection.structure.sha256, referenceStructures, session?.session_id],
  );
  const activeVersion = useMemo(() => activeSceneVersion(session), [session]);
  const legacyScenePml = useMemo(
    () => combinedPml(projection, regions, session),
    [projection, regions, session],
  );
  const authoritativePml = useMemo(
    () => activeVersion?.pml || withRegionOverlay(legacyScenePml, projection, regions),
    [activeVersion?.pml, legacyScenePml, projection, regions],
  );
  const editableRegionKey = useMemo(
    () => regionArrayKey(editableRegions),
    [editableRegions],
  );
  const shouldApplyEditableRegions = (
    !pendingAssistantRegionKey.current
    || pendingAssistantRegionKey.current === editableRegionKey
  );
  const displayOverlayRegions = (
    stageNumber === 2 && editableRegions
      ? (shouldApplyEditableRegions ? editableRegions : undefined)
      : (regions.length ? regions : undefined)
  );
  const scenePml = useMemo(
    () => (
      displayOverlayRegions
        ? replaceManagedRegionSelections(authoritativePml, projection, displayOverlayRegions)
        : authoritativePml
    ),
    [
      authoritativePml,
      displayOverlayRegions,
      projection,
    ],
  );
  const sceneRegions = regions;
  const sceneVersions = session?.scene_versions || [];
  const molstarProjection = useMemo(
    () => pmlToMolstarProjection(scenePml),
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
    sessionRef.current = session;
  }, [session]);
  useEffect(() => {
    if (pendingAssistantRegionKey.current === editableRegionKey) {
      pendingAssistantRegionKey.current = undefined;
    }
  }, [editableRegionKey]);
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

  const flushSceneDraft = useCallback(async () => {
    if (sceneSyncPromise.current) {
      await sceneSyncPromise.current;
      return;
    }
    const operation = (async () => {
      while (true) {
        const current = sessionRef.current;
        const desired = desiredScenePml.current;
        const active = activeSceneVersion(current);
        if (!current || !desired || !active || desired === active.pml) break;
        const response = await api.saveScenePml(
          current.session_id,
          desired,
          "viewer",
          active.version_id,
        );
        sessionRef.current = response.session;
        setSession(response.session);
      }
    })();
    sceneSyncPromise.current = operation;
    try {
      await operation;
    } catch (error) {
      setStatus(
        error instanceof Error
          ? `区域草稿的 PML 版本同步失败：${error.message}`
          : "区域草稿的 PML 版本同步失败",
      );
      throw error;
    } finally {
      if (sceneSyncPromise.current === operation) {
        sceneSyncPromise.current = null;
      }
    }
  }, []);

  useEffect(() => {
    if (stageNumber !== 2 || editableRegions === undefined || !session || !activeVersion) {
      return;
    }
    desiredScenePml.current = scenePml;
    if (scenePml === activeVersion.pml) return;
    if (sceneSyncTimer.current !== undefined) {
      window.clearTimeout(sceneSyncTimer.current);
    }
    sceneSyncTimer.current = window.setTimeout(() => {
      sceneSyncTimer.current = undefined;
      void flushSceneDraft().catch(() => undefined);
    }, 350);
    return () => {
      if (sceneSyncTimer.current !== undefined) {
        window.clearTimeout(sceneSyncTimer.current);
        sceneSyncTimer.current = undefined;
      }
    };
  }, [
    activeVersion,
    editableRegions,
    flushSceneDraft,
    scenePml,
    session,
    stageNumber,
  ]);

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
      const updated = pendingPmlSession.current;
      sessionRef.current = updated;
      setSession(updated);
      pendingPmlSession.current = undefined;
      return;
    }
    const current = sessionRef.current;
    if (!commands?.trim() || !current) return;
    api.appendStructurePml(current.session_id, commands, "viewer")
      .then((updated) => {
        sessionRef.current = updated;
        setSession(updated);
        setStatus("原生 PyMOL 操作已保存为 PML 版本。");
      })
      .catch((error: unknown) => {
        setStatus(error instanceof Error ? error.message : "原生 PyMOL 操作保存失败");
      });
  }, []);
  const nativeFailure = useCallback((failure: string) => {
    setStatus(failure);
  }, []);
  const nativeReady = useCallback(() => {
    setStatus("");
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
      desiredScenePml.current = scenePml;
      await flushSceneDraft();
      const currentSession = sessionRef.current || session;
      const updated = await api.assistantMessage(
        currentSession.session_id,
        text,
      );
      const updatedRegionKey = regionRecordKey(updated.current_regions);
      pendingAssistantRegionKey.current = updatedRegionKey;
      const updatedActive = activeSceneVersion(updated);
      if (updatedActive) desiredScenePml.current = updatedActive.pml;
      if (sceneSyncTimer.current !== undefined) {
        window.clearTimeout(sceneSyncTimer.current);
        sceneSyncTimer.current = undefined;
      }
      setPendingMessages([]);
      setSession(updated);
      sessionRef.current = updated;
      if (stageNumber === 2) {
        onRegionDraft?.(updated.current_regions);
      }
      const latest = updated.messages.at(-1);
      setStatus(latest?.version_id ? "助手已更新 PML 场景并保存版本。" : "助手已生成待确认建议。");
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "结构助手请求失败";
      setPendingMessages([
        optimisticUser,
        {
          ...optimisticAssistant,
          content: `请求失败：${errorMessage}`,
          pending: false,
          failed: true,
        },
      ]);
      setStatus(errorMessage);
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
        session.active_scene_version_id || undefined,
      );
      setSession(response.session);
      sessionRef.current = response.session;
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
                  onReady={nativeReady}
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
                regions={sceneRegions}
                compact={compact}
                onResidueClick={onResidueClick}
                viewActions={molstarProjection.actions}
              />
              {molstarProjection.unsupported.length > 0 && (
                <div className="molstar-compatibility-note">
                  当前场景有 {molstarProjection.unsupported.length} 条 PyMOL 专属命令；
                  Mol* 仅显示可可靠投影的部分，完整场景仍保存在同一 PML 版本中。
                </div>
              )}
            </div>
          )}
        </div>
        <details className="scene-version-panel">
          <summary>
            <span>专家显示设置</span>
            <span>PML、参考结构与历史显示版本</span>
          </summary>
          <div className="scene-version-toolbar">
            <div>
              <strong>PML 场景版本</strong>
              <span>{activeVersion ? `当前版本 ${activeVersion.revision}` : "尚未建立版本"}</span>
            </div>
            <button type="button" onClick={() => setPmlEditorOpen((value) => !value)}>
              {pmlEditorOpen ? "收起 PML" : "编辑 PML"}
            </button>
          </div>
          {stageNumber === 2 && (
            <div className="reference-controls">
              <div>
                <strong>参考结构</strong>
                <span>仅用于第2步可视化比对，不改变目标结构包。</span>
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
          )}
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
                  {!!version.skill_ids?.length && (
                    <small>Skills：{version.skill_ids.join("、")}</small>
                  )}
                </button>
              ))}
            </div>
          )}
        </details>
      </section>
      {assistantOpen && (
        <aside className="structure-assistant">
          <header>
            <div>
              <strong>结构助手</strong>
              <span>完整 PML 驱动 PyMOL；Mol* 显示兼容投影</span>
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
