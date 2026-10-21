import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const auditSource = await readFile(
  new URL("./audit-viewport-3d-fem-topology-uploads.mjs", import.meta.url),
  "utf8",
);
const installStart = auditSource.indexOf(
  "async function installBrowserAuditInstrumentation(page) {",
);
const installEnd = auditSource.indexOf(
  "\n\nasync function waitForViewportDiagnostics",
  installStart,
);
assert.ok(installStart >= 0, "the audit must expose its WebGL instrumentation function");
assert.ok(installEnd > installStart, "the audit instrumentation boundary must remain parseable");
const installSource = auditSource.slice(installStart, installEnd);

async function createInstrumentedContext({ activePosition }) {
  const gl = {
    ARRAY_BUFFER: 0x8892,
    ELEMENT_ARRAY_BUFFER: 0x8893,
    STATIC_DRAW: 0x88e4,
    createBuffer() {
      return {};
    },
    bindBuffer() {},
    bufferData() {},
    bufferSubData() {},
    useProgram() {},
    getActiveAttrib(_program, index) {
      if (index !== 0) return null;
      return { name: activePosition ? "position" : "normal" };
    },
    getAttribLocation(_program, name) {
      return activePosition && name === "position" ? 3 : -1;
    },
    vertexAttribPointer() {},
    vertexAttribIPointer() {},
  };
  class FakeCanvas {
    getContext() {
      return gl;
    }
  }
  const context = {
    HTMLCanvasElement: FakeCanvas,
    window: {},
  };
  const install = runInNewContext(`(${installSource})`, context);
  let initScript;
  await install({
    addInitScript(callback) {
      initScript = callback;
    },
  });
  assert.equal(typeof initScript, "function");
  await initScript();
  const canvas = new FakeCanvas();
  const instrumentedGl = canvas.getContext("webgl2");
  return { counters: context.window.__FM_VIEWPORT_BROWSER_AUDIT__, gl: instrumentedGl };
}

test("WebGL position probe counts real position buffers and upload overloads", async () => {
  const { counters, gl } = await createInstrumentedContext({ activePosition: true });
  const positionBuffer = gl.createBuffer();
  const normalBuffer = gl.createBuffer();
  const program = {};

  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(3), gl.STATIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(6), gl.STATIC_DRAW);
  assert.equal(counters.positionArrayBufferBytesUploaded, 0);

  gl.useProgram(program);
  assert.equal(gl.getActiveAttrib(program, 0).name, "position");
  assert.equal(gl.getAttribLocation(program, "position"), 3);
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.vertexAttribPointer(3, 3, 0x1406, false, 0, 0);
  assert.equal(counters.positionArrayBufferBytesUploaded, 12);

  gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Float32Array(2));
  assert.equal(counters.positionArrayBufferBytesUploaded, 12);

  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  gl.bufferSubData(gl.ARRAY_BUFFER, 0, new Float32Array(3), 0, 0);
  gl.bufferData(gl.ARRAY_BUFFER, new Uint16Array(4), gl.STATIC_DRAW, 1, 0);
  assert.equal(counters.positionArrayBufferBytesUploaded, 30);
  assert.equal(counters.arrayBufferBytesUploaded, 62);
  assert.equal(counters.positionBuffersObserved, 1);
  assert.equal(counters.positionActiveAttributesObserved, 1);
  assert.equal(counters.positionLocationsObserved, 1);
  assert.equal(counters.positionPointerCalls, 1);
  assert.ok(counters.arrayBufferBytesUploaded > counters.positionArrayBufferBytesUploaded);
});

test("WebGL position probe does not classify inactive attributes as position", async () => {
  const { counters, gl } = await createInstrumentedContext({ activePosition: false });
  const normalBuffer = gl.createBuffer();
  const program = {};

  gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(3), gl.STATIC_DRAW);
  gl.useProgram(program);
  assert.equal(gl.getActiveAttrib(program, 0).name, "normal");
  assert.equal(gl.getAttribLocation(program, "position"), -1);
  gl.vertexAttribPointer(3, 3, 0x1406, false, 0, 0);

  const confirmedPositionEvidence =
    counters.positionActiveAttributesObserved > 0 &&
    counters.positionLocationsObserved > 0 &&
    counters.positionPointerCalls > 0 &&
    counters.positionBuffersObserved > 0 &&
    counters.positionArrayBufferBytesUploaded > 0;
  assert.equal(confirmedPositionEvidence, false);
  assert.equal(counters.positionArrayBufferBytesUploaded, 0);
});
