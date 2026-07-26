import { useEffect, useId, useRef, useState } from "react";
import type { MolstarViewer } from "./types";

interface Region {
  id: string;
  label_seq_ids: number[];
}

interface Props {
  structureUrl?: string;
  regions?: Region[];
  compact?: boolean;
}

const colors: Record<string, string> = {
  A: "#ff4d55",
  B: "#3f7cf7",
  C: "#ffd447",
};

export function MolViewer({ structureUrl, regions = [], compact = false }: Props) {
  const uid = useId().replaceAll(":", "");
  const elementId = `molstar-${uid}`;
  const viewer = useRef<MolstarViewer | null>(null);
  const [status, setStatus] = useState("等待结构");
  const [regionTheme, setRegionTheme] = useState(regions.length > 0);

  useEffect(() => {
    let disposed = false;
    async function load() {
      if (!structureUrl || !window.molstar?.Viewer) return;
      setStatus("载入结构…");
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
        viewportBackgroundColor: "#0b1219",
      });
      if (disposed) {
        instance.dispose?.();
        return;
      }
      viewer.current = instance;
      const mvs = window.molstar.PluginExtensions.mvs;
      const builder = mvs.createBuilder();
      builder.canvas({ background_color: "#0B1219" });
      const structure = builder.download({ url: structureUrl }).parse({ format: "mmcif" }).modelStructure();
      const representation = structure
        .component({ selector: "polymer" })
        .representation({ type: "cartoon" });
      if (regionTheme) {
        for (const region of regions) {
          for (const residue of region.label_seq_ids) {
            representation.color({
              selector: { label_asym_id: "A", label_seq_id: residue },
              color: colors[region.id] || "#22a68a",
            });
          }
        }
      }
      await mvs.loadMVS(instance.plugin, builder.getState(), { replaceExisting: true });
      setStatus("结构已就绪");
    }
    load().catch((error: unknown) =>
      setStatus(error instanceof Error ? error.message : "结构载入失败"),
    );
    return () => {
      disposed = true;
      viewer.current?.dispose?.();
      viewer.current = null;
    };
  }, [structureUrl, elementId, compact, regionTheme, regions]);

  return (
    <div className={`mol-card ${compact ? "compact" : ""}`}>
      <div className="mol-toolbar">
        <span className="live-dot" />
        <span>{status}</span>
        <div className="mol-actions">
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
