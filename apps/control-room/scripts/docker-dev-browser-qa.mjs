import { createRequire } from "node:module";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runViewportAppearanceBrowserQa } from "./lib/viewport-appearance-browser-qa.mjs";
import { startBrowserQaLoopbackProxy } from "./lib/browser-qa-loopback-proxy.mjs";
import { runViewportExportBrowserQa } from "./lib/viewport-export-browser-qa.mjs";
import { runViewportLifecycleBrowserQa } from "./lib/viewport-lifecycle-browser-qa.mjs";
import { installViewportPerformanceProbe } from "./lib/viewport-performance-proof.mjs";
import { runViewportLayoutBrowserQa } from "./lib/viewport-layout-browser-qa.mjs";
import { runViewportQaFixtureBrowser } from "./lib/viewport-qa-fixture-browser.mjs";
import { runViewportCameraBrowserQa } from "./lib/viewport-camera-browser-qa.mjs";

const require = createRequire(import.meta.url);
const playwrightPackage = require("playwright/package.json");
const playwrightRequire = createRequire(require.resolve("playwright/package.json"));
const { PNG } = playwrightRequire("playwright-core/lib/utilsBundle");
const runnerSourcePath = fileURLToPath(import.meta.url);
const appearanceQaSourcePath = fileURLToPath(new URL("./lib/viewport-appearance-browser-qa.mjs", import.meta.url));
const proxySourcePath = fileURLToPath(new URL("./lib/browser-qa-loopback-proxy.mjs", import.meta.url));
const exportSourcePath = fileURLToPath(new URL("./lib/viewport-export-browser-qa.mjs", import.meta.url));
const lifecycleSourcePath = fileURLToPath(new URL("./lib/viewport-lifecycle-browser-qa.mjs", import.meta.url));
const performanceSourcePath = fileURLToPath(new URL("./lib/viewport-performance-proof.mjs", import.meta.url));
const layoutSourcePath = fileURLToPath(new URL("./lib/viewport-layout-browser-qa.mjs", import.meta.url));
const fixtureSourcePath = fileURLToPath(new URL("./lib/viewport-qa-fixture-browser.mjs", import.meta.url));
const scratchSourcePath = fileURLToPath(new URL("./lib/scratch-authoring-browser.mjs", import.meta.url));
const fixtureDataPath = fileURLToPath(new URL("./fixtures/scratch-authoring/fdm.v1.json", import.meta.url));
const cameraSourcePath = fileURLToPath(new URL("./lib/viewport-camera-browser-qa.mjs", import.meta.url));
const expectedVersion = process.env.CONTROL_ROOM_EXPECTED_PLAYWRIGHT_VERSION ?? "1.62.1";
// Leave room for bounded UI restoration and result publication before the
// managed outer runtime deadline expires.
const timeout = Math.min(Number.parseInt(process.env.CONTROL_ROOM_BROWSER_QA_TIMEOUT_MS ?? "180000", 10), 30_000);
const publicUrl = process.env.CONTROL_ROOM_PUBLIC_URL ?? "";
const probeUrl = process.env.CONTROL_ROOM_URL ?? "http://frontend:8080";
const browserGpuMode = process.env.CONTROL_ROOM_BROWSER_GPU_MODE ?? "swiftshader-webgl-requested";
const resultSchema = "fullmag.docker-dev-browser-qa-result.v1";

const pageErrors = [];
const consoleErrors = [];
const requestFailures = [];
const requestCancellations = [];
const resourceResponses = [];
const httpErrors = [];
let harnessSourceHashes = null;
let failurePageState = null;
let browserRoute = null;
let partialProof = {};
const bounded = (value) => String(value).slice(0, 2048);
const collect = (target, value) => {
  if (target.length < 32) target.push(bounded(value));
};

const sha256File = async (path) => createHash("sha256").update(await readFile(path)).digest("hex");
const readHarnessSourceHashes = async () => ({
  runner: await sha256File(runnerSourcePath),
  appearance_helper: await sha256File(appearanceQaSourcePath),
  loopback_proxy: await sha256File(proxySourcePath),
  export_helper: await sha256File(exportSourcePath),
  lifecycle_helper: await sha256File(lifecycleSourcePath),
  performance_helper: await sha256File(performanceSourcePath),
  layout_helper: await sha256File(layoutSourcePath),
  fixture_helper: await sha256File(fixtureSourcePath),
  fixture_builders: await sha256File(scratchSourcePath),
  fixture_data: await sha256File(fixtureDataPath),
  camera_helper: await sha256File(cameraSourcePath),
});
const sameHarnessSourceHashes = (left, right) =>
  Object.keys(left).every((key) => left[key] === right[key]);

const sessionIdentity = async (page) => {
  const endpoint = new URL("/v2/sessions/current/status", page.url()).toString();
  const response = await page.request.get(endpoint, { timeout });
  if (response.status() !== 200) {
    throw new Error(`GET /v2/sessions/current/status returned ${response.status()}`);
  }
  const body = await response.json();
  const session = body?.session;
  const lifecycle = body?.lifecycle;
  for (const key of ["session_id", "session_epoch", "request_scope_epoch"]) {
    if (typeof session?.[key] !== "string" || session[key].trim() === "") {
      throw new Error(`Current status response omitted session.${key}`);
    }
  }
  if (lifecycle?.session_resource !== "active") {
    throw new Error("Current status response did not identify an active session resource");
  }
  return {
    session_id: session.session_id,
    session_epoch: session.session_epoch,
    request_scope_epoch: session.request_scope_epoch,
  };
};

const canvasState = async (page) => page.locator(".fm-viewport-3d canvas").first().evaluate((canvas) => {
  const rect = canvas.getBoundingClientRect();
  const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
  const debugInfo = context?.getExtension("WEBGL_debug_renderer_info");
  return {
    rect: { width: rect.width, height: rect.height },
    width: canvas.width,
    height: canvas.height,
    context_type: context?.constructor?.name ?? null,
    context_lost: context?.isContextLost?.() ?? null,
    drawing_buffer_width: context?.drawingBufferWidth ?? 0,
    drawing_buffer_height: context?.drawingBufferHeight ?? 0,
    preserve_drawing_buffer: context?.getContextAttributes?.().preserveDrawingBuffer ?? null,
    vendor: debugInfo ? context.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : null,
    renderer: debugInfo ? context.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : null,
  };
});

const assertCanvas = async (page, label) => {
  const canvas = page.locator(".fm-viewport-3d canvas");
  await canvas.first().waitFor({ state: "visible", timeout });
  if (await canvas.count() !== 1) throw new Error(`${label}: expected one viewport canvas`);
  const state = await canvasState(page);
  if (state.rect.width <= 0 || state.rect.height <= 0 || state.width <= 0 || state.height <= 0
      || !state.context_type || state.context_lost !== false
      || state.drawing_buffer_width <= 0 || state.drawing_buffer_height <= 0) {
    throw new Error(`${label}: visible WebGL canvas/context/drawing buffer is invalid`);
  }
  return state;
};

const main = async () => {
  if (!publicUrl) throw new Error("CONTROL_ROOM_PUBLIC_URL is required");
  if (playwrightPackage.version !== expectedVersion || expectedVersion !== "1.62.1") {
    throw new Error(`Playwright package ${playwrightPackage.version} does not match ${expectedVersion}`);
  }
  if (typeof PNG?.sync?.read !== "function") {
    throw new Error("Pinned Playwright utilsBundle does not expose PNG.sync.read");
  }
  const sourceHashesBefore = await readHarnessSourceHashes();
  let browser = null;
  let page = null;
  let loopbackProxy = null;
  try {
    loopbackProxy = await startBrowserQaLoopbackProxy(publicUrl, probeUrl);
    browserRoute = { document_origin: loopbackProxy.origin, private_upstream: loopbackProxy.upstream, published_ports: 0 };
    browser = await chromium.launch({
      headless: true,
      args: [
        "--headless=new",
        "--disable-dev-shm-usage",
        "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist",
        "--no-sandbox",
        "--use-angle=swiftshader-webgl",
        "--use-gl=angle",
      ],
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    page = await context.newPage();
    page.setDefaultTimeout(timeout);
    await installViewportPerformanceProbe(page);
    page.on("pageerror", (error) => collect(pageErrors, error));
    page.on("console", (message) => {
      if (message.type() === "error") collect(consoleErrors, message.text());
    });
    page.on("requestfailed", (request) => {
      const error = request.failure()?.errorText ?? "failed";
      const record = `${request.method()} ${request.url()} ${error}`;
      // Resource hooks cancel obsolete GET subscriptions during reload,
      // invalidation and unmount. Keep those observable without treating a
      // client abort as a failed HTTP response or transport connection.
      const resourceCancellation = request.method() === "GET" && error === "net::ERR_ABORTED" &&
        new URL(request.url()).pathname.startsWith("/v2/");
      collect(resourceCancellation ? requestCancellations : requestFailures, record);
    });
    page.on("response", (response) => {
      const url = new URL(response.url());
      if (response.status() >= 400 && httpErrors.length < 32) {
        httpErrors.push({ url: response.url(), status: response.status() });
      }
      if (!url.pathname.startsWith("/v2/") || resourceResponses.length >= 32) return;
      const headers = response.headers();
      resourceResponses.push({ url: response.url(), status: response.status(),
        content_type: headers["content-type"], contract_version: headers["x-fullmag-api-contract-version"] });
    });

    const response = await page.goto(loopbackProxy.origin, { waitUntil: "domcontentloaded", timeout });
    if (!response || response.status() >= 400) throw new Error(`Fullmag DEV returned ${response?.status() ?? "no response"}`);
    if (!new URL(page.url()).pathname.startsWith("/workspace")) throw new Error(`Expected /workspace, got ${page.url()}`);
    const home = page.locator('.fm-home-overlay[data-state="home-overlay"]');
    if (await home.isVisible()) {
      const returnToWorkspace = page.getByRole("button", { name: "Back to simulation", exact: true });
      await returnToWorkspace.click();
      await home.waitFor({ state: "hidden", timeout });
    }
    await page.locator("#fm-main-content.fm-workspace-body").waitFor({ state: "visible", timeout });
    const sessionBefore = await sessionIdentity(page);
    if (process.env.CONTROL_ROOM_PREPARE_VIEWPORT_FIXTURE === "1") {
      partialProof.fixture_preparation = await runViewportQaFixtureBrowser(page, {
        expectedSession: sessionBefore, getSessionIdentity: () => sessionIdentity(page), timeout,
      });
      if (partialProof.fixture_preparation.state !== "ready") {
        throw new Error(`Viewport QA fixture unavailable: ${partialProof.fixture_preparation.reason}`);
      }
    }
    const appearanceQa = await runViewportAppearanceBrowserQa(page, {
      assertCanvas: (label) => assertCanvas(page, label),
      expectedSession: sessionBefore,
      getSessionIdentity: () => sessionIdentity(page),
      pngDecoder: PNG,
      timeout,
    });
    partialProof.viewport_appearance = appearanceQa;
    partialProof.viewport_camera = await runViewportCameraBrowserQa(page, {
      assertCanvas: (label) => assertCanvas(page, label), pngDecoder: PNG, timeout,
    });
    const exportQa = await runViewportExportBrowserQa(page, {
      assertCanvas: (label) => assertCanvas(page, label), pngDecoder: PNG, timeout,
    });
    partialProof.viewport_export = exportQa;
    const layoutQa = await runViewportLayoutBrowserQa(page, {
      assertCanvas: (label) => assertCanvas(page, label), pngDecoder: PNG, timeout, expectedDpr: 1,
    });
    partialProof.viewport_layout_dpr1 = layoutQa;
    const highDprContext = await browser.newContext({
      viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2,
    });
    const originalPage = page;
    try {
      page = await highDprContext.newPage();
      page.setDefaultTimeout(timeout);
      await installViewportPerformanceProbe(page);
      page.on("pageerror", (error) => collect(pageErrors, error));
      page.on("console", (message) => {
        if (message.type() === "error") collect(consoleErrors, message.text());
      });
      page.on("requestfailed", (request) => {
        const error = request.failure()?.errorText ?? "failed";
        const cancelled = request.method() === "GET" && error === "net::ERR_ABORTED" &&
          new URL(request.url()).pathname.startsWith("/v2/");
        collect(cancelled ? requestCancellations : requestFailures,
          `${request.method()} ${request.url()} ${error}`);
      });
      page.on("response", (response) => {
        if (response.status() >= 400 && httpErrors.length < 32) {
          httpErrors.push({ url: response.url(), status: response.status() });
        }
      });
      const dprResponse = await page.goto(loopbackProxy.origin, { waitUntil: "domcontentloaded", timeout });
      if (!dprResponse || dprResponse.status() >= 400) throw new Error("DPR2 workspace navigation failed");
      const dprHome = page.locator('.fm-home-overlay[data-state="home-overlay"]');
      if (await dprHome.isVisible()) {
        await page.getByRole("button", { name: "Back to simulation", exact: true }).click();
        await dprHome.waitFor({ state: "hidden", timeout });
      }
      await page.locator("#fm-main-content.fm-workspace-body").waitFor({ state: "visible", timeout });
      if (JSON.stringify(await sessionIdentity(page)) !== JSON.stringify(sessionBefore)) {
        throw new Error("DPR2 context has a different active session");
      }
      partialProof.viewport_layout_dpr2 = await runViewportLayoutBrowserQa(page, {
        assertCanvas: (label) => assertCanvas(page, label), pngDecoder: PNG, timeout, expectedDpr: 2,
      });
      partialProof.viewport_export_dpr2 = await runViewportExportBrowserQa(page, {
        assertCanvas: (label) => assertCanvas(page, label), pngDecoder: PNG, timeout, expectedCaptureDpr: 2,
      });
    } finally {
      await highDprContext.close();
      page = originalPage;
    }
    const lifecycleQa = await runViewportLifecycleBrowserQa(page, {
      assertCanvas: (label) => assertCanvas(page, label), expectedSession: sessionBefore,
      getSessionIdentity: () => sessionIdentity(page), timeout, cycles: 20,
    });
    partialProof.viewport_lifecycle = lifecycleQa;
    const before = await assertCanvas(page, "before Home");
    const canvasHandle = await page.locator(".fm-viewport-3d canvas").first().elementHandle();
    if (!canvasHandle) throw new Error("before Home: could not retain the workspace canvas element");

    const start = page.getByRole("button", { name: "Start", exact: true });
    await start.waitFor({ state: "visible", timeout });
    await start.click();
    await home.waitFor({ state: "visible", timeout });
    await page.waitForFunction(() => document.querySelector(".fm-home-overlay .fm-start-status")?.textContent?.includes("Simulation open:") === true, null, { timeout });
    const homeText = await home.innerText();
    if (!homeText.includes("Simulation open:")) throw new Error("Home did not show the active session label");

    const back = page.getByRole("button", { name: "Back to simulation", exact: true });
    await back.waitFor({ state: "visible", timeout });
    await back.click();
    await home.waitFor({ state: "hidden", timeout });
    await page.locator("#fm-main-content.fm-workspace-body").waitFor({ state: "visible", timeout });
    const canvasDomStable = await canvasHandle.evaluate((canvas) => canvas === document.querySelector(".fm-viewport-3d canvas") && document.contains(canvas));
    if (!canvasDomStable) throw new Error("Home unmounted or replaced the workspace canvas");
    const after = await assertCanvas(page, "after Home");
    const sessionAfter = await sessionIdentity(page);
    if (JSON.stringify(sessionBefore) !== JSON.stringify(sessionAfter)) throw new Error("Active session identity changed during Home round trip");
    if (pageErrors.length || consoleErrors.length || requestFailures.length || httpErrors.length) {
      throw new Error("Browser flow recorded page, console, transport, or HTTP failures");
    }

    return {
      schema: resultSchema,
      state: "passed",
      public_url: publicUrl,
      probe_url: probeUrl,
      final_url: page.url(),
      playwright_version: playwrightPackage.version,
      browser_gpu_mode: browserGpuMode,
      viewport_appearance: appearanceQa,
      home_round_trip: true,
      home: { section: "home", visible: true, session_label: homeText.match(/Simulation open:[^\n]*/)?.[0] ?? "Simulation open:" },
      session: sessionAfter,
      workspace: { visible: true, canvas_dom_stable: canvasDomStable },
      canvas_before: before,
      canvas_after: after,
      page_errors: pageErrors.length,
      console_errors: consoleErrors.length,
      request_failures: requestFailures.length,
      http_errors: httpErrors,
      request_cancellations: requestCancellations,
      viewport_export: exportQa,
      viewport_lifecycle: lifecycleQa,
      viewport_layout_dpr1: layoutQa,
      viewport_layout_dpr2: partialProof.viewport_layout_dpr2,
      viewport_export_dpr2: partialProof.viewport_export_dpr2,
      fixture_preparation: partialProof.fixture_preparation ?? { state: "not-requested" },
      viewport_camera: partialProof.viewport_camera,
    };
  } catch (error) {
    if (error?.partialProof) partialProof.failed_step = error.partialProof;
    if (page) {
      failurePageState = {
        url: page.url(),
        visible_text: bounded(await page.locator("body").innerText({ timeout: 3000 }).catch(() => "unavailable")),
      };
      try {
        const response = await page.request.get(new URL("/v2/sessions/current/status", page.url()).toString(), { timeout: 3000 });
        const status = await response.json();
        failurePageState.session_probe = { http_status: response.status(), lifecycle: status?.lifecycle, session_identity: status?.session };
      } catch (probeError) {
        failurePageState.session_probe_error = bounded(probeError?.message ?? probeError);
      }
    }
    throw error;
  } finally {
    try {
      await browser?.close();
    } finally {
      if (loopbackProxy) {
        browserRoute.proxy_failures = [...loopbackProxy.failures];
        await loopbackProxy.close();
      }
      const sourceHashesAfter = await readHarnessSourceHashes();
      const unchanged = sameHarnessSourceHashes(sourceHashesBefore, sourceHashesAfter);
      harnessSourceHashes = {
        algorithm: "sha256",
        runner_before: sourceHashesBefore.runner,
        runner_after: sourceHashesAfter.runner,
        appearance_helper_before: sourceHashesBefore.appearance_helper,
        appearance_helper_after: sourceHashesAfter.appearance_helper,
        loopback_proxy_before: sourceHashesBefore.loopback_proxy,
        loopback_proxy_after: sourceHashesAfter.loopback_proxy,
        export_helper_before: sourceHashesBefore.export_helper,
        export_helper_after: sourceHashesAfter.export_helper,
        lifecycle_helper_before: sourceHashesBefore.lifecycle_helper,
        lifecycle_helper_after: sourceHashesAfter.lifecycle_helper,
        performance_helper_before: sourceHashesBefore.performance_helper,
        performance_helper_after: sourceHashesAfter.performance_helper,
        layout_helper_before: sourceHashesBefore.layout_helper,
        layout_helper_after: sourceHashesAfter.layout_helper,
        fixture_helper_before: sourceHashesBefore.fixture_helper,
        fixture_helper_after: sourceHashesAfter.fixture_helper,
        fixture_builders_before: sourceHashesBefore.fixture_builders,
        fixture_builders_after: sourceHashesAfter.fixture_builders,
        fixture_data_before: sourceHashesBefore.fixture_data,
        fixture_data_after: sourceHashesAfter.fixture_data,
        camera_helper_before: sourceHashesBefore.camera_helper,
        camera_helper_after: sourceHashesAfter.camera_helper,
        unchanged,
      };
      if (!unchanged) throw new Error("Browser QA harness source changed during the run");
      if (browserRoute?.proxy_failures?.length) throw new Error("Browser QA loopback proxy reported upstream failures");
    }
  }
};

try {
  const payload = await main();
  payload.harness_source_sha256 = harnessSourceHashes;
  payload.browser_route = browserRoute;
  console.log(JSON.stringify(payload));
} catch (error) {
  console.log(JSON.stringify({
    schema: resultSchema,
    state: "failed",
    public_url: publicUrl,
    probe_url: probeUrl,
    playwright_version: playwrightPackage.version ?? null,
    browser_gpu_mode: browserGpuMode,
    harness_source_sha256: harnessSourceHashes,
    failure_page_state: failurePageState,
    browser_route: browserRoute,
    error: bounded(error?.stack ?? error),
    page_errors: pageErrors,
    console_errors: consoleErrors,
    request_failures: requestFailures,
    resource_responses: resourceResponses,
    http_errors: httpErrors,
    request_cancellations: requestCancellations,
    partial_proof: partialProof,
  }));
  process.exitCode = 1;
}
