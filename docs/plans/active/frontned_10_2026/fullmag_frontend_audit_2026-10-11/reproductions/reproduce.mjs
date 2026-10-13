/**
 * Minimal isolated reproductions for Fullmag master 2a3c6bec.
 * Source-equivalent port of createMoveGestureController (TypeScript annotations removed).
 * This is NOT the repository's Vitest/React/WebGL test suite.
 * Source: apps/control-room/src/modules/viewport-3d/MoveObjectGizmo.tsx
 * Additional cases explicitly model the expressions in the named source files.
 */
import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';

function createMoveGestureController({baseRevision,objectId,onCommit,onDraftChange,onGestureActiveChange,origin}) {
  let active = null;
  let translation = [...origin];
  const publish = () => onDraftChange({objectId,origin:[...origin],translation:[...translation]});
  return {
    begin(axis,pointerId,point,setPointerCapture,releasePointerCapture) {
      if(active) cancelActive(false);
      active = {axis,pointerId,releasePointerCapture,start:[...point]};
      translation = [...origin];
      setPointerCapture(pointerId);
      onGestureActiveChange?.(true);
      publish();
    },
    cancel() {if(!active)return false;cancelActive(true);return true;},
    async end(pointerId) {
      if(!active || active.pointerId!==pointerId)return;
      releaseActiveCapture();
      const committed = await onCommit(objectId,[...translation],baseRevision);
      if(committed!==false)onDraftChange(null);
    },
    move(pointerId,point) {
      if(!active || active.pointerId!==pointerId)return;
      const axisIndex=active.axis==='x'?0:active.axis==='y'?1:2;
      translation=[...origin];
      translation[axisIndex]+=point[axisIndex]-active.start[axisIndex];
      publish();
    }
  };
  function releaseActiveCapture(){
    const terminal=active;if(!terminal)return;active=null;
    try{terminal.releasePointerCapture(terminal.pointerId);}catch{}
    onGestureActiveChange?.(false);
  }
  function cancelActive(clearDraft){releaseActiveCapture();translation=[...origin];if(clearDraft)onDraftChange(null);}
}
const noop=()=>{};
const results=[];
async function reproduce(id,description,fn){
  const evidence=await fn();
  results.push({id,description,outcome:'REPRODUCED_IN_ISOLATED_MODEL',...evidence});
  console.log(`${id}: REPRODUCED — ${description}`);
}
await reproduce('R01','ACK poprzedniego gestu usuwa podgląd nowszego gestu',async()=>{
  let resolveAck;let draft;
  const controller=createMoveGestureController({baseRevision:10,objectId:'box',origin:[0,0,0],onDraftChange:d=>draft=d,onCommit:()=>new Promise(resolve=>resolveAck=resolve)});
  controller.begin('x',1,[0,0,0],noop,noop);controller.move(1,[10e-9,0,0]);
  const completion=controller.end(1);
  controller.begin('y',2,[0,0,0],noop,noop);controller.move(2,[0,20e-9,0]);
  assert.equal(draft.translation[1],20e-9);
  resolveAck(true);await completion;
  assert.equal(draft,null);
  return {actual:'draft=null while pointer 2 still owns an active gesture',expected:'old ACK must not clear gesture 2'};
});
await reproduce('R02','Klik osi bez ruchu nadal wywołuje commit',async()=>{
  let count=0;let payload;
  const c=createMoveGestureController({baseRevision:10,objectId:'box',origin:[1,2,3],onDraftChange:noop,onCommit:(_id,t)=>{count++;payload=t;return true;}});
  c.begin('x',1,[5,5,5],noop,noop);await c.end(1);
  assert.equal(count,1);assert.deepEqual(payload,[1,2,3]);
  return {actual:{commitCount:count,payload},expected:'no-op should not submit a model mutation'};
});
await reproduce('R03','Błąd transportu z end() jest propagowany jako odrzucona Promise',async()=>{
  const c=createMoveGestureController({baseRevision:10,objectId:'box',origin:[0,0,0],onDraftChange:noop,onCommit:async()=>{throw new Error('HTTP 500');}});
  c.begin('x',1,[0,0,0],noop,noop);c.move(1,[1,0,0]);
  await assert.rejects(c.end(1),/HTTP 500/);
  return {actual:'end rejects; UI handler invokes it using void and no catch in the inspected chain',expected:'recoverable error state and retained draft; no unhandled rejection'};
});
await reproduce('R04','Puste współrzędne stają się zerem w Number(value)',async()=>{
  const values=['','   '].map(v=>({input:v,parsed:Number(v),finite:Number.isFinite(Number(v))}));
  assert(values.every(x=>x.parsed===0&&x.finite));
  return {actual:values,expected:'empty required coordinate is invalid, not zero',source:'geometryObjectPanelModel.ts — numeric conversion expression'};
});
await reproduce('R05','Bazowa rewizja szkicu nie wynika automatycznie z nowego baseDraft',async()=>{
  const draftState={key:'committed:box',draft:{baseRevision:10,size:'100 nm'}};
  const baseDraft={mode:'committed',objectId:'box',baseRevision:11,size:'100 nm'};
  const draftKey=`${baseDraft.mode}:${baseDraft.objectId}`;
  const draft=draftState.key===draftKey?draftState.draft:baseDraft;
  assert.equal(draft.baseRevision,10);
  return {actual:{draftRevision:draft.baseRevision,sceneRevision:baseDraft.baseRevision},expected:'acknowledged draft baseline should advance to revision 11',scope:'expression-level model; not React integration test'};
});
await reproduce('R06','Freshness klasyfikuje przyszłą rewizję meshu jako current',async()=>{
  const sceneRevision=10,meshSourceSceneRevision=11;
  const meshIsStale=sceneRevision!==null&&meshSourceSceneRevision!==null&&meshSourceSceneRevision<sceneRevision;
  const freshness=meshIsStale?'stale':sceneRevision!==null&&meshSourceSceneRevision!==null?'current':'unknown';
  assert.equal(freshness,'current');
  return {actual:{sceneRevision,meshSourceSceneRevision,freshness},expected:'inconsistent/loading, not current',source:'useMeshDetailsModel.ts — freshness expression'};
});
await reproduce('R07','Fallback wymiarów walca ignoruje wysokość',async()=>{
  // boundsFromGeometry falls back to radiusSize(params.radius) when min/max and size are absent.
  const radius=50e-9,height=10e-9;
  const diameter=Math.max(radius*2,1e-12);
  const boundsSize=[diameter,diameter,diameter];
  assert.notEqual(boundsSize[2],height);
  return {actual:{radius,height,boundsSize},expected:'[2r,2r,h] for a z-axis cylinder',scope:'fallback path only; authoritative valid bounds bypass it'};
});
const report={commit:'2a3c6becb9c7e111ae1497ec0cd9ac9576acba95',scope:'isolated JS source-equivalent and expression-level reproductions, no React/WebGL/backend',node:process.version,count:results.length,results};
writeFileSync(new URL('./results.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
