import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
const root = new URL("../src/", import.meta.url), cache = new Map();
function load(url) { if (!cache.has(url.href)) cache.set(url.href, new vm.SourceTextModule(stripTypeScriptTypes(readFileSync(url, "utf8")), { identifier: url.href })); return cache.get(url.href); }
const entry = load(new URL("modules/viewport-3d/model/artifactFieldOverlayModel.ts", root));
await entry.link((name, parent) => load(name.startsWith("@/") ? new URL(`${name.slice(2)}.ts`, root) : new URL(`${name}.ts`, parent.identifier))); await entry.evaluate();
const { buildArtifactFieldOverlayModel: build } = entry.namespace;
const carrier = cache.get(new URL("modules/viewport-3d/model/artifactFieldCarrierModel.ts", root).href).namespace;
const digest = "a".repeat(64), content = `sha256:${"b".repeat(64)}`, source = `sha256:${"c".repeat(64)}`;
const owner = Object.fromEntries(["session_id", "session_epoch", "request_scope_epoch", "run_id", "runtime_stage_id", "authored_stage_id", "module_id", "object_id", "output_id", "native_mesh_identity", "native_topology_identity"].map(key => [key, key]));
Object.assign(owner, { source_digest: source, content_digest: content, historical_inspection: true });
const positions = Float64Array.from([0,0,0, 1,0,0, 0,1,0, 0,0,1, 0,0,0, 0,1,0, 1,0,0, 0,0,-1]);
const first = 9007199254740992n;
const ids = BigUint64Array.from([first,first+1n,first+2n,first+3n, first,first+2n,first+1n,first+4n]);
const locator = { carrier_scope_kind: "object", carrier_scope_id: "object_id", carrier_id: `artifact:${digest}:tet4_cell_local_nodes`, carrier_digest: digest, carrier_revision: "1", indexing: "tet4_cell_local_nodes", sample_count: 8, coordinate_frame: "world", coordinate_unit: "m", topology_binary_schema: "FMMT.v2", owner };
const mapping = { indexing: "tet4_cell_local_nodes", identityIds: ids, elementOrdinals: BigUint64Array.from([10n,10n,10n,10n,20n,20n,20n,20n]), localVertexIndices: Uint8Array.from([0,1,2,3,0,1,2,3]) };
const values = Float64Array.from([1,2,3, 2,3,4, 3,4,5, 4,5,6, -10,-20,-30, -20,-30,-40, -30,-40,-50, -40,-50,-60]);
const field = { formatVersion: 6, sourceKind: "artifact_inspection", artifactMapping: mapping, domainGenerationId: digest, meshTopologyHash: digest, meshTopologyRevision: "1", sourceId: source, fieldGenerationId: content, scopeKind: "object", scopeId: "object_id", indexing: "tet4_cell_local_nodes", pointCount: 8, quantityId: "J_charge", nComp: 3, values, sourceRevision: "2" };
const topology = { formatVersion: 2, nodeCount: 8, positions, cellTypes: Uint32Array.from([1,1]), cellOffsets: Uint32Array.from([0,4,8]), cellNodes: Uint32Array.from([0,1,2,3,4,5,6,7]) };
const headers = { carrierId: locator.carrier_id, carrierDigest: digest, carrierRevision: "1", identityIssues: [] }, geometry = { ...headers, coordinateFrame: "world", coordinateUnit: "m" };
const settings = { shaderColorMode: "x", vectorsVisible: true, vectorBudget: 8, vectorLengthScale: 1, vectorCenteringEnabled: false, scalarColorPalette: "viridis", vectorColorMode: "magnitude", shaderVisible: true, wireframeVisible: true };
function fixture() { return structuredClone({ locator, field, topology, headers, geometry, settings }); }
function render(f) { return build(carrier.admitArtifactFieldCarrier(f.locator, f.field, f.headers, f.topology, f.geometry), f.settings); }
let checks = 0;
function check(name, run) { run(); checks++; console.log(`PASS ${name}`); }
check("two J cells retain six exterior faces and distinct local values", () => {
  const f = fixture(), before = JSON.stringify([...f.field.values]), model = render(f);
  assert.equal(model.quantityId, "J_charge"); assert.equal(model.unit, "A/m^2"); assert.equal(model.surfaceTriangles.length, 18);
  for (let i=0; i<18; i+=3) { const face = [...model.surfaceTriangles.subarray(i,i+3)]; assert.ok(face.every(v=>v<4) || face.every(v=>v>=4)); assert.notDeepEqual(face.slice().sort((a,b)=>a-b), [0,1,2]); assert.notDeepEqual(face.slice().sort((a,b)=>a-b), [4,5,6]); }
  assert.deepEqual([...model.scalarValues], [1,2,3,4,-10,-20,-30,-40]);
  for (let i=0; i<values.length; i++) assert.ok(Math.abs(model.surfaceVectorValues[i] * model.surfaceVectorScale - values[i]) < 1e-5);
  assert.equal(JSON.stringify([...f.field.values]), before); assert.deepEqual(f.topology.positions, positions); assert.deepEqual(f.field.artifactMapping.identityIds, ids);
});
check("presentation reuses immutable geometry preparation and raw field arrays", () => {
  const f = fixture();
  const data = entry.namespace.prepareArtifactFieldOverlay(carrier.admitArtifactFieldCarrier(f.locator, f.field, f.headers, f.topology, f.geometry));
  const original = entry.namespace.presentArtifactFieldOverlay(data, f.settings);
  const updated = entry.namespace.presentArtifactFieldOverlay(data, { ...f.settings, scalarColorPalette: "plasma", surfaceOpacityPercent: 45 });
  assert.strictEqual(updated.geometry, original.geometry);
  for (const key of ["positions", "surfaceTriangles", "surfaceEdges", "surfaceVectorValues"]) assert.strictEqual(updated[key], original[key]);
  assert.deepEqual(updated.scalarValues, original.scalarValues);
  assert.deepEqual(f.field.values, values);
});
for (const [name, mutate] of [
  ["same stable ID has other geometry", f=>{f.topology.positions[12]=0.01;}],
  ["same stable ID has different signed zero", f=>{f.topology.positions[12]=-0;}],
  ["duplicate physical cell", f=>{f.field.artifactMapping.identityIds.set(ids.subarray(0,4),4); f.topology.positions.set(positions.subarray(0,12),12);}],
  ["overlapping neighbors", f=>{f.topology.positions[23]=2;}],
  ["degenerate cell", f=>{f.topology.positions[11]=0;}],
  ["trace count mismatch", f=>{f.field.artifactMapping.identityIds=ids.slice(0,7);}],
  ["local topology merges values", f=>{f.topology.cellNodes[4]=0;}],
  ["vector budget is explicit", f=>{f.settings.vectorBudget=7;}],
  ["non-finite J", f=>{f.field.values[0]=Infinity;}],
]) check(name, ()=>{const f=fixture();mutate(f);assert.throws(()=>render(f));});
check("equal coordinates with different IDs do not merge", ()=>{const f=fixture();for(let i=4;i<8;i++)f.field.artifactMapping.identityIds[i]+=100n; assert.equal(render(f).surfaceTriangles.length,24);});
const boundary = cache.get(new URL("modules/viewport-3d/model/artifactTet4Boundary.ts", root).href).namespace.artifactCellLocalBoundary;
check("third neighbor on one stable face is rejected", ()=>{
  const xyz = new Float64Array(positions.length + 12); xyz.set(positions); xyz.set([0,0,0,1,0,0,0,1,0,0,0,2], positions.length);
  const stable = new BigUint64Array(12); stable.set(ids); stable.set([first,first+1n,first+2n,first+5n],8);
  assert.throws(()=>boundary(xyz,stable));
});
for (const [name,mutate] of [
  ["missing local ordinals", f=>{f.field.artifactMapping.elementOrdinals=null;}],
  ["duplicate element identity", f=>{f.field.artifactMapping.elementOrdinals.fill(10n);}],
  ["mixed local element", f=>{f.field.artifactMapping.elementOrdinals[1]=11n;}],
  ["wrong local order", f=>{f.field.artifactMapping.localVertexIndices[1]=0;}],
]) check(name,()=>{const f=fixture();mutate(f);assert.throws(()=>render(f));});
check("J metadata requires its canonical unit and historical owner lane", ()=>{
  const c = { quantity_id: "J_charge", provider: "available", request: "field_vector", materialization: "materialized", render: "renderable", publication: "interactive", reason_code: "historical_inspection_read_only", lane: "artifact_inspection_read_only", carriers: [{ carrier_id: locator.carrier_id, carrier_fingerprint: digest, scope_kind: "object", scope_id: "object_id", payload_state: "historical", payload_version: "FMVP.v6", components: 3, indexing: "tet4_cell_local_nodes" }] };
  const m = { quantity_id:"J_charge",unit:"A/m^2",components:3,state:"stale_complete",materialization_reason_code:"historical_inspection_read_only",resolved_capability:c,artifact_field_locator:locator };
  const session = { sessionId:"session_id",sessionEpoch:"session_epoch",requestScopeEpoch:"request_scope_epoch" };
  assert.equal(entry.namespace.artifactOverlayLocator(m,session,"object_id","J_charge").carrier_id,locator.carrier_id);
  assert.throws(()=>entry.namespace.artifactOverlayLocator({...m,unit:"A/m"},session,"object_id","J_charge"));
  assert.throws(()=>entry.namespace.artifactOverlayLocator({...m,resolved_capability:{...c,lane:"live"}},session,"object_id","J_charge"));
  assert.throws(()=>entry.namespace.artifactOverlayLocator(m,{...session,sessionEpoch:"other"},"object_id","J_charge"));
  assert.throws(()=>entry.namespace.artifactOverlayLocator(m,session,"foreign","J_charge"));
  assert.throws(()=>entry.namespace.artifactOverlayLocator(m,session,"object_id"));
});
for (const indexing of ["sample_nodes", "point_samples"]) check(`existing raw H keeps its ${indexing} carrier and SI unit`, ()=>{
  const f=fixture(); f.locator.indexing=indexing; f.locator.sample_count=4; f.locator.carrier_id=`artifact:${digest}:${indexing}`;
  Object.assign(f.field,{quantityId:"H_ant",pointCount:4,indexing,values:values.slice(0,12),artifactMapping:{indexing,identityIds:BigUint64Array.from([0n,1n,2n,3n]),elementOrdinals:null,localVertexIndices:null}});
  f.topology.positions=positions.slice(0,12);f.topology.nodeCount=4;
  Object.assign(f.topology,indexing==="sample_nodes"?{cellTypes:Uint32Array.from([1]),cellOffsets:Uint32Array.from([0,4]),cellNodes:Uint32Array.from([0,1,2,3])}:{cellTypes:undefined,cellOffsets:undefined,cellNodes:undefined});
  f.headers.carrierId=f.locator.carrier_id; f.geometry.carrierId=f.locator.carrier_id;
  if(indexing==="point_samples"){f.settings.shaderVisible=false;f.settings.wireframeVisible=false;}
  const model=render(f);assert.equal(model.quantityId,"H_ant");assert.equal(model.unit,"A/m");assert.equal(model.count,4);
  assert.equal(model.surfaceTriangles?.length??0,indexing==="sample_nodes"?12:0);assert.equal(model.vectorSegments.length,28);
  const capability={quantity_id:"H_ant",provider:"available",request:"field_vector",materialization:"materialized",render:"renderable",publication:"interactive",reason_code:"historical_inspection_read_only",lane:"artifact_inspection_read_only",carriers:[{carrier_id:f.locator.carrier_id,carrier_fingerprint:digest,scope_kind:"object",scope_id:"object_id",payload_state:"historical",payload_version:"FMVP.v6",components:3,indexing}]};
  const metadata={quantity_id:"H_ant",unit:"A/m",components:3,state:"stale_complete",materialization_reason_code:"historical_inspection_read_only",resolved_capability:capability,artifact_field_locator:f.locator};
  assert.equal(entry.namespace.artifactOverlayLocator(metadata,{sessionId:"session_id",sessionEpoch:"session_epoch",requestScopeEpoch:"request_scope_epoch"},"object_id").carrier_id,f.locator.carrier_id);
});
check("signed V uses source-node scalar interpolation and never creates vector glyphs",()=>{
  const f=fixture(), indexing="source_nodes";
  Object.assign(f.locator,{indexing,sample_count:4,carrier_id:`artifact:${digest}:${indexing}`});
  Object.assign(f.field,{quantityId:"V_electric",nComp:1,pointCount:4,indexing,values:Float64Array.from([-2,0,1,4]),artifactMapping:{indexing,identityIds:ids.slice(0,4),elementOrdinals:null,localVertexIndices:null}});
  Object.assign(f.topology,{positions:positions.slice(0,12),nodeCount:4,cellTypes:Uint32Array.from([1]),cellOffsets:Uint32Array.from([0,4]),cellNodes:Uint32Array.from([0,1,2,3])});
  f.headers.carrierId=f.locator.carrier_id;f.geometry.carrierId=f.locator.carrier_id;f.settings.vectorBudget=0;
  const m=render(f);assert.equal(m.scalar,true);assert.equal(m.unit,"V");assert.equal(m.minimum,-2);assert.equal(m.maximum,4);assert.deepEqual([...m.scalarValues],[-2,0,1,4]);assert.equal(m.vectorSegments,null);assert.equal(m.surfaceVectorValues.length,0);assert.equal(m.surfaceTriangles.length,12);
  const normalized=m.geometry.surfaceScalarValues;assert.equal(normalized[0],0);assert.equal(normalized[3],1);assert.ok(Math.abs(normalized[1]-1/3)<1e-7);assert.equal(normalized[2],.5);
  f.field.nComp=3;assert.throws(()=>render(f));
});
const glyphRenderer=load(new URL("modules/viewport-3d/layers/vectorGlyphGeometry.ts",root));
await glyphRenderer.link((name,parent)=>load(name.startsWith("@/")?new URL(`${name.slice(2)}.ts`,root):new URL(`${name}.ts`,parent.identifier)));await glyphRenderer.evaluate();
for(const count of [7,14])check(`${count} samples keep exact renderer glyph cardinality`,()=>{
  const f=fixture(),indexing="point_samples";f.locator.indexing=indexing;f.locator.sample_count=count;f.locator.carrier_id=`artifact:${digest}:${indexing}`;
  const xyz=Float64Array.from(Array.from({length:count},(_,i)=>[0,0,i]).flat()), data=Float64Array.from(Array.from({length:count},(_,i)=>[i+1,0,0]).flat());
  Object.assign(f.field,{quantityId:"H_ant",pointCount:count,indexing,values:data,artifactMapping:{indexing,identityIds:BigUint64Array.from(Array.from({length:count},(_,i)=>BigInt(i))),elementOrdinals:null,localVertexIndices:null}});
  Object.assign(f.topology,{positions:xyz,nodeCount:count,cellTypes:undefined,cellOffsets:undefined,cellNodes:undefined});f.headers.carrierId=f.locator.carrier_id;f.geometry.carrierId=f.locator.carrier_id;
  f.settings.shaderVisible=false;f.settings.wireframeVisible=false;f.settings.vectorBudget=count;
  const model=render(f),transforms=glyphRenderer.namespace.buildVectorGlyphTransforms(model.vectorSegments);
  assert.equal(transforms.count,count);
  for(let i=0;i<count;i++)assert.deepEqual([...transforms.directions.subarray(i*3,i*3+3)],[1,0,0]);
});
console.log(JSON.stringify({status:"passed",checks,unit_test_compilation:false,browser_qualification:false}));
