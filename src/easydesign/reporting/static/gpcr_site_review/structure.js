(function () {
  "use strict";

  const data = window.__GPCR_REVIEW_DATA__;
  const layerColors = {
    tm: "#2A8A78",
    ecl: "#6DA947",
    icl: "#D68F2F",
    ecd: "#3477AD",
    ligand: "#DDBD32",
    partner: "#7A6A9D",
    candidate: "#DC5845",
    avoid: "#AA3E75",
  };
  const state = {
    viewer: null,
    mode: data && data.mode === "activate" ? "activate" : "inhibit",
    layers: new Set(),
    blobUrl: null,
    loading: false,
  };

  window.__GPCR_REVIEW_READY__ = false;
  window.__GPCR_REVIEW_STATE__ = state;

  function byId(id) {
    const element = document.getElementById(id);
    if (!element) throw new Error(`Page is missing required element: ${id}`);
    return element;
  }

  function showFailure(error) {
    const message = error instanceof Error ? error.message : String(error);
    byId("viewer-error-message").textContent = message || "Unknown error";
    byId("viewer-error").hidden = false;
    const status = byId("load-state");
    status.textContent = "Viewer failed";
    status.classList.add("failed");
    window.__GPCR_REVIEW_ERROR__ = message;
  }

  function validateData() {
    if (!data || data.schema_version !== "1.0" || data.read_only !== true) {
      throw new Error("Invalid or writable review-data.js payload.");
    }
    if (!data.structure || !["pdb", "mmcif"].includes(data.structure.format)) {
      throw new Error("Unsupported structure payload.");
    }
    if (!Array.isArray(data.candidate_residues) || !Array.isArray(data.warnings)) {
      throw new Error("Review candidate or warning data is malformed.");
    }
  }

  function segmentLayer(segment) {
    const normalized = String(segment || "").toUpperCase();
    if (/^TM[1-7]$/.test(normalized)) return "tm";
    if (/^ECL/.test(normalized)) return "ecl";
    if (/^(ICL|H8)/.test(normalized)) return "icl";
    if (/^(ECD|N-TERM|NTERM|GAIN|GPS|VFT|CRD)/.test(normalized)) return "ecd";
    return null;
  }

  function selectorFor(residue) {
    if (residue.label_asym_id && Number.isInteger(residue.label_seq_id)) {
      return {
        label_asym_id: residue.label_asym_id,
        label_seq_id: residue.label_seq_id,
      };
    }
    const authSeqId = Number(residue.auth_seq_id);
    if (residue.auth_asym_id && Number.isInteger(authSeqId)) {
      const selector = {
        auth_asym_id: residue.auth_asym_id,
        auth_seq_id: authSeqId,
      };
      if (residue.insertion_code) {
        selector.pdbx_PDB_ins_code = residue.insertion_code;
      }
      return selector;
    }
    return null;
  }

  function sameResidue(first, second) {
    if (
      first.label_asym_id &&
      second.label_asym_id &&
      Number.isInteger(first.label_seq_id) &&
      Number.isInteger(second.label_seq_id)
    ) {
      return (
        first.label_asym_id === second.label_asym_id &&
        first.label_seq_id === second.label_seq_id
      );
    }
    return (
      first.auth_asym_id === second.auth_asym_id &&
      String(first.auth_seq_id || "") === String(second.auth_seq_id || "") &&
      String(first.insertion_code || "") === String(second.insertion_code || "")
    );
  }

  function roleIsAvoid(role) {
    return String(role || "").toLowerCase().includes("avoid");
  }

  function modeMatches(item) {
    return item.mode === state.mode || item.mode === "both";
  }

  function residueColor(residue) {
    const matching = data.candidate_residues.filter(
      (candidate) => modeMatches(candidate) && sameResidue(candidate, residue)
    );
    if (state.layers.has("avoid") && matching.some((item) => roleIsAvoid(item.role))) {
      return layerColors.avoid;
    }
    if (state.layers.has("candidate") && matching.some((item) => !roleIsAvoid(item.role))) {
      return layerColors.candidate;
    }
    const layer = segmentLayer(residue.segment);
    return layer && state.layers.has(layer) ? layerColors[layer] : null;
  }

  function addCandidateRepresentations(structure) {
    for (const residue of data.candidate_residues) {
      if (!modeMatches(residue)) continue;
      const avoid = roleIsAvoid(residue.role);
      if ((avoid && !state.layers.has("avoid")) || (!avoid && !state.layers.has("candidate"))) {
        continue;
      }
      const selector = selectorFor(residue);
      if (!selector) continue;
      structure
        .component({ selector })
        .representation({ type: "ball_and_stick" })
        .color({ color: avoid ? layerColors.avoid : layerColors.candidate });
    }
  }

  function addPartnerRepresentations(structure) {
    if (!state.layers.has("partner")) return;
    for (const chain of data.chains) {
      const role = String(chain.role || "").toLowerCase();
      if (!chain.label_asym_id || role.includes("receptor") || role.includes("ligand")) continue;
      structure
        .component({ selector: { label_asym_id: chain.label_asym_id } })
        .representation({ type: "cartoon" })
        .color({ color: layerColors.partner });
    }
  }

  function buildMvs() {
    const mvs = molstar.PluginExtensions.mvs;
    const builder = mvs.createBuilder();
    builder.canvas({ background_color: "#EEF2EF" });
    const structure = builder
      .download({ url: state.blobUrl })
      .parse({ format: data.structure.format })
      .modelStructure();
    const polymer = structure
      .component({ selector: "polymer" })
      .representation({ type: "cartoon" });
    polymer.color({ color: "#AEB9B2" });
    for (const residue of data.residues) {
      const selector = selectorFor(residue);
      const color = residueColor(residue);
      if (selector && color) polymer.color({ selector, color });
    }
    if (state.layers.has("ligand")) {
      structure
        .component({ selector: "ligand" })
        .representation({ type: "ball_and_stick" })
        .color({ color: layerColors.ligand });
    }
    addPartnerRepresentations(structure);
    addCandidateRepresentations(structure);
    return builder.getState({
      title: `GPCR hotspot review · ${data.identity.structure_id}`,
      description: "Read-only local GPCR hotspot evidence",
    });
  }

  async function reloadStructure(keepCamera) {
    if (state.loading) return;
    state.loading = true;
    try {
      await molstar.PluginExtensions.mvs.loadMVS(state.viewer.plugin, buildMvs(), {
        replaceExisting: true,
        keepCamera: Boolean(keepCamera),
      });
    } finally {
      state.loading = false;
    }
  }

  function formatResidue(residue) {
    const amino = residue.amino_acid || "Residue";
    const number = residue.auth_seq_id || residue.label_seq_id || "?";
    return `${amino} ${number}${residue.insertion_code || ""}`;
  }

  function showResidue(residue) {
    const box = byId("selected-residue");
    box.replaceChildren();
    const strong = document.createElement("strong");
    strong.textContent = formatResidue(residue);
    box.append(strong, document.createElement("br"));
    box.append(
      `Author ${residue.auth_asym_id || "?"}:${residue.auth_seq_id || "?"}${residue.insertion_code || ""}`,
      document.createElement("br"),
      Number.isInteger(residue.label_seq_id)
        ? `Label ${residue.label_asym_id || "?"}:${residue.label_seq_id}`
        : "Label unavailable (PDB source)",
      document.createElement("br"),
      `Generic ${residue.generic_number || "unresolved"} · ${residue.segment || "unresolved"}`
    );
  }

  function subscribeToResidues() {
    const lookup = new Map(
      [...data.residues, ...data.candidate_residues]
        .filter((residue) => selectorFor(residue))
        .flatMap((residue) => {
          const keys = [];
          if (residue.label_asym_id && Number.isInteger(residue.label_seq_id)) {
            keys.push(`label:${residue.label_asym_id}:${residue.label_seq_id}`);
          }
          if (residue.auth_asym_id && residue.auth_seq_id) {
            keys.push(
              `auth:${residue.auth_asym_id}:${residue.auth_seq_id}:` +
                `${residue.insertion_code || ""}`
            );
          }
          return keys.map((key) => [key, residue]);
        })
    );
    state.viewer.subscribe(state.viewer.plugin.behaviors.interaction.click, (event) => {
      const loci = event.current && event.current.loci;
      const structureElement = molstar.lib.structure.StructureElement;
      if (!structureElement.Loci.is(loci)) return;
      let selected = null;
      structureElement.Loci.forEachLocation(loci, (location) => {
        if (selected) return;
        const properties = molstar.lib.structure.StructureProperties;
        selected = lookup.get(
          `label:${properties.chain.label_asym_id(location)}:` +
            `${properties.residue.label_seq_id(location)}`
        );
        if (!selected) {
          selected = lookup.get(
            `auth:${properties.chain.auth_asym_id(location)}:` +
              `${properties.residue.auth_seq_id(location)}:` +
              `${properties.residue.pdbx_PDB_ins_code(location) || ""}`
          );
        }
      });
      if (selected) showResidue(selected);
    });
  }

  function roleClass(role) {
    const normalized = String(role || "unresolved").toLowerCase().replace(/[^a-z_]/g, "_");
    return `role-${normalized}`;
  }

  function cell(text) {
    const element = document.createElement("td");
    element.textContent = text || "—";
    return element;
  }

  function renderResidues() {
    const rows = data.candidate_residues.filter(modeMatches);
    const body = byId("residue-rows");
    body.replaceChildren();
    for (const residue of rows) {
      const row = document.createElement("tr");
      row.tabIndex = 0;
      const role = document.createElement("td");
      const pill = document.createElement("span");
      pill.className = `role-pill ${roleClass(residue.role)}`;
      pill.textContent = residue.role || "unresolved";
      role.append(pill);
      row.append(
        role,
        cell(formatResidue(residue)),
        cell(`${residue.auth_asym_id || "?"}:${residue.auth_seq_id || "?"}${residue.insertion_code || ""}`),
        cell(
          Number.isInteger(residue.label_seq_id)
            ? `${residue.label_asym_id || "?"}:${residue.label_seq_id}`
            : "unavailable (PDB source)",
        ),
        cell(residue.generic_number),
        cell(residue.segment),
        cell(residue.evidence_tier),
        cell(residue.approach_direction)
      );
      row.addEventListener("click", () => showResidue(residue));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") showResidue(residue);
      });
      body.append(row);
    }
    byId("no-residues").hidden = rows.length !== 0;
    const counts = data.candidate_counts[state.mode];
    byId("candidate-summary").textContent =
      `${counts.primary} primary · ${counts.backup} backup · ${counts.avoid} avoid · ${counts.unresolved} unresolved`;
  }

  function renderWarnings() {
    const list = byId("warning-list");
    list.replaceChildren();
    for (const warning of data.warnings) {
      const item = document.createElement("li");
      item.textContent = warning;
      list.append(item);
    }
    byId("warnings-section").hidden = data.warnings.length === 0;
  }

  function compactMetrics(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return "";
    return Object.entries(value)
      .map(([key, metric]) => `${key}: ${metric}`)
      .join(" · ");
  }

  function renderCandidates() {
    const container = byId("candidate-list");
    container.replaceChildren();
    const candidates = data.candidates.filter(modeMatches);
    for (const candidate of candidates) {
      const item = document.createElement("article");
      item.className = "candidate-item";
      const title = document.createElement("h3");
      title.textContent = candidate.id;
      const meta = document.createElement("div");
      meta.className = "candidate-meta";
      for (const value of [
        candidate.role,
        candidate.mechanism_role,
        candidate.evidence_tier,
        candidate.confidence,
      ]) {
        if (!value || value === "unresolved") continue;
        const chip = document.createElement("span");
        chip.textContent = value;
        meta.append(chip);
      }
      item.append(title, meta);
      if (candidate.hypothesis) {
        const hypothesis = document.createElement("p");
        hypothesis.textContent = candidate.hypothesis;
        item.append(hypothesis);
      }
      const metricsText = compactMetrics(candidate.geometry_metrics);
      if (metricsText) {
        const metrics = document.createElement("p");
        metrics.textContent = metricsText;
        item.append(metrics);
      }
      if (candidate.falsifier) {
        const falsifier = document.createElement("p");
        falsifier.className = "candidate-falsifier";
        falsifier.textContent = `Falsifier: ${candidate.falsifier}`;
        item.append(falsifier);
      }
      if (candidate.risks.length) {
        const risks = document.createElement("p");
        risks.textContent = `Risks: ${candidate.risks.join(" · ")}`;
        item.append(risks);
      }
      container.append(item);
    }
    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No hypotheses for this mode.";
      container.append(empty);
    }
  }

  function renderProvenance() {
    const list = byId("provenance-list");
    list.replaceChildren();
    for (const item of data.provenance) {
      const term = document.createElement("dt");
      term.textContent = item.label;
      const detail = document.createElement("dd");
      if (item.url) {
        const link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noreferrer noopener";
        link.textContent = item.value;
        detail.append(link);
      } else {
        detail.textContent = item.value;
      }
      list.append(term, detail);
    }
    if (data.provenance.length === 0) {
      const term = document.createElement("dt");
      term.textContent = "Status";
      const detail = document.createElement("dd");
      detail.textContent = "No provenance fields supplied";
      list.append(term, detail);
    }
  }

  function updateModeButtons() {
    for (const mode of ["inhibit", "activate"]) {
      const button = byId(`mode-${mode}`);
      button.classList.toggle("active", state.mode === mode);
      button.setAttribute("aria-selected", state.mode === mode ? "true" : "false");
      button.disabled = data.mode !== "both" && data.mode !== mode;
    }
  }

  function bindControls() {
    for (const input of document.querySelectorAll("#layer-controls input")) {
      if (input.checked) state.layers.add(input.value);
      input.addEventListener("change", async () => {
        if (input.checked) state.layers.add(input.value);
        else state.layers.delete(input.value);
        try {
          await reloadStructure(true);
        } catch (error) {
          showFailure(error);
        }
      });
    }
    for (const mode of ["inhibit", "activate"]) {
      byId(`mode-${mode}`).addEventListener("click", async () => {
        if (data.mode !== "both" && data.mode !== mode) return;
        state.mode = mode;
        updateModeButtons();
        renderCandidates();
        renderResidues();
        try {
          await reloadStructure(true);
        } catch (error) {
          showFailure(error);
        }
      });
    }
    byId("center-view").addEventListener("click", () => {
      try {
        state.viewer.plugin.managers.camera.reset();
      } catch (error) {
        showFailure(error);
      }
    });
  }

  function requireWebGl() {
    const canvas = document.createElement("canvas");
    const context =
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    if (!context) throw new Error("WebGL is unavailable in this browser.");
  }

  async function start() {
    validateData();
    if (!window.molstar || !molstar.Viewer) {
      throw new Error("Local Mol* 5.11.0 assets did not load.");
    }
    requireWebGl();
    state.blobUrl = URL.createObjectURL(
      new Blob([data.structure.text], { type: "text/plain;charset=utf-8" })
    );
    renderWarnings();
    renderProvenance();
    updateModeButtons();
    bindControls();
    renderCandidates();
    renderResidues();
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
      viewportBackgroundColor: "#EEF2EF",
    });
    subscribeToResidues();
    await reloadStructure(false);
    const status = byId("load-state");
    status.textContent = `Review loaded · ${data.membrane_status} membrane`;
    status.classList.add("ready");
    window.__GPCR_REVIEW_READY__ = true;
  }

  start().catch(showFailure);
})();
