(function () {
  "use strict";

  const state = {
    data: null,
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
    if (!data || data.schema_version !== "0.1") {
      throw new Error("viewer-data.json schema_version 不受支持。");
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

  function renderMetadata(data) {
    setText("target-title", data.target_id);
    setText(
      "target-summary",
      `${data.sequence_length} aa · ${data.origin} · mmCIF · Mol* 5.11.0`
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
      "theme-default",
      "theme-pse",
      "center-structure",
    ]) {
      byId(id).disabled = disabled;
    }
  }

  function buildMvs(data) {
    const mvs = molstar.PluginExtensions.mvs;
    const builder = mvs.createBuilder();
    builder.canvas({ background_color: "#EEF1F6" });
    const structure = builder
      .download({ url: data.structure_relative_path })
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
        setButtonState(["theme-default", "theme-pse"], "theme-default");
        await reloadStructure(true);
      } catch (error) {
        showFailure(error);
      }
    });
    byId("theme-pse").addEventListener("click", async () => {
      try {
        state.theme = "pse";
        setButtonState(["theme-default", "theme-pse"], "theme-pse");
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
    state.data = data;
    renderMetadata(data);
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
