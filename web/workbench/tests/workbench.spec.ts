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
  score_yaml: .6,
  selected_for_expansion: index === 0,
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
    if (url.pathname.endsWith("/stages/5/candidates")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          phase: url.searchParams.get("phase") || "pilot",
          page: 1,
          page_size: 50,
          total: url.searchParams.get("phase") === "full-target" ? 10 : 840,
          total_pages: url.searchParams.get("phase") === "full-target" ? 1 : 17,
          items: candidateItems,
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
  await expect(page.getByRole("heading", { name: "当前没有可进入规模化生成的设计策略" })).toBeVisible();
  await expect(page.getByText("程序已正常完成，但当前结果没有达到进入下一步的科学门槛。")).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "新建设计" })).toBeVisible();
  for (const source of ["PyMOL PSE", "PDB / mmCIF", "FASTA / 序列", "RCSB PDB ID", "UniProt", "目标结构包"]) {
    await expect(page.getByRole("button", { name: new RegExp(source) })).toBeVisible();
  }
  await expect(page.getByText("标准 YAML 配置预览")).toBeVisible();
  await expect(page.getByText('schema_version: "0.7"')).toBeVisible();
});
