import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { RabbitActor, type RabbitStage } from "../src/views/easy/RabbitActor";

const renderStage = (stage: RabbitStage) =>
  renderToStaticMarkup(createElement(RabbitActor, { stage, active: true }));

describe("DouDou stage artwork", () => {
  it("keeps the transparent mascot and adds distinct task props for scientific stages", () => {
    const target = renderStage("Target");
    const site = renderStage("Site");
    const design = renderStage("Design");
    const pilot = renderStage("Pilot");
    const scale = renderStage("Scale");
    const candidates = renderStage("Candidates");

    expect(target).toContain("bunny-magnifier");
    expect(site).toContain("bunny-site-map");
    expect(design).toContain("bunny-laptop");
    expect(pilot).toContain("bunny-pipette");
    expect(scale).toContain("bunny-rack");
    expect(candidates).toContain("bunny-celebration");

    for (const stage of [target, site, design, pilot, scale, candidates]) {
      expect(stage).toContain("rabbit-mesh");
      expect(stage).not.toContain("/originals/");
    }
  });
});
