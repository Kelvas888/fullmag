import assert from "node:assert/strict";
import { mkdir, realpath, writeFile } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";

const url = process.env.CONTROL_ROOM_URL ?? "http://127.0.0.1:3265/antenna-source-spectrum";
const storage = process.env.FULLMAG_PROJECT_STORAGE_ROOT;
const output = process.env.FULLMAG_ANTENNA_SOURCE_SPECTRUM_REPORT_DIR;
if (!storage || !output || !isAbsolute(storage) || !isAbsolute(output)) throw new Error("Managed absolute storage/report paths are required");
const inside = (root, path) => { const suffix = relative(root, path); return Boolean(suffix) && suffix !== ".." && !suffix.startsWith(`..${sep}`) && !isAbsolute(suffix); };
const directory = resolve(output), realStorage = await realpath(storage);
if (!inside(resolve(storage), directory) || !inside(realStorage, await realpath(dirname(directory)))) throw new Error("Report must remain inside managed storage");
await mkdir(directory, { recursive: true });
if (!inside(realStorage, await realpath(directory))) throw new Error("Report escaped storage");
const reportPath = resolve(process.env.FULLMAG_ANTENNA_SOURCE_SPECTRUM_REPORT ?? resolve(directory, "antenna-source-spectrum.json"));
if (!inside(directory, reportPath)) throw new Error("Report file escaped directory");
const checks = [], screenshots = [], evidence = [], pageErrors = [], consoleErrors = [];
let browser, page, failure = null;
const startedAt = new Date().toISOString();
try {
  let playwright;
  try { playwright = await import("playwright"); } catch { playwright = await import("@playwright/test"); }
  const channel = process.env.FULLMAG_ANTENNA_SOURCE_SPECTRUM_BROWSER_CHANNEL;
  if (channel && !["chrome", "msedge"].includes(channel)) throw new Error("Unsupported managed channel");
  browser = await playwright.chromium.launch({ headless: true, ...(channel ? { channel } : {}) });
  page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  for (const scenario of ["ready", "foreign-digest", "foreign-request", "foreign-catalog", "missing-catalog", "invalid-authoring"]) {
    const location = new URL(url); location.searchParams.set("scenario", scenario);
    await page.goto(location.href, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForFunction(() => window.__antennaSpectrumFixture?.read().calls.some((call) => call.path.endsWith("/output-catalog")) && window.__antennaSpectrumFixture.read().calls.some((call) => call.path.endsWith("/source-spectra/fft")), undefined, { timeout: 60_000 });
    await page.waitForTimeout(500);
    if (scenario === "ready") await page.getByRole("grid").waitFor({ timeout: 60_000 });
    const before = await page.evaluate(() => window.__antennaSpectrumFixture.read());
    const sectionCount = await page.locator('section[aria-label="Antenna source spectrum payload"]').count();
    const payloads = before.calls.filter((call) => call.path.includes("/payloads/"));
    const text = await page.locator("main").textContent();
    const passed = scenario === "ready" ? payloads.length === 4 && sectionCount === 1 && await page.getByRole("gridcell").count() === 4 : payloads.length === 0 && sectionCount === 0;
    checks.push({ name: `${scenario}: ${scenario === "ready" ? "matched metadata renders four scoped carriers" : "refuses binary reads and payload view"}`, passed, payloadRequests: payloads.length, sectionCount });
    const screenshot = resolve(directory, `${scenario}.png`); await page.screenshot({ path: screenshot, fullPage: true }); screenshots.push(screenshot);
    await page.waitForTimeout(300);
    const after = await page.evaluate(() => window.__antennaSpectrumFixture.read());
    assert.equal(after.calls.length, before.calls.length, `${scenario} polls while settled`);
    assert.deepEqual(before.unexpected, []);
    assert.ok(before.calls.length <= 15);
    assert.ok(payloads.every((call) => Boolean(call.scope)), "Binary reads must be scoped");
    if (scenario === "invalid-authoring") assert.ok(text.includes("transverse spectrum requires equilibrium_ref"), "Negative fixture did not reach authoring validation");
    evidence.push({ ...before, panelText: text });
  }
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(consoleErrors, []);
  assert.ok(checks.every((check) => check.passed), "Unconfirmed or invalid source FFT mounted/read binary payloads");
} catch (error) {
  failure = error instanceof Error ? error.message : String(error);
  if (page) { try { const path = resolve(directory, "failure.png"); await page.screenshot({ path, fullPage: true }); screenshots.push(path); } catch { /* Preserve original failure. */ } }
} finally {
  if (browser) { try { await browser.close(); } catch (error) { failure = `${failure ?? ""}; cleanup: ${String(error)}`; } }
}
const report = { schema: "fullmag_antenna_source_spectrum_browser_fixture_v1", state: failure ? "failed" : "passed", qualification: "fixture_only_not_backend_runtime_or_science", actual_backend_runtime: false, production_hooks: true, unit_tests: "not_compiled_not_run", started_at: startedAt, finished_at: new Date().toISOString(), checks, screenshots, evidence, page_errors: pageErrors, console_errors: consoleErrors, error: failure };
await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({ report: reportPath, state: report.state, checks: checks.length, error: failure }));
process.exitCode = failure ? 1 : 0;
