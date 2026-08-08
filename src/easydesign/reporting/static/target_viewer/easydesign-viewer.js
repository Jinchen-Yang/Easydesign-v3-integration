(function () {
  "use strict";

  const state = {
    data: null,
    overlay: null,
    evidence: null,
    structureUrl: null,
    viewer: null,
    representation: "cartoon",
    theme: "default",
    loading: false,
  };
  const representationTypes = {
    cartoon: "cartoon",
    surface: "surface",
    stick: "ball_and_stick",
  };

  window.__EASYDESIGN_VIEWER_READY__ = false;
  window.__EASYDESIGN_VIEWER_STATE__ = state;

  function byId(id) {
    const element = document.getElementById(id);
    if (!element) throw new Error(`页面缺少必要元素：${id}`);
    return element;
  }

  function setText(id, value) {
    byId(id).textContent = String(value);
  }

  function showFailure(error) {
    const message = error instanceof Error ? error.message : String(error);
    setText("viewer-error-message", message || "未知错误");
    byId("viewer-error").hidden = false;
    const status = byId("load-state");
    status.textContent = "加载失败";
    status.classList.remove("ready");
    status.classList.add("failed");
    window.__EASYDESIGN_VIEWER_ERROR__ = message;
  }

  function validateData(data) {
    if (!data || !["0.1", "0.2"].includes(data.schema_version)) {
      throw new Error("viewer-data.json schema_version 不受支持。");
    }
    if (
      data.schema_version === "0.2" &&
      (!Array.isArray(data.coordinate_model_ids) ||
        data.coordinate_model_ids.length !== data.coordinate_model_count ||
        !data.coordinate_model_ids.includes(data.representative_model_id))
    ) {
      throw new Error("Viewer coordinate ensemble 信息非法。");
    }
    if (!Array.isArray(data.residues) || data.residues.length !== data.sequence_length) {
      throw new Error("Viewer residue mapping 数量与序列长度不一致。");
    }
    const keys = new Set();
    for (const residue of data.residues) {
      const key = `${residue.label_asym_id}:${residue.label_seq_id}`;
      if (keys.has(key)) throw new Error(`Viewer mapping 存在重复残基：${key}`);
      keys.add(key);
    }
    if (!data.annotation || !["available", "not_applicable"].includes(data.annotation.status)) {
      throw new Error("Viewer annotation 状态非法。");
    }
  }

  function validateOverlay(overlay) {
    if (!overlay || overlay.schema_version !== "0.1" || !Array.isArray(overlay.layers)) {
      throw new Error("stage02-regions.json schema_version 不受支持。");
    }
    for (const layer of overlay.layers) {
      if (!Array.isArray(layer.regions) || layer.regions.length < 1 || layer.regions.length > 3) {
        throw new Error(`Stage 02 layer ${layer.id} 区域数量非法。`);
      }
      for (const region of layer.regions) {
        const expected = { A: "#EF4444", B: "#3B82F6", C: "#FACC15" }[region.id];
        if (!expected || expected !== region.color_hex || !Array.isArray(region.residues)) {
          throw new Error(`Stage 02 region ${region.id} 颜色或 residue 数据非法。`);
        }
      }
    }
  }

  function validateEvidence(evidence) {
    if (!evidence || evidence.schema_version !== "0.1" || !Array.isArray(evidence.structures)) {
      throw new Error("evidence.json schema_version 不受支持。");
    }
    const ids = new Set();
    for (const item of evidence.structures) {
      if (
        ids.has(item.id) ||
        !["pilot-representative", "final-selection"].includes(item.kind) ||
        !item.structure_url.startsWith("/evidence-structures/")
      ) {
        throw new Error(`Evidence structure 非法：${item.id}`);
      }
      ids.add(item.id);
    }
  }

  function formatValue(value) {
    if (typeof value === "boolean") return value ? "是" : "否";
    return String(value);
  }

  function renderMetrics(elementId, metrics) {
    const container = byId(elementId);
    container.replaceChildren();
    for (const metric of metrics) {
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = metric.label;
      detail.textContent = formatValue(metric.value);
      container.append(term, detail);
    }
  }

  function renderDownloads(downloads) {
    const container = byId("downloads");
    container.replaceChildren();
    for (const item of downloads) {
      const link = document.createElement("a");
      link.href = item.relative_path;
      link.download = item.relative_path.split("/").pop();
      link.textContent = item.label;
      link.title = `SHA-256: ${item.sha256}`;
      container.append(link);
    }
  }

  function renderColorCounts(annotation) {
    if (annotation.status !== "available") return;
    byId("pse-controls").hidden = false;
    const container = byId("pse-color-counts");
    container.replaceChildren();
    for (const entry of annotation.color_counts) {
      const chip = document.createElement("span");
      chip.className = "color-chip";
      const swatch = document.createElement("span");
      swatch.className = "color-swatch";
      swatch.style.backgroundColor = entry.color_hex;
      const text = document.createElement("span");
      text.textContent = `${entry.color_hex} · ${entry.residue_count}`;
      chip.append(swatch, text);
      container.append(chip);
    }
  }

  function themeButtonIds() {
    const values = ["theme-default", "theme-pse"];
    if (state.overlay) {
      for (const layer of state.overlay.layers) values.push(`theme-region-${layer.id}`);
    }
    return values;
  }

  function renderStage02(overlay) {
    if (!overlay || overlay.layers.length === 0) return;
    byId("stage02-controls").hidden = false;
    const container = byId("stage02-methods");
    container.replaceChildren();
    for (const layer of overlay.layers) {
      const button = document.createElement("button");
      button.id = `theme-region-${layer.id}`;
      button.type = "button";
      button.textContent = layer.approved ? `${layer.label}（已批准）` : layer.label;
      button.addEventListener("click", async () => {
        try {
          state.theme = `region:${layer.id}`;
          setButtonState(themeButtonIds(), button.id);
          await reloadStructure(true);
        } catch (error) {
          showFailure(error);
        }
      });
      container.append(button);
    }
  }

  function evidenceButtonIds() {
    return [
      "evidence-target",
      ...(state.evidence ? state.evidence.structures.map((_, index) => `evidence-${index}`) : []),
    ];
  }

  function renderEvidence(evidence) {
    if (!evidence || evidence.structures.length === 0) return;
    byId("evidence-controls").hidden = false;
    const container = byId("evidence-structures");
    container.replaceChildren();
    const target = document.createElement("button");
    target.id = "evidence-target";
    target.type = "button";
    target.className = "active";
    target.textContent = "Target / site";
    target.addEventListener("click", async () => {
      state.structureUrl = null;
      setButtonState(evidenceButtonIds(), target.id);
      await reloadStructure(false);
    });
    container.append(target);
    evidence.structures.forEach((item, index) => {
      const button = document.createElement("button");
      button.id = `evidence-${index}`;
      button.type = "button";
      button.textContent = item.label;
      button.title = `SHA-256: ${item.sha256}`;
      button.addEventListener("click", async () => {
        state.structureUrl = item.structure_url;
        setButtonState(evidenceButtonIds(), button.id);
        await reloadStructure(false);
      });
      container.append(button);
    });
  }

  function renderMetadata(data) {
    setText("target-title", data.target_id);
    setText(
      "target-summary",
      `${data.sequence_length} aa · ${data.origin} · mmCIF · ` +
        `${data.coordinate_model_count || 1} model(s) · ` +
        `representative ${data.representative_model_id || "1"} · Mol* 5.11.0`
    );
    renderMetrics("quality-metrics", data.quality_metrics);
    renderMetrics("provenance-metrics", data.provenance_metrics);
    renderDownloads(data.downloads);
    renderColorCounts(data.annotation);
  }

  function setButtonState(group, active) {
    for (const value of group) {
      const button = byId(value);
      button.classList.toggle("active", value === active);
      button.setAttribute("aria-pressed", value === active ? "true" : "false");
    }
  }

  function setButtonsDisabled(disabled) {
    for (const id of [
      "representation-cartoon",
      "representation-surface",
      "representation-stick",
      "center-structure",
      ...themeButtonIds(),
    ]) {
      byId(id).disabled = disabled;
    }
  }

  function buildMvs(data) {
    const mvs = molstar.PluginExtensions.mvs;
    const builder = mvs.createBuilder();
    builder.canvas({ background_color: "#EEF1F6" });
    const structure = builder
      .download({ url: state.structureUrl || data.structure_relative_path })
      .parse({ format: "mmcif" })
      .modelStructure();
    const representation = structure
      .component({ selector: "polymer" })
      .representation({ type: representationTypes[state.representation] });
    if (state.theme === "pse") {
      for (const residue of data.residues) {
        if (!residue.pse_color_hex) {
          throw new Error("PSE 来源颜色不完整，拒绝显示部分着色结果。");
        }
        representation.color({
          selector: {
            label_asym_id: residue.label_asym_id,
            label_seq_id: residue.label_seq_id,
          },
          color: residue.pse_color_hex,
        });
      }
    } else if (state.theme.startsWith("region:")) {
      const layerId = state.theme.split(":", 2)[1];
      const layer = state.overlay.layers.find((item) => item.id === layerId);
      if (!layer) throw new Error(`Stage 02 layer 不存在：${layerId}`);
      for (const region of layer.regions) {
        for (const residue of region.residues) {
          representation.color({
            selector: {
              label_asym_id: residue.label_asym_id,
              label_seq_id: residue.label_seq_id,
            },
            color: region.color_hex,
          });
        }
      }
    }
    return builder.getState({
      title: `EasyDesign ${data.target_id}`,
      description: "Stage 01 portable target viewer",
    });
  }

  async function reloadStructure(keepCamera) {
    if (state.loading) return;
    state.loading = true;
    setButtonsDisabled(true);
    try {
      const mvsState = buildMvs(state.data);
      await molstar.PluginExtensions.mvs.loadMVS(state.viewer.plugin, mvsState, {
        replaceExisting: true,
        keepCamera: Boolean(keepCamera),
      });
    } finally {
      state.loading = false;
      setButtonsDisabled(false);
    }
  }

  function residueKey(chain, labelSeqId) {
    return `${chain}:${labelSeqId}`;
  }

  function subscribeToResidues(data) {
    const lookup = new Map(
      data.residues.map((residue) => [
        residueKey(residue.label_asym_id, residue.label_seq_id),
        residue,
      ])
    );
    state.viewer.subscribe(state.viewer.plugin.behaviors.interaction.click, (event) => {
      const loci = event.current && event.current.loci;
      const structureElement = molstar.lib.structure.StructureElement;
      if (!structureElement.Loci.is(loci)) return;
      let selected = null;
      structureElement.Loci.forEachLocation(loci, (location) => {
        if (selected) return;
        const properties = molstar.lib.structure.StructureProperties;
        const chain = properties.chain.label_asym_id(location);
        const labelSeqId = properties.residue.label_seq_id(location);
        selected = lookup.get(residueKey(chain, labelSeqId)) || null;
      });
      if (!selected) {
        setText("selected-residue", "所选位置无法映射到 Stage 01 residue mapping。");
        return;
      }
      const insertion = selected.insertion_code || "—";
      const container = byId("selected-residue");
      const headline = document.createElement("strong");
      headline.textContent = `${selected.amino_acid} · sequence ${selected.sequence_index}`;
      container.replaceChildren(headline);
      container.append(
        document.createElement("br"),
        `label: ${selected.label_asym_id}:${selected.label_seq_id}`,
        document.createElement("br"),
        `author: ${selected.auth_asym_id}:${selected.auth_seq_id} · insertion: ${insertion}`
      );
    });
  }

  function bindControls() {
    for (const name of Object.keys(representationTypes)) {
      byId(`representation-${name}`).addEventListener("click", async () => {
        try {
          state.representation = name;
          setButtonState(
            [
              "representation-cartoon",
              "representation-surface",
              "representation-stick",
            ],
            `representation-${name}`
          );
          await reloadStructure(true);
        } catch (error) {
          showFailure(error);
        }
      });
    }
    byId("theme-default").addEventListener("click", async () => {
      try {
        state.theme = "default";
        setButtonState(themeButtonIds(), "theme-default");
        await reloadStructure(true);
      } catch (error) {
        showFailure(error);
      }
    });
    byId("theme-pse").addEventListener("click", async () => {
      try {
        state.theme = "pse";
        setButtonState(themeButtonIds(), "theme-pse");
        await reloadStructure(true);
      } catch (error) {
        showFailure(error);
      }
    });
    byId("center-structure").addEventListener("click", () => {
      try {
        state.viewer.plugin.managers.camera.reset();
      } catch (error) {
        showFailure(error);
      }
    });
  }

  function requireWebGl() {
    const probe = document.createElement("canvas");
    const context =
      probe.getContext("webgl2") ||
      probe.getContext("webgl") ||
      probe.getContext("experimental-webgl");
    if (!context) {
      throw new Error(
        "WebGL 不可用。请启用浏览器硬件加速，或使用支持 WebGL 的桌面 Chromium。"
      );
    }
  }

  async function start() {
    if (!window.molstar || !molstar.Viewer) {
      throw new Error("Mol* 5.11.0 本地资源未加载。");
    }
    requireWebGl();
    const response = await fetch("viewer-data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`无法读取 viewer-data.json：HTTP ${response.status}`);
    }
    const data = await response.json();
    validateData(data);
    const overlayResponse = await fetch("stage02-regions.json", { cache: "no-store" });
    let overlay = null;
    if (overlayResponse.ok) {
      overlay = await overlayResponse.json();
      validateOverlay(overlay);
    } else if (overlayResponse.status !== 404) {
      throw new Error(`无法读取 stage02-regions.json：HTTP ${overlayResponse.status}`);
    }
    const evidenceResponse = await fetch("evidence.json", { cache: "no-store" });
    let evidence = null;
    if (evidenceResponse.ok) {
      evidence = await evidenceResponse.json();
      validateEvidence(evidence);
    } else if (evidenceResponse.status !== 404) {
      throw new Error(`无法读取 evidence.json：HTTP ${evidenceResponse.status}`);
    }
    state.data = data;
    state.overlay = overlay;
    state.evidence = evidence;
    renderMetadata(data);
    renderStage02(overlay);
    renderEvidence(evidence);
    bindControls();
    state.viewer = await molstar.Viewer.create("molstar-viewer", {
      extensions: ["mvs"],
      layoutIsExpanded: false,
      layoutShowControls: true,
      layoutShowRemoteState: false,
      layoutShowSequence: true,
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
      viewportBackgroundColor: "#EEF1F6",
    });
    subscribeToResidues(data);
    await reloadStructure(false);
    const status = byId("load-state");
    status.textContent = "已就绪";
    status.classList.add("ready");
    window.__EASYDESIGN_VIEWER_READY__ = true;
  }

  start().catch(showFailure);
})();
