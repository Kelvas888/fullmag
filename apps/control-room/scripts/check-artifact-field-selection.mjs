import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import vm from "node:vm";
const root=new URL("../src/",import.meta.url),cache=new Map();
function load(url){if(!cache.has(url.href))cache.set(url.href,new vm.SourceTextModule(stripTypeScriptTypes(readFileSync(url,"utf8")),{identifier:url.href}));return cache.get(url.href);}
const entry=load(new URL("kernel/visualization/artifactFieldSelection.ts",root));
await entry.link((name,parent)=>load(name.startsWith("@/")?new URL(`${name.slice(2)}.ts`,root):new URL(`${name}.ts`,parent.identifier)));await entry.evaluate();
const {artifactInspectionQuantity:gate,artifactSelectionForQuantity:select}=entry.namespace;
function catalog(q="J_charge"){return {quantities:[{id:q,n_comp:q==="V_electric"?1:3,unit:q==="V_electric"?"V":q==="J_charge"?"A/m^2":"A/m",resolved_capability:{quantity_id:q,lane:"artifact_inspection_read_only",provider:"available",request:"field_vector",render:"renderable",publication:"interactive",materialization:"materialized",carriers:[{payload_state:"historical",components:q==="V_electric"?1:3,indexing:q==="V_electric"?"source_nodes":q==="J_charge"?"tet4_cell_local_nodes":"sample_nodes"}]}}]};}
let checks=0;function check(name,run){run();checks++;console.log(`PASS ${name}`);}
for(const q of ["H_ant","J_charge","V_electric"])check(`${q} historical lane admitted`,()=>assert.equal(gate(catalog(q),q),true));
for(const [name,mutate] of [
 ["live solver lane",c=>{c.quantities[0].resolved_capability.lane="live";}],
 ["current payload",c=>{c.quantities[0].resolved_capability.carriers[0].payload_state="current";}],
 ["not materialized",c=>{c.quantities[0].resolved_capability.materialization="unmaterialized";}],
 ["unsupported provider",c=>{c.quantities[0].resolved_capability.provider="unavailable";}],
 ["wrong unit",c=>{c.quantities[0].unit="A/m";}],
 ["wrong component count",c=>{c.quantities[0].n_comp=1;}],
 ["wrong indexing",c=>{c.quantities[0].resolved_capability.carriers[0].indexing="sample_nodes";}],
 ["wrong capability quantity",c=>{c.quantities[0].resolved_capability.quantity_id="H_ant";}],
 ["duplicate entry",c=>{c.quantities.push(structuredClone(c.quantities[0]));}],
 ["no compatible carrier",c=>{c.quantities[0].resolved_capability.carriers=[];}],
])check(`${name} cannot take over a solver field`,()=>{const c=catalog();mutate(c);assert.equal(gate(c,"J_charge"),false);});
check("missing catalog and unsupported quantity stay outside artifact routing",()=>{assert.equal(gate(null,"H_ant"),false);assert.equal(gate(catalog(),"V_electric"),false);});
for(const [name,mutate] of [["wrong V unit",c=>{c.quantities[0].unit="A/m";}],["vector V",c=>{c.quantities[0].n_comp=3;}],["wrong V indexing",c=>{c.quantities[0].resolved_capability.carriers[0].indexing="sample_nodes";}]])check(name,()=>{const c=catalog("V_electric");mutate(c);assert.equal(gate(c,"V_electric"),false);});
const pin={identity:{sessionId:"s",sessionEpoch:"e",requestScopeEpoch:"r"},runId:"run",runtimeStageId:"stage",authoredStageId:"solve",sourceObjectId:"source",quantityId:"H_ant",carrierId:"h-carrier",carrierRevision:"9",carrierScopeKind:"full",carrierScopeId:null};
check("H to J preserves owner and clears every H carrier pin",()=>{const before=structuredClone(pin),next=select(pin,"J_charge");assert.deepEqual(next,{identity:pin.identity,runId:"run",runtimeStageId:"stage",authoredStageId:"solve",sourceObjectId:"source",quantityId:"J_charge"});assert.deepEqual(pin,before);});
check("same quantity preserves stable pinned identity",()=>assert.strictEqual(select(pin,"H_ant"),pin));
check("legacy untyped carrier is never adopted by name",()=>{const legacy={...pin};delete legacy.quantityId;assert.equal(select(legacy,"H_ant").carrierId,undefined);});
console.log(JSON.stringify({status:"passed",checks,unit_test_compilation:false}));
