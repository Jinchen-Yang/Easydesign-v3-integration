import { expect, test, type Page } from "@playwright/test";

const states = [
  "succeeded",
  "succeeded",
  "succeeded",
  "succeeded",
  "scientific-stop",
  "not-reached",
  "not-reached",
] as const;

const stages = states.map((state, index) => ({
  stage_number: index + 1,
  stage_id: `0${index + 1}-fixture-stage`,
  title: `fixture-${index + 1}`,
  state,
  capability: {
    status: index < 5 ? "smoke-validated" : "implemented",
    summary: index === 5
      ? "2×500 / 20×2500 分片能力"
      : index === 6
        ? "三 seed、TNP 与主备候选包"
        : "已验证能力",
  },
  summary: state === "scientific-stop"
    ? "软件正常完成，但科学门槛未通过"
    : state === "not-reached"
      ? "当前运行未到达本阶段"
      : "正式输出文件",
  evidence_status: "smoke-validated",
  highlights: index === 0
    ? { target_id: "apoe-1b68-pse", sequence_length: 138, origin: "imported", model_count: 1 }
    : index === 3
      ? { strategy_count: 21, planned_candidates: 840, collected_candidates: 840 }
    : index === 4
      ? { pilot_candidate_count: 840, local_gate_pass_count: 12 }
      : {},
  tables: index === 4 ? {
    predictions: Array.from({ length: 10 }, (_, candidate) => ({
      candidate_id: `candidate-${candidate + 1}`,
      binder_pose_rmsd_angstrom: 18 + candidate,
    })),
  } : {},
  artifacts: [],
}));

const run = {
  run_key: "apoe-run-key",
  project_id: "apoe",
  run_id: "20260726-004-stage05-pilot-filter",
  status: "succeeded",
  evidence_status: "smoke-validated",
  created_at: "2026-07-26T01:00:00Z",
  updated_at: "2026-07-26T09:00:00Z",
  completed_at: "2026-07-26T09:00:00Z",
  code_version: "0.1.0.dev7",
  code_commit: "98ebef79da43469d173ff7c2af082206e6903c2e",
  profile_id: "proteindigger1",
  integrity_status: "verified",
  stages,
};

const stepwiseRun = {
  ...run,
  run_key: "stepwise-run-key",
  project_id: "new-design",
  run_id: "stage01-pse-fixture",
  stages: stages.map((item, index) => ({
    ...item,
    state: index === 0 ? "succeeded" : "not-reached",
    summary: index === 0 ? "目标结构已准备，可以开始结构审查" : "尚未开始",
  })),
};

const overview = {
  run_key: run.run_key,
  state: "scientific-stop",
  conclusion_title: "当前没有可进入规模化生成的设计策略",
  conclusion: "程序已正常完成，但当前结果没有达到进入下一步的科学门槛。",
  next_actions: ["查看候选淘汰原因与指标分布", "按 VAL-003 进行 Protenix 受控复核"],
  counts: {
    pilot: 840,
    strategies: 21,
    selected_strategies: 1,
    expanded: 100,
    local_gate_pass: 12,
    full_target: 10,
    full_target_pass: 0,
  },
  tier_counts: { "tier-a": 1, "tier-b": 1, "tier-c": 5, "tier-d": 14 },
  step_chain: [
    ["pilot", "小规模候选", 840],
    ["hard-gates", "逐项硬门筛选", 32],
    ["strategies", "进入扩展的策略", 1],
    ["expansion", "扩展候选", 100],
    ["local-gate", "通过初步结构筛选", 12],
    ["full-target", "进入 Protenix 完整目标复核", 10],
    ["winner", "满足结合位姿稳定性", 0],
  ].map(([id, label, count]) => ({ id, label, count })),
  failed_rule_counts: { "iptm-gate": 400, "hotspot-coverage-gate": 210 },
};

const strategies = Array.from({ length: 21 }, (_, index) => ({
  strategy_id: `${["A", "B", "C"][Math.floor(index / 7)]}__scaffold-${index % 7 + 1}`,
  region_id: ["A", "B", "C"][Math.floor(index / 7)],
  scaffold_id: `scaffold-${index % 7 + 1}`,
  candidate_count: 40,
  unique_sequence_count: 40,
  hard_pass_count: index === 0 ? 4 : 1,
  final_gate_pass_count: index === 0 ? 2 : 0,
  final_gate_pass_rate: index === 0 ? .05 : 0,
  tier: index === 0 ? "tier-a" : "tier-d",
  score_screen: .5,
  score_screen_top_quartile_mean: .7,
  score_yaml: .6,
  selected_for_expansion: index === 0,
  configuration: {
    hotspot_strategy: "H_all",
    crop_strategy: "C_full",
    candidates_per_strategy: 40,
  },
  metric_aggregates: [
    ["hotspot-coverage", .52],
    ["design-to-target-iptm", .61],
    ["min-design-to-target-pae", 7.5],
    ["filter-rmsd-design", 1.2],
    ["bb_target_aligned_rmsd_design", 1.4],
    ["target-ca-rmsd", 1.1],
  ].map(([metric_id, mean]) => ({
    metric_id,
    observed_count: 40,
    missing_count: 0,
    mean,
    median: mean,
    minimum: mean,
    maximum: mean,
  })),
  yaml_artifact: {
    artifact_id: `strategy-${index}`,
    role: "boltzgen-design-specification",
    file_format: "yaml",
    size_bytes: 1024,
    sha256: "b".repeat(64),
    token: `yaml-${index}`,
  },
}));

const metrics = [
  ["hotspot-coverage", "结合区域覆盖率", "结合质量"],
  ["design-to-target-iptm", "设计链与目标链界面置信度", "结合质量"],
  ["min-design-to-target-pae", "最小设计链—目标链预测对齐误差", "结合质量"],
  ["filter-rmsd-design", "筛选设计链骨架偏差", "结构稳定性"],
  ["bb_target_aligned_rmsd_design", "目标对齐后的设计链骨架偏差", "结构稳定性"],
  ["target-ca-rmsd", "目标结构偏差", "结构稳定性"],
  ["protenix-binder-pose-rmsd", "Protenix 结合位姿偏差", "Protenix 复核"],
].map(([metric_id, name, group]) => ({
  metric_id, name, group, definition: `${name}定义`, source: "EasyDesign",
  direction: "按定义解释", role: "硬门", missing_value_policy: "缺失不通过",
}));

const candidateItems = Array.from({ length: 50 }, (_, index) => ({
  candidate_id: `candidate-${index + 1}`,
  phase: "pilot",
  strategy_id: "A__scaffold-1",
  sequence_length: 123,
  gate_status: index < 4 ? "通过" : "未通过",
  score: .5,
  metrics: {
    "hotspot-coverage": .52,
    "design-to-target-iptm": .61,
    "min-design-to-target-pae": 7.5,
    "filter-rmsd-design": 1.2,
    bb_target_aligned_rmsd_design: 1.4,
    "target-ca-rmsd": 1.1,
  },
  failed_rules: index < 4 ? [] : ["iptm-gate"],
}));

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/remote-executors") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          executors: [
            { executor_id: "suzhou2-a100x8", label: "suzhou2-a100x8" },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/project-catalog") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ entries: [] }),
      });
      return;
    }
    if (url.pathname === "/api/v1/self-tests") {
      await route.fulfill({
        contentType: "application/json",
        body: route.request().method() === "POST"
          ? JSON.stringify({
            schema_version: "0.1",
            self_test_id: "selftest-fixture",
            mode: "deterministic-seven-stage",
            status: "passed",
            engineering_status: "passed",
            backend_status: "not-requested",
            scientific_status: "not-applicable",
            stage_statuses: Object.fromEntries(
              Array.from({ length: 7 }, (_, index) => [`stage${String(index + 1).padStart(2, "0")}`, "passed"]),
            ),
            environment: {},
            created_at: "2026-07-27T00:00:00Z",
            updated_at: "2026-07-27T00:00:01Z",
            message: "七阶段工程链路通过。",
          })
          : JSON.stringify([]),
      });
      return;
    }
    if (url.pathname === "/api/v1/design-sessions") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify([]),
      });
      return;
    }
    if (url.pathname.endsWith("/regions/editor")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          run_key: run.run_key,
          target_id: "apoe-1b68-pse",
          target_structure_sha256: "a".repeat(64),
          structure: {
            artifact_id: "target-structure",
            role: "normalized-target-structure",
            file_format: "cif",
            size_bytes: 12,
            sha256: "a".repeat(64),
            token: "target-token",
          },
          source_annotation_status: "uninterpreted annotation",
          current_region_source: "pse-color-annotation",
          residues: [
            {
              label_seq_id: 1,
              amino_acid: "A",
              sequence_index: 1,
              auth_chain_id: "A",
              auth_residue_id: "23",
              source_color: "#FF0000",
              current_region: "A",
            },
            {
              label_seq_id: 2,
              amino_acid: "C",
              sequence_index: 2,
              auth_chain_id: "A",
              auth_residue_id: "24",
              source_color: "#0000FF",
              current_region: "B",
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/remote-jobs") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ jobs: [] }),
      });
      return;
    }
    if (url.pathname === "/api/v1/uploads/raw" && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          upload_token: "upload-fixture",
          filename: "target.pse",
          size_bytes: 18,
          sha256: "a".repeat(64),
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/projects" && route.request().method() === "POST") {
      const requestBody = route.request().postDataJSON() as {
        design_mode?: string;
        stop_after_stage?: number;
      };
      const stepwise = requestBody.design_mode === "stepwise";
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          project_id: "new-design",
          config: [
            'schema_version: "0.7"',
            "project_id: new-design",
            "design:",
            "  binder_profile: vhh",
            "  intent: exploratory",
            "workflow:",
            "  execution_mode: review-gated",
            `  stop_after_stage: ${stepwise ? 1 : 2}`,
            "stage01:",
            "  target:",
            "    source:",
            "      type: local-file",
            "      path: inputs/target.pse",
            stepwise ? "stage02: null" : "stage02:",
            stepwise ? "" : "  mode: detect",
          ].join("\n"),
          status: "draft",
          session: {
            schema_version: "0.1",
            session_id: "session-fixture",
            project_id: "new-design",
            design_mode: stepwise ? "stepwise" : "full-workflow",
            execution_mode: "review-gated",
            current_stage: stepwise ? 1 : 2,
            status: "draft",
            config_revisions: [],
            run_lineage: [],
            created_at: "2026-07-27T00:00:00Z",
            updated_at: "2026-07-27T00:00:00Z",
          },
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/config") && route.request().method() === "PUT") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "valid", plan: {} }),
      });
      return;
    }
    if (url.pathname === "/api/v1/preflight") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ plan: {}, diagnostic: { ok: true } }),
      });
      return;
    }
    if (url.pathname === "/api/v1/jobs" && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ job_id: "job-fixture", status: "queued" }),
      });
      return;
    }
    if (url.pathname === "/api/v1/jobs/job-fixture") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "job-fixture",
          status: "succeeded",
          run_key: stepwiseRun.run_key,
          run_id: stepwiseRun.run_id,
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/projects") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          projects: [{ project_id: "apoe", run_count: 1, latest_run: run, runs: [run] }],
          editable_projects: ["apoe-draft"],
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/stages/5/overview")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(overview) });
      return;
    }
    if (url.pathname.endsWith("/stages/5/strategies")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(strategies) });
      return;
    }
    if (url.pathname.endsWith("/stages/5/metrics")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(metrics) });
      return;
    }
    if (url.pathname.endsWith("/stages/4/execution")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          stage_number: 4,
          stage_id: "04-fixture-stage",
          status: "succeeded",
          updated_at: run.updated_at,
          total_tasks: 21,
          pending_tasks: 0,
          waiting_tasks: 0,
          running_tasks: 0,
          succeeded_tasks: 21,
          failed_tasks: 0,
          planned_candidates: 840,
          collected_candidates: 840,
          elapsed_seconds: 20914,
          throughput_candidates_per_hour: 144.6,
          estimated_remaining_seconds: 0,
          device_history_status: "available",
          recent_events: [],
          recent_errors: [],
          devices: [
            {
              device: 0,
              assigned_task_count: 11,
              succeeded_task_count: 11,
              attempt_count: 14,
              failed_attempt_count: 3,
              collected_candidates: 440,
              busy_seconds: 20885,
              tasks: [],
            },
            {
              device: 1,
              assigned_task_count: 10,
              succeeded_task_count: 10,
              attempt_count: 14,
              failed_attempt_count: 4,
              collected_candidates: 400,
              busy_seconds: 19402,
              tasks: [],
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname.includes("/stages/5/candidates/")) {
      const candidateId = decodeURIComponent(url.pathname.split("/").at(-1) || "");
      const phase = url.searchParams.get("phase") || "pilot";
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          candidate_id: candidateId,
          phase,
          strategy_id: "A__scaffold-1",
          sequence: "QVQLVESGGGLVQAGGSLRLSCAAS",
          gate_status: phase === "full-target" ? "未通过" : "通过",
          score: .72,
          metrics: [],
          decisions: [],
          failed_reasons: phase === "full-target" ? ["require-binder-pose-rmsd"] : [],
          backend_metrics: {},
          structures: {},
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/stages/5/candidates")) {
      const phase = url.searchParams.get("phase") || "pilot";
      const items = phase === "full-target"
        ? candidateItems.slice(0, 10).map((item, index) => ({
          ...item,
          phase,
          gate_status: "未通过",
          metrics: {
            "protenix-target-rmsd": 1.3 + index / 10,
            "protenix-binder-pose-rmsd": 18 + index,
            "protenix-pairwise-iptm": .35,
            "protenix-min-interface-pae": 4.33 + index,
          },
        }))
        : phase === "expansion"
          ? candidateItems.slice(0, 12).map((item, index) => ({
            ...item,
            phase,
            gate_status: "通过",
            score: 1 - index / 20,
          }))
          : candidateItems;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          phase,
          page: 1,
          page_size: 50,
          total: phase === "full-target" ? 10 : phase === "expansion" ? 12 : 840,
          total_pages: phase === "pilot" ? 17 : 1,
          items,
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/replay")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          replay_id: "replay-apoe",
          source_run_key: run.run_key,
          source_manifest_sha256: "a".repeat(64),
          banner: "演示回放",
          frames: Array.from({ length: 13 }, (_, index) => ({
            frame_id: `frame-${index}`,
            label: `时间点 ${index}`,
            state: index === 10 ? "scientific-stop" : "simulated-preview",
            description: "fixture",
          })),
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/clone")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ project_id: "apoe-rerun", config: "schema_version: '0.7'", status: "draft" }),
      });
      return;
    }
    if (url.pathname === `/api/v1/runs/${stepwiseRun.run_key}`) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(stepwiseRun),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("project-first navigation and scientific stop are explained in Chinese", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "我的项目" })).toBeVisible();
  await expect(page.getByRole("button", { name: "我的项目" })).toBeVisible();
  await expect(page.getByRole("button", { name: "运行任务" })).toBeVisible();
  await expect(page.getByRole("button", { name: "待审批" })).toHaveCount(0);
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await expect(page.getByRole("heading", { name: "第5步：筛选与验证" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "筛选工作已经完成，已有多层结构证据可供审阅" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "12 个候选值得查看结构" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "当前没有可进入规模化生成的设计策略" })).toBeVisible();
});

test("stage five exposes strategy, candidate and metric layers", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await page.getByRole("button", { name: "策略比较" }).click();
  await expect(page.getByRole("heading", { name: "21 个设计策略的真实表现" })).toBeVisible();
  await expect(page.getByText("scaffold-7").first()).toBeVisible();
  await page.getByRole("button", { name: "候选筛选" }).click();
  await expect(page.getByText("共 840 个")).toBeVisible();
  await expect(page.getByText("目标对齐后的设计链骨架偏差")).toBeVisible();
  await page.getByRole("button", { name: "指标说明" }).click();
  await expect(page.getByRole("heading", { name: "结合质量" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Protenix 结合位姿偏差" })).toBeVisible();
});

test("completed gpu history and staged candidate evidence remain visible", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await expect(page.getByText("等级 A").first()).toBeVisible();
  await expect(page.getByText("已做 Protenix 复核").first()).toBeVisible();
  await expect(page.getByText("当前观测到的最低结合位姿 RMSD")).toBeVisible();
  await page.locator(".stage-node").nth(3).click();
  await expect(page.getByText("GPU 0")).toBeVisible();
  await expect(page.getByText("440")).toBeVisible();
  await expect(page.getByText("GPU 1")).toBeVisible();
  await expect(page.getByText("400")).toBeVisible();
});

test("task page does not fall through to technical audit", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "运行任务" }).click();
  await expect(page.getByRole("heading", { name: "运行任务" })).toBeVisible();
  await expect(page.getByText("全部运行")).toBeVisible();
  await expect(page.getByText("源代码提交")).toHaveCount(0);
});

test("font floor and user-facing Chinese navigation meet the product baseline", async ({ page }) => {
  await page.goto("/");
  const bodySize = await page.locator("body").evaluate((node) => getComputedStyle(node).fontSize);
  const navSize = await page.getByRole("button", { name: "我的项目" }).evaluate((node) => getComputedStyle(node).fontSize);
  expect(Number.parseFloat(bodySize)).toBeGreaterThanOrEqual(16);
  expect(Number.parseFloat(navSize)).toBeGreaterThanOrEqual(14);
  await expect(page.getByText("Scientific Workbench")).toHaveCount(0);
  await expect(page.getByText("证据审计")).toHaveCount(0);
});

test("all molecular workspaces use the portable viewer light canvas", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await page.locator(".stage-node").first().click();
  const background = await page.locator(".mol-card").first().evaluate(
    (node) => getComputedStyle(node).backgroundColor,
  );
  expect(background).toBe("rgb(238, 241, 246)");
  const toolbar = await page.locator(".mol-toolbar").first().evaluate(
    (node) => getComputedStyle(node).backgroundColor,
  );
  expect(toolbar).toBe("rgb(255, 255, 255)");
});

test("project and stage-five workspaces keep the approved visual hierarchy", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "视觉基线固定在 Chromium；Firefox 执行交互 smoke");
  await page.goto("/");
  await expect(page).toHaveScreenshot("projects.png", {
    animations: "disabled",
    fullPage: true,
  });
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await expect(page).toHaveScreenshot("stage-five-conclusion.png", {
    animations: "disabled",
    fullPage: true,
  });
});

test("demo replay is conspicuous and read-only", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await page.getByRole("button", { name: "▶ 演示回放" }).click();
  await expect(page.getByText("演示回放", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/不会启动 GPU/)).toBeVisible();
});

test("new design exposes six entry classes and standard YAML", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await expect(page.getByRole("heading", { name: "选择设计路线" })).toBeVisible();
  await page.getByRole("button", { name: /全流程设计/ }).click();
  await expect(page.getByRole("heading", { name: "全流程设计" })).toBeVisible();
  for (const source of ["PyMOL PSE", "PDB / mmCIF", "FASTA / 序列", "RCSB PDB ID", "UniProt", "目标结构包"]) {
    await expect(page.getByRole("button", { name: new RegExp(source) })).toBeVisible();
  }
  await expect(page.getByText("标准 YAML 配置预览")).toBeVisible();
  await expect(page.getByText('schema_version: "0.7"')).toBeVisible();
});

test("new design steps are freely browsable and file receipt unlocks final checks", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /全流程设计/ }).click();

  for (const stage of ["目标结构", "结合区域", "设计方案", "小规模", "筛选验证", "规模化", "最终候选"]) {
    await expect(
      page.locator(".scientific-stage-browser").getByRole("button", { name: new RegExp(stage) }),
    ).toBeVisible();
  }

  await page.getByRole("button", { name: /预算与资源/ }).click();
  await expect(page.getByText("运行到第几步")).toBeVisible();
  await expect(page.getByLabel("在哪里运行")).toContainText("远程服务器 · suzhou2-a100x8");
  await page.getByLabel("在哪里运行").selectOption("suzhou2-a100x8");
  await page.getByRole("button", { name: /设计意图/ }).click();
  await expect(page.getByRole("heading", { name: "你希望这个 binder 做什么？" })).toBeVisible();
  await page.getByRole("button", { name: /目标输入/ }).click();

  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await expect(page.getByText("文件已接收", { exact: true })).toBeVisible();
  await expect(page.getByText(/本地服务已接收 target\.pse/)).toBeVisible();
  await expect(page.getByText('path: "inputs/target.pse"')).toBeVisible();

  await page.getByRole("button", { name: /检查并启动/ }).click();
  const createDraft = page.getByRole("button", { name: "1. 生成项目草稿" });
  const validate = page.getByRole("button", { name: "2. 检查配置与环境" });
  const launch = page.getByRole("button", { name: "3. 确认并真实启动 →" });
  await expect(createDraft).toBeEnabled();
  await expect(validate).toBeDisabled();
  await expect(launch).toBeDisabled();

  await createDraft.click();
  await expect(page.getByText(/草稿已创建/).first()).toBeVisible();
  await expect(validate).toBeEnabled();
  await expect(launch).toBeDisabled();
  await validate.click();
  await expect(page.getByText(/远程执行服务器 suzhou2-a100x8 可连接/)).toBeVisible();
  await expect(launch).toBeEnabled();
});

test("stepwise PSE upload runs stage one and opens structure review directly", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await expect(page.getByRole("heading", { name: "按步骤设计" })).toBeVisible();
  await expect(page.getByRole("button", { name: /第1步：准备目标结构/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /检查并启动/ })).toHaveCount(0);
  await expect(page.getByText(/第五项 · 启动前检查/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /区域策略/ })).toHaveCount(0);
  await expect(page.getByText("本次只要求完成第1步")).toBeVisible();

  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });

  await expect(page.getByRole("heading", { name: "第1步：准备目标结构" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "new-design" })).toBeVisible();
  await expect(page.getByText("138 aa")).toBeVisible();
  await expect(page.getByRole("button", { name: "配置下一步：选择结合区域" })).toBeVisible();
});

test("developer smoke is separated from scientific projects", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /开发者自检/ }).click();
  await expect(page.getByRole("heading", { name: "开发者全阶段自检" })).toBeVisible();
  await page.getByRole("button", { name: "运行快速七步自检" }).click();
  await expect(page.getByText("七阶段工程链路通过。")).toBeVisible();
});

test("stage two region editor keeps source layers and editable selection separate", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await page.locator(".stage-node").nth(1).click();
  await page.getByRole("button", { name: "重新选择结合区域" }).click();
  await expect(page.getByRole("heading", { name: "重新选择结合区域" })).toBeVisible();
  await expect(page.getByLabel("显示 PSE 来源颜色")).toBeChecked();
  await expect(page.getByLabel("显示当前批准区域")).toBeChecked();
  await page.getByRole("button", { name: /区域 B/ }).click();
  const firstResidue = page.locator(".sequence-editor button").first();
  await firstResidue.click();
  await expect(firstResidue).toHaveClass(/region-b/);
  await page.getByRole("button", { name: "清空本次选择" }).click();
  await expect(firstResidue).not.toHaveClass(/region-b/);
});
