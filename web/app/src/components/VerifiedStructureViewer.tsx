import { useEffect, useRef, useState } from "react";
import type { AtomSelectionSpec, GLViewer } from "3dmol";
import { RotateCcw, Rotate3D, ZoomIn, ZoomOut } from "lucide-react";
import type { Artifact, Site } from "../data/product-contracts";
import { useTranslation } from "react-i18next";

const verifiedStructureCache = new Map<string, ArrayBuffer>();

function cacheStructure(key: string, data: ArrayBuffer) {
  verifiedStructureCache.delete(key);
  verifiedStructureCache.set(key, data);
  while (verifiedStructureCache.size > 8)
    verifiedStructureCache.delete(
      verifiedStructureCache.keys().next().value as string,
    );
}

/** Exactly one verified artifact per view. Missing evidence stays visibly unavailable. */
export function VerifiedStructureViewer({
  artifact,
  roles,
  sites = [],
  selectedSite,
  showArtifactLabel = true,
  emptyMessage = "Structure evidence is not available yet.",
}: {
  artifact: Artifact | null;
  roles: Record<string, string>;
  sites?: Site[];
  selectedSite?: string;
  showArtifactLabel?: boolean;
  emptyMessage?: string;
}) {
  const { t } = useTranslation("easy");
  const host = useRef<HTMLDivElement>(null),
    viewer = useRef<GLViewer | null>(null),
    framedView = useRef<number[]>([]);
  const [status, setStatus] = useState("loading"),
    [retry, setRetry] = useState(0),
    [modelVersion, setModelVersion] = useState(0);
  const [representation, setRepresentation] = useState<"cartoon" | "sticks">(
    "cartoon",
  );
  const [chainMode, setChainMode] = useState("all");
  useEffect(() => {
    setChainMode("all");
  }, [artifact?.id]);
  const rolesKey = JSON.stringify(roles),
    sitesKey = JSON.stringify(sites);

  // Artifact loading, integrity verification and parsing are tied only to the
  // artifact. Site/representation controls are deliberately handled below so
  // changing a highlight never downloads or reparses the same structure.
  useEffect(() => {
    if (!artifact) {
      viewer.current?.clear();
      viewer.current = null;
      host.current?.replaceChildren();
      setStatus("unavailable");
      return;
    }
    const abort = new AbortController();
    let instance: GLViewer | undefined;
    let observer: ResizeObserver | undefined;
    setStatus("loading");
    void (async () => {
      try {
        if (!["pdb", "cif", "mmcif"].includes(artifact.format))
          throw new Error("Unsupported structure format");
        // URLs include the authorized scope. Reusing bytes must preserve both the
        // manifest identity and its size contract, including across Easy/Pro.
        const cacheKey = JSON.stringify([
          artifact.url,
          artifact.sha256,
          artifact.size_bytes,
        ]);
        let data = verifiedStructureCache.get(cacheKey);
        if (!data) {
          const response = await fetch(artifact.url, {
            credentials: "same-origin",
            signal: abort.signal,
          });
          if (!response.ok)
            throw new Error("Verified structure is unavailable");
          data = await response.arrayBuffer();
          const hash = Array.from(
            new Uint8Array(await crypto.subtle.digest("SHA-256", data)),
          )
            .map((b) => b.toString(16).padStart(2, "0"))
            .join("");
          if (
            hash !== artifact.sha256 ||
            data.byteLength !== artifact.size_bytes
          )
            throw new Error("Structure integrity check failed");
          cacheStructure(cacheKey, data);
        }
        const mol = await import("3dmol");
        if (abort.signal.aborted || !host.current) return;
        host.current.replaceChildren();
        instance = mol.createViewer(host.current, {
          backgroundColor: "#fafafd",
          antialias: true,
        });
        instance.addModel(
          new TextDecoder().decode(data),
          artifact.format === "pdb" ? "pdb" : "cif",
          { doAssembly: false },
        );
        if (!instance.selectedAtoms({}).length)
          throw new Error("No readable atoms");
        instance.zoomTo();
        instance.zoom(Object.values(roles).includes("binder") ? 1.55 : 1.28);
        instance.rotate(20, "x");
        instance.rotate(-35, "y");
        framedView.current = instance.getView();
        instance.render();
        viewer.current = instance;
        observer = new ResizeObserver(() => instance?.resize());
        observer.observe(host.current);
        setModelVersion((value) => value + 1);
        setStatus("ready");
      } catch (error) {
        if (!abort.signal.aborted) {
          instance?.clear();
          setStatus((error as Error).message);
        }
      }
    })();
    return () => {
      abort.abort();
      observer?.disconnect();
      instance?.clear();
      viewer.current = null;
      host.current?.replaceChildren();
    };
  }, [
    artifact?.id,
    artifact?.sha256,
    artifact?.url,
    artifact?.size_bytes,
    artifact?.format,
    retry,
  ]);

  useEffect(() => {
    const instance = viewer.current;
    if (!instance || status !== "ready") return;
    try {
      // Short peptides / sparse fixtures may have no drawable ribbon. Show their
      // actual atoms even when no bonds can be drawn between isolated Cα atoms.
      const sparse = instance.selectedAtoms({ atom: "CA" }).length < 20;
      const style = (color: string) => ({
        ...(representation === "cartoon"
          ? { cartoon: { color } }
          : { stick: { color, radius: 0.15 } }),
        ...(sparse
          ? { stick: { color, radius: 0.15 }, sphere: { color, radius: 0.45 } }
          : {}),
      });
      instance.setStyle({}, style("#b9bdc9"));
      for (const [chain, role] of Object.entries(
        JSON.parse(rolesKey) as Record<string, string>,
      )) {
        if (!instance.selectedAtoms({ chain }).length)
          throw new Error("Declared chain missing from structure");
        instance.setStyle(
          { chain },
          style(
            role === "focus-target"
              ? "#6657e8"
              : role === "binder"
                ? "#8070d6"
                : "#b9bdc9",
          ),
        );
      }
      // Draw the selected site last: overlapping alternatives must not erase it.
      const highlightedSites = (JSON.parse(sitesKey) as Site[]).sort(
        (a, b) => Number(a.id === selectedSite) - Number(b.id === selectedSite),
      );
      for (const site of highlightedSites) {
        const selected = site.id === selectedSite;
        const color = selected ? "#8270d4" : "#d5d1ea";
        for (const point of site.coordinates) {
          const selection: AtomSelectionSpec = {
            chain: point.author_chain_id,
            resi: Number(point.author_residue_id),
            predicate: (atom) =>
              (atom.icode || "").trim() === (point.insertion_code || "").trim(),
          };
          instance.addStyle(selection, {
            ...(representation === "cartoon"
              ? {
                  cartoon: {
                    color: selected ? "#6657e8" : "#d5d1ea",
                    thickness: 0.7,
                  },
                }
              : {}),
            stick: { color, radius: selected ? 0.23 : 0.14 },
            ...(sparse
              ? { sphere: { color, radius: selected ? 0.65 : 0.45 } }
              : {}),
          });
        }
      }
      if (chainMode !== "all") {
        const chainRoles = JSON.parse(rolesKey) as Record<string, string>;
        const chains = new Set(
          instance.selectedAtoms({}).map((atom) => atom.chain || ""),
        );
        for (const chain of chains) {
          const role = chainRoles[chain];
          const visible =
            chainMode === "target"
              ? role === "target" || role === "focus-target"
              : role === chainMode;
          if (!visible) instance.setStyle({ chain }, {});
        }
      }
      instance.render();
    } catch (error) {
      setStatus((error as Error).message);
    }
  }, [
    chainMode,
    modelVersion,
    representation,
    rolesKey,
    selectedSite,
    sitesKey,
    status,
  ]);
  return (
    <section
      className="molecule live-molecule"
      aria-label={t("Molecular structure")}
      data-status={status}
      data-artifact={artifact?.id}
      data-candidate={artifact?.candidate_id || ""}
    >
      <div className="viewer-top">
        {showArtifactLabel && (
          <span className="pdb-label" title={artifact?.label}>
            {artifact?.label || t("Target structure")}
          </span>
        )}
        <div className="viewer-view-toggle">
          <button
            aria-pressed={representation === "cartoon"}
            onClick={() => setRepresentation("cartoon")}
          >
            {t("Ribbon")}
          </button>
          <button
            aria-pressed={representation === "sticks"}
            onClick={() => setRepresentation("sticks")}
          >
            {t("Atoms")}
          </button>
        </div>
      </div>
      <div
        ref={host}
        className="molecule-canvas live-canvas"
        aria-label={t("Interactive structure — drag to rotate, scroll to zoom")}
      />
      {status === "ready" && (
        <>
          <div className="viewer-controls">
            <button
              aria-label={t("Reset structure view")}
              onClick={() => {
                viewer.current?.setView(framedView.current);
                viewer.current?.render();
              }}
            >
              <RotateCcw size={14} />
            </button>
            <button
              aria-label={t("Zoom in")}
              onClick={() => {
                viewer.current?.zoom(1.2);
                viewer.current?.render();
              }}
            >
              <ZoomIn size={14} />
            </button>
            <button
              aria-label={t("Zoom out")}
              onClick={() => {
                viewer.current?.zoom(0.8);
                viewer.current?.render();
              }}
            >
              <ZoomOut size={14} />
            </button>
          </div>
          <span className="rotate-hint">
            <Rotate3D size={12} />
            {t("Drag to explore")}
          </span>
        </>
      )}
      {status !== "ready" && (
        <div className="live-viewer-status" role="status">
          {status === "loading"
            ? t("Loading verified coordinates…")
            : status === "unavailable"
              ? t(emptyMessage)
              : t(status)}
          {artifact && status !== "loading" && (
            <button onClick={() => setRetry((r) => r + 1)}>
              {t("Retry structure")}
            </button>
          )}
        </div>
      )}
      <div className="viewer-bottom">
        <label className="chain-picker">
          {t("Show")}{" "}
          <select
            aria-label={t("Structure chains")}
            value={chainMode}
            onChange={(e) => setChainMode(e.target.value)}
          >
            <option value="all">
              {Object.values(roles).includes("binder")
                ? t("Target + VHH")
                : Object.values(roles).includes("focus-target")
                  ? t("Target + partners")
                  : t("Target")}
            </option>
            {Object.values(roles).includes("binder") && (
              <>
                <option value="target">{t("Target")}</option>
                <option value="binder">VHH</option>
              </>
            )}
          </select>
        </label>
        <span className="viewer-selection">
          {sites.length
            ? t("Site {site} highlighted", {
                site: sites.find((s) => s.id === selectedSite)?.rank || "",
              })
            : artifact?.candidate_id
              ? Object.values(roles).includes("focus-target")
                ? t("Target chain highlighted")
                : t("Candidate complex")
              : t("Target structure")}
        </span>
      </div>
    </section>
  );
}
