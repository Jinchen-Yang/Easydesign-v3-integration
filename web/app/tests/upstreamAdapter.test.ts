import { afterEach, expect, it, vi } from "vitest";
import { EasyProductAdapter } from "../src/views/easy/EasyProductAdapter";
import type { ProductSnapshot } from "../src/data/product-contracts";
const adapters: EasyProductAdapter[] = [];
afterEach(() => {
  adapters.forEach((a) => a.dispose());
  adapters.length = 0;
});
function snapshot(project = "p1"): ProductSnapshot {
  return {
    schema_version: "1",
    mode: "live",
    revision: "revision-1",
    project: {
      id: project,
      title: "Research",
      goal: "A goal",
      thread_id: null,
      phase: "site",
      status: "awaiting_scientist",
      last_activity: 1,
      validation_only: true,
    },
    workflow: [],
    current_action: {
      id: "gate",
      stage: "site",
      message: "Review site",
      resumable: false,
    },
    specialists: [],
    scientific_context: { structure: null, sites: [], arms: [] },
    decision: {
      id: "card-1",
      gate: 2,
      type: "site",
      question: "Which site?",
      default_option_id: "site-a",
      options: [],
      warnings: [],
      limitations: [],
      action_summary: "",
      revision_targets: [],
      review_status: null,
      required_fields: {},
      summary: {},
    },
    jobs: [],
    artifacts: [],
    conversation: [],
    recent_activity: [],
    tasks: [],
    lifecycle: "scientific_project",
    event_cursor: 1,
    candidates: {
      total: 0,
      counts: {},
      url: `/projects/${project}/candidates`,
    },
    capabilities: { decide: true, message: true, resume: true },
    requests: [],
    lab_order: null,
    connection: "connected",
  };
}

it("publishes progress before slow candidate reads and ignores obsolete phase responses", async () => {
  let current = snapshot();
  current.project.phase = "pilot";
  current.project.status = "running";
  let resolvePilot!: (response: Response) => void;
  const pilot = new Promise<Response>((resolve) => {
    resolvePilot = resolve;
  });
  const empty = () =>
    Response.json({ items: [], total: 0, offset: 0, limit: 100 });
  const transport = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/workbench")) return Response.json(current);
    if (url.includes("/candidates?") && url.includes("phase=pilot"))
      return pilot;
    return empty();
  });
  const adapter = new EasyProductAdapter(transport);
  adapters.push(adapter);
  let observed = await adapter.load();
  adapter.subscribe((event) => {
    observed = event.snapshot;
  });
  await adapter.selectProject("p1");
  expect(observed.snapshot?.project.phase).toBe("pilot");
  current = { ...current, revision: "new-revision", event_cursor: 2 };
  await adapter.refresh();
  expect(observed.snapshot?.event_cursor).toBe(2);
  await adapter.candidatePage(0, "scale");
  expect(observed.candidatePhase).toBe("scale");
  resolvePilot(empty());
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(observed.candidatePhase).toBe("scale");
});

it("loads YAML and localizes through the injected scoped transport", async () => {
  const transport = vi.fn(async (input: RequestInfo | URL) =>
    String(input).includes("/artifacts/")
      ? new Response("version: 1")
      : Response.json({ locale: "zh-CN", items: { why: "已验证" } }),
  );
  const adapter = new EasyProductAdapter(transport);
  adapters.push(adapter);
  const url = "/api/v1/scopes/user-test/artifacts/" + "a".repeat(64);
  expect(await adapter.artifactText(url)).toBe("version: 1");
  await adapter.localizeScientific([{ id: "why", text: "Verified" }], {
    stage: "Site",
    goal: "Synthetic",
  });
  expect(transport.mock.calls.map(([url]) => url)).toContain(
    "/api/v1/rabbit/localize",
  );
  await expect(
    adapter.artifactText("https://example.com/secret"),
  ).rejects.toThrow();
});
