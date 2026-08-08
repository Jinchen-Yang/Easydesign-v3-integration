const { test, expect } = require("@playwright/test");
const { spawn, spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const WEB_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "..", "..");
const FIXTURE_ROOT = path.join(WEB_ROOT, ".tmp-fixtures");
const PYTHON = process.env.EASYDESIGN_CORE_PYTHON || "python3";
const SERVERS = [];
const URLS = {
  sequence: "http://127.0.0.1:18131/",
  pse: "http://127.0.0.1:18132/",
};
const REAL_REPORTS = {
  sequence: process.env.EASYDESIGN_APOE_SEQUENCE_REPORT || "",
  pse: process.env.EASYDESIGN_APOE_PSE_REPORT || "",
};
const REAL_URLS = {
  sequence: "http://127.0.0.1:18133/",
  pse: "http://127.0.0.1:18134/",
};
const REAL_PSE_FIRST_RESIDUE = REAL_REPORTS.pse
  ? JSON.parse(
      fs.readFileSync(path.join(path.resolve(REAL_REPORTS.pse), "viewer-data.json"), "utf-8")
    ).residues[0]
  : null;

async function waitForServer(url) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch (_) {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Viewer server did not start: ${url}`);
}

function startServer(report, port, overlay = "", evidence = "") {
  const serverArgs = [
    path.join(__dirname, "serve_fixture.py"),
    report,
    "--port",
    String(port),
  ];
  if (overlay) serverArgs.push("--overlay", overlay);
  if (evidence) serverArgs.push("--evidence", evidence);
  const child = spawn(
    PYTHON,
    serverArgs,
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: path.join(REPO_ROOT, "src"),
      },
      stdio: ["ignore", "pipe", "pipe"],
    }
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  child.on("exit", (code) => {
    if (code && code !== 0) {
      process.stderr.write(`Target Viewer server exited ${code}: ${stderr}\n`);
    }
  });
  SERVERS.push(child);
}

test.beforeAll(async () => {
  const generated = spawnSync(
    PYTHON,
    [path.join(__dirname, "create_fixtures.py"), FIXTURE_ROOT],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONPATH: path.join(REPO_ROOT, "src"),
      },
      encoding: "utf-8",
    }
  );
  if (generated.status !== 0) {
    throw new Error(`Fixture generation failed:\n${generated.stderr}`);
  }
  startServer(
    path.join(FIXTURE_ROOT, "sequence"),
    18131,
    path.join(FIXTURE_ROOT, "sequence", "stage02-test-overlay.json"),
    path.join(FIXTURE_ROOT, "sequence", "evidence-test-overlay.json")
  );
  startServer(path.join(FIXTURE_ROOT, "pse"), 18132);
  const expectedServers = [waitForServer(URLS.sequence), waitForServer(URLS.pse)];
  if (REAL_REPORTS.sequence) {
    startServer(path.resolve(REAL_REPORTS.sequence), 18133);
    expectedServers.push(waitForServer(REAL_URLS.sequence));
  }
  if (REAL_REPORTS.pse) {
    startServer(path.resolve(REAL_REPORTS.pse), 18134);
    expectedServers.push(waitForServer(REAL_URLS.pse));
  }
  await Promise.all(expectedServers);
});

test.afterAll(() => {
  for (const child of SERVERS) child.kill("SIGTERM");
});

async function openViewer(page, url) {
  const pageErrors = [];
  const remoteRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const parsed = new URL(request.url());
    if (parsed.protocol.startsWith("http") && parsed.hostname !== "127.0.0.1") {
      remoteRequests.push(request.url());
    }
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__EASYDESIGN_VIEWER_READY__ === true);
  return { pageErrors, remoteRequests };
}

test("predicted report loads Mol*, mapping controls and local downloads", async ({
  page,
}) => {
  const diagnostics = await openViewer(page, URLS.sequence);

  await expect(page.locator("#load-state")).toHaveText("已就绪");
  await expect(page.locator("#molstar-viewer canvas")).toBeVisible();
  await expect(page.locator("#molstar-viewer")).toHaveCSS("touch-action", "none");
  await expect(page.locator("#molstar-viewer canvas")).toHaveCSS(
    "touch-action",
    "none"
  );
  await expect(
    page.locator('#molstar-viewer [style*="touch-action"]').first()
  ).toHaveCSS("touch-action", "none");
  await expect(page.locator("#pse-controls")).toBeHidden();
  await expect(page.locator("#target-summary")).toContainText("predicted");
  await expect(page.locator("#provenance-metrics")).toContainText("609");
  await expect(page.locator("#downloads a")).toHaveCount(3);
  for (const link of await page.locator("#downloads a").all()) {
    await expect(link).toHaveAttribute("href", /^data\//);
  }
  await page.locator('.msp-sequence-wrapper span[data-seqid="0"]').click();
  await expect(page.locator("#selected-residue")).toContainText("A · sequence 1");
  await expect(page.locator("#selected-residue")).toContainText("label: A:1");
  await expect(page.locator("#selected-residue")).toContainText("author: A:1");

  await page.locator("#representation-surface").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.representation === "surface" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await expect(page.locator("#representation-surface")).toHaveClass(/active/);
  await page.locator("#representation-stick").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.representation === "stick" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await page.locator("#center-structure").click();

  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});

test("Stage 2 methods and approved regions are read-only fixed-color layers", async ({
  page,
}) => {
  const diagnostics = await openViewer(page, URLS.sequence);

  await expect(page.locator("#stage02-controls")).toBeVisible();
  await expect(page.locator("#stage02-methods button")).toHaveCount(3);
  await expect(page.locator("#stage02-methods")).toContainText("SASA surface diversity");
  await expect(page.locator("#stage02-methods")).toContainText("ScanNet epitope no-MSA");
  await expect(page.locator("#stage02-methods")).toContainText("Approved hotspots");
  await expect(page.locator("#stage02-controls")).toContainText("A");
  await expect(page.locator("#stage02-controls")).toContainText("B");
  await expect(page.locator("#stage02-controls")).toContainText("C");
  await page.locator("#theme-region-scannet").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.theme === "region:scannet" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await page.locator("#theme-region-approved").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.theme === "region:approved" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await expect(
    page.locator("button", { hasText: /^(编辑|上传|批准|提交)(区域|结果|文件)?$/ })
  ).toHaveCount(0);

  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});

test("pilot representatives and final selections are read-only evidence structures", async ({
  page,
}) => {
  const diagnostics = await openViewer(page, URLS.sequence);

  await expect(page.locator("#evidence-controls")).toBeVisible();
  await expect(page.locator("#evidence-structures button")).toHaveCount(3);
  await expect(page.locator("#evidence-structures")).toContainText("Pilot · fixture-strategy");
  await expect(page.locator("#evidence-structures")).toContainText("Final primary #1");
  await page.locator("#evidence-0").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.structureUrl.includes("pilot-fixture") &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await page.locator("#evidence-1").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.structureUrl.includes("final-fixture") &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await expect(
    page.locator("button", { hasText: /^(编辑|上传|批准|提交)(区域|结果|文件)?$/ })
  ).toHaveCount(0);
  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});

test("PSE report toggles complete uninterpreted source colors", async ({ page }) => {
  const diagnostics = await openViewer(page, URLS.pse);

  await expect(page.locator("#pse-controls")).toBeVisible();
  await expect(page.locator("#pse-controls")).toContainText("uninterpreted annotation");
  await expect(page.locator("#pse-color-counts .color-chip")).toHaveCount(4);
  await page.locator("#theme-pse").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.theme === "pse" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  await expect(page.locator("#theme-pse")).toHaveClass(/active/);
  await page.locator("#theme-default").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.theme === "default" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );

  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});

test("WebGL failure is explicit instead of a false success", async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
      if (kind === "webgl" || kind === "webgl2" || kind === "experimental-webgl") {
        return null;
      }
      return original.call(this, kind, ...args);
    };
  });
  await page.goto(URLS.sequence, { waitUntil: "domcontentloaded" });

  await expect(page.locator("#viewer-error")).toBeVisible();
  await expect(page.locator("#load-state")).toHaveText("加载失败");
  await expect(page.locator("#viewer-error-message")).not.toBeEmpty();
});

test("real copied APOE Protenix report opens independently", async ({ page }) => {
  test.skip(!REAL_REPORTS.sequence, "未提供真实 APOE sequence report");
  const diagnostics = await openViewer(page, REAL_URLS.sequence);

  await expect(page.locator("#target-summary")).toContainText("143 aa · predicted");
  await expect(page.locator("#provenance-metrics")).toContainText("609");
  await expect(page.locator("#pse-controls")).toBeHidden();
  await page.locator('.msp-sequence-wrapper span[data-seqid="0"]').click();
  await expect(page.locator("#selected-residue")).toContainText("label: A:1");
  await expect(page.locator("#selected-residue")).toContainText("author: A:1");
  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});

test("real copied APOE PSE report preserves label/auth mapping and colors", async ({
  page,
}) => {
  test.skip(!REAL_REPORTS.pse, "未提供真实 APOE PSE report");
  const diagnostics = await openViewer(page, REAL_URLS.pse);

  await expect(page.locator("#target-summary")).toContainText("138 aa · imported");
  await expect(page.locator("#pse-controls")).toBeVisible();
  await expect(page.locator("#pse-color-counts .color-chip")).toHaveCount(4);
  await page.locator('.msp-sequence-wrapper span[data-seqid="0"]').click();
  await expect(page.locator("#selected-residue")).toContainText(
    `label: ${REAL_PSE_FIRST_RESIDUE.label_asym_id}:${REAL_PSE_FIRST_RESIDUE.label_seq_id}`
  );
  await expect(page.locator("#selected-residue")).toContainText(
    `author: ${REAL_PSE_FIRST_RESIDUE.auth_asym_id}:${REAL_PSE_FIRST_RESIDUE.auth_seq_id}`
  );
  await page.locator("#theme-pse").click();
  await page.waitForFunction(
    () =>
      window.__EASYDESIGN_VIEWER_STATE__.theme === "pse" &&
      window.__EASYDESIGN_VIEWER_STATE__.loading === false
  );
  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.remoteRequests).toEqual([]);
});
