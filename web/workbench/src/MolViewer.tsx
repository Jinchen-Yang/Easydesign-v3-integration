import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { MolstarViewer } from "./types";

interface Region {
  id: string;
  label_seq_ids: number[];
}

interface Props {
  structureUrl?: string;
  regions?: Region[];
  compact?: boolean;
  onResidueClick?: (labelSeqId: number) => void;
}

const colors: Record<string, string> = {
  A: "#ff4d55",
  B: "#3f7cf7",
  C: "#ffd447",
};

export const MOL_CANVAS_BACKGROUND = "#EEF1F6";
const EMPTY_REGIONS: Region[] = [];

function structureCount(instance: MolstarViewer) {
  const hierarchy = instance.plugin.managers.structure?.hierarchy?.current;
  return hierarchy?.structures?.length ?? 0;
}

function representationCount(instance: MolstarViewer) {
  const hierarchy = instance.plugin.managers.structure?.hierarchy?.current;
  const structures = hierarchy?.structures ?? [];
  return structures.reduce((total: number, structure: any) => (
    total
    + (structure?.components ?? []).reduce((componentTotal: number, component: any) => (
      componentTotal + (component?.representations?.length ?? 0)
    ), 0)
  ), 0);
}

async function waitForRenderableStructure(instance: MolstarViewer) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (structureCount(instance) > 0 && representationCount(instance) > 0) return;
    await new Promise((resolve) => window.setTimeout(resolve, 50));
  }
  throw new Error("结构文件已读取，但 Mol* 没有建立可显示的结构和表示");
}

export function MolViewer({
  structureUrl,
  regions = EMPTY_REGIONS,
  compact = false,
  onResidueClick,
}: Props) {
  const uid = useId().replaceAll(":", "");
  const elementId = `molstar-${uid}`;
  const viewer = useRef<MolstarViewer | null>(null);
  const generation = useRef(0);
  const loadQueue = useRef<Promise<void>>(Promise.resolve());
  const loadedStructureUrl = useRef<string | null>(null);
  const clickHandler = useRef(onResidueClick);
  const [viewerRevision, setViewerRevision] = useState(0);
  const [status, setStatus] = useState("等待结构");
  const [regionTheme, setRegionTheme] = useState(regions.length > 0);
  const [representation, setRepresentation] = useState<"cartoon" | "surface" | "ball_and_stick">("cartoon");
  const regionKey = JSON.stringify(
    regions.map((region) => ({
      id: region.id,
      label_seq_ids: [...region.label_seq_ids].sort((left, right) => left - right),
    })),
  );
  const normalizedRegions = useMemo(
    () => JSON.parse(regionKey) as Region[],
    [regionKey],
  );
  useEffect(() => {
    clickHandler.current = onResidueClick;
  }, [onResidueClick]);

  useEffect(() => {
    let disposed = false;
    let ownedInstance: MolstarViewer | null = null;
    let clickSubscription: { unsubscribe?: () => void } | undefined;
    async function createViewer() {
      if (!window.molstar?.Viewer) {
        setStatus("Mol* 资源没有正确载入");
        return;
      }
      const instance = await window.molstar.Viewer.create(elementId, {
        extensions: ["mvs"],
        layoutIsExpanded: false,
        layoutShowControls: false,
        layoutShowRemoteState: false,
        layoutShowSequence: !compact,
        layoutShowLog: false,
        layoutShowLeftPanel: false,
        collapseRightPanel: true,
        viewportShowExpand: false,
        viewportShowToggleFullscreen: false,
        viewportShowScreenshotControls: false,
        volumeStreamingDisabled: true,
        pluginStateServer: "",
        powerPreference: "high-performance",
        allowMajorPerformanceCaveat: true,
        viewportBackgroundColor: MOL_CANVAS_BACKGROUND,
      });
      ownedInstance = instance;
      if (disposed) {
        instance.dispose?.();
        return;
      }
      viewer.current = instance;
      const molstar = window.molstar;
      const behavior = instance.plugin.behaviors?.interaction?.click;
      const structureElement = molstar?.lib?.structure?.StructureElement;
      const structureProperties = molstar?.lib?.structure?.StructureProperties;
      if (
        behavior
        && instance.subscribe
        && structureElement?.Loci
        && structureProperties?.residue
      ) {
        clickSubscription = instance.subscribe(behavior, (event: any) => {
          const loci = event?.current?.loci;
          if (!structureElement.Loci?.is(loci)) return;
          let selected: number | undefined;
          structureElement.Loci.forEachLocation(loci, (location: unknown) => {
            if (selected != null) return;
            const value = structureProperties.residue?.label_seq_id(location);
            if (typeof value === "number" && Number.isFinite(value)) {
              selected = value;
            }
          });
          if (selected != null) clickHandler.current?.(selected);
        });
      }
      setViewerRevision((value) => value + 1);
    }
    createViewer().catch((error: unknown) => {
      if (!disposed) {
        setStatus(error instanceof Error ? error.message : "结构载入失败");
      }
    });
    return () => {
      disposed = true;
      generation.current += 1;
      clickSubscription?.unsubscribe?.();
      if (viewer.current === ownedInstance) viewer.current = null;
      ownedInstance?.dispose?.();
    };
  }, [elementId, compact]);

  useEffect(() => {
    const instance = viewer.current;
    if (!structureUrl) {
      setStatus("当前步骤没有可显示的结构");
      return;
    }
    if (!instance || !viewerRevision) return;
    const currentGeneration = generation.current + 1;
    generation.current = currentGeneration;
    const keepCamera = loadedStructureUrl.current === structureUrl;
    setStatus("载入结构…");
    loadQueue.current = loadQueue.current
      .catch(() => undefined)
      .then(async () => {
        if (generation.current !== currentGeneration || viewer.current !== instance) return;
        const mvs = window.molstar?.PluginExtensions.mvs;
        if (!mvs) throw new Error("Mol* MVS 资源没有正确载入");
        const builder = mvs.createBuilder();
        builder.canvas({ background_color: MOL_CANVAS_BACKGROUND });
        const structure = builder
          .download({ url: structureUrl })
          .parse({ format: "mmcif" })
          .modelStructure();
        const representationNode = structure
          .component({ selector: "polymer" })
          .representation({ type: representation });
        if (regionTheme) {
          for (const region of normalizedRegions) {
            for (const residue of region.label_seq_ids) {
              representationNode.color({
                selector: { label_asym_id: "A", label_seq_id: residue },
                color: colors[region.id] || "#22a68a",
              });
            }
          }
        }
        await mvs.loadMVS(
          instance.plugin,
          builder.getState({
            title: "EasyDesign structure workspace",
            description: "EasyDesign scientific workbench",
          }),
          { replaceExisting: true, keepCamera },
        );
        if (generation.current !== currentGeneration || viewer.current !== instance) return;
        await waitForRenderableStructure(instance);
        if (generation.current !== currentGeneration || viewer.current !== instance) return;
        loadedStructureUrl.current = structureUrl;
        if (!keepCamera) {
          await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
          instance.plugin.managers.camera.reset();
        }
        setStatus("结构已就绪");
      })
      .catch((error: unknown) => {
        if (generation.current === currentGeneration && viewer.current === instance) {
          setStatus(error instanceof Error ? error.message : "结构载入失败");
        }
      });
  }, [
    structureUrl,
    viewerRevision,
    regionTheme,
    normalizedRegions,
    representation,
  ]);

  return (
    <div className={`mol-card ${compact ? "compact" : ""}`}>
      <div className="mol-toolbar">
        <span className="live-dot" />
        <span>{status}</span>
        <div className="mol-actions">
          <button type="button" className={representation === "cartoon" ? "active" : ""} onClick={() => setRepresentation("cartoon")}>Cartoon</button>
          <button type="button" className={representation === "surface" ? "active" : ""} onClick={() => setRepresentation("surface")}>Surface</button>
          <button type="button" className={representation === "ball_and_stick" ? "active" : ""} onClick={() => setRepresentation("ball_and_stick")}>Stick</button>
          {regions.length > 0 && (
            <button
              type="button"
              className={regionTheme ? "active" : ""}
              onClick={() => setRegionTheme((value) => !value)}
            >
              区域颜色
            </button>
          )}
          <button type="button" onClick={() => viewer.current?.plugin.managers.camera.reset()}>
            居中
          </button>
        </div>
      </div>
      <div id={elementId} className="mol-viewport" aria-label="Mol* 三维结构" />
    </div>
  );
}
