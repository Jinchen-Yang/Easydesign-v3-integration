import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LiveWorkbenchAdapter,
  ApiError as ProApiError,
} from "../src/adapters/LiveWorkbenchAdapter";
import {
  EasyProductAdapter,
  ApiError as EasyApiError,
} from "../src/views/easy/EasyProductAdapter";
import { type LiveProductStore } from "../src/data/LiveProductStore";
import type {
  LiveState,
  ProductLabOrder,
  ProductSnapshot,
  RequestState,
} from "../src/data/product-contracts";
import { emptyInput } from "../src/views/easy/contracts";

const adapters: LiveProductStore[] = [];
afterEach(() => {
  adapters.splice(0).forEach((adapter) => adapter.dispose());
  vi.useRealTimers();
});
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
const page = { items: [], offset: 0, limit: 20, total: 0, revision: "rev" };
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
const request = (id: string, state = "succeeded"): RequestState => ({
  id,
  project: "p1",
  state,
  result: null,
  created: 1,
  updated: 1,
});
function labOrder(): ProductLabOrder {
  return {
    schema_version: "1",
    mode: "simulation",
    provider: "mock-lab-v1",
    project_id: "p1",
    handoff_sha256: "hash",
    handoff_status: "available",
    ordering_status: "simulation-only-not-ordered",
    revision: "order-revision",
    candidates: [],
    draft: null,
    quote: null,
    receipt: null,
    capabilities: { save: true, quote: true, submit: true, real_order: false },
    disclaimer: "Simulation only",
  };
}
const variants = [
  {
    name: "Easy",
    create: (transport: typeof fetch) => new EasyProductAdapter(transport),
    projectQuery: "surface=easy&offset=0&limit=5",
    candidateQuery: "offset=0&limit=100&view=summary&phase=pilot",
  },
  {
    name: "Pro",
    create: (transport: typeof fetch) => new LiveWorkbenchAdapter(transport),
    projectQuery: "offset=0&limit=20",
    candidateQuery: "offset=0&limit=20",
  },
];
it("exposes one API error type through both compatibility imports", () => {
  expect(ProApiError).toBe(EasyApiError);
});
describe.each(variants)(
  "$name shared live state",
  ({ create, projectQuery, candidateQuery }) => {
    it("keeps its server projection and publishes live fields when approval revision is unchanged", async () => {
      let current = snapshot();
      current.candidates.total = 1;
      current.project.phase = "pilot";
      const transport = vi.fn(async (input: RequestInfo | URL) =>
        json(String(input).endsWith("/workbench") ? current : page),
      );
      const adapter = create(transport);
      adapters.push(adapter);
      let state: LiveState = await adapter.load();
      adapter.subscribe((event) => {
        state = event.snapshot;
      });
      await adapter.selectProject("p1");
      expect(transport.mock.calls.map(([url]) => url)).toContain(
        `/api/v1/projects?${projectQuery}`,
      );
      expect(transport.mock.calls.map(([url]) => url)).toContain(
        `/api/v1/projects/p1/candidates?${candidateQuery}`,
      );
      current = {
        ...current,
        conversation: [
          { id: "reply-1", kind: "summary", text: "New answer", phase: "site" },
        ],
        capabilities: { ...current.capabilities, resume: false },
      };
      await adapter.refresh();
      expect(state.snapshot?.conversation?.[0].text).toBe("New answer");
      expect(state.snapshot?.capabilities.resume).toBe(false);
    });
    it("reuses the same gate request identity after uncertain failure and prevents concurrent submission", async () => {
      const bodies: Record<string, unknown>[] = [];
      let release: (() => void) | undefined;
      const transport = vi.fn(
        async (input: RequestInfo | URL, init?: RequestInit) => {
          if (init?.method === "POST") {
            const body = JSON.parse(String(init.body));
            bodies.push(body);
            if (bodies.length === 1) {
              await new Promise<void>((resolve) => {
                release = resolve;
              });
              return json(
                { error: { code: "unavailable", message: "Try again" } },
                503,
              );
            }
            return json(request(body.request_id));
          }
          return json(String(input).endsWith("/workbench") ? snapshot() : page);
        },
      );
      const adapter = create(transport);
      adapters.push(adapter);
      await adapter.selectProject("p1");
      const decision = {
        action: "approve" as const,
        selected_option_id: "site-a",
      };
      const first = adapter.decide(decision);
      const rejection = expect(first).rejects.toMatchObject({ status: 503 });
      await adapter.decide(decision);
      expect(bodies).toHaveLength(1);
      release!();
      await rejection;
      await adapter.decide(decision);
      expect(bodies[1]).toEqual(bodies[0]);
      expect(bodies[1]).toMatchObject({
        card_id: "card-1",
        revision: "revision-1",
      });
      await adapter.decide(decision);
      expect(bodies[2].request_id).toBe(bodies[0].request_id);
    });
    it("pauses on 401, preserves command identity and resumes on the same adapter", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
      let expired = true;
      const bodies: Record<string, unknown>[] = [];
      const transport = vi.fn(
        async (input: RequestInfo | URL, init?: RequestInit) => {
          if (init?.method === "POST") {
            const body = JSON.parse(String(init.body));
            bodies.push(body);
            if (expired)
              return json(
                {
                  error: {
                    code: "authentication_required",
                    message: "Sign in",
                  },
                },
                401,
              );
            return json(request(body.request_id));
          }
          return json(String(input).endsWith("/workbench") ? snapshot() : page);
        },
      );
      const adapter = create(transport);
      adapters.push(adapter);
      await adapter.load();
      await adapter.selectProject("p1");
      await expect(adapter.resume()).rejects.toMatchObject({ status: 401 });
      const calls = transport.mock.calls.length;
      await vi.advanceTimersByTimeAsync(120000);
      await adapter.refresh();
      expect(transport).toHaveBeenCalledTimes(calls);
      expired = false;
      adapter.resumePolling();
      await adapter.refresh();
      await adapter.resume();
      expect(bodies[1].request_id).toBe(bodies[0].request_id);
      await adapter.resume();
      expect(bodies[2].request_id).not.toBe(bodies[1].request_id);
    });
    it("serializes slow polling and drops snapshots for a previously selected project", async () => {
      let release: ((response: Response) => void) | undefined;
      const transport = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/p1/workbench"))
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        return json(url.endsWith("/workbench") ? snapshot("p2") : page);
      });
      const adapter = create(transport);
      adapters.push(adapter);
      let state = await adapter.load();
      adapter.subscribe((event) => {
        state = event.snapshot;
      });
      const oldSelection = adapter.selectProject("p1");
      await adapter.selectProject("p2");
      release!(json(snapshot("p1")));
      await oldSelection;
      expect(state.snapshot?.project.id).toBe("p2");
      expect(state.selectedProject).toBe("p2");
      let resolvePoll: ((response: Response) => void) | undefined;
      transport.mockImplementation(
        async () =>
          new Promise<Response>((resolve) => {
            resolvePoll = resolve;
          }),
      );
      const poll = adapter.refresh(),
        joined = adapter.refresh();
      const during = transport.mock.calls.length;
      resolvePoll!(json(snapshot("p2")));
      await Promise.all([poll, joined]);
      expect(transport).toHaveBeenCalledTimes(during);
    });
    it("retains simulated order identity across network uncertainty", async () => {
      const current = { ...snapshot(), lab_order: labOrder() };
      const bodies: Record<string, unknown>[] = [];
      let fail = true;
      const transport = vi.fn(
        async (input: RequestInfo | URL, init?: RequestInit) => {
          if (init?.method === "POST") {
            const body = JSON.parse(String(init.body));
            bodies.push(body);
            if (fail) {
              fail = false;
              throw new TypeError("network unavailable");
            }
            return json({ order: labOrder() });
          }
          return json(String(input).endsWith("/workbench") ? current : page);
        },
      );
      const adapter = create(transport);
      adapters.push(adapter);
      await adapter.selectProject("p1");
      const submit = () =>
        adapter instanceof EasyProductAdapter
          ? adapter.submitLabOrder()
          : adapter.applyLabOrder("submit", undefined, "SIMULATED_ORDER_ONLY");
      await expect(submit()).rejects.toThrow("network unavailable");
      await submit();
      expect(bodies[1]).toEqual(bodies[0]);
      expect(bodies[1]).toMatchObject({
        action: "submit",
        acknowledgement: "SIMULATED_ORDER_ONLY",
        revision: "order-revision",
      });
    });
  },
);
it("Easy typed input encodes a discriminated target and uses the shared command identity", async () => {
  const bodies: Record<string, unknown>[] = [];
  const transport = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        bodies.push(body);
        return json(request(body.request_id));
      }
      return json(String(input).endsWith("/workbench") ? snapshot() : page);
    },
  );
  const adapter = new EasyProductAdapter(transport);
  adapters.push(adapter);
  await adapter.createTypedProject("Target", "Goal", {
    ...emptyInput(),
    type: "protein-name",
    text: " NK2R ",
    species: " human ",
  });
  expect(bodies[0]).toMatchObject({
    surface: "easy",
    title: "Target",
    target_input: { kind: "protein-name", name: "NK2R", organism: "human" },
  });
  expect(bodies[0].request_id).toMatch(/^[a-zA-Z0-9_-]{16,96}$/);
});

describe.each(variants)("$name denied access boundaries", ({ create }) => {
  it.each([403, 404])(
    "clears stale evidence and stops automatic reads on %s while explicit refresh may recover",
    async (status) => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
      let denied = false;
      const transport = vi.fn(async (input: RequestInfo | URL) =>
        denied
          ? json(
              {
                error: {
                  code: status === 404 ? "not_found" : "forbidden",
                  message: "Scope unavailable",
                },
              },
              status,
            )
          : json(String(input).endsWith("/workbench") ? snapshot() : page),
      );
      const adapter = create(transport);
      adapters.push(adapter);
      let state = await adapter.load();
      adapter.subscribe((event) => {
        state = event.snapshot;
      });
      await adapter.selectProject("p1");
      denied = true;
      await adapter.refresh();
      expect(state.connection).toBe("access-denied");
      expect(state.snapshot).toBeNull();
      expect(state.selectedProject).toBeNull();
      expect(state.projects.items).toEqual([]);
      expect(state.candidates.items).toEqual([]);
      const calls = transport.mock.calls.length;
      await vi.advanceTimersByTimeAsync(120000);
      expect(transport).toHaveBeenCalledTimes(calls);
      denied = false;
      await adapter.refresh();
      expect(state.connection).toBe("connected");
    },
  );
  it("a forbidden command retains authorized reads and does not pause their heartbeat", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    const transport = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) =>
        init?.method === "POST"
          ? json(
              {
                error: {
                  code: "team_admin_required",
                  message: "Only team administrators may execute",
                },
              },
              403,
            )
          : json(String(input).endsWith("/workbench") ? snapshot() : page),
    );
    const adapter = create(transport);
    adapters.push(adapter);
    let state = await adapter.load();
    adapter.subscribe((event) => {
      state = event.snapshot;
    });
    await adapter.selectProject("p1");
    await expect(adapter.resume()).rejects.toMatchObject({
      code: "team_admin_required",
      status: 403,
    });
    expect(state.connection).toBe("connected");
    expect(state.snapshot?.project.id).toBe("p1");
    const calls = transport.mock.calls.length;
    await vi.advanceTimersByTimeAsync(12500);
    expect(transport.mock.calls.length).toBeGreaterThan(calls);
  });
  it("cannot start a project after an upload finishes in a disposed workspace", async () => {
    let finish!: (response: Response) => void;
    const transport = vi.fn(
      async () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    const adapter = create(transport);
    adapters.push(adapter);
    const pending = adapter.createProject(
      "Title",
      "Goal",
      new File(["ATOM"], "target.pdb"),
    );
    const rejection = expect(pending).rejects.toThrow();
    adapter.dispose();
    finish(json({ id: "input-id" }));
    await rejection;
    expect(transport).toHaveBeenCalledTimes(1);
  });
});
