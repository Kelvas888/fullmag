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
const checks = [], screenshots = [], pageErrors = [], consoleErrors = [], httpErrors = [], writes = [], visualizationAcks = [], websockets = [];
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
    if (request.url().startsWith(target.api_base) && !["GET", "OPTIONS"].includes(request.method())) {
      const record = { method: request.method(), path: new URL(request.url()).pathname, body: request.postDataJSON(), instance: request.headers()["x-fullmag-api-instance"], scope: request.headers()["x-fullmag-session-scope"] };
      if (record.path === "/v2/sessions/current/visualization/client-acks") visualizationAcks.push(record);
      else writes.push(record);
    }
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
  const beforeMeshWrites = writes.length;
  const meshNode = page.locator(`[data-node-id="model:object:${objectId}:mesh"]`);
  await meshNode.waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Open Mesh Policy", exact: true }).click();
  const meshPolicy = page.locator('[data-mesh-policy-draft="object"]');
  await meshPolicy.getByRole("checkbox", { name: "Use object policy", exact: true }).waitFor();
  assert.equal(writes.length, beforeMeshWrites, "Opening mesh policy must not build or write");
  await meshPolicy.getByRole("checkbox", { name: "Use object policy", exact: true }).check();
  const maximumSize = meshPolicy.getByRole("textbox", { name: "Maximum element size", exact: true });
  await maximumSize.fill("2e-8");
  await maximumSize.focus();
  await page.evaluate(() => {
    const root = document.querySelector('[data-mesh-policy-draft="object"]'), input = document.activeElement, scroll = root.closest(".fm-inspector__body");
    const controls = [...root.querySelectorAll("input")].map(element => ({ element, disabled: element.disabled, opacity: getComputedStyle(element).opacity }));
    const proof = { root, input, scroll, scrollTop: scroll.scrollTop, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 };
    const sample = () => {
      proof.samples++;
      if (document.querySelector('[data-mesh-policy-draft="object"]') !== root) proof.rootChanges++;
      for (const saved of controls) {
        if (!saved.element.isConnected) proof.controlChanges++;
        if (saved.element.disabled !== saved.disabled) proof.disabledChanges++;
        if (getComputedStyle(saved.element).opacity !== saved.opacity) proof.opacityChanges++;
      }
      proof.opacityAnimations += root.getAnimations({ subtree: true }).filter(animation => (animation.playState === "running" || animation.pending) && animation.effect?.getKeyframes().some(frame => "opacity" in frame)).length;
    };
    const observer = new MutationObserver(sample); observer.observe(root, { attributes: true, childList: true, subtree: true });
    sample(); window.__antennaMeshPolicyProof = { proof, observer, sample };
  });
  const applyPolicy = meshPolicy.getByRole("button", { name: "Apply Policy", exact: true });
  assert.equal(await applyPolicy.isEnabled(), true, await meshPolicy.innerText());
  await applyPolicy.evaluate(button => button.click());
  await meshPolicy.getByText("Policy saved. Current solver mesh is stale until a mesh build completes.", { exact: true }).waitFor();
  const meshScene = await waitScene(s => s.objects.find(o => o.id === objectId)?.object_mesh?.maximum_element_size === "2e-8");
  const meshWrites = writes.slice(beforeMeshWrites);
  assert.equal(meshWrites.length, 1); assert.equal(meshWrites[0].method, "PUT");
  assert.ok(meshWrites[0].path.includes(encodeURIComponent(objectId)));
  const policyRead = await json(await context.request.get(`${target.api_base}${meshWrites[0].path}`, { headers: headers() }));
  assert.equal(policyRead.object_id, objectId); assert.equal(policyRead.config.maximum_element_size, "2e-8"); assert.equal(policyRead.config.mode, "custom");
  assert.deepEqual(meshScene.current_transports, materialScene.current_transports);
  assert.deepEqual(meshScene.antenna_port_modes, materialScene.antenna_port_modes);
  const meshObject = meshScene.objects.find(o => o.id === objectId), beforeMeshObject = materialScene.objects.find(o => o.id === objectId);
  assert.deepEqual(meshObject.geometry, beforeMeshObject.geometry); assert.deepEqual(meshObject.transform, beforeMeshObject.transform);
  assert.equal(meshObject.magnetization_ref ?? null, beforeMeshObject.magnetization_ref ?? null);
  const meshStability = await page.evaluate(() => {
    const { proof, observer, sample } = window.__antennaMeshPolicyProof; sample(); observer.disconnect();
    return { root: proof.root.isConnected, focus: document.activeElement === proof.input, scroll: proof.scroll.scrollTop === proof.scrollTop,
      rootChanges: proof.rootChanges, controlChanges: proof.controlChanges, disabledChanges: proof.disabledChanges, opacityChanges: proof.opacityChanges, opacityAnimations: proof.opacityAnimations, samples: proof.samples };
  });
  assert.ok(meshStability.samples > 1 && meshStability.samples < 100);
  assert.deepEqual({ ...meshStability, samples: 0 }, { root: true, focus: true, scroll: true, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 });
  for (const label of ["Report state", "Quality state"]) {
    await meshPolicy.getByText(label, { exact: true }).locator("..").getByText("not published", { exact: true }).waitFor();
  }
  await screenshot("07-antenna-object-mesh-policy");
  await selectNode(`model:object:${objectId}:antenna:conductor`);
  await page.locator('[data-inspector-owner="object.antenna.conductor"]').getByText("authored", { exact: true }).waitFor();
  await selectNode(`model:object:${objectId}:mesh`);
  await meshPolicy.getByRole("checkbox", { name: "Use object policy", exact: true }).waitFor();
  assert.equal(await maximumSize.inputValue(), "2e-8");
  checks.push({ name: "Antenna Mesh node and Conductor link use the canonical object policy, save 20 nm without building, and retain source physics and Inspector stability", passed: true, stability: meshStability });


  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:solution:${encodeURIComponent(stage.id)}`);
  const beforeProjection = await scene(), beforeProjectionWrites = writes.length;
  const composer = page.getByTestId("antenna-projection-composer");
  const projectionTarget = composer.getByRole("combobox", { name: "Projection target", exact: true });
  await page.getByRole("combobox", { name: "Field-sampling domain", exact: true }).selectOption(JSON.stringify(["object", objectId]));
  await selectNode(`model:object:${objectId}:geometry`);
  const dirtyGuard = page.getByRole("dialog", { name: "Unapplied Inspector changes" });
  await dirtyGuard.waitFor();
  assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), true);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  await projectionTarget.selectOption(JSON.stringify(["global"]));
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor();
  assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), false);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Revert field-solve settings", exact: true }).click();
  assert.equal(writes.length, beforeProjectionWrites);
  checks.push({ name: "A clean projection form cannot hide dirty sampling; two dirty forms block aggregate Apply and retain separate drafts without writes", passed: true });

  assert.equal(await composer.getByRole("combobox", { name: "Run stage", exact: true }).count(), 0);
  await projectionTarget.focus();
  await page.evaluate(() => {
    const root = document.querySelector('[data-testid="antenna-projection-composer"]'), input = document.activeElement, scroll = root.closest(".fm-inspector__body");
    const controls = [...root.querySelectorAll("input, select")].map(element => ({ element, disabled: element.disabled, opacity: getComputedStyle(element).opacity }));
    const proof = { root, input, scroll, top: scroll.scrollTop, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 };
    const sample = () => {
      proof.samples++;
      if (document.querySelector('[data-testid="antenna-projection-composer"]') !== root) proof.rootChanges++;
      for (const saved of controls) {
        if (!saved.element.isConnected) proof.controlChanges++;
        if (saved.element.disabled !== saved.disabled) proof.disabledChanges++;
        if (getComputedStyle(saved.element).opacity !== saved.opacity) proof.opacityChanges++;
      }
      proof.opacityAnimations += root.getAnimations({ subtree: true }).filter(animation => (animation.playState === "running" || animation.pending) && animation.effect?.getKeyframes().some(frame => "opacity" in frame)).length;
    };
    const observer = new MutationObserver(sample); observer.observe(root, { attributes: true, childList: true, subtree: true }); sample();
    window.__projectionProof = { proof, observer, sample };
  });
  await composer.getByRole("button", { name: "Create projection", exact: true }).evaluate(button => button.click());
  await composer.getByText("Projection committed without a drive or Run stage.", { exact: false }).waitFor();
  const projected = await waitScene(s => s.antenna_target_projections?.length === (beforeProjection.antenna_target_projections?.length ?? 0) + 1);
  assert.deepEqual(projected.solved_antenna_drives, beforeProjection.solved_antenna_drives);
  assert.deepEqual(projected.study, beforeProjection.study);
  assert.deepEqual(projected.current_transports, beforeProjection.current_transports);
  assert.deepEqual(projected.antenna_field_solve_stages, beforeProjection.antenna_field_solve_stages);
  const projection = projected.antenna_target_projections.at(-1);
  assert.deepEqual(projection.target, { kind: "global" });
  assert.equal(projection.solution.stage_id, stage.id);
  assert.equal(writes.length, beforeProjectionWrites + 1);
  assert.deepEqual(Object.keys(writes.at(-1).body.merge_patch), ["antenna_target_projections"]);
  assert.equal(await composer.getByRole("button", { name: "Create projection", exact: true }).isEnabled(), false);
  const projectionStable = await page.evaluate(() => {
    const { proof: p, observer, sample } = window.__projectionProof; sample(); observer.disconnect();
    return { root: document.querySelector('[data-testid="antenna-projection-composer"]') === p.root, focus: document.activeElement === p.input, scroll: p.scroll.scrollTop === p.top, rootChanges: p.rootChanges, controlChanges: p.controlChanges, disabledChanges: p.disabledChanges, opacityChanges: p.opacityChanges, opacityAnimations: p.opacityAnimations, samples: p.samples };
  });
  assert.ok(projectionStable.samples > 1 && projectionStable.samples < 100);
  assert.deepEqual({ ...projectionStable, samples: 0 }, { root: true, focus: true, scroll: true, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 });
  await screenshot("08-independent-projection");
  checks.push({ name: "Projection-only creation uses one scoped real transaction, retains Inspector identity and focus, preserves physics and adds no Run or drive", passed: true, stability: projectionStable });
  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:projection:${encodeURIComponent(projection.id)}`);
  const projectionEditor = page;
  await projectionEditor.getByRole("combobox", { name: "Target", exact: true }).selectOption(JSON.stringify(["object", objectId]));
  await projectionEditor.getByRole("button", { name: "Apply projection", exact: true }).click();
  const rebound = await waitScene(s => s.antenna_target_projections?.find(p => p.id === projection.id)?.target?.object_id === objectId);
  assert.deepEqual(rebound.antenna_target_projections.find(p => p.id === projection.id).solution, projection.solution);
  await projectionEditor.getByText("Resource committed.", { exact: false }).waitFor();
  const removeProjection = projectionEditor.getByRole("button", { name: "Remove projection (no cascade)", exact: true });
  await removeProjection.click();
  const removedProjection = await waitScene(s => !s.antenna_target_projections?.some(p => p.id === projection.id));
  assert.deepEqual(removedProjection.antenna_field_solve_stages, beforeProjection.antenna_field_solve_stages);
  assert.deepEqual(removedProjection.solved_antenna_drives, beforeProjection.solved_antenna_drives);
  assert.equal(writes.length, beforeProjectionWrites + 3);
  checks.push({ name: "Existing typed projection inspector edits the target while preserving source pins and removes the declaration without cascading", passed: true });
  await selectNode(`model:object:${objectId}:antenna:solution:${encodeURIComponent(stage.id)}`);
  const beforeFFT = await scene(), beforeFFTWrites = writes.length;
  const fftComposer = page.getByTestId("antenna-spectrum-composer");
  await fftComposer.getByRole("combobox", { name: "FFT target object", exact: true }).selectOption(objectId);
  for (const [name, value] of [["Plane origin", "0 0 0"], ["Axis u", "1 0 0"], ["Axis v", "1 0 0"], ["Extent u", "2e-7"], ["Extent v", "1e-7"], ["Samples u", "16"], ["Samples v", "8"]]) {
    await fftComposer.getByRole("textbox", { name, exact: true }).fill(value);
  }
  await fftComposer.getByRole("combobox", { name: "Window", exact: true }).selectOption("hann");
  const createFFT = fftComposer.getByRole("button", { name: "Create source FFT request", exact: true });
  assert.equal(await createFFT.isEnabled(), false);
  await fftComposer.getByText("Sampling axes must be orthonormal unit vectors.", { exact: true }).waitFor();
  await fftComposer.getByRole("textbox", { name: "Axis v", exact: true }).fill("0 1 0");
  await fftComposer.getByRole("textbox", { name: "Samples u", exact: true }).fill("10000000");
  assert.equal(await createFFT.isEnabled(), false);
  await fftComposer.getByText("FFT grid exceeds the runtime limit of 10000000 samples.", { exact: true }).waitFor();
  await fftComposer.getByRole("textbox", { name: "Samples u", exact: true }).fill("16");
  assert.equal(await createFFT.isEnabled(), true); assert.equal(writes.length, beforeFFTWrites);
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor(); assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), true);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByTestId("antenna-projection-composer").getByRole("combobox", { name: "Projection target", exact: true }).selectOption(JSON.stringify(["global"]));
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor(); assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), false);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Discard projection draft", exact: true }).click();
  assert.equal(await fftComposer.getByRole("textbox", { name: "Samples u", exact: true }).inputValue(), "16");
  const fftSamples = fftComposer.getByRole("textbox", { name: "Samples v", exact: true });
  await fftSamples.focus();
  await page.evaluate(() => {
    const root = document.querySelector('[data-testid="antenna-spectrum-composer"]'), input = document.activeElement, scroll = root.closest(".fm-inspector__body");
    const controls = [...root.querySelectorAll("input, select")].map(element => ({ element, disabled: element.disabled, opacity: getComputedStyle(element).opacity }));
    const proof = { root, input, scroll, top: scroll.scrollTop, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 };
    const sample = () => {
      proof.samples++;
      if (document.querySelector('[data-testid="antenna-spectrum-composer"]') !== root) proof.rootChanges++;
      for (const saved of controls) {
        if (!saved.element.isConnected) proof.controlChanges++;
        if (saved.element.disabled !== saved.disabled) proof.disabledChanges++;
        if (getComputedStyle(saved.element).opacity !== saved.opacity) proof.opacityChanges++;
      }
      proof.opacityAnimations += root.getAnimations({ subtree: true }).filter(animation => (animation.playState === "running" || animation.pending) && animation.effect?.getKeyframes().some(frame => "opacity" in frame)).length;
    };
    const observer = new MutationObserver(sample); observer.observe(root, { attributes: true, childList: true, subtree: true }); sample(); window.__fftProof = { proof, observer, sample };
  });
  await createFFT.evaluate(button => button.click());
  await fftComposer.getByText("Source FFT request committed. No spectrum was computed;", { exact: false }).waitFor();
  const fftScene = await waitScene(s => s.antenna_spectrum_requests?.length === (beforeFFT.antenna_spectrum_requests?.length ?? 0) + 1);
  const fft = fftScene.antenna_spectrum_requests.at(-1);
  assert.equal(fft.solution_ref.stage_id, stage.id); assert.equal(fft.port_mode_id, stage.port_mode_ids[0]); assert.equal(fft.target.object_id, objectId);
  assert.equal(fft.transform, "spatial_fft"); assert.equal(fft.window, "hann"); assert.equal(fft.normalization, "integral_si");
  assert.deepEqual(fft.sampling_plane.origin_m, [0, 0, 0]); assert.deepEqual(fft.sampling_plane.axis_u, [1, 0, 0]); assert.deepEqual(fft.sampling_plane.axis_v, [0, 1, 0]);
  assert.equal(fft.sampling_plane.sample_count_u, 16); assert.equal(fft.sampling_plane.sample_count_v, 8); assert.equal(fft.sampling_plane.extent_u_m, 2e-7);
  for (const collection of ["antenna_field_solve_stages", "antenna_port_modes", "current_transports", "solved_antenna_drives", "study"]) assert.deepEqual(fftScene[collection], beforeFFT[collection]);
  assert.deepEqual(Object.keys(writes.at(-1).body.merge_patch), ["antenna_spectrum_requests"]); assert.equal(writes.length, beforeFFTWrites + 1);
  assert.equal(await createFFT.isEnabled(), false);
  const fftStable = await page.evaluate(() => {
    const { proof: p, observer, sample } = window.__fftProof; sample(); observer.disconnect();
    return { root: document.querySelector('[data-testid="antenna-spectrum-composer"]') === p.root, focus: document.activeElement === p.input, scroll: p.scroll.scrollTop === p.top, rootChanges: p.rootChanges, controlChanges: p.controlChanges, disabledChanges: p.disabledChanges, opacityChanges: p.opacityChanges, opacityAnimations: p.opacityAnimations, samples: p.samples };
  });
  assert.ok(fftStable.samples > 1 && fftStable.samples < 100);
  assert.deepEqual({ ...fftStable, samples: 0 }, { root: true, focus: true, scroll: true, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 });
  await screenshot("09-source-fft-request");
  checks.push({ name: "FFT validates axes and native budget before writes, shares the draft guard, and saves one canonical request with stable focus, scroll and controls", passed: true, stability: fftStable });
  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:spectrum:${encodeURIComponent(fft.id)}`);
  await page.getByRole("combobox", { name: "Window", exact: true }).selectOption("blackman");
  await page.getByRole("button", { name: "Apply spectrum", exact: true }).click();
  const editedFFT = await waitScene(s => s.antenna_spectrum_requests?.find(r => r.id === fft.id)?.window === "blackman");
  assert.deepEqual(editedFFT.antenna_spectrum_requests.find(r => r.id === fft.id).solution_ref, fft.solution_ref);
  await page.getByText("Resource committed.", { exact: false }).waitFor();
  await page.getByRole("button", { name: "Remove spectrum (no cascade)", exact: true }).click();
  const removedFFT = await waitScene(s => !s.antenna_spectrum_requests?.some(r => r.id === fft.id));
  assert.deepEqual(removedFFT.antenna_field_solve_stages, beforeFFT.antenna_field_solve_stages);
  assert.equal(writes.length, beforeFFTWrites + 3);
  checks.push({ name: "Existing spectrum inspector edits the request without rebinding its source and removes it without cascading or running analysis", passed: true });
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
  const beforeReceiver = await scene();
  async function publicCommand(title) {
    await page.getByRole("button", { name: /command search/i }).first().click();
    await page.getByPlaceholder("Search commands").fill(title);
    await page.getByRole("option").filter({ hasText: title }).first().click();
  }
  await publicCommand("Add Box");
  await page.getByText("Primitive Geometry", { exact: true }).first().waitFor();
  for (const [name, value] of [["Name", "Antenna drive receiver"], ["Region", "antenna-drive-receiver"], ["Size X", "1e-7"], ["Size Y", "2e-7"], ["Size Z", "1e-8"], ["Translation Z", "1e-7"]]) {
    await page.getByRole("textbox", { name, exact: true }).fill(value);
  }
  await page.getByRole("button", { name: "Apply Draft", exact: true }).click();
  const withReceiver = await waitScene(s => s.objects.length === beforeReceiver.objects.length + 1);
  const receiver = withReceiver.objects.find(o => !beforeReceiver.objects.some(old => old.id === o.id));
  assert.ok(receiver?.id && receiver.id !== objectId);
  await page.locator(`[data-node-id="model:object:${receiver.id}"]`).waitFor({ state: "visible" });
  await publicCommand("Add Run Stage");
  const withRun = await waitScene(s => s.study?.stages?.some(item => item.kind === "run"));
  const runInstructions = withRun.study.stages.filter(item => item.kind === "run"); assert.equal(runInstructions.length, 1);
  // The pipeline editor is read-only. Seed its canonical representation through
  // the public transaction API while retaining the real UI-authored payloads.
  const pipelineNodes = withRun.study.stages.map((payload, index) => ({ id: `activation-node-${index + 1}`, label: `${payload.kind} ${index + 1}`, node_kind: "primitive", stage_kind: payload.kind, enabled: true, payload }));
  const runNode = pipelineNodes.find(node => node.stage_kind === "run");
  assert.notEqual(runNode.id, runNode.payload.stage_id);
  const pipelineRequest = { base_revision: withRun.revision, kind: "merge_patch", merge_patch: { study: { study_pipeline: { version: "study_pipeline.v1", nodes: pipelineNodes } } } };
  await json(await context.request.post(`${target.api_base}/v2/sessions/current/model/transactions`, { headers: headers(), data: pipelineRequest }));
  writes.push({ method: "POST", path: "/v2/sessions/current/model/transactions", body: pipelineRequest, instance: target.api_instance, scope, source: "public_api_pipeline_setup" });
  const pipelineScene = await waitScene(s => s.study?.study_pipeline?.nodes?.some(node => node.id === runNode.id));
  assert.deepEqual(pipelineScene.study.stages, withRun.study.stages, "Dormant flat instructions remain intact");
  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:solution:${encodeURIComponent(stage.id)}`);
  const driveComposer = page.getByTestId("antenna-projection-composer");
  await driveComposer.getByRole("combobox", { name: "Projection composition", exact: true }).selectOption("drive");
  await driveComposer.getByRole("combobox", { name: "Projection target", exact: true }).selectOption(JSON.stringify(["object", receiver.id]));
  const runChoice = driveComposer.getByRole("combobox", { name: "Run stage", exact: true });
  await runChoice.selectOption(runNode.id);
  const runOptions = await runChoice.locator("option").evaluateAll(options => options.map(option => option.value).filter(Boolean));
  assert.deepEqual(runOptions, [runNode.id]); assert.ok(!runOptions.includes(runNode.payload.stage_id));
  await driveComposer.getByRole("textbox", { name: "Peak current", exact: true }).fill("0.01");
  await driveComposer.getByRole("textbox", { name: "Frequency", exact: true }).fill("1e9");
  const beforeDrive = await scene(), beforeDriveWrites = writes.length;
  await driveComposer.getByRole("button", { name: "Create projection and drive", exact: true }).click();
  await driveComposer.getByText("Projection and drive committed.", { exact: false }).waitFor();
  const driven = await waitScene(s => (s.solved_antenna_drives?.length ?? 0) === (beforeDrive.solved_antenna_drives?.length ?? 0) + 1);
  const drive = driven.solved_antenna_drives.at(-1);
  assert.deepEqual(drive.activation, { kind: "stage_ids", stage_ids: [runNode.id] });
  assert.equal(drive.peak_current_a, 0.01); assert.equal(drive.time_origin, "stage_local");
  assert.deepEqual(drive.waveform, { kind: "sinusoidal", frequency_hz: 1e9, phase_rad: 0, offset: 0 });
  assert.equal(driven.antenna_target_projections.find(p => p.id === drive.projection_ref)?.target?.object_id, receiver.id);
  assert.equal(drive.port_mode_id, stage.port_mode_ids[0]);
  assert.deepEqual(driven.study, beforeDrive.study); assert.deepEqual(driven.current_transports, beforeDrive.current_transports);
  assert.equal(writes.length, beforeDriveWrites + 1);
  assert.deepEqual(Object.keys(writes.at(-1).body.merge_patch).sort(), ["antenna_target_projections", "solved_antenna_drives"]);
  await screenshot("10-pipeline-drive-composition");
  await page.getByTitle("Expand All").click();
  await selectNode(`model:object:${objectId}:antenna:drive:${encodeURIComponent(drive.id)}`);
  const activation = page.getByRole("checkbox", { name: `Run ${runNode.id}`, exact: true });
  await activation.waitFor(); assert.equal(await activation.isChecked(), true);
  assert.equal(await page.getByRole("textbox", { name: "Stage IDs", exact: true }).inputValue(), runNode.id);
  await screenshot("11-pipeline-drive-inspector");
  checks.push({ name: "Real UI-authored receiver and Run, represented by the public pipeline API, bind one atomic antenna drive to the executable queue ID and display it in the existing drive editor", passed: true, setup: "receiver and flat Run via UI; pipeline representation via public API; composition and inspection via UI", queueId: runNode.id, definitionId: runNode.payload.stage_id });
  const driveEditor = page.getByTestId("antenna-drive-editor"), currentPreview = page.getByTestId("antenna-drive-preview");
  const drivePeak = driveEditor.getByRole("textbox", { name: "Peak current", exact: true });
  const driveSave = driveEditor.getByRole("button", { name: "Save drive", exact: true });
  assert.equal(await driveSave.isEnabled(), false, "A clean drive must not submit another transaction");
  const beforeDriveEditWrites = writes.length;
  await driveEditor.getByRole("textbox", { name: "Frequency", exact: true }).fill("0");
  assert.equal(await driveSave.isEnabled(), false);
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor();
  assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), false);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(await driveEditor.getByRole("textbox", { name: "Frequency", exact: true }).inputValue(), "0");
  await driveEditor.getByRole("textbox", { name: "Frequency", exact: true }).fill("1e9");
  await drivePeak.fill("-0.02");
  await driveEditor.getByRole("textbox", { name: "Phase", exact: true }).fill(String(Math.PI / 2));
  await driveEditor.getByRole("textbox", { name: "Offset", exact: true }).fill("0.5");
  await driveEditor.getByRole("combobox", { name: "Time origin", exact: true }).selectOption("absolute");
  await currentPreview.getByRole("textbox", { name: "Preview to", exact: true }).fill("1e-5");
  await currentPreview.getByRole("alert").filter({ hasText: "Reduce the preview time range" }).last().waitFor();
  await currentPreview.getByRole("textbox", { name: "Preview to", exact: true }).fill("2e-9");
  const previewCursor = currentPreview.getByRole("slider", { name: "Preview sample", exact: true });
  await previewCursor.focus(); await previewCursor.press("Home");
  await currentPreview.getByText("-3.000000e-2 A", { exact: true }).waitFor();
  const previewImage = currentPreview.getByRole("img", { name: /Authored antenna current I/ });
  await previewImage.waitFor();
  const chartCanvas = currentPreview.locator("canvas");
  await chartCanvas.waitFor(); assert.equal(await chartCanvas.isVisible(), true);
  const chartDimensions = await chartCanvas.evaluate(canvas => ({ width: canvas.width, height: canvas.height }));
  assert.ok(chartDimensions.width > 0 && chartDimensions.height > 0);
  await screenshot("12-authored-current-preview");
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor();
  assert.equal(await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).isEnabled(), true);
  await dirtyGuard.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(writes.length, beforeDriveEditWrites, "Preview and cancelled navigation are read-only");
  checks.push({ name: "Drive guard preserves invalid and valid drafts on cancelled navigation; bounded I(t) preview exposes SI units, signed phase/offset current, keyboard cursor and a real chart canvas", passed: true, chartDimensions });
  await drivePeak.focus();
  await page.evaluate(() => {
    const root = document.querySelector('[data-testid="antenna-drive-editor"]'), input = document.activeElement, scroll = root.closest(".fm-inspector__body");
    const controls = [...root.querySelectorAll("input, select")].map(element => ({ element, disabled: element.disabled, opacity: getComputedStyle(element).opacity }));
    const proof = { root, input, scroll, top: scroll.scrollTop, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 };
    const sample = () => {
      proof.samples++;
      if (document.querySelector('[data-testid="antenna-drive-editor"]') !== root) proof.rootChanges++;
      for (const saved of controls) {
        if (!saved.element.isConnected) proof.controlChanges++;
        if (saved.element.disabled !== saved.disabled) proof.disabledChanges++;
        if (getComputedStyle(saved.element).opacity !== saved.opacity) proof.opacityChanges++;
      }
      proof.opacityAnimations += root.getAnimations({ subtree: true }).filter(animation => (animation.playState === "running" || animation.pending) && animation.effect?.getKeyframes().some(frame => "opacity" in frame)).length;
    };
    const observer = new MutationObserver(sample); observer.observe(root, { attributes: true, childList: true, subtree: true }); sample(); window.__driveProof = { proof, observer, sample };
  });
  await driveSave.evaluate(button => button.click());
  const editedDriveScene = await waitScene(s => s.solved_antenna_drives.find(item => item.id === drive.id)?.time_origin === "absolute");
  await driveEditor.getByText("Antenna drive committed.", { exact: true }).waitFor();
  const editedDrive = editedDriveScene.solved_antenna_drives.find(item => item.id === drive.id);
  assert.equal(editedDrive.peak_current_a, -0.02); assert.equal(editedDrive.waveform.phase_rad, Math.PI / 2); assert.equal(editedDrive.waveform.offset, 0.5);
  assert.equal(editedDrive.projection_ref, drive.projection_ref); assert.equal(editedDrive.port_mode_id, drive.port_mode_id);
  assert.deepEqual(editedDrive.activation, drive.activation); assert.deepEqual(editedDriveScene.study, driven.study);
  assert.equal(writes.length, beforeDriveEditWrites + 1);
  assert.equal(await driveSave.isEnabled(), false);
  const driveStability = await page.evaluate(() => {
    const { proof, observer, sample } = window.__driveProof; sample(); observer.disconnect();
    return { root: proof.root.isConnected, focus: document.activeElement === proof.input, scroll: proof.scroll.scrollTop === proof.top,
      rootChanges: proof.rootChanges, controlChanges: proof.controlChanges, disabledChanges: proof.disabledChanges, opacityChanges: proof.opacityChanges, opacityAnimations: proof.opacityAnimations, samples: proof.samples };
  });
  assert.ok(driveStability.samples > 1 && driveStability.samples < 200);
  assert.deepEqual({ ...driveStability, samples: 0 }, { root: true, focus: true, scroll: true, rootChanges: 0, controlChanges: 0, disabledChanges: 0, opacityChanges: 0, opacityAnimations: 0, samples: 0 });
  await drivePeak.fill("0.7");
  await driveEditor.getByRole("button", { name: "Reset drive", exact: true }).click();
  assert.equal(await drivePeak.inputValue(), "-0.02"); assert.equal(writes.length, beforeDriveEditWrites + 1);
  await currentPreview.scrollIntoViewIfNeeded(); await screenshot("13-current-preview-committed");
  checks.push({ name: "Drive edits persist signed current and absolute clock through one real API transaction while preserving bindings, root, focus, scroll and unrelated controls; Reset remains local", passed: true, stability: driveStability });
  await driveEditor.getByRole("combobox", { name: "Time origin", exact: true }).selectOption("stage_local");
  await selectNode(`model:object:${objectId}:geometry`);
  await dirtyGuard.waitFor();
  await dirtyGuard.getByRole("button", { name: "Apply and continue", exact: true }).click();
  await geometry.waitFor();
  const appliedDrive = await waitScene(s => s.solved_antenna_drives.find(item => item.id === drive.id)?.time_origin === "stage_local");
  assert.equal(appliedDrive.solved_antenna_drives.find(item => item.id === drive.id).peak_current_a, -0.02);
  assert.equal(writes.length, beforeDriveEditWrites + 2);
  checks.push({ name: "Global Apply and continue awaits the real drive ACK and transitions only after the draft is clean", passed: true });
  const webgl = await page.locator("canvas").evaluateAll(canvases => canvases.map(canvas => {
    const bounds = canvas.getBoundingClientRect(); if (!bounds.width || !bounds.height) return null;
    const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    return gl ? { lost: gl.isContextLost(), width: gl.drawingBufferWidth, height: gl.drawingBufferHeight } : null;
  }).filter(Boolean));
  assert.ok(webgl.some(gl => !gl.lost && gl.width > 0 && gl.height > 0)); assert.ok(webgl.every(gl => !gl.lost));
  assert.ok(websockets.some(url => url.startsWith(target.api_base.replace("http:", "ws:"))), "Realtime must use the admitted API");
  assert.ok(writes.length >= 3 && writes.length <= 19);
  for (const write of [...writes, ...visualizationAcks]) { assert.equal(write.instance, target.api_instance); assert.equal(write.scope, scope); assert.ok(!write.path.includes("/simulation/"), "Authoring smoke must not execute a solver"); }
  assert.ok(Date.now() - Date.parse(startedAt) > 5000, "The scenario must outlive the adoption timeout");
  assert.deepEqual(visualizationAcks.filter(ack => ack.body.status === "failed"), [], "No nonexistent-buffer adoption may fail during empty/nonmagnetic authoring");
  checks.push({ name: "Empty and nonmagnetic antenna authoring outlives the adoption timeout without a fabricated failed data ACK", passed: true, visualizationAcks });
  assert.deepEqual(pageErrors, []); assert.deepEqual(consoleErrors, []);
  assert.deepEqual(httpErrors.filter(error => error.status >= 500), []);
  checks.push({ name: "real workspace has healthy WebGL, correctly routed realtime and scoped writes without solver execution", passed: true, webgl });
} catch (error) {
  failure = error.stack ?? String(error);
  if (page) { try { const path = resolve(reportRoot, "failure.png"); await page.screenshot({ path, fullPage: true }); screenshots.push(path); await writeFile(resolve(reportRoot, "failure-dom.txt"), await page.locator("body").innerText()); } catch { /* Preserve original failure. */ } }
} finally { if (browser) await browser.close(); }
const report = { schema: "fullmag.antenna-workspace-authoring.v1", state: failure ? "failed" : "passed", qualification: "real_api_workspace_authoring_only_not_solve_science_or_durability", startedAt, finishedAt: new Date().toISOString(), target, sessionId, checks, screenshots, writes, visualizationAcks, websockets, pageErrors, consoleErrors, httpErrors, error: failure };
await writeFile(resolve(reportRoot, "antenna-workspace-authoring.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ state: report.state, checks: checks.length, error: failure }));
process.exitCode = failure ? 1 : 0;