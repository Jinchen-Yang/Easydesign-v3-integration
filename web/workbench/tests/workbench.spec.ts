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
  title: [
    "Target 准备",
    "区域发现与批准",
    "BoltzGen 策略",
    "Pilot 生成",
    "Pilot 筛选",
    "规模生成",
    "最终筛选与选择",
  ][index],
  state,
  capability: {
    status: index < 5 ? "smoke-validated" : "implemented",
    summary: index === 5 ? "2×500 / 20×2500 分片能力" : index === 6 ? "三 seed、TNP 与主备候选包" : "已验证能力",
  },
  summary: state === "scientific-stop" ? "软件正常完成，但科学门槛未通过" : state === "not-reached" ? "当前 run 未到达本阶段" : "manifest-declared artifacts",
  evidence_status: "smoke-validated",
  highlights: index === 4 ? {
    pilot_candidate_count: 840,
    tier_counts: { "tier-a": 1 },
    expanded_candidate_count: 100,
    local_gate_pass_count: 12,
    protenix_prediction_count: 10,
    protenix_pass_count: 0,
    boltzgen_filter_rmsd_design_range: [0.7, 2.2],
    protenix_binder_pose_rmsd_range: [18.005, 31.726],
    winner_strategy_id: null,
  } : index === 3 ? {
    strategy_count: 21,
    planned_candidates: 840,
    collected_candidates: 840,
    succeeded_tasks: 21,
    elapsed_seconds: 7200,
    throughput_candidates_per_hour: 420,
  } : {},
  tables: index === 4 ? {
    predictions: Array.from({ length: 10 }, (_, candidate) => ({
      candidate_id: `candidate-${candidate + 1}`,
      target_ca_rmsd_angstrom: 1.4,
      binder_pose_rmsd_angstrom: 18.005 + candidate,
      pairwise_iptm: 0.3,
      minimum_interface_pae_angstrom: 16.2,
      passed: false,
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
  code_version: "0.1.0.dev6",
  code_commit: "98ebef79da43469d173ff7c2af082206e6903c2e",
  profile_id: "proteindigger1",
  integrity_status: "verified",
  stages,
};

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
    if (url.pathname.endsWith("/replay")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          replay_id: "replay-apoe",
          source_run_key: run.run_key,
          source_manifest_sha256: "a".repeat(64),
          banner: "DEMO REPLAY · 不修改科学证据",
          frames: Array.from({ length: 13 }, (_, index) => ({
            frame_id: `frame-${index}`,
            label: `Frame ${index}`,
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

test("dashboard and scientific-stop workspace keep software and run state separate", async ({ page }) => {
  const errors: string[] = [];
  const requestHosts = new Set<string>();
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => requestHosts.add(new URL(request.url()).hostname));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "早上好，今天继续把证据做扎实。" })).toBeVisible();
  await page.getByText("20260726-004-stage05-pilot-filter").first().click();
  await expect(page.getByRole("heading", { name: "没有策略通过 full-target binder-pose gate" })).toBeVisible();
  await expect(page.getByText("12 个候选通过 local gate")).toBeVisible();
  await expect(page.getByText("18.01–31.73 Å")).toBeVisible();

  await page.getByRole("button", { name: /06 规模生成/ }).click();
  await expect(page.getByRole("heading", { name: "本阶段未到达" })).toBeVisible();
  await expect(page.getByText("2×500 / 20×2500 分片能力")).toBeVisible();
  await expect(page.getByText("功能存在不代表本次 APOE 已执行。")).toBeVisible();

  await page.getByRole("button", { name: /07 最终筛选与选择/ }).click();
  await expect(page.getByRole("button", { name: "生成湿实验候选草案" })).toBeDisabled();
  expect(errors).toEqual([]);
  expect([...requestHosts]).toEqual(["127.0.0.1"]);
});

test("demo replay is conspicuous and does not claim a new run", async ({ page }) => {
  await page.goto("/");
  await page.getByText("20260726-004-stage05-pilot-filter").first().click();
  await page.getByRole("button", { name: "▶ 回放已验证案例" }).click();
  await expect(page.getByText("DEMO REPLAY", { exact: true })).toBeVisible();
  await expect(page.getByText("不会启动 GPU 或修改科学证据。")).toBeVisible();
});

test("new design exposes six entry classes and canonical YAML", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await expect(page.getByRole("heading", { name: "创建一条可追溯设计任务" })).toBeVisible();
  for (const source of ["PyMOL PSE", "PDB / mmCIF", "FASTA / 序列", "RCSB PDB ID", "UniProt", "Target Bundle"]) {
    await expect(page.getByRole("button", { name: new RegExp(source) })).toBeVisible();
  }
  await expect(page.getByText("CANONICAL YAML · PREVIEW")).toBeVisible();
  await expect(page.getByText('schema_version: "0.7"')).toBeVisible();
});
