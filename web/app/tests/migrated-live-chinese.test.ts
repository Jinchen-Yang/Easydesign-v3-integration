import { describe, expect, it } from "vitest";
import {
  gateIntro,
  gateOptionFallback,
  gateTitle,
  liveActionName,
  liveConnectionName,
  liveInputTypeName,
  liveStageName,
  liveStatusName,
  normalizeLiveScientificChinese,
} from "../src/views/easy/liveChinese";
import type { Decision } from "../src/views/easy/product-contracts";

const decision: Decision = {
  id: "gate-2",
  gate: 2,
  type: "site",
  question: "Which site should be approved?",
  default_option_id: "site-a",
  options: [],
  warnings: [],
  limitations: [],
  action_summary: "Choose a site.",
  revision_targets: [],
  review_status: "SUPPORTED",
  required_fields: {},
  summary: {},
};

describe("Easy live Chinese presentation", () => {
  it("localizes stages, statuses, connections and input types without changing protocol ids", () => {
    expect(liveStageName("pilot")).toBe("小规模验证");
    expect(liveStatusName("awaiting_scientist")).toBe("等待审批");
    expect(liveConnectionName("connected")).toBe("已连接");
    expect(liveInputTypeName("structure")).toBe("结构文件");
  });

  it("uses concise Chinese for native workflow actions", () => {
    expect(liveActionName("pilot-operational-evidence")).toBe(
      "正在执行小规模验证",
    );
    expect(liveActionName("scientist-gate")).toBe("等待科学家审批");
    expect(liveActionName("handoff-complete")).toBe("当前阶段已完成");
  });

  it("never falls back to an English approval option while localization loads", () => {
    expect(gateTitle(2)).toBe("选择并批准结合位点");
    expect(gateIntro(2)).toContain("默认选中");
    expect(
      gateOptionFallback(
        decision,
        {
          option_id: "site-a",
          eligible: true,
          actions: ["approve"],
          rank: "A",
        },
        0,
      ),
    ).toEqual({
      label: "位点 A（推荐）",
      description: "正在整理该位点的科学依据。",
    });
  });

  it("provides a Chinese loading state for every scientist gate", () => {
    for (const gate of [1, 2, 3, 4, 5]) {
      const value = { ...decision, gate };
      const fallback = gateOptionFallback(
        value,
        { option_id: "choice", eligible: true, actions: ["approve"] },
        0,
      );
      expect(gateTitle(gate)).not.toMatch(
        /Approve|Target|Site|Design|Pilot|Scale|Candidate/,
      );
      expect(gateIntro(gate)).not.toMatch(
        /Approve|Target|Site|Design|Pilot|Scale|Candidate/,
      );
      expect(fallback.label).not.toMatch(
        /Approve|Target|Site|Design|Pilot|Scale|Candidate/,
      );
      expect(fallback.description).not.toMatch(
        /Approve|Target|Site|Design|Pilot|Scale|Candidate/,
      );
    }
    expect(
      gateOptionFallback(
        { ...decision, gate: 3 },
        { option_id: "choice", eligible: true, actions: ["approve"] },
        0,
      ).description,
    ).toBe("");
  });

  it("presents every Gate 4 route as a distinct concise Chinese action", () => {
    const gate4: Decision = {
      ...decision,
      gate: 4,
      default_option_id: "PROMOTE_TO_SCALE",
      summary: {
        proposed_interpretation: {
          selected_strategy_ids: [
            "arm-1-scaffold-8coh",
            "arm-1-scaffold-sonelokimab",
          ],
          requested_scale_candidates: 30,
          production_strategy_allocations: {
            "arm-1-scaffold-8coh": 15,
            "arm-1-scaffold-sonelokimab": 15,
          },
        },
      },
    };
    const routes = [
      "PROMOTE_TO_SCALE",
      "RUN_ANOTHER_PILOT",
      "REVISE_DESIGN",
      "REVISE_SITE",
      "STOP",
    ];
    const copy = routes.map((option_id, index) =>
      gateOptionFallback(
        gate4,
        { option_id, eligible: true, actions: ["approve"] },
        index,
      ),
    );
    expect(copy.map((item) => item.label)).toEqual([
      "进入扩大验证（推荐）",
      "再进行一轮小规模验证",
      "修改设计方案",
      "重新选择结合位点",
      "停止本次设计",
    ]);
    expect(copy[0].description).toBe(
      "将小规模验证支持的 2 条策略进入扩大验证，共 30 个候选（骨架 8COH：15 个；骨架 SONELOKIMAB：15 个）。",
    );
    expect(copy.every((item) => !item.description.includes("正在整理"))).toBe(
      true,
    );
  });

  it("presents Gate 5 routes without exposing internal route names", () => {
    const gate5 = { ...decision, gate: 5, default_option_id: "wet-lab-panel" };
    expect(
      gateOptionFallback(
        gate5,
        { option_id: "wet-lab-panel", eligible: true, actions: ["approve"] },
        0,
      ),
    ).toEqual({
      label: "确认最终候选并生成交接方案（推荐）",
      description:
        "确认主候选与备选列表，生成模拟下单所需的交接信息；不会授权真实实验或采购。",
    });
  });

  it("normalizes workflow terms retained by scientific localization without changing acronyms", () => {
    expect(
      normalizeLiveScientificChinese(
        "批准此确切的Design和Pilot计划；未授权任何Scale。针对NK2R的VHH binder，仅冻结Gate3 YAML规范。",
      ),
    ).toBe(
      "批准此确切的设计方案和小规模验证计划；未授权任何扩大验证。针对NK2R的VHH 结合分子，仅冻结第 3 关 YAML规范。",
    );
    expect(
      normalizeLiveScientificChinese(
        "Scientist reviews Site A hotspots; AFO, BoltzGen, PDB and UniProt remain named.",
      ),
    ).toBe(
      "科学家 reviews 位点 A 热点残基; AFO, BoltzGen, PDB and UniProt remain named.",
    );
  });

  it("turns internal review tokens into readable Chinese for approval risks", () => {
    expect(
      normalizeLiveScientificChinese(
        "region-A-has-2-spatial-components;user-members-preserved; approach_validation not-performed; avoid; INCONCLUSIVE; override",
      ),
    ).toBe(
      "位点 A 包含两个空间组分；已保留用户指定残基; 尚未进行接近路径验证; 应避免; 结论不确定; 越权批准",
    );
  });
});
