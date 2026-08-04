import { expect, test, type Page } from "@playwright/test";
import { pymolDisplayPml } from "../src/pymolDisplay";

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

const automaticStageTwoRun = {
  ...stepwiseRun,
  run_key: "automatic-stage02-run-key",
  run_id: "stage02-sasa-fixture",
  stages: stages.map((item, index) => ({
    ...item,
    state: index === 0
      ? "succeeded"
      : index === 1
        ? "awaiting-human-approval"
        : "not-reached",
    summary: index === 1 ? "自动候选区域已生成，等待人工确认" : item.summary,
  })),
};

const manualStageTwoRun = {
  ...stepwiseRun,
  run_key: "manual-stage02-run-key",
  project_id: "apoe",
  run_id: "stage02-manual-fixture",
  stages: stages.map((item, index) => ({
    ...item,
    state: index < 2 ? "succeeded" : "not-reached",
    summary: index === 1 ? "人工区域已批准并发布" : item.summary,
    highlights: index === 1
      ? {
        region_count: 3,
        region_source: "manual-residue-list",
        approved_by: "human:local-workbench",
        approval_authority: "human",
        approval_source: "explicit-review",
      }
      : item.highlights,
    tables: index === 1
      ? {
        regions: [
          { id: "A", member_count: 9, label_ranges: "10,14,17,24,28,33,37,41,44" },
          { id: "B", member_count: 14, label_ranges: "36,39,43,47,50,54,67,71,78,81,85,89,92,96" },
          { id: "C", member_count: 14, label_ranges: "75,79,82,86,90,93,97,112,116,119,123,126,130,133" },
        ],
      }
      : item.tables,
  })),
};

const stageThreeRun = {
  ...manualStageTwoRun,
  run_key: "stage03-run-key",
  run_id: "stage03-basic-vhh-fixture",
  stages: stages.map((item, index) => ({
    ...item,
    state: index < 3 ? "succeeded" : "not-reached",
    summary: index === 2 ? "21 个设计方案已生成并验证" : item.summary,
    highlights: index === 2
      ? {
        strategy_count: 21,
        region_count: 3,
        scaffold_count: 7,
        planned_candidates: 840,
      }
      : item.highlights,
    tables: index === 2
      ? {
        strategies: ["A", "B", "C"].flatMap((region) =>
          Array.from({ length: 7 }, (_, scaffold) => ({
            region_id: region,
            scaffold_id: `scaffold-${scaffold + 1}`,
            strategy_id: `${region}__scaffold-${scaffold + 1}`,
            candidates_per_strategy: 40,
          }))),
      }
      : item.tables,
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
  hard_pass_count: index === 0 ? 5 : index >= 2 && index <= 6 ? 2 : 1,
  final_gate_pass_count: index === 0 ? 5 : index === 1 ? 1 : 0,
  final_gate_pass_rate: index === 0 ? .125 : index === 1 ? .025 : 0,
  tier: index === 0
    ? "tier-a"
    : index === 1
      ? "tier-b"
      : index <= 6
        ? "tier-c"
        : "tier-d",
  score_screen: .5,
  score_screen_top_quartile_mean: .7,
  score_yaml: index === 0 ? .391 : Math.max(0, .35 - index / 100),
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
  const jobPolls = new Map<string, number>();
  const archivedProjectIds = new Set<string>();
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/install/status") {
      const environments = [
        "easydesign-core",
        "reporting-web",
        "pymol-pse",
        "protenix-v2",
        "scannet-epitope",
        "boltzgen",
        "tnp",
      ].map((environment_id) => ({
        environment_id,
        status: environment_id === "easydesign-core" ? "retired" : "available",
      }));
      const componentEnvironments: Record<string, string[]> = {
        "core-ui": ["easydesign-core", "reporting-web"],
        "pymol-pse": ["pymol-pse"],
        "protenix-v2": ["protenix-v2"],
        "scannet-epitope": ["scannet-epitope"],
        boltzgen: ["boltzgen"],
        tnp: ["tnp"],
      };
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          workspace: "/fixture/easydesign",
          core_runtime: {
            status: "available",
            manager: "uv-venv",
            version: "0.1.0.dev48",
          },
          plan: {
            disk: {
              free_bytes: 80 * 1024 ** 3,
              incremental_peak_bytes: 0,
              reserve_bytes: 10 * 1024 ** 3,
              sufficient: true,
            },
          },
          component_plans: Object.fromEntries(Object.entries(componentEnvironments).map(([component, ids]) => [component, {
            component,
            environments: ids.map((environment_id) => ({ environment_id, already_present: true, estimated_install_bytes: 0 })),
            assets: [],
            disk: {
              free_bytes: 80 * 1024 ** 3,
              incremental_peak_bytes: 0,
              reserve_bytes: 10 * 1024 ** 3,
              sufficient: true,
            },
          }])),
          environments,
          assets: [],
          jobs: [],
          quarantine: { path: "runtime/quarantine", entries: 0 },
        }),
      });
      return;
    }
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
    if (url.pathname === "/api/v1/execution-targets") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          local: {
            type: "local-current-host",
            status: "available",
            gpu_count: 2,
            eligible_gpu_count: 2,
            selected_devices: [0, 1],
            devices: [0, 1].map((device) => ({
              snapshot: {
                device,
                name: "NVIDIA RTX 4080 SUPER",
                memory_total_mib: 32768,
                memory_used_mib: 512,
                utilization_percent: 0,
                compute_process_pids: [],
              },
              eligible: true,
              reasons: [],
              active_lease_id: null,
            })),
            detail: "2 张 GPU 可用；启动前仍会重新预检。",
          },
          managed: [
            {
              type: "managed-ssh",
              executor_id: "suzhou2",
              controller_id: "fixture-controller",
              pairing_state: "paired",
              host: "suzhou2.example.invalid",
              port: 22,
              user: "root",
              status: "available",
              gpu_count: 8,
              eligible_gpu_count: 6,
              devices: Array.from({ length: 8 }, (_, device) => ({
                device,
                name: "NVIDIA A100-PCIE-40GB",
                memory_total_mib: 40960,
                memory_used_mib: device < 6 ? 1024 : 18432,
                utilization_percent: device < 6 ? 0 : 96,
                compute_process_count: device < 6 ? 0 : 1,
                eligible: device < 6,
                reasons: device < 6 ? [] : ["external-compute-process"],
                active_lease: false,
              })),
              queue_depth: 1,
              running_jobs: 1,
              resource_observed_at: run.updated_at,
              detail: "当前 6/8 张 GPU 符合启动条件",
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/browser-pymol/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          available: false,
          renderer: "open-source-pymol-wasm",
          pymol_version: "2.6.0a0",
          pyodide_version: "0.22.1",
          offline_assets: true,
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/structure-assistant/status") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          available: false,
          service_name: "EasyDesign 结构助手",
          detail: "平台结构助手尚未由部署者启用",
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/structure-sessions") && route.request().method() === "POST") {
      const requestBody = route.request().postDataJSON() as { stage_number?: 1 | 2 };
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "0.1",
          session_id: `structure-session-fixture-${requestBody.stage_number || 1}`,
          project_id: "apoe",
          run_key: run.run_key,
          stage_number: requestBody.stage_number || 1,
          target_structure_sha256: "a".repeat(64),
          residue_mapping_sha256: "b".repeat(64),
          messages: [],
          pml_revisions: [],
          current_regions: {},
          created_at: "2026-07-29T00:00:00Z",
          updated_at: "2026-07-29T00:00:00Z",
        }),
      });
      return;
    }
    if (url.pathname.startsWith("/api/v1/project-catalog/") && url.pathname.endsWith("/archive") && route.request().method() === "POST") {
      const encodedProjectId = url.pathname.split("/").at(-2) || "";
      const projectId = decodeURIComponent(encodedProjectId);
      archivedProjectIds.add(projectId);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          project_id: projectId,
          category: "archived-project-run",
          moved_paths: [[`${projectId}/${run.run_id}`, `_archive/${projectId}/${run.run_id}`]],
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/project-catalog") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ entries: archivedProjectIds.has("apoe") ? [{
          project_id: "apoe",
          category: "archived-project-run",
          run_count: 1,
          paths: [`_archive/apoe/${run.run_id}`],
        }] : [] }),
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
        body: route.request().method() === "POST"
          ? JSON.stringify({
            schema_version: "0.1",
            session_id: "session-stage02",
            project_id: "apoe",
            design_mode: "stepwise",
            execution_mode: "review-gated",
            current_stage: 2,
            status: "draft",
            config_revisions: [],
            run_lineage: [],
            created_at: "2026-07-28T00:00:00Z",
            updated_at: "2026-07-28T00:00:00Z",
          })
          : JSON.stringify([]),
      });
      return;
    }
    if (url.pathname === "/api/v1/config/forms/3") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "0.1",
          stage_number: 3,
          title: "生成设计方案",
          defaults: {
            profile: "boltzgen-vhh-basic-v1",
            scaffold_registry: "official-vhh7-v1",
            candidates_per_strategy: 40,
          },
          presentation: {
            description: "把所有已批准区域分别与官方 VHH 骨架组合，生成并验证 BoltzGen 设计文件。",
            action_label: "生成并验证设计方案",
            facts: [
              {
                label: "基础模板",
                value: "boltzgen-vhh-basic-v1",
                note: "正向结合约束；其余残基保持中性",
              },
              {
                label: "VHH 骨架",
                value: 7,
                note: "official-vhh7-v1",
              },
              {
                label: "每套候选预算",
                value: 40,
                note: "在第4步执行小规模生成",
              },
            ],
          },
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/config/forms/4") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "0.1",
          stage_number: 4,
          title: "小规模生成",
          defaults: {
            backend: "boltzgen-0.3.2",
            candidates_per_strategy: 40,
          },
          presentation: {
            description: "按设计方案运行可恢复的小规模 BoltzGen 生成。",
            action_label: "开始小规模生成",
            facts: [],
          },
        }),
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
          residue_mapping_sha256: "b".repeat(64),
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
    if (url.pathname.includes("/continuation-job/")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ job: null }),
      });
      return;
    }
    if (url.pathname === "/api/v1/project-preflight") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          available: true,
          project_id: url.searchParams.get("project_id") || "new-design",
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/uploads/raw" && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          schema_version: "0.2",
          upload_token: "upload-fixture",
          filename: "target.pse",
          size_bytes: 18,
          sha256: "a".repeat(64),
          status: "received",
          relative_path: "runtime/state/uploads/upload-fixture/target.pse",
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
    if (url.pathname.endsWith("/continue/2") && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          session: {},
          job: { job_id: "job-stage02-auto", status: "running" },
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/continue/3") && route.request().method() === "POST") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          session: {},
          job: { job_id: "job-stage03", status: "running" },
        }),
      });
      return;
    }
    if (url.pathname.endsWith("/regions/revise") && route.request().method() === "POST") {
      const requestBody = route.request().postDataJSON() as Record<string, unknown>;
      expect(requestBody.confirmed).toBe(true);
      expect(requestBody).not.toHaveProperty("approved_by");
      expect(requestBody).not.toHaveProperty("execution_mode");
      expect(requestBody).not.toHaveProperty("acknowledge_user_provided_regions");
      expect(requestBody).not.toHaveProperty("acknowledge_evidence_limitations");
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          session: {},
          job: { job_id: "job-stage02-manual", status: "running" },
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/jobs/job-stage02-auto") {
      const count = (jobPolls.get("auto") || 0) + 1;
      jobPolls.set("auto", count);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(count === 1
          ? { job_id: "job-stage02-auto", status: "running" }
          : {
            job_id: "job-stage02-auto",
            status: "awaiting-human-approval",
            run_key: automaticStageTwoRun.run_key,
          }),
      });
      return;
    }
    if (url.pathname === "/api/v1/jobs/job-stage02-manual") {
      const count = (jobPolls.get("manual") || 0) + 1;
      jobPolls.set("manual", count);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(count === 1
          ? { job_id: "job-stage02-manual", status: "running" }
          : {
            job_id: "job-stage02-manual",
            status: "succeeded",
            run_key: manualStageTwoRun.run_key,
          }),
      });
      return;
    }
    if (url.pathname === "/api/v1/jobs/job-stage03") {
      const count = (jobPolls.get("stage03") || 0) + 1;
      jobPolls.set("stage03", count);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(count === 1
          ? { job_id: "job-stage03", status: "running" }
          : {
            job_id: "job-stage03",
            status: "succeeded",
            run_key: stageThreeRun.run_key,
          }),
      });
      return;
    }
    if (url.pathname === "/api/v1/projects") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          projects: archivedProjectIds.has("apoe")
            ? []
            : [{ project_id: "apoe", run_count: 1, latest_run: run, runs: [run] }],
          drafts: [],
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
      const strategyId = url.searchParams.get("strategy_id");
      const gateStatus = url.searchParams.get("gate_status");
      const focusedPilot = phase === "pilot"
        && strategyId === "A__scaffold-1"
        && gateStatus === "通过";
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
          : focusedPilot
            ? candidateItems.slice(0, 5)
            : candidateItems;
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          phase,
          page: 1,
          page_size: 50,
          total: phase === "full-target"
            ? 10
            : phase === "expansion"
              ? 12
              : focusedPilot
                ? 5
                : 840,
          total_pages: phase === "pilot" && !focusedPilot ? 17 : 1,
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
    if (url.pathname === `/api/v1/runs/${automaticStageTwoRun.run_key}`) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(automaticStageTwoRun),
      });
      return;
    }
    if (url.pathname === `/api/v1/runs/${manualStageTwoRun.run_key}`) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(manualStageTwoRun),
      });
      return;
    }
    if (url.pathname === `/api/v1/runs/${stageThreeRun.run_key}`) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(stageThreeRun),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("legacy managed region sticks are hidden without affecting custom sticks", () => {
  const pml = [
    "show sticks, ed_region_A",
    "show stick, ed_region_B",
    "show sticks, ligand_focus",
    "show sticks, target and resi 23",
  ].join("\n");

  for (const stageNumber of [1, 2] as const) {
    const display = pymolDisplayPml(pml, stageNumber);
    expect(display).not.toContain("show sticks, ed_region_A");
    expect(display).not.toContain("show stick, ed_region_B");
    expect(display).toContain("show sticks, ligand_focus");
    expect(display).toContain("show sticks, target and resi 23");
  }
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
  await expect(page.getByText("这是按 v1.5 规则完成的历史运行")).toBeVisible();
  await expect(page.getByRole("heading", { name: "点击等级查看设计方案" })).toBeVisible();
});

test("v1.6 promotes tier-a strategies even when diagnostics warn", async ({ page }) => {
  await page.route("**/api/v1/runs/apoe-run-key/stages/5/overview", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...overview,
        state: "succeeded",
        advisory_validation: true,
        conclusion_title: "1 组 Tier A 晋级，完整目标复核产生提醒",
        conclusion: "诊断提醒不会撤销 Tier A 晋级。",
        counts: {
          ...overview.counts,
          promoted_strategies: 1,
          diagnostic_warnings: 1,
        },
      }),
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await expect(page.getByRole("heading", { name: "1 组 Tier A 进入规模化生成" })).toBeVisible();
  await expect(page.getByText("科学负结果显示为提醒")).toBeVisible();
});


test("dashboard trash button archives a project after confirmation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "我的项目" })).toBeVisible();
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("runs/_archive/");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "删除项目 apoe" }).click();
  await expect(page.getByText("项目 apoe 已移入可恢复归档。")).toBeVisible();
  await expect(page.getByText("还没有设计项目")).toBeVisible();
  await expect(page.getByRole("heading", { name: "apoe" })).toHaveCount(0);
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
  await page.getByRole("button", { name: "诊断证据" }).click();
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

test("ordinary users only see the platform assistant service status", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByText("技术详情", { exact: true }).click();
  await expect(page.getByText("EasyDesign 结构助手", { exact: true })).toBeVisible();
  await expect(page.getByText(/API 由 EasyDesign 部署者统一提供/)).toBeVisible();
  await expect(page.getByLabel("API key")).toHaveCount(0);
  await expect(page.getByLabel("模型 ID")).toHaveCount(0);
  await expect(page.getByLabel("提供方")).toHaveCount(0);
});

test("settings separates local readiness, public compute and archives", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "设置" }).click();

  await expect(page.getByRole("heading", { name: "工作区设置" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /当前设备/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "基础环境已就绪" })).toBeVisible();
  await expect(page.getByText("EasyDesign 基础环境", { exact: true })).toBeVisible();
  await expect(page.getByText("BoltzGen", { exact: true })).toBeVisible();
  await expect(page.getByText("/fixture/easydesign", { exact: true })).toBeHidden();
  await page.getByText("技术详情", { exact: true }).click();
  await expect(page.getByText("uv-venv · 0.1.0.dev48 · available", { exact: true })).toBeVisible();
  await expect(page.getByText("retired", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "刷新状态" })).toHaveCount(0);

  await page.getByRole("tab", { name: /公共算力/ }).click();
  await expect(page.getByRole("heading", { name: "Suzhou2 尚未连接" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Suzhou2", exact: true })).toBeVisible();
  await expect(page.getByText(/不会读取、替换或修改 ~\/.ssh/)).toBeVisible();
  await expect(page.getByRole("button", { name: "1. 核对服务器身份" })).toBeVisible();
  await expect(page.getByRole("button", { name: "2. 检测或生成工作区密钥" })).toBeVisible();

  await page.getByRole("tab", { name: /项目存档/ }).click();
  await expect(page.getByRole("heading", { name: "项目存档", exact: true })).toBeVisible();
  await expect(page.getByText("还没有存档项目")).toBeVisible();
  await expect(page.getByText("自检历史")).toHaveCount(0);
});

test("settings returns directly to the project that opened it", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  await expect(page.getByRole("heading", { name: "第5步：筛选与验证", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "设置" }).click();
  const back = page.getByRole("button", { name: "返回项目 apoe" });
  await expect(back).toBeVisible();
  await back.click();

  await expect(page.getByRole("heading", { name: "第5步：筛选与验证", exact: true })).toBeVisible();
});

test("Suzhou2 pairing reuses an existing workspace key and accepts one password once", async ({ page }) => {
  let pairingState = "awaiting-public-key";
  let submittedPassword = "";
  await page.route("**/api/v1/remote-executors**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() === "POST" && pathname.endsWith("/pair-password-bootstrap")) {
      const payload = request.postDataJSON() as { password: string; confirmed: boolean };
      submittedPassword = payload.password;
      pairingState = "paired";
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          status: "paired",
          pairing: { pairing_state: "paired" },
          installation: { status: "installed" },
          probe: { gpu_count: 8 },
        }),
      });
      return;
    }
    if (request.method() === "POST" && pathname.endsWith("/unpair")) {
      pairingState = "unpaired";
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "unpaired", pairing: { pairing_state: "unpaired" } }),
      });
      return;
    }
    if (request.method() === "GET" && pathname === "/api/v1/remote-executors") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          executors: [{
            executor_id: "suzhou2",
            label: "Suzhou2 公共算力",
            type: "managed-ssh",
            pairing_state: pairingState,
            controller_id: "controller-primary",
            host: "36.212.4.47",
            port: 22,
            user: "root",
            host_fingerprint: "SHA256:verified",
            key_pair_available: true,
          }],
        }),
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("tab", { name: /公共算力/ }).click();

  await expect(page.getByText(/已检测到完整的工作区专用密钥/)).toBeVisible();
  await expect(page.getByRole("button", { name: "2. 工作区密钥已就绪" })).toBeDisabled();
  const connect = page.getByRole("button", { name: "3. 用一次性密码安装并连接" });
  await expect(connect).toBeDisabled();
  await page.getByLabel("Suzhou2 一次性登录密码").fill("temporary-password");
  await expect(connect).toBeEnabled();
  await connect.click();

  await expect(page.getByRole("heading", { name: "Suzhou2 已连接" })).toBeVisible();
  expect(submittedPassword).toBe("temporary-password");
  await expect(page.getByLabel("Suzhou2 一次性登录密码")).toHaveCount(0);

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "解除绑定并重新配置" }).click();
  await expect(page.getByRole("heading", { name: "Suzhou2 尚未连接" })).toBeVisible();
  await expect(page.getByText(/已解除绑定，可以重新核对服务器并配置连接/)).toBeVisible();
  await expect(page.getByRole("button", { name: "1. 核对服务器身份" })).toBeVisible();
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
  const touchAction = await page.locator(".mol-viewport").first().evaluate(
    (node) => getComputedStyle(node).touchAction,
  );
  expect(touchAction).toBe("none");
});

test("project, filtering and settings pages keep the approved visual hierarchy", async ({ page, browserName }) => {
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
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByRole("heading", { name: "工作区设置" })).toBeVisible();
  await expect(page).toHaveScreenshot("settings-current-device.png", {
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
  const routeCards = page.locator(".design-route-grid > button");
  await expect(routeCards.nth(0)).toContainText("01");
  await expect(routeCards.nth(0)).toContainText("按步骤设计");
  await expect(routeCards.nth(1)).toContainText("02");
  await expect(routeCards.nth(1)).toContainText("全流程设计");
  await page.getByRole("button", { name: /全流程设计/ }).click();
  await expect(page.getByRole("heading", { name: "全流程设计" })).toBeVisible();
  for (const source of ["PyMOL PSE", "PDB / mmCIF", "FASTA / 序列", "RCSB PDB ID", "UniProt", "目标结构包"]) {
    await expect(page.getByRole("button", { name: new RegExp(source) })).toBeVisible();
  }
  await expect(page.getByText("标准 YAML 配置预览")).toBeVisible();
  await expect(page.getByText('schema_version: "0.8"')).toBeVisible();
});

test("stage six uses the exact user-entered candidate count", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /全流程设计/ }).click();
  await page.locator(".scientific-stage-browser").getByRole("button", { name: /规模化/ }).click();
  await page.getByRole("button", { name: "将本次运行范围扩展到第 6 步" }).click();

  const candidateCount = page.getByLabel("Stage 06 总生成条数");
  await expect(candidateCount).toHaveValue("50000");
  await candidateCount.fill("37");
  await expect(page.getByText("total_candidate_count: 37")).toBeVisible();
  await expect(page.getByText(/当前为 37 条/)).toBeVisible();

  await candidateCount.fill("0");
  await expect(candidateCount).toHaveAttribute("aria-invalid", "true");
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

test("project name is validated before a local file can be uploaded", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();

  const projectName = page.getByLabel("项目名称");
  await projectName.fill("Test");
  await expect(projectName).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText(/建议使用 test/)).toBeVisible();
  await expect(page.getByLabel("选择本地文件")).toBeDisabled();

  await page.getByRole("button", { name: "使用 test" }).click();
  await expect(projectName).toHaveValue("test");
  await expect(projectName).toHaveAttribute("aria-invalid", "false");
  await expect(page.getByLabel("选择本地文件")).toBeEnabled();
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
  const stageOneSidebar = page.locator(".structure-sidebar");
  await expect(stageOneSidebar.getByText("序列长度", { exact: true })).toBeVisible();
  await expect(stageOneSidebar.getByText("138 aa", { exact: true })).toBeVisible();
  await expect(stageOneSidebar.getByText("目标结构", { exact: true })).toHaveCount(0);
  await expect(stageOneSidebar.getByText("来源", { exact: true })).toHaveCount(0);
  await expect(stageOneSidebar.getByText("结构模型数", { exact: true })).toHaveCount(0);
  await expect(stageOneSidebar.getByText("缺失的 CA 原子", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "配置下一步：选择结合区域" })).toBeVisible();
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await expect(page.getByRole("heading", { name: "第2步：选择结合区域" })).toBeVisible();
  await expect(page.locator(".stage-node").nth(1)).toHaveClass(/selected/);
  await expect(page.locator(".region-editor-embedded")).toBeVisible();
  await expect(page.locator(".region-editor-overlay")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "选择结合区域", exact: true }),
  ).toBeVisible();
});

test("structure assistant shows the real upstream error type", async ({ page }) => {
  await page.route("**/api/v1/structure-assistant/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        available: true,
        service_name: "EasyDesign 结构助手",
        detail: "平台服务已就绪",
      }),
    });
  });
  await page.route("**/api/v1/structure-sessions/*/messages", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "deepseek API 响应超时（ReadTimeout，等待上限 60 秒）；当前场景未修改，请稍后重试",
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await page.getByPlaceholder("输入显示操作或明确的残基编号…").fill("仅保留区域 A");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(
    page.getByText(/请求失败：deepseek API 响应超时（ReadTimeout，等待上限 60 秒）/),
  ).toBeVisible();
  await expect(page.getByText(/当前场景未修改，请稍后重试/).first()).toBeVisible();
});

test("developer smoke is separated from scientific projects", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /开发者自检/ }).click();
  await expect(page.getByRole("heading", { name: "开发者全阶段自检" })).toBeVisible();
  await page.getByRole("button", { name: "运行快速七步自检" }).click();
  await expect(page.getByText("七阶段工程链路通过。")).toBeVisible();
});

test("a stage-five run keeps all accepted upstream stages read-only", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "查看项目 →" }).click();
  for (const stageIndex of [0, 1, 2, 3, 4]) {
    await page.locator(".stage-node").nth(stageIndex).click();
    await expect(page.getByText("本步骤仅供查看", { exact: false })).toBeVisible();
  }
  await page.locator(".stage-node").nth(0).click();
  await expect(page.getByRole("button", { name: "配置下一步：选择结合区域" })).toHaveCount(0);
  await page.locator(".stage-node").nth(1).click();
  await expect(page.getByRole("button", { name: "重新选择结合区域" })).toHaveCount(0);
});

test("stage two region editor keeps source layers and editable selection separate", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await expect(page.getByRole("heading", { name: "选择结合区域", exact: true })).toBeVisible();
  await expect(page.getByLabel("显示 PSE 来源颜色")).not.toBeChecked();
  await expect(page.getByLabel("显示当前批准区域")).not.toBeChecked();
  const firstResidue = page.locator(".sequence-editor button").first();
  await expect(firstResidue).toContainText("规范 1");
  await expect(firstResidue).toContainText("原始 A:23");
  await expect(page.getByRole("button", { name: /区域 A/ })).toContainText("本次可编辑 1 个残基");
  await expect(page.getByRole("button", { name: /区域 B/ })).toContainText("本次可编辑 1 个残基");
  await page.getByRole("button", { name: /区域 B/ }).click();
  await firstResidue.click();
  await expect(firstResidue).toHaveClass(/region-b/);
  await expect(page.getByRole("button", { name: /区域 A/ })).toContainText("本次可编辑 0 个残基");
  await expect(page.getByRole("button", { name: /区域 B/ })).toContainText("本次可编辑 2 个残基");
  await expect(page.locator(".region-editor-feedback")).toHaveText("已将规范残基 1 设为区域 B。");
  await expect(page.getByRole("button", { name: "橡皮擦" })).toHaveCount(0);
  await firstResidue.click();
  await expect(firstResidue).not.toHaveClass(/region-b/);
  await expect(page.getByRole("button", { name: /区域 B/ })).toContainText("本次可编辑 1 个残基");
  await expect(page.locator(".region-editor-feedback")).toHaveText(
    "已取消规范残基 1 的区域 B 选择。",
  );
  await page.getByRole("button", { name: "从空白开始" }).click();
  await expect(firstResidue).not.toHaveClass(/region-b/);
  await expect(page.getByLabel("显示 PSE 来源颜色")).not.toBeChecked();
  await expect(page.getByLabel("显示当前批准区域")).not.toBeChecked();
  await expect(page.locator(".region-editor-feedback")).toHaveText(
    "已隐藏上游颜色并清空本次编辑层；现在可以从空白结构重新选择。",
  );
  await expect(page.getByText("设计目的", { exact: true })).toHaveCount(0);
  await expect(page.getByText("生物学理由", { exact: true })).toHaveCount(0);
  await expect(page.getByText("结构理由", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/无需为 A、B、C 分别重复填写目的和理由/)).toBeVisible();
});

test("stage two reload restores the persisted assistant region draft before scene sync", async ({ page }) => {
  let sceneWrites = 0;
  await page.route("**/api/v1/runs/*/structure-sessions", async (route) => {
    const requestBody = route.request().postDataJSON() as { stage_number?: 1 | 2 };
    const stageNumber = requestBody.stage_number || 1;
    const existingScene = {
      version_id: "scene-v000002-fixture",
      revision: 2,
      parent_version_id: "scene-v000001-fixture",
      actor: "ai",
      source: "assistant",
      summary: "仅保留区域 A",
      pml: [
        "select ed_region_A, target and chain A and resi 23",
        "select ed_region_B, none",
        "select ed_region_C, none",
        "color red, ed_region_A",
      ].join("\n"),
      sha256: "c".repeat(64),
      created_at: "2026-08-03T00:00:00Z",
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "0.4",
        session_id: `structure-session-reload-${stageNumber}`,
        project_id: "apoe",
        run_key: run.run_key,
        stage_number: stageNumber,
        target_structure_sha256: "a".repeat(64),
        residue_mapping_sha256: "b".repeat(64),
        messages: stageNumber === 2 ? [{
          message_id: "message-reload-fixture",
          role: "assistant",
          content: "已清空 B、C 区域。",
          created_at: "2026-08-03T00:00:00Z",
        }] : [],
        pml_revisions: [],
        scene_versions: stageNumber === 2 ? [
          { ...existingScene, version_id: "scene-v000001-fixture", revision: 1 },
          existingScene,
        ] : [],
        active_scene_version_id: stageNumber === 2
          ? "scene-v000002-fixture"
          : undefined,
        current_regions: stageNumber === 2 ? { A: [1] } : {},
        created_at: "2026-08-03T00:00:00Z",
        updated_at: "2026-08-03T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/structure-sessions/*/scene-pml", async (route) => {
    sceneWrites += 1;
    await route.fulfill({ status: 500, body: "unexpected scene write" });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await expect(page.getByRole("button", { name: /区域 A/ })).toContainText("本次可编辑 1 个残基");
  await expect(page.getByRole("button", { name: /区域 B/ })).toContainText("本次可编辑 0 个残基");
  await expect(page.getByRole("button", { name: /区域 C/ })).toContainText("本次可编辑 0 个残基");
  await expect(page.locator(".region-editor-feedback")).toHaveText(
    "已恢复结构助手会话中的 1 个区域残基；来源颜色和正式结果未被修改。",
  );
  await page.waitForTimeout(500);
  expect(sceneWrites).toBe(0);
});

test("stage two automatic branch shows real progress and opens the new run", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await page.getByRole("button", { name: /^SASA/ }).click();
  await expect(page.getByText("后续运行方式", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "启动第2步" }).click();
  await expect(page.getByRole("progressbar", { name: "第2步正在运行" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "第2步：选择结合区域" })).toBeVisible();
  await expect(page.locator(".status-awaiting-human-approval")).toContainText("等待你的确认");
});

test("explicit manual regions complete one approval and open a succeeded branch", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await expect(page.getByLabel("批准人")).toHaveCount(0);
  await expect(page.getByText(/我确认这些是用户提供的设计区域/)).toHaveCount(0);
  await expect(page.getByText("后续运行方式", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "保存并完成第2步" }).click();
  await expect(page.getByRole("progressbar", { name: "第2步正在运行" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "第3步：生成设计方案", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "配置第3步：生成设计方案" })).toBeVisible();
  await expect(page.getByText("3 个区域 × 7 个骨架")).toBeVisible();
  await expect(page.getByText("已完成", { exact: true }).first()).toBeVisible();
  await page.locator(".stage-node").nth(1).click();
  await expect(page.getByText("9 个残基", { exact: true })).toBeVisible();
  await expect(page.getByText("14 个残基", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("这些区域是用户确认的设计输入，不代表实验验证的结合位点。")).toBeVisible();
  await expect(page.getByText(/规范编号 10/)).toHaveCount(0);
  await expect(page.getByText("manual-residue-list", { exact: true })).toHaveCount(0);
  await expect(page.getByText("human:local-workbench", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "技术记录" }).click();
  await expect(page.getByText("manual-residue-list", { exact: true })).toBeVisible();
  await expect(page.getByText("explicit-review", { exact: true })).toBeVisible();
});

test("stage three continuation runs from Python defaults and advances to stage four", async ({ page }) => {
  let releaseResources: () => void = () => {};
  const resourcesReady = new Promise<void>((resolve) => {
    releaseResources = resolve;
  });
  await page.route("**/api/v1/execution-targets", async (route) => {
    await resourcesReady;
    await route.fallback();
  });
  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await page.getByRole("button", { name: "保存并完成第2步" }).click();
  await expect(page.getByRole("heading", { name: "配置第3步：生成设计方案" })).toBeVisible();

  await page.getByRole("button", { name: "生成并验证设计方案" }).click();
  await expect(page.getByRole("progressbar", { name: "第3步真实进度" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "第4步：小规模生成", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("选择计算位置")).toBeVisible();
  await expect(page.getByText("生成后端", { exact: true })).toHaveCount(0);
  await expect(page.getByText("目标候选数", { exact: true })).toHaveCount(0);
  await expect(page.getByText("默认设备数", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /当前机器/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Suzhou2 公共算力/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始小规模生成" })).toBeDisabled();
  await page.getByRole("button", { name: /Suzhou2 公共算力/ }).click();
  await expect(page.getByText("正在读取 GPU 状态", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "查看 GPU 状态" }).click();
  const gpuDialog = page.getByRole("dialog", { name: "Suzhou2 公共算力 GPU 状态" });
  await expect(gpuDialog).toBeVisible();
  await expect(gpuDialog.getByText("正在读取逐卡状态", { exact: true }).first()).toBeVisible();
  await expect(gpuDialog.getByText("逐卡探针暂时不可用", { exact: true })).toHaveCount(0);
  releaseResources();
  await expect(page.getByRole("button", { name: /Suzhou2 公共算力/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: /Suzhou2 公共算力/ })).toContainText("已配对");
  await expect(page.getByText("6/8 张 GPU 符合启动条件", { exact: true })).toBeVisible();
  await expect(gpuDialog.locator(".gpu-resource-grid > article")).toHaveCount(8);
  await expect(gpuDialog.getByText("GPU 0", { exact: true })).toBeVisible();
  await expect(gpuDialog.getByText("空闲", { exact: true }).first()).toBeVisible();
  await expect(gpuDialog.getByText("占用", { exact: true }).first()).toBeVisible();
  await gpuDialog.getByRole("button", { name: "关闭 GPU 状态" }).click();
  await expect(gpuDialog).toBeHidden();
  await expect(page.locator(".stage-node").nth(3)).toHaveClass(/selected/);
  await page.locator(".stage-node").nth(2).click();
  await expect(page.getByText("21").first()).toBeVisible();
  await expect(page.getByText("结合区域 × VHH 骨架设计矩阵")).toBeVisible();
});

test("managed stage run shows the linked stage rail and real structured progress", async ({ page }) => {
  let continuationRequests = 0;
  await page.route("**/api/v1/runs/*/continue/4", async (route) => {
    continuationRequests += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session: {},
        job: { job_id: "job-stage04-managed", status: "queued" },
        execution_target: "managed-ssh",
        remote_job: { executor_id: "suzhou2", job_id: "job-stage04-managed" },
      }),
    });
  });
  await page.route("**/api/v1/runs/*/continuation-job/4", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(continuationRequests === 0
        ? { job: null }
        : {
          job: {
            job_id: "job-acceptance-stage04-managed",
            status: "running",
            stage_number: 4,
          },
          execution_target: "managed-ssh",
          remote_job: { executor_id: "suzhou2", job_id: "job-stage04-managed" },
        }),
    });
  });
  await page.route("**/api/v1/remote-jobs/suzhou2/job-stage04-managed", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        executor_id: "suzhou2",
        job_id: "job-stage04-managed",
        connection_state: "connected",
        queue: { status: "running", assigned_devices: [2, 3] },
        progress: {
          stage_id: "05-pilot-filtering",
          phase: "pilot-structure-metrics",
          status: "running",
          total_tasks: 8,
          running_tasks: 2,
          succeeded_tasks: 4,
          failed_tasks: 0,
          planned_candidates: 8,
          collected_candidates: 4,
          estimated_remaining_seconds: 600,
        },
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "新建设计" }).first().click();
  await page.getByRole("button", { name: /按步骤设计/ }).click();
  await page.getByLabel("选择本地文件").setInputFiles({
    name: "target.pse",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("fixture-pse-content"),
  });
  await page.getByRole("button", { name: "配置下一步：选择结合区域" }).click();
  await page.getByRole("button", { name: "保存并完成第2步" }).click();
  await page.getByRole("button", { name: "生成并验证设计方案" }).click();
  await expect(page.getByRole("heading", { name: "配置第4步：小规模生成" })).toBeVisible();
  await page.getByRole("button", { name: /Suzhou2 公共算力/ }).click();
  await page.getByText(/我确认本步骤会调用真实计算后端/).click();
  await page.getByRole("button", { name: "开始小规模生成" }).click();

  await expect(page.getByRole("heading", { name: "第4步 → 第5步" })).toBeVisible();
  const rail = page.locator(".linked-stage-rail");
  await expect(rail.locator("article").nth(0)).toHaveClass(/complete/);
  await expect(rail.locator("article").nth(1)).toHaveClass(/active/);
  await expect(page.getByText("正在计算小规模候选结构指标")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "第5步真实进度" })).toHaveAttribute("aria-valuenow", "50");
  await expect(page.getByText("4 / 8 个候选")).toBeVisible();

  // Leaving and re-entering the stage destroys component memory just like a
  // refreshed workbench.  The durable continuation endpoint must restore the
  // existing manager job instead of presenting a second submit action.
  await page.locator(".stage-node").nth(2).click();
  await page.locator(".stage-node").nth(3).click();
  await expect(page.getByRole("heading", { name: "第4步 → 第5步" })).toBeVisible();
  await expect(page.getByRole("button", { name: "第4步正在运行…" })).toBeDisabled();
  await expect(page.getByText("Suzhou2 正在运行", { exact: false })).toBeVisible();
  expect(continuationRequests).toBe(1);
});
