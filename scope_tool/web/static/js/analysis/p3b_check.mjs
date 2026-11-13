// L8：P3b 表格／TSV／剪貼簿退路與觸控命中；變異僅改暫存副本。
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildMarkerRows, markerTSV, HEADERS, copyText, mountCursorTable } from './cursor_table.js';
import { nearestCursor, cursorRadius, bindGestures } from './gestures.js';
import { hitBox, hitHandle, channelHandles, cursorEdges } from './handles.js';
import { createStore } from './store.js';
import { createController, mount as mountCursors } from './cursors.js';
import { mountTabs } from './bpanel.js';
import { lowerSummary } from './tab_analysis.js';
import * as fmt from '../fmt.js';
const header = ['Marker','水平(X)','垂直(Y，來源單位)','ΔX','1/ΔX','ΔY','ΔY/ΔX','Delta To'];
assert.deepEqual(HEADERS,header);
const base = {kind:'marker',mode:'Manual X and Y',t1:3e-3,t2:1e-3,v1:0.004,v2:-0.002,unit:'V²',available:true};
const rows = buildMarkerRows(base);
assert.deepEqual(rows,[
  ['X1','3 ms','—','-2 ms','-500 Hz','-6 mV²','3 V²/s','X2'],
  ['X2','1 ms','—','-2 ms','-500 Hz','-6 mV²','3 V²/s','X1'],
  ['Y1','—','4 mV²','-2 ms','-500 Hz','-6 mV²','3 V²/s','Y2'],
  ['Y2','—','-2 mV²','-2 ms','-500 Hz','-6 mV²','3 V²/s','Y1'],
]);
const tsv = markerTSV(rows);
assert.equal(tsv,header.join('\t')+'\n'+rows.map(r=>r.join('\t')).join('\n'));
assert.ok(!tsv.includes('<') && !tsv.includes('\r'));
assert.equal(markerTSV([]),header.join('\t'));
const dirtyTSV=markerTSV(buildMarkerRows({...base,unit:'V\tA\rB\nC'}));
assert.equal(dirtyTSV.split('\n').length,5);
assert.ok(dirtyTSV.split('\n').every(line=>line.split('\t').length===8));
assert.ok(dirtyTSV.includes('V A B C')&&!dirtyTSV.includes('\r'));
for (const [mode,names] of [['Manual X only',['X1','X2']],['Manual Y only',['Y1','Y2']],['Track Waveforms',['X1','X2']]]) {
  const result = buildMarkerRows({...base,mode}); assert.deepEqual(result.map(r=>r[0]),names);
  if (mode==='Manual X only') assert.ok(result.every(r=>r[2]==='—'&&r[5]==='—'&&r[6]==='—'));
  if (mode==='Manual Y only') assert.ok(result.every(r=>r[1]==='—'&&r[3]==='—'&&r[4]==='—'&&r[6]==='—'));
  if (mode==='Track Waveforms') { assert.deepEqual(result.map(r=>r[2]),['4 mV²','-2 mV²']); assert.ok(result.every(r=>r[5]==='-6 mV²'&&r[6]==='3 V²/s')); }
}
for (const readout of [null,{...base,kind:'unsupported'},{...base,available:false}]) assert.deepEqual(buildMarkerRows(readout),[]);
for (const t2 of [base.t1,null,Infinity]) {
  const result = buildMarkerRows({...base,t2}); assert.ok(result.every(r=>r[4]==='—'&&r[6]==='—'));
}
assert.equal(buildMarkerRows({...base,t2:base.t1})[0][3],'0 s');
assert.equal(buildMarkerRows({...base,unit:''})[0][6],'3 1/s');
assert.equal(buildMarkerRows({...base,kind:'legacy',mode:null}).length,4);
assert.equal(buildMarkerRows({...base,v2:NaN})[0][5],'—');
assert.deepEqual(base,{kind:'marker',mode:'Manual X and Y',t1:3e-3,t2:1e-3,v1:0.004,v2:-0.002,unit:'V²',available:true});
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.style={}; this.dataset={}; this.attrs={}; this.listeners={}; }
  get classList() { return {add:c=>{this.className=c;}}; }
  append(...nodes) { for (const n of nodes) { this.children.push(n); n.parentNode=this; } }
  replaceChildren(...nodes) { this.children=[]; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k]=v; }
  addEventListener(k,v) { this.listeners[k]=v; }
  select() { this.selected=true; }
  remove() { this.removed=true; }
  focus() { this.focused=true; }
  getBoundingClientRect() { return {left:0,top:0}; }
  setPointerCapture() {}
  hasPointerCapture() { return false; }
}
const doc={activeElement:new Element('input'),body:new Element('body'),createElement:t=>new Element(t),execCommand:()=>true};
let copied;
assert.equal(await copyText(tsv,{clipboard:{writeText:async t=>{copied=t;}}},doc),true); assert.equal(copied,tsv); assert.equal(doc.body.children.length,0);
for (const success of [true,false]) {
  doc.execCommand=command=>{assert.equal(command,'copy');return success;};
  assert.equal(await copyText(tsv,{clipboard:{writeText:async()=>{throw Error('拒絕');}}},doc),success);
  const area=doc.body.children.at(-1); assert.equal(area.value,tsv); assert.ok(area.selected&&area.removed&&doc.activeElement.focused);
}
doc.execCommand=()=>{throw Error('拒絕');}; assert.equal(await copyText(tsv,{},doc),false);
globalThis.document=doc; globalThis.window=new Element('window');
Object.defineProperty(globalThis,'navigator',{value:{clipboard:{writeText:async t=>{copied=t;}}},configurable:true});
const messages=[], view=mountCursorTable({ui:{toast:(m,type)=>messages.push([m,type])}});
view.render(base); const table=view.el.children[1].children[0],button=view.el.children[0].children[1];
assert.deepEqual(table.children.map(r=>r.children.map(c=>c.textContent)),[header,...rows]);
await button.onclick(); assert.equal(copied,tsv); assert.deepEqual(messages.at(-1),['已複製','success']);
globalThis.navigator.clipboard.writeText=async()=>{throw Error('拒絕');}; await button.onclick(); assert.deepEqual(messages.at(-1),['複製失敗','error']);
assert.equal(view.el.children[0].children[0].textContent,'游標結果（—，Manual X and Y）');
view.render({...base,source:'CHAN2'}); assert.equal(table.attrs['aria-label'],'游標結果（CHAN2，Manual X and Y）');
view.render({...base,kind:'legacy',mode:null,source:'CHAN1'}); assert.equal(table.attrs['aria-label'],'游標結果（CHAN1，傳統游標）');
view.render(null); assert.equal(button.disabled,true);
// 實際 mount 排序：傳統通道表前置；Marker 有列時隱藏重複讀值。
const store=createStore(), panel=new Element('div');
const bridge={call:async(method)=>method==='cursor_readout'?{t1:0,t2:1,y:{CHAN1:{y1:2,y2:4}}}:{position:{x1:0,x2:1,y1:2,y2:4},points:[],available:true,delta_x:1,delta_y:2,inverse_delta_x:1}};
mountCursors(panel,{store,fmt,ui:{toast(){}},bridge});
assert.equal(panel.children[2].tagName,'table'); assert.equal(panel.children[3].className,'cursors__readout'); assert.equal(panel.children[4].className,'cursor-results');
const channel={name:'CHAN1',visible:true,scale:1,position:0,unit:'V',t0:0,t1:1};
store.set({file:{gen:1},channels:[channel]});
const settle=()=>new Promise(resolve=>setTimeout(resolve,65));
await settle();
assert.equal(panel.children[2].hidden,false); assert.equal(panel.children[3].hidden,true);
for(const mode of ['Manual X only','Manual Y only','Manual X and Y','Track Waveforms','Track Measurements']) {
  store.set({markerMode:mode}); await settle(); assert.equal(panel.children[2].hidden,true,mode);
}
// 隱藏所有來源後不可洩漏舊物理真值，畫面及 TSV 的 Y 欄都必須缺值。
const hiddenStore=createStore(); hiddenStore.set({file:{gen:1},channels:[channel],cursors:{x1:0,x2:1,y1:2,y2:-2}});
const hiddenController=createController({store:hiddenStore,bridge});
await hiddenController.refresh(); assert.equal(hiddenController.readout.v1,2);
hiddenStore.set({channels:[{...channel,visible:false}]}); await hiddenController.refresh();
assert.equal(hiddenController.readout.v1,null); assert.equal(hiddenController.readout.v2,null);
const hiddenRows=buildMarkerRows(hiddenController.readout);
assert.ok(hiddenRows.filter(r=>r[0][0]==='Y').every(r=>r[2]==='—'&&r[5]==='—'&&r[6]==='—'));
assert.ok(markerTSV(hiddenRows).split('\n').slice(3).every(line=>line.split('\t')[2]==='—'));
const body=new Element('div'),bar=new Element('div'),panels=Object.fromEntries(['measure','cursor','peaks'].map(k=>[k,new Element('div')]));body.append(...Object.values(panels));
const tabs=mountTabs(bar,panels,{initial:{version:1,tab:'measure',columns:[]},persist:()=>{}});
tabs.update({width:1100,height:180}); assert.equal(bar.children[0].attrs['aria-multiselectable'],'true');
bar.children[0].children[1].onclick();
assert.ok(panels.measure.hidden&&!panels.cursor.hidden); assert.equal(body.dataset.resultTabbed,'true');
assert.equal(bar.children[0].attrs['aria-multiselectable'],'false');
bar.children[0].children[0].onclick(); assert.equal(bar.children[0].attrs['aria-multiselectable'],'true');
tabs.update({width:700,height:180}); assert.equal(bar.children[0].attrs['aria-multiselectable'],'false');
for(const markerMode of [null,'Manual X only','Manual X and Y','Track Waveforms']) {
  assert.equal(lowerSummary({measurements:[],markerMode,cursors:{x1:3e-6,x2:1e-6}},false),'量測 0／FFT 峰值 0／ΔX -2 µs');
}
assert.equal(lowerSummary({measurements:[],markerMode:'Manual Y only',cursors:{x1:3e-6,x2:1e-6}},false),'量測 0／FFT 峰值 0');
assert.match(lowerSummary({measurements:[],cursors:{x1:null,x2:1}},false),/ΔX —$/);
const r={l:0,t:0,w:100,h:100},v={t0:0,t1:1},cur={x1:0.5};
for (const type of ['touch','mouse','pen',undefined]) {
  const radius=type==='touch'?12:8; assert.equal(cursorRadius(type),radius);
  assert.equal(nearestCursor(cur,v,r,50+radius,30,type),'x1'); assert.equal(nearestCursor(cur,v,r,51+radius,30,type),null);
}
assert.equal(nearestCursor({...cur,x2:0.6},v,r,59,30,'touch'),'x2');
assert.equal(nearestCursor(cur,v,r,50,-1,'touch'),null);
const ch={name:'CH1',visible:true,scale:1,position:0};
for (const b of [...channelHandles([ch],r),...cursorEdges({x1:-1},v,r)]) { const box=hitBox(b); assert.ok(box.w>=24&&box.h>=24); }
const overlap=[ch,{...ch,name:'CH2'}];
assert.equal(hitHandle(overlap,r,10,63)?.name,'CH2'); assert.equal(hitHandle(overlap,r,10,62)?.name,'CH1');
assert.equal(hitHandle(overlap,{...r,h:20},22,10)?.name,'CH1'); assert.equal(hitHandle(overlap,{...r,h:20},34,10)?.name,'CH2', '矮圖分欄（把手 24px 寬）各取自己的命中框');
assert.equal(hitHandle([ch],r,20,50)?.name,'CH1'); assert.equal(hitHandle([ch],r,8,61)?.name,'CH1');
// 透過實際 pointerdown 確認 pointerType 傳到純函式。
store.set({file:{gen:1},channels:[],view:v,cursors:{x1:null,x2:null,y1:null,y2:null}});
store.command('cursor.intent',{which:'x1',value:0.5});
const cv=new Element('canvas'),gestures=bindGestures(cv,{store},()=>r,()=>{});
for(const [pointerType,x,expected] of [['touch',62,'x1'],['touch',63,null],['mouse',62,null],['pen',62,null]]) {
  cv.listeners.pointermove({clientX:x,clientY:30,pointerId:1,pointerType}); assert.equal(gestures.hovered(),expected); }

cv.listeners.pointerdown({clientX:61,clientY:30,button:0,pointerId:1,pointerType:'touch'});
let intent;store.onCommand('cursor.intent',p=>{intent=p;});cv.listeners.pointermove({clientX:70,clientY:30,pointerId:1,pointerType:'touch'});
assert.equal(intent?.which,'x1'); assert.equal(intent.value,0.7);cv.listeners.pointerup({pointerId:1});gestures.dispose();
const css=readFileSync(new URL('../../css/analysis.css',import.meta.url),'utf8');assert.match(css,/\.cursor-results__table td \{[^}]*font-size: 12.5px;[^}]*white-space: nowrap;/);
console.log('P3b self-check OK：模式／有號差值／缺值／SI／TSV／剪貼簿／DOM／觸控');
if (process.argv.includes('--mutations')) {
  const mutations=[
    ['M1 追蹤漏 ΔY 與斜率','cursor_table.js','dy = y || track ?','dy = y ?'],
    ['M2 非傳統模式仍顯示通道表','cursors.js',`chTbl.hidden = r?.kind !== "legacy";`,'chTbl.hidden = false;'],
    ['M4 重疊把手取首個','handles.js','.sort((a, b) => Math.hypot(x-a.x-a.w/2,y-a.y-a.h/2)-Math.hypot(x-b.x-b.w/2,y-b.y-b.h/2))',''],
    ['M5 hover 漏傳觸控類型','gestures.js','hitCursor(pointer.x, pointer.y, pointer.pointerType)','hitCursor(pointer.x, pointer.y)'],
    ['M15 aria 不隨游標分頁','bpanel.js',"String(!single)","String(!tabbed)"],
    ['M16 複製失敗報 success','cursor_table.js',"ok ? 'success' : 'error'","'success'"],
    ['隱藏來源沿用舊值','cursors.js','ch ? [source.y1, source.y2] : [null, null]','[source.y1, source.y2]'],
    ['重複讀值未隱藏','cursors.js','tbl.hidden = markerTable.render(r) > 0;','markerTable.render(r); tbl.hidden = false;'],
    ['TSV 未清理分隔字元','cursor_table.js',"String(cell).replace(/[\\t\\r\\n]/g, ' ')",'String(cell)'],
    ['Y 模式誤顯示 ΔX','tab_analysis.js',"st.markerMode === 'Manual Y only'","false"],
    ['差值反向','cursor_table.js','b - a','a - b'],
    ['手動 X 多列 Y','cursor_table.js',"const y = legacy ||",'const y = x || legacy ||'],
    ['倒數變間隔','cursor_table.js','? 1 / dx : null','? dx : null'],
    ['零間隔除零','cursor_table.js',"const inv = finite(dx) && dx !== 0 ? 1 / dx : null;","const inv = finite(dx) ? 1 / (dx || 1) : null;"],
    ['斜率單位錯','cursor_table.js','`${r.unit}/s`','r.unit'],
    ['TSV 無表頭','cursor_table.js','[HEADERS, ...rows].map','rows.map'],
    ['TSV 改逗號','cursor_table.js',".join('\\t')",".join(',')"],
    ['配對錯誤','cursor_table.js',"second ? '1' : '2'","second ? '2' : '1'"],
    ['觸控半徑退化','gestures.js','? 12 : 8','? 8 : 8'],
    ['漏傳觸控類型','gestures.js','which = hitCursor(x, y, e.pointerType)','which = hitCursor(x, y)'],
    ['把手過窄','handles.js','w: Math.max(24, b.w)','w: b.w'],
    ['複製退路報成功','cursor_table.js',"return !!doc.execCommand('copy');","doc.execCommand('copy'); return true;"],
  ];
  const temp=mkdtempSync(join(tmpdir(),'scope-p3b-'));
  try {
    cpSync(fileURLToPath(new URL('../',import.meta.url)),join(temp,'js'),{recursive:true});
    cpSync(fileURLToPath(new URL('../../css/',import.meta.url)),join(temp,'css'),{recursive:true});
    for (const [name,file,old,next] of mutations) {
      const path=join(temp,'js/analysis',file),original=readFileSync(path,'utf8');assert.ok(original.includes(old),name);
      try {writeFileSync(path,original.replace(old,next));const result=spawnSync(process.execPath,[join(temp,'js/analysis/p3b_check.mjs')],{encoding:'utf8',timeout:10000});assert.notEqual(result.status,0,`${name} 未抓到`);assert.match(result.stderr,/AssertionError/);console.log(`${name}：如預期失敗`);}
      finally {writeFileSync(path,original);}
    }
  } finally {rmSync(temp,{recursive:true,force:true});}
  console.log(`P3b 變異 ${mutations.length}/${mutations.length} self-check OK（暫存副本已還原）`);
}
