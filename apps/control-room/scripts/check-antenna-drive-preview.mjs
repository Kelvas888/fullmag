import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const root = new URL("../src/", import.meta.url), cache = new Map();
async function load(url) {
  const key = url.href;
  if (cache.has(key)) return cache.get(key);
  const sourceModule = new vm.SourceTextModule(stripTypeScriptTypes(readFileSync(url, "utf8")));
  cache.set(key, sourceModule);
  await sourceModule.link(name => load(name.startsWith("@/") ? new URL(`${name.slice(2)}.ts`, root) : new URL(`${name}.ts`, url)));
  await sourceModule.evaluate(); return sourceModule;
}
const base = "modules/inspector/panels/antenna/";
const model = (await load(process.argv[2] ? pathToFileURL(resolve(process.argv[2])) : new URL(`${base}SolvedAntennaDriveEditorModel.ts`, root))).namespace;
const preview = (await load(new URL(`${base}AntennaDrivePreviewModel.ts`, root))).namespace;
const drive = { id: "drive", name: "Drive", projection_ref: "projection", port_mode_id: "port", peak_current_a: 0.01,
  waveform: { kind: "sinusoidal", frequency_hz: 1e9, phase_rad: 0, offset: 0 }, time_origin: "stage_local", activation: { kind: "stage_ids", stage_ids: ["run"] } };
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);
let checks = 0;
const check = (name, run) => { run(); checks++; console.log(`PASS ${name}`); };
check("time origin survives draft and authored update", () => { const draft = { ...model.solvedDriveDraft(drive), timeOrigin: "absolute" }; assert.equal(model.buildSolvedDrive(drive, draft).time_origin, "absolute"); });
check("unknown clock is rejected", () => assert.throws(() => model.buildSolvedDrive(drive, { ...model.solvedDriveDraft(drive), timeOrigin: "guess" }), /time origin/));
check("zero current remains a valid disabled drive", () => close(model.buildSolvedDrive(drive, { ...model.solvedDriveDraft(drive), peakCurrentA: "0" }).peak_current_a, 0));
check("signed current is not converted to RMS", () => { const points = preview.sampleAntennaDrive({ ...drive, peak_current_a: -0.01 }, 0, 1e-9); close(points.find(p => p.x === 2.5e-10).y, -0.01); });
check("phase and offset use the shared waveform convention", () => close(preview.sampleAntennaDrive({ ...drive, waveform: { ...drive.waveform, phase_rad: Math.PI / 2, offset: 0.5 } }, 0, 1e-9)[0].y, 0.015));
check("constant current is constant", () => assert.ok(preview.sampleAntennaDrive({ ...drive, waveform: { kind: "constant" } }, 0, 1e-9).every(p => p.y === 0.01)));
check("narrow pulse keeps both exact one-sided boundaries", () => {
  const pulse = { ...drive, waveform: { kind: "pulse", t_on: 1e-12, t_off: 1.01e-12 } };
  const points = preview.sampleAntennaDrive(pulse, 0, 1e-9);
  assert.equal(JSON.stringify(points.filter(p => p.x === 1e-12).map(p => p.y)), "[0,0.01]");
  assert.equal(JSON.stringify(points.filter(p => p.x === 1.01e-12).map(p => p.y)), "[0.01,0]");
  assert.ok(points.every((p,i) => i === 0 || p.x >= points[i-1].x));
});
check("piecewise knots and clamped end values are preserved", () => {
  const points = preview.sampleAntennaDrive({ ...drive, waveform: { kind: "piecewise_linear", points: [[1e-10, 2], [1.001e-10, -3], [2e-10, 0]] } }, 0, 1e-9);
  close(points[0].y, 0.02); close(points.find(p => p.x === 1.001e-10).y, -0.03); close(points.at(-1).y, 0);
});
check("sinc center and its amplitude remain authored", () => { const w = { kind: "sinc_pulse", cutoff_hz: 1e9, t0: 2e-10, amplitude: 3 }; const points = preview.sampleAntennaDrive({ ...drive, waveform: w }, 0, 1e-9); close(points.find(p => p.x === w.t0).y, 0.03); });
for (const [name, from, to] of [["blank interval", 0, 0], ["reversed interval", 1, 0], ["infinite interval", 0, Infinity], ["overflowing interval", -1e308, 1e308]]) check(name, () => assert.throws(() => preview.sampleAntennaDrive(drive, from, to), /range/));
check("oversized frequency range is rejected instead of aliased", () => assert.throws(() => preview.sampleAntennaDrive(drive, 0, 100e-9), /16 oscillations/));
check("sample budget is explicit and enforced", () => assert.ok(preview.sampleAntennaDrive(drive, 0, 16e-9).length <= preview.MAX_DRIVE_PREVIEW_POINTS));
check("too many piecewise knots do not get silently truncated", () => assert.throws(() => preview.sampleAntennaDrive({ ...drive, waveform: { kind: "piecewise_linear", points: Array.from({length:513},(_,i)=>[i,1]) } }, 0, 512), /512 authored knots/));
check("overflowing current is rejected", () => assert.throws(() => preview.sampleAntennaDrive({ ...drive, peak_current_a: 1e308, waveform: { kind: "sinusoidal", frequency_hz: 1e9, phase_rad: Math.PI / 2, offset: 10 } }, 0, 1e-9), /overflow/));
check("ACK cannot change the projection binding", () => assert.throws(() => model.resolveCommittedSolvedDriveScene({ scene_revision: 2, committed_scene: { revision: 2, scene: { id: "scene" }, solved_antenna_drives: [{ ...drive, projection_ref: "foreign" }] } }, drive, "scene", 1), /immutable binding/));
check("ACK cannot change the time origin", () => assert.throws(() => model.resolveCommittedSolvedDriveScene({ scene_revision: 2, committed_scene: { revision: 2, scene: { id: "scene" }, solved_antenna_drives: [{ ...drive, time_origin: "absolute" }] } }, drive, "scene", 1), /parameters/));
check("ACK preserves later unsaved clock edits", () => { const draft=model.solvedDriveDraft(drive); const ack=model.acknowledgeSolvedDriveDraft({id:drive.id,draft:{...draft,timeOrigin:"absolute"},dirtyKeys:["timeOrigin"],editedAgainst:{timeOrigin:"stage_local"}},drive.id,draft,draft); assert.equal(ack.draft.timeOrigin,"absolute"); });
check("409 conflict blocks both save paths until explicit rebase", () => {
  for (const phase of ["conflict", "refreshing", "refetched"]) assert.ok(model.solvedDriveSaveBlockReason(null,0,phase));
  assert.equal(model.solvedDriveSaveBlockReason(null,0,"rebased"),undefined);
  assert.ok(model.solvedDriveSaveBlockReason(null,1,"rebased"));
  assert.equal(model.solvedDriveSaveBlockReason("Invalid frequency",0,"rebased"),"Invalid frequency");
});
console.log(JSON.stringify({ state: "passed", checks, scope: "interpreted production drive/preview/evaluator; no unit test compilation or solver qualification" }));
