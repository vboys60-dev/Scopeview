// L8：P3b-2 純函式、實際手勢／歷史接線、游標物理值及暫存變異。
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verticalZoom, verticalRect, DEFAULT_ZOOM_KIND, FIT_DIVS } from './vzoom.js';
import { V_TABLE, STEPS_125, DIVS } from './scales.js';
import { createStore } from './store.js';
import { bindViewport, bindGestures } from './gestures.js';
import { createController, cursorSource } from './cursors.js';
import { mount as mountAxes } from './axes.js';
const near = (a,b) => assert.ok(Math.abs(a-b)<1e-10, `${a} ≠ ${b}`);
const ch = {name:'CHAN1',unit:'V',visible:true,scale:1,position:2,time_offset:0,t0:0,t1:10};
assert.equal(DEFAULT_ZOOM_KIND,'horizontal'); assert.equal(FIT_DIVS,2*DIVS);
assert.deepEqual(verticalZoom(ch,-1,3,V_TABLE),{scale:0.5,position:2});
assert.deepEqual(verticalZoom({...ch,scale:V_TABLE[0]},-4,4,V_TABLE),{scale:V_TABLE[0],position:2});
assert.equal(verticalZoom(ch,1,1+1e-10,V_TABLE).scale,V_TABLE[0]);
assert.equal(verticalZoom(ch,-100,100,V_TABLE).scale,V_TABLE.at(-1));
assert.equal(verticalZoom(ch,-6,6,V_TABLE).scale,2);
assert.equal(verticalZoom(ch,1,1,V_TABLE),null);
assert.equal(verticalZoom(ch,-5,5,V_TABLE).scale,1);
assert.equal(verticalZoom({...ch,scale:0.1},-1.1,6.9,V_TABLE).scale,0.1);
// 十格邊界的浮點尾差仍選原檔；超出容差則升檔。
assert.equal(verticalZoom({...ch,scale:0.1},-1.1,8.9+1e-10,V_TABLE).scale,0.1);
assert.equal(verticalZoom({...ch,scale:0.1},-1.1,8.9+1e-6,V_TABLE).scale,0.2);
assert.deepEqual(ch,{name:'CHAN1',unit:'V',visible:true,scale:1,position:2,time_offset:0,t0:0,t1:10});
assert.equal(verticalZoom({...ch,scale:NaN},-1,1,V_TABLE),null);
for(const c of [ch,{...ch,name:'F1',derived:true,unit:'V²',scale:0.03,position:-3}]) {
  const steps=c.unit==='V'?V_TABLE:STEPS_125, patch=verticalZoom(c,-1,2,steps);
  const lo=(-1-c.position)*c.scale,hi=(2-c.position)*c.scale;
  near(-patch.position*patch.scale,(lo+hi)/2);
  assert.ok(hi-lo<=FIT_DIVS*patch.scale+1e-12);
  assert.ok(steps.includes(patch.scale));
  assert.ok(steps.indexOf(patch.scale)===0 || steps[steps.indexOf(patch.scale)-1]*FIT_DIVS<hi-lo);
}
class Element {
  constructor(tag='div') {this.tagName=tag;this.children=[];this.style={};this.dataset={};this.attrs={};this.listeners={};this.classList={add(){}};}
  append(...nodes) {this.children.push(...nodes);}
  setAttribute(k,v) {this.attrs[k]=v;}
  addEventListener(k,fn) {this.listeners[k]=fn;}
  removeEventListener() {}
  getBoundingClientRect() {return {left:0,top:0};}
  focus() {document.activeElement=this;}
  setPointerCapture() {}
  hasPointerCapture() {return false;}
}
globalThis.window=new Element('window');
globalThis.document={activeElement:null,createElement:t=>new Element(t)};
const store=createStore(),file={gen:1,channels:[{name:ch.name,t0:0,t1:10,points:10001}]};
const math={...ch,name:'F1',derived:true,unit:'V²',scale:0.002,position:-3};
store.set({file,view:{t0:0,t1:10},channels:[ch,math,{...ch,name:'HIDDEN',visible:false}],cursors:{x1:2,x2:8,y1:1,y2:3}});
// 實際產品的唯一通道寫入者為 chanbar；此處驗證意圖只含 scale／position。
const intents=[];
store.onCommand('channel.scale_intent',({name,scale,position,...extra})=>{
  assert.deepEqual(extra,{}); intents.push(name); store.updateChannel(name,{scale,position},'user');
});
const history=bindViewport(store);
const ctl=createController({store,bridge:{call:async()=>({t1:2,t2:8,y:{}})}});
const physical=[cursorSource(store).y1,cursorSource(store).y2];
const axes=new Element();mountAxes(axes,{store});
const group=axes.children[0],kindGroup=group.children[2],kinds=kindGroup.children;
assert.notEqual(kindGroup.hidden,true);assert.equal(kindGroup.attrs.role,'group');assert.equal(kindGroup.style.opacity,'0.55');assert.ok(kinds.every(b=>b.disabled));
store.command('view.mode','zoom');assert.notEqual(kindGroup.hidden,true);assert.equal(kindGroup.style.opacity,'1');
assert.equal(kinds[0].attrs['aria-pressed'],'true');
kinds[1].onclick();assert.equal(kinds[1].attrs['aria-pressed'],'true');
const canvas=new Element('canvas'),r={l:100,t:30,w:800,h:400};
const gestures=bindGestures(canvas,{store,ui:{toast(){}}},()=>r,()=>{});
const fire=(type,x,y,other={})=>canvas.listeners[type]({clientX:x,clientY:y,button:0,pointerId:1,timeStamp:100,preventDefault(){},...other});
const drag=(a,b,other={})=>{fire('pointerdown',...a,other);fire('pointermove',...b,other);fire('pointerup',...b,other);};
const reset=()=>{store.set({channels:[ch,math,{...ch,name:'HIDDEN',visible:false}],view:{t0:0,t1:10}},'program');history.clear();};
// 起點與終點在圖內；純垂直拖曳完全不依賴框寬。
store.command('view.mode','zoom');store.command('view.zoomKind','vertical');
drag([400,150],[400,270]);
assert.equal(store.get().channels[0].scale,0.5);assert.equal(store.get().channels[2].scale,1);
assert.equal(store.get().channels[1].scale,0.001);
assert.deepEqual(store.get().view,{t0:0,t1:10});assert.equal(history.status().undo,1);
assert.deepEqual([cursorSource(store).y1,cursorSource(store).y2],physical);
for(const key of ['y1','y2']) near((store.get().cursors[key]-store.get().channels[0].position)*store.get().channels[0].scale,cursorSource(store)[key]);
store.command('view.undo');assert.deepEqual(store.get().channels[0],ch);assert.equal(history.status().undo,0);
store.command('view.redo');assert.equal(store.get().channels[0].scale,0.5);
reset();store.command('view.zoomKind','both');drag([300,150],[700,270]);
assert.deepEqual(store.get().view,{t0:2.5,t1:7.5});assert.equal(store.get().channels[0].scale,0.5);assert.equal(history.status().undo,1);
// 歷史不得還原可見性、顏色、dx 等其他通道欄位。
store.updateChannel(ch.name,{color:'#123456',time_offset:0.25},'user');
store.command('view.undo');assert.deepEqual(store.get().view,{t0:0,t1:10});assert.equal(store.get().channels[0].scale,1);
assert.equal(store.get().channels[0].color,'#123456');assert.equal(store.get().channels[0].time_offset,0.25);
assert.equal(history.status().undo,0);assert.deepEqual([cursorSource(store).y1,cursorSource(store).y2],physical);
reset();drag([300,150],[700,155]);assert.deepEqual(store.get().view,{t0:2.5,t1:7.5});assert.equal(store.get().channels[0].scale,1);
reset();store.command('view.zoomKind','vertical');drag([300,150],[700,155]);assert.equal(history.status().undo,0);
assert.equal(verticalRect([ch],150,156,r,6).length,1);
assert.equal(verticalRect([ch],-100,r.t+5,r,6).length,0);
// Shift 暫時框選保留種類，反向拖曳、夾邊、取消與 overlay。
store.command('view.mode','pan');drag([400,270],[400,150],{shiftKey:true});assert.equal(store.get().channels[0].scale,0.5);
reset();assert.deepEqual(verticalRect([ch],-100,900,r,6),verticalRect([ch],r.t,r.t+r.h,r,6));
store.command('view.mode','zoom');
fire('pointerdown',400,150);fire('pointermove',600,270);
const fills=[],strokes=[],lines=[];
const g={save(){},restore(){},setLineDash(){},fillRect(...a){fills.push(a);},strokeRect(...a){strokes.push(a);},beginPath(){},moveTo(...a){lines.push(a);},lineTo(...a){lines.push(a);},stroke(){}};
gestures.overlay(g);assert.deepEqual(fills.pop(),[r.l,150,r.w,120]);assert.equal(strokes.length,0);assert.equal(lines.length,4);
window.listeners.keydown({key:'Escape'});fire('pointerup',600,270);assert.equal(history.status().undo,0);
for(const [kind,expected] of [['horizontal',[400,r.t,200,r.h]],['both',[400,150,200,120]]]) {
  store.command('view.zoomKind',kind);fire('pointerdown',400,150);fire('pointermove',600,270);gestures.overlay(g);
  assert.deepEqual(fills.pop(),expected);assert.deepEqual(strokes.pop(),expected);window.listeners.keydown({key:'Escape'});
}
store.command('view.mode','pan');assert.notEqual(kindGroup.hidden,true);assert.equal(kindGroup.style.opacity,'0.55');assert.ok(kinds.every(b=>b.disabled));
// 平移歷史只記時間；Undo／Redo 均不得送出通道意圖。
reset();store.command('view.mode','pan');drag([400,150],[480,150]);
const panned={...store.get().view};store.updateChannel(ch.name,{scale:2,position:4},'user');
let sent=intents.length;store.command('view.undo');assert.equal(intents.length-sent,0);
assert.deepEqual(store.get().view,{t0:0,t1:10});assert.equal(store.get().channels[0].scale,2);assert.equal(store.get().channels[0].position,4);
store.command('view.redo');assert.deepEqual(store.get().view,panned);assert.equal(intents.length-sent,0);
// 只改 CHAN1 的垂直框選；其他可見／隱藏通道後來的調整不受影響。
reset();store.command('view.zoomRect',{channels:[{name:ch.name,scale:0.5,position:3}]});
store.updateChannel('F1',{scale:0.2,position:7},'user');store.updateChannel('HIDDEN',{scale:5,position:8},'user');
store.command('viewport.intent',{t0:1,t1:9});store.command('view.undo');
// 垂直歷史亦不得帶回當下時間。
store.set({view:{t0:2,t1:8}},'program');
sent=intents.length;store.command('view.undo');assert.equal(intents.length-sent,1);assert.equal(intents.at(-1),ch.name);
assert.deepEqual(store.get().view,{t0:2,t1:8});assert.deepEqual(store.get().channels[0],ch);
for(const [name,scale,position] of [['F1',0.2,7],['HIDDEN',5,8]]) {
  const c=store.get().channels.find(c=>c.name===name);assert.equal(c.scale,scale);assert.equal(c.position,position);
}
store.updateChannel('F1',{scale:0.5,position:9},'user');sent=intents.length;store.command('view.redo');assert.equal(intents.length-sent,1);
assert.equal(store.get().channels[1].scale,0.5);assert.equal(store.get().channels[1].position,9);
// 未變動通道不進歷史；指令層拒絕隱藏／不存在通道。
reset();sent=intents.length;
store.command('view.zoomRect',{channels:[{name:'HIDDEN',scale:2,position:5},{name:'MISSING',scale:2,position:5},{...ch}]});
assert.equal(intents.length-sent,0);assert.equal(history.status().undo,0);
store.command('view.zoomRect',{channels:[{name:ch.name,scale:0.5,position:3},{...math}]});
store.updateChannel('F1',{scale:0.2,position:7},'user');sent=intents.length;store.command('view.undo');
assert.equal(intents.length-sent,1);assert.equal(store.get().channels[1].scale,0.2);assert.equal(store.get().channels[1].position,7);
// Undo 目標已等於目前值時，不送多餘的 scale_intent。
reset();store.command('view.zoomRect',{channels:[{name:ch.name,scale:0.5,position:3},{name:'F1',scale:0.001,position:2}]});
store.updateChannel(ch.name,{scale:ch.scale,position:ch.position},'user');sent=intents.length;store.command('view.undo');
assert.equal(intents.length-sent,1);assert.equal(intents.at(-1),'F1');
// 框選命令仍經 limitView，最小／最大跨度均受限。
reset();store.command('view.zoomRect',{view:{t0:4,t1:4.00001}});near(store.get().view.t1-store.get().view.t0,0.01);
store.command('view.zoomRect',{view:{t0:-100,t1:1000}});near(store.get().view.t1-store.get().view.t0,100);
// wheel → 100ms → 框選 → wheel，各自為一步，且 Undo 可逐步還原。
reset();store.command('view.mode','zoom');store.command('view.zoomKind','horizontal');
const now=Date.now;let time=1000;Date.now=()=>time;
try {
  fire('wheel',500,200,{deltaY:-40});const wheeled={...store.get().view};time+=100;
  drag([300,150],[700,270]);const boxed={...store.get().view};assert.equal(history.status().undo,2);
  time+=100;fire('wheel',500,200,{deltaY:-40});assert.equal(history.status().undo,3);
  store.command('view.undo');assert.deepEqual(store.get().view,boxed);
  store.command('view.undo');assert.deepEqual(store.get().view,wheeled);
  store.command('view.undo');assert.deepEqual(store.get().view,{t0:0,t1:10});
} finally {Date.now=now;}
// 拖曳中改種類須 end() 取消，不能提交舊框或殘留 overlay。
reset();store.command('view.zoomKind','both');fire('pointerdown',400,150);fire('pointermove',600,270);
store.command('view.zoomKind','vertical');let count=fills.length;gestures.overlay(g);assert.equal(fills.length,count);
fire('pointerup',600,270);assert.equal(history.status().undo,0);assert.deepEqual(store.get().channels[0],ch);
// 焦點移到輸入框後 Esc 仍能取消進行中的拖曳。
fire('pointerdown',400,150);fire('pointermove',600,270);document.activeElement=new Element('INPUT');
window.listeners.keydown({key:'Escape'});count=fills.length;gestures.overlay(g);assert.equal(fills.length,count);
fire('pointerup',600,270);assert.equal(history.status().undo,0);assert.deepEqual(store.get().channels[0],ch);
gestures.dispose();await ctl.refresh();assert.ok(intents.length>0);
console.log('p3b2 self-check OK');
if(process.argv.includes('--mutations')) {
  const root=dirname(dirname(fileURLToPath(import.meta.url)));
  const mutations=[
    ['vzoom.js','DEFAULT_ZOOM_KIND = "horizontal"','DEFAULT_ZOOM_KIND = "vertical"'],
    ['vzoom.js','s >= target','s <= target'],
    ['vzoom.js','2 * DIVS;','2 * (DIVS - 1);'],
    ['vzoom.js','target * (1 - 1e-9)','target'],
    ['vzoom.js','?? steps.at(-1)','?? steps[0]'],
    ['vzoom.js','-(lo / 2 + hi / 2)','(lo / 2 + hi / 2)'],
    ['vzoom.js','c.visible','!c.visible'],
    ['vzoom.js','< minPixels','< 1'],
    ['vzoom.js','scaleSteps(c.unit)','scaleSteps("V")'],
    ['gestures.js','d.zoomKind !== "vertical"','true'],
    ['gestures.js','d.zoomKind !== "horizontal"','false'],
    ['gestures.js','history.record(before, next); apply(next)','history.record(before, before); apply(next)'],
    ['gestures.js','history[action](snapshot)','null'],
    ['gestures.js','const before = { ...store.get().view }, next =','const before = snapshot({ ...store.get().view, channels: store.get().channels }), next ='],
    ['gestures.js','const before = snapshot(next);','const before = snapshot({ ...store.get().view, channels: store.get().channels });'],
    ['gestures.js','const next = history[action](snapshot);','const next = history[action](() => snapshot({ ...store.get().view, channels: store.get().channels }));'],
    ['gestures.js','c.visible && (c.scale !== n.scale || c.position !== n.position)','(c.scale !== n.scale || c.position !== n.position)'],
    ['gestures.js','(c.scale !== n.scale || c.position !== n.position)','true'],
    ['gestures.js','if (current && (current.scale !== c.scale || current.position !== c.position))','if (current)'],
    ['gestures.js','view ? limitView(view, viewLimits(store.get().file)) : null','view ?? null'],
    ['gestures.js','history.end(); history.record(before, next);','history.record(before, next, { key: "wheel", time: Date.now() });'],
    ['gestures.js','{ end(); zoomKind = v; }','{ zoomKind = v; }'],
    ['gestures.js','if (e.key === "Escape" && drag)','if (!editableTarget(document.activeElement) && e.key === "Escape" && drag)'],
    ['axes.js','kindGroup.setAttribute("role", "group");',''],
    ['axes.js','kindGroup.style.opacity = mode === "zoom" ? "1" : "0.55";','kindGroup.hidden = mode !== "zoom";'],
    ['gestures.js','zoomKind, view:','zoomKind: "horizontal", view:'],
    ['cursors.js','else setSnap(Object.fromEntries','else if (false) setSnap(Object.fromEntries'],
  ];
  for(const [file,from,to] of mutations) {
    const tmp=mkdtempSync(join(tmpdir(),'p3b2-'));
    try {
      cpSync(root,join(tmp,'js'),{recursive:true});writeFileSync(join(tmp,'package.json'),' {"type":"module"}');
      const path=join(tmp,'js','analysis',file),source=readFileSync(path,'utf8');assert.ok(source.includes(from),from);
      writeFileSync(path,source.replace(from,to));
      const result=spawnSync(process.execPath,[join(tmp,'js/analysis/p3b2_check.mjs')],{encoding:'utf8'});
      assert.notEqual(result.status,0,`變異未被抓到：${file} ${from}`);
      assert.match(result.stderr,/AssertionError/);
    } finally {rmSync(tmp,{recursive:true,force:true});}
  }
  console.log(`p3b2 mutations self-check OK（${mutations.length}/${mutations.length}）`);
}
