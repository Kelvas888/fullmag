import assert from "node:assert/strict";
import { mkdir, writeFile, realpath } from "node:fs/promises";
import { resolve, relative, isAbsolute, sep } from "node:path";
import { chromium } from "playwright";

const target = JSON.parse(process.env.FULLMAG_MANAGED_BROWSER_TARGET ?? "null");
const workspace = new URL(process.env.CONTROL_ROOM_URL);
const reportRoot = resolve(process.env.FULLMAG_ANTENNA_WORKSPACE_REPORT_DIR);
const runRoot = await realpath(process.env.FULLMAG_FRONTEND_SOURCE_RUN_ROOT);
const suffix = relative(runRoot, reportRoot);
assert.ok(suffix && suffix !== ".." && !suffix.startsWith(`..${sep}`) && !isAbsolute(suffix));
assert.equal(workspace.hostname, "127.0.0.1"); assert.equal(workspace.port, "3274");
assert.equal(workspace.searchParams.get("fullmag_api_instance"), target.api_instance);
assert.equal(target.session_storage, "disposable_tmpfs");
assert.match(target.container_id, /^[0-9a-f]{64}$/);
const apiBase = new URL(target.api_base);
assert.equal(apiBase.hostname, "127.0.0.1"); assert.notEqual(apiBase.port, "3197");
await mkdir(reportRoot, { recursive: true });
const checks = [], screenshots = [], pageErrors = [], consoleErrors = [], httpErrors = [], writes = [], websockets = [];
let browser, page, failure = null, scope = null, sessionId = null;
const startedAt = new Date().toISOString();
const headers = () => ({ "x-fullmag-api-instance": target.api_instance, ...(scope ? { "x-fullmag-session-scope": scope } : {}) });
async function json(response) {
  assert.equal(response.headers()["x-fullmag-api-instance"], target.api_instance, "API process identity changed");
  assert.equal(response.headers()["x-api-contract-version"], "1.0.0");
  const body = await response.text();
  assert.ok(response.ok(), `HTTP ${response.status()} ${response.url()}: ${body.slice(0, 1500)}`);
  return JSON.parse(body);
}
try {
  browser = await chromium.launch({ headless: true, channel: process.env.FULLMAG_ANTENNA_WORKSPACE_BROWSER_CHANNEL ?? "chrome" });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  const sessions = await json(await context.request.get(`${target.api_base}/v2/sessions`, { headers: headers() }));
  assert.deepEqual(sessions.sessions, [], "Do not replace an existing API session");
  const created = await json(await context.request.post(`${target.api_base}/v2/sessions`, {
    headers: headers(), data: { name: "Managed antenna workspace authoring", backend: "fem", device: "cpu", precision: "double", replace_current: false },
  }));
  sessionId = created.session_id; assert.ok(sessionId);
  const status = await json(await context.request.get(`${target.api_base}/v2/sessions/current/status`, { headers: headers() }));
  assert.equal(status.session.session_id, sessionId);
  const owner = status.session;
  for (const key of ["session_id", "session_epoch", "request_scope_epoch"]) assert.ok(owner[key]?.trim());
  scope = `session=${encodeURIComponent(owner.session_id)}&epoch=${encodeURIComponent(owner.session_epoch)}&request_scope_epoch=${encodeURIComponent(owner.request_scope_epoch)}`;
  const scene = () => context.request.get(`${target.api_base}/v2/sessions/current/model/scene`, { headers: headers() }).then(json);
  const waitScene = async (predicate) => {
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) { const current = await scene(); if (predicate(current)) return current; await new Promise(done => setTimeout(done, 250)); }
    throw new Error("Authoritative scene did not confirm the UI transaction");
  };
  checks.push({ name: "fresh receipt-attested API creates its own FEM CPU session without replacement", passed: true });
  page = await context.newPage(); page.setDefaultTimeout(30_000);
  page.on("pageerror", error => pageErrors.push(error.message));
  page.on("console", message => { if (message.type() === "error" && !message.text().startsWith("Failed to load resource:")) consoleErrors.push(message.text()); });
  page.on("websocket", socket => websockets.push(socket.url()));
  page.on("response", response => { if (response.status() >= 400) httpErrors.push({ status: response.status(), url: response.url() }); });
  page.on("request", request => {
    if (request.url().startsWith(target.api_base) && !["GET", "OPTIONS"].includes(request.method())) writes.push({ method: request.method(), path: new URL(request.url()).pathname, body: request.postDataJSON(), instance: request.headers()["x-fullmag-api-instance"], scope: request.headers()["x-fullmag-session-scope"] });
  });
  const screenshot = async name => { const path = resolve(reportRoot, `${name}.png`); await page.screenshot({ path, fullPage: true }); screenshots.push(path); };
  await page.goto(workspace.href, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.getByText("Managed antenna workspace authoring", { exact: true }).first().waitFor();
  await page.locator('[data-node-id="model:objects"]').waitFor({ state: "visible" });
  await page.getByRole("button", { name: /command search/i }).first().click();
  await page.getByPlaceholder("Search commands").fill("Add Microstrip Antenna");
  await page.getByRole("option").filter({ hasText: "Add Microstrip Antenna" }).first().click();
  const authored = await waitScene(s => s.objects?.some(o => o.role === "antenna"));
  const objects = authored.objects.filter(o => o.role === "antenna"); assert.equal(objects.length, 1);
  const object = objects[0], objectId = object.id;
  const stages = authored.antenna_field_solve_stages.filter(s => s.source_object_id === objectId); assert.equal(stages.length, 1);
  const stage = stages[0];
  checks.push({ name: "public command creates microstrip, current transport, observation port and field definition through real API", passed: true });
  await page.getByTitle("Expand All").click();
  const selectNode = async id => { const node = page.locator(`[data-node-id="${id}"]`); await node.waitFor({ state: "visible" }); await node.click(); };
  await selectNode(`model:object:${objectId}:antenna:terminals`);
  const terminals = page.locator('[data-inspector-owner="object.antenna.terminals"]');
  await terminals.getByRole("combobox", { name: "Terminal preparation port" }).waitFor();
  assert.equal(await terminals.getByTestId("antenna-terminal-source").count(), 0);
  checks.push({ name: "legacy microstrip keeps the explicit inspection preparation form", passed: true });
  await selectNode(`model:object:${objectId}:geometry`);
  const geometry = page.locator('[data-inspector-owner="object.antenna.geometry"]');
  await geometry.getByRole("checkbox", { name: "Full 3D conducting circuit", exact: true }).check();
  for (const end of ["inlet", "outlet"]) {
    for (const [name, value] of [["length", "1e-7"], ["width", "5e-8"], ["center v", "0"], ["part ID", `${end}_bridge`], ["conductivity", "58000000"]]) {
      await geometry.getByRole("textbox", { name: `${end} bridge ${name}`, exact: true }).fill(value);
    }
  }
  await geometry.getByRole("textbox", { name: "Inlet source-cut potential jump", exact: true }).fill("0.25");
  await screenshot("01-circuit-draft");
  const save = geometry.getByRole("button", { name: "Save conductor authoring", exact: true });
  assert.equal(await save.isEnabled(), true, await geometry.innerText()); await save.click();
  const closed = await waitScene(s => s.objects.find(o => o.id === objectId)?.geometry?.geometry_params?.loop?.enabled === true);
  const current = closed.current_transports.find(c => c.name === stage.current_transport_id);
  assert.equal(current.structured_current_closure.kind, "closed_geometry");
  assert.equal(current.structured_current_closure.source_cuts[0].drive.potential_jump_V, 0.25);
  assert.equal(current.materials.length, 4);
  assert.equal(closed.antenna_port_modes.find(p => p.source_object_id === objectId).schema_version, "antenna_port_mode.v3");
  await geometry.getByText("Conductor authoring committed.", { exact: false }).waitFor();
  await screenshot("02-circuit-committed");
  checks.push({ name: "Geometry commits both physical bridges, voltage cut, four materials and v3 port atomically", passed: true });
  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:terminals`);
  const source = terminals.getByTestId("antenna-terminal-source");
  await source.getByText("Authored voltage source", { exact: true }).waitFor();
  const sourceText = await source.innerText();
  for (const expected of ["0.25", "V⁺ − V⁻", "Coordinate frame", "object", "Inlet observation", "Outlet observation"]) assert.ok(sourceText.includes(expected), expected);
  assert.equal(await terminals.getByRole("combobox", { name: "Terminal preparation port" }).count(), 0);
  assert.equal(await terminals.getByRole("button", { name: "Apply inspection preparation" }).count(), 0);
  await screenshot("04-explicit-source-and-observations");
  const writesBeforeNavigation = writes.length;
  await source.getByRole("button", { name: "Open Geometry", exact: true }).click();
  await geometry.waitFor();
  await selectNode(`model:object:${objectId}:antenna:terminals`);
  const port = closed.antenna_port_modes.find(p => p.source_object_id === objectId);
  const openPort = source.getByRole("button", { name: `Open port ${port.id}`, exact: true });
  assert.equal(await openPort.isEnabled(), true, await source.innerText());
  await openPort.scrollIntoViewIfNeeded();
  await screenshot("05-port-observations");
  await openPort.click();
  await page.getByText("Port terminal pairs", { exact: true }).waitFor();
  assert.equal(writes.length, writesBeforeNavigation, "Source navigation must not mutate the scene");
  checks.push({ name: "closed circuit presents its voltage source and observations with scoped read-only Geometry/Port navigation", passed: true });
  await selectNode(`model:object:${objectId}:antenna:conductor`);
  const materialEditor = page.getByTestId("antenna-conductor-material-editor");
  const conductivity = materialEditor.getByRole("textbox", { name: "Layout conductor conductivity", exact: true });
  await conductivity.waitFor();
  const beforeConductivityWrites = writes.length;
  await conductivity.fill("0");
  assert.equal(await materialEditor.getByRole("button", { name: "Apply conductivity", exact: true }).isEnabled(), false);
  assert.equal(writes.length, beforeConductivityWrites);
  await conductivity.fill("41000000");
  await materialEditor.getByRole("textbox", { name: "Inlet bridge conductivity", exact: true }).fill("32000000");
  await materialEditor.getByRole("textbox", { name: "Outlet bridge conductivity", exact: true }).fill("27000000");
  await conductivity.focus();
  await page.evaluate(() => {
    const root = document.querySelector('[data-testid="antenna-conductor-material-editor"]'), input = document.activeElement;
    const scroll = root.closest(".fm-inspector__body");
    const controls = [...root.querySelectorAll("input")].map(element => ({ element, disabled: element.disabled, opacity: getComputedStyle(element).opacity }));
    const proof = { root, input, scroll, scrollTop: scroll.scrollTop, controls, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 };
    const sample = () => {
      proof.samples++;
      if (document.querySelector('[data-testid="antenna-conductor-material-editor"]') !== root) proof.rootChanges++;
      for (const saved of controls) {
        if (!saved.element.isConnected) proof.controlChanges++;
        if (saved.element.disabled !== saved.disabled) proof.disabledChanges++;
        if (getComputedStyle(saved.element).opacity !== saved.opacity) proof.opacityChanges++;
      }
      proof.opacityAnimations += root.getAnimations({ subtree: true }).filter(animation => (animation.playState === "running" || animation.pending) && animation.effect?.getKeyframes().some(frame => "opacity" in frame)).length;
    };
    const observer = new MutationObserver(sample); observer.observe(root, { attributes: true, childList: true, subtree: true });
    sample(); window.__antennaConductivityProof = { proof, observer, sample };
  });
  assert.equal(await materialEditor.getByRole("button", { name: "Apply conductivity", exact: true }).isEnabled(), true);
  // DOM activation exercises the actual Apply handler without moving the input focus under inspection.
  await materialEditor.getByRole("button", { name: "Apply conductivity", exact: true }).evaluate(button => button.click());
  const materialScene = await waitScene(s => s.objects.find(o => o.id === objectId)?.geometry?.geometry_params?.conductivity_s_per_m === 41000000);
  await materialEditor.getByText("Conductivity committed to geometry and charge materials.", { exact: false }).waitFor();
  const materialTransport = materialScene.current_transports.find(c => c.name === stage.current_transport_id);
  const params = materialScene.objects.find(o => o.id === objectId).geometry.geometry_params;
  assert.equal(params.loop.inlet_connection_conductivity_s_per_m, 32000000);
  assert.equal(params.loop.outlet_connection_conductivity_s_per_m, 27000000);
  for (const assignment of materialTransport.materials) assert.equal(assignment.material.sigma_Spm,
    assignment.region.region_id === params.loop.inlet_connection_part_id ? 32000000 : assignment.region.region_id === params.loop.outlet_connection_part_id ? 27000000 : 41000000);
  assert.deepEqual(materialTransport.structured_current_closure, current.structured_current_closure);
  assert.deepEqual(materialTransport.solver, current.solver);
  assert.deepEqual(materialScene.antenna_port_modes, closed.antenna_port_modes);
  assert.equal(writes.length, beforeConductivityWrites + 1);
  const stability = await page.evaluate(() => {
    const { proof, observer, sample } = window.__antennaConductivityProof; sample(); observer.disconnect();
    return { root: proof.root.isConnected, focus: document.activeElement === proof.input, scroll: proof.scroll.scrollTop === proof.scrollTop,
      rootChanges: proof.rootChanges, controlChanges: proof.controlChanges, disabledChanges: proof.disabledChanges, opacityChanges: proof.opacityChanges, opacityAnimations: proof.opacityAnimations, samples: proof.samples };
  });
  assert.ok(stability.samples > 1 && stability.samples < 100);
  assert.deepEqual({ ...stability, samples: 0 }, { root: true, focus: true, scroll: true, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 });
  await screenshot("06-conductor-conductivity-committed");
  checks.push({ name: "Conductor atomically updates layout and charge conductivity while preserving source, solver, port, focus, scroll and input stability", passed: true, stability });

  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:solution:${encodeURIComponent(stage.id)}`);
  const add = page.getByRole("button", { name: "Add Field Solve to Study", exact: true });
  await add.waitFor(); assert.equal(await add.isEnabled(), true); await add.click();
  const open = page.getByRole("button", { name: "Open Study stage", exact: true });
  await open.waitFor(); assert.equal(await open.isEnabled(), true); await open.click();
  await page.getByText("Antenna Definition Reference", { exact: true }).waitFor();
  await screenshot("03-real-study-stage");
  const queued = await scene();
  const flat = queued.study?.stages ?? [];
  const visit = nodes => (nodes ?? []).flatMap(node => [node, ...visit(node.children)]);
  const pipeline = visit(queued.study?.study_pipeline?.nodes);
  const references = [...flat.filter(s => s.kind === "antenna_field_solve" && s.stage_id === stage.id), ...pipeline.filter(n => n.stage_kind === "antenna_field_solve" && n.payload?.stage_id === stage.id)];
  assert.equal(references.length, 1);
  checks.push({ name: "Add and Open Field Solve reaches the actual Study inspector with one canonical definition reference", passed: true });
  const webgl = await page.locator("canvas").evaluateAll(canvases => canvases.map(canvas => {
    const bounds = canvas.getBoundingClientRect(); if (!bounds.width || !bounds.height) return null;
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    return gl ? { lost: gl.isContextLost(), width: gl.drawingBufferWidth, height: gl.drawingBufferHeight } : null;
  }).filter(Boolean));
  assert.ok(webgl.some(gl => !gl.lost && gl.width > 0 && gl.height > 0)); assert.ok(webgl.every(gl => !gl.lost));
  assert.ok(websockets.some(url => url.startsWith(target.api_base.replace("http:", "ws:"))), "Realtime must use the admitted API");
  assert.ok(writes.length >= 3 && writes.length <= 10);
  for (const write of writes) { assert.equal(write.instance, target.api_instance); assert.equal(write.scope, scope); assert.ok(!write.path.includes("/simulation/"), "Authoring smoke must not execute a solver"); }
  assert.deepEqual(pageErrors, []); assert.deepEqual(consoleErrors, []);
  assert.deepEqual(httpErrors.filter(error => error.status >= 500), []);
  checks.push({ name: "real workspace has healthy WebGL, correctly routed realtime and scoped writes without solver execution", passed: true, webgl });
} catch (error) {
  failure = error.stack ?? String(error);
  if (page) { try { const path = resolve(reportRoot, "failure.png"); await page.screenshot({ path, fullPage: true }); screenshots.push(path); await writeFile(resolve(reportRoot, "failure-dom.txt"), await page.locator("body").innerText()); } catch { /* Preserve original failure. */ } }
} finally { if (browser) await browser.close(); }
const report = { schema: "fullmag.antenna-workspace-authoring.v1", state: failure ? "failed" : "passed", qualification: "real_api_workspace_authoring_only_not_solve_science_or_durability", startedAt, finishedAt: new Date().toISOString(), target, sessionId, checks, screenshots, writes, websockets, pageErrors, consoleErrors, httpErrors, error: failure };
await writeFile(resolve(reportRoot, "antenna-workspace-authoring.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ state: report.state, checks: checks.length, error: failure }));
process.exitCode = failure ? 1 : 0;