// L8：P3a 物理真值、實際 DOM 接線與暫存副本變異驗證。
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createStore } from './store.js';
import { createController, cursorSource, divisionAt, toSource, toDisplay, mount, cursorRows, onCursorSource } from './cursors.js';
import { mount as mountPlot } from './mainplot.js';
import { voltageAt } from './voltage.js';
import { nearestCursor, bindGestures } from './gestures.js';
import { summaryText, mountSummary, disableTrackMeasurements } from './summary.js';
import * as fmt from '../fmt.js';
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.attrs = {}; this.listeners = {}; }
  get classList() { return { add:c => { this.className = c; } }; }
  append(...nodes) { for (const n of nodes) { this.children.push(n); n.parentNode = this; } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(k,v) { this.listeners[k] = v; }
  getBoundingClientRect() { return { left:0,top:0,width:500,height:300 }; }
  setPointerCapture() {}
  hasPointerCapture() { return false; }
}
globalThis.document = { activeElement:null,createElement:tag => new Element(tag) };
globalThis.window = new Element('window');
globalThis.Option = function(t,v) { const o = new Element('option'); o.textContent = t; o.value = v; return o; };
const close = (a,b) => assert.ok(Math.abs(a-b) <= 1e-12*Math.max(1,Math.abs(b)),`${a} != ${b}`);
const channels = [
  { name:'CHAN1',visible:true,unit:'V',scale:0.2,position:1,time_offset:0.01,t0:0,t1:1 },
  { name:'CHAN2',visible:true,unit:'V²',scale:2,position:-1,time_offset:0,t0:0,t1:1 },
];
for (const ch of channels) for (const value of [-5,0,1e-6,2]) {
  close(voltageAt(divisionAt(value,ch),ch),value);
  const [x,y] = toDisplay(0.4,value,ch), src = toSource({x1:x,y1:y},ch);
  close(src.x1,0.4); close(src.y1,value);
}
const store = createStore(), calls = [];
const bridge = { call:async (m,p) => { calls.push([m,p]); return { t1:p.t1,t2:p.t2,y:{ CHAN1:{y1:7,y2:9} } }; } };
const ctl = createController({store,bridge},{delay:1});
store.set({file:{gen:1},channels,selected:'CHAN2'});
assert.equal(cursorSource(store).channel.name,'CHAN1');
close(cursorSource(store).y1,0.2); close(cursorSource(store).y2,-0.6);
const original = { ...cursorSource(store) }, oldDiv = store.get().cursors.y1;
store.set({selected:'CHAN1'}); store.set({selected:'CHAN2'});
assert.equal(cursorSource(store).channel.name,'CHAN1'); close(cursorSource(store).y1,original.y1);
await ctl.refresh(); assert.equal(ctl.readout.source,'CHAN1');
store.updateChannel('CHAN1',{scale:0.5,position:-2},'user');
close(cursorSource(store).y1,original.y1); close(cursorSource(store).y2,original.y2);
close(store.get().cursors.y1,original.y1/0.5-2); assert.notEqual(store.get().cursors.y1,oldDiv);
// 模擬適配／零位拖曳／復原／重做均經同一 channels 路徑。
for (const patch of [{scale:0.1,position:3},{scale:0.2,position:1},{scale:0.5,position:-2}]) {
  store.updateChannel('CHAN1',patch,'user'); close(cursorSource(store).y1,original.y1);
}
const fallbackDiv = store.get().cursors.y1;
store.updateChannel('CHAN1',{visible:false},'user');
assert.equal(cursorSource(store).channel.name,'CHAN2'); close(cursorSource(store).y1,voltageAt(fallbackDiv,channels[1]));
close(store.get().cursors.y1,fallbackDiv);
store.updateChannel('CHAN2',{visible:false}); assert.equal(cursorSource(store).channel,null);
store.updateChannel('CHAN2',{visible:true}); close(cursorSource(store).y1,voltageAt(fallbackDiv,channels[1]));
store.command('cursor.intent',{which:'y1',value:2}); // 舊意圖仍為格數
assert.equal(store.get().cursors.y1,2); close(cursorSource(store).y1,6);
ctl.setSource('CHAN1'); assert.equal(cursorSource(store).channel.name,'CHAN2'); close(cursorSource(store).y1,6);
store.updateChannel('CHAN1',{visible:true}); assert.equal(cursorSource(store).channel.name,'CHAN1','自動還原原選來源');
close(store.get().cursors.y1,2); close(cursorSource(store).y1,2);
ctl.setSource('CHAN1'); close(cursorSource(store).y1,2);
store.removeChannel('CHAN1'); assert.equal(cursorSource(store).channel.name,'CHAN2'); close(cursorSource(store).y1,6);
let writes = 0; store.on(['cursors'],() => { writes++; assert.ok(writes<5,'投影迴圈'); });
for (let i=0;i<10;i++) store.updateChannel('CHAN2',{scale:2,position:-1});
store.updateChannel('CHAN2',{position:-1+1e-14});
assert.equal(writes,0,'differs 阻止同值與容差內投影');
await ctl.refresh();
assert.equal(ctl.readout.v1,6); assert.deepEqual(ctl.readout.y.CHAN1,{y1:7,y2:9});
const rows = cursorRows(ctl.readout,fmt.fmt); assert.equal(rows[4][1],fmt.fmt(6,'V²'));
// 同單位回退／復原保留物理值；同批 set 明寫格數不得被投影覆蓋。
const atomic = createStore(); const ac = createController({store:atomic,bridge},{delay:1});
atomic.set({file:{gen:3},channels:channels.map(c=>({...c,unit:'V'}))});
ac.setSource('CHAN2'); const physical = cursorSource(atomic).y1;
atomic.updateChannel('CHAN2',{visible:false}); close(cursorSource(atomic).y1,physical);
atomic.updateChannel('CHAN2',{visible:true}); assert.equal(cursorSource(atomic).channel.name,'CHAN2'); close(cursorSource(atomic).y1,physical);
atomic.set({channels:atomic.get().channels.map(c=>({...c,scale:4})),cursors:{...atomic.get().cursors,y1:3}});
assert.equal(atomic.get().cursors.y1,3); close(cursorSource(atomic).y1,16);
let notices = 0; onCursorSource(atomic,()=>notices++);
atomic.set({cursors:{...atomic.get().cursors,x1:0.123}}); assert.equal(notices,0,'只改 X 不重發 Y 真值通知');
ac.setSource('CHAN2'); assert.equal(notices,0,'相同來源與物理值不通知');
atomic.set({cursors:{...atomic.get().cursors,y1:4}}); assert.equal(notices,1);
atomic.removeChannel('CHAN2'); const deletedDiv = atomic.get().cursors.y1;
atomic.setChannels([...atomic.get().channels,{...channels[1],unit:'A'}]);
assert.equal(cursorSource(atomic).channel.name,'CHAN2','被刪來源重新出現也還原'); close(atomic.get().cursors.y1,deletedDiv);
close(cursorSource(atomic).y1,voltageAt(deletedDiv,{...channels[1],unit:'A'}));
atomic.set({file:null,channels:[]}); assert.deepEqual(cursorSource(atomic),{channel:null,y1:null,y2:null,readout:null});
atomic.set({file:{gen:4},channels}); assert.equal(cursorSource(atomic).channel.name,'CHAN1','換檔清除偏好來源');
const r = { l:0,t:0,w:100,h:100 }, v = {t0:0,t1:1}, cur = {x1:0.5,x2:0.56,y1:null,y2:null};
assert.equal(nearestCursor(cur,v,r,55,30),'x2'); assert.equal(nearestCursor(cur,v,r,51,30),'x1');
assert.equal(nearestCursor(cur,v,r,53,30),'x1','等距按固定鍵順序');
assert.equal(nearestCursor({...cur,x2:0.5},v,r,50,30),'x1');
assert.equal(nearestCursor({...cur,x2:null},v,r,58,30),'x1'); assert.equal(nearestCursor({...cur,x2:null},v,r,59,30),null);
assert.equal(nearestCursor({y1:0,y2:0.6},v,r,30,45),'y2');
for (const [x,y] of [[50,-1],[50,101],[-1,50],[101,50]]) assert.equal(nearestCursor({...cur,y1:0},v,r,x,y),null,'圖框外不可命中');
for (const x1 of [-0.01,1.01]) assert.equal(nearestCursor({x1},v,r,x1<0?0:100,30),null,'畫面外 X 不可抓');
const zero = summaryText(null,channels[0],{x1:1,x2:1},{y1:2,y2:3}); assert.ok(zero.includes('1/ΔX —'));
assert.match(summaryText(null,channels[0],{x1:2,x2:1},{y1:2,y2:3}),/ΔX -1/);
for (const [a,b] of [[2,5],[5,2]]) {
  const text = summaryText(null,channels[0],{x1:1,x2:3},{y1:a,y2:b});
  assert.ok(text.includes(`1/ΔX ${fmt.fmt(0.5,'Hz')}`)); assert.ok(text.includes(`ΔY ${fmt.fmt(b-a,'V')}`));
}
const select = new Element('select'); disableTrackMeasurements(select); disableTrackMeasurements(select);
assert.equal(select.children.length,1); assert.equal(select.children[0].disabled,true); assert.match(select.children[0].title,/需先補後端事件座標/);
// 真正 mount 的輸入 parseSI／來源下拉／單位標題。
const domStore = createStore(), panel = new Element('div');
mount(panel,{store:domStore,bridge,fmt,ui:{toast:()=>{}}});
domStore.set({file:{gen:2},channels,selected:'CHAN2'});
const inputs = panel.children[0], y1 = inputs.children[2].children[1], source = inputs.children[5].children[0];
assert.equal(inputs.children[2].children[0].textContent,'Y1 (V)');
assert.equal(source.value,'CHAN1'); assert.equal(y1.value,fmt.fmt(0.2,'V'));
for (const value of ['-1.234 V','-500 mV','-12.34 mV']) {
  y1.value = value; y1.onchange(); close(cursorSource(domStore).y1,fmt.parseSI(value)); assert.equal(y1.value,value);
}
y1.value = '1.2m'; y1.onchange(); close(cursorSource(domStore).y1,0.0012); close(domStore.get().cursors.y1,1.006);
y1.value = '錯誤'; y1.onchange(); close(cursorSource(domStore).y1,0.0012);
source.value = 'CHAN2'; source.onchange(); assert.equal(cursorSource(domStore).channel.name,'CHAN2');
assert.equal(inputs.children[2].children[0].textContent,'Y1 (V²)'); close(cursorSource(domStore).y1,0.0012);
domStore.updateChannel('CHAN1',{visible:false}); assert.deepEqual(source.children.map(o=>o.value),['CHAN2']);
source.value = 'CHAN1'; source.onchange(); assert.equal(source.value,'CHAN2'); assert.equal(cursorSource(domStore).channel.name,'CHAN2','不可選隱藏通道');
domStore.updateChannel('CHAN1',{visible:true}); assert.deepEqual(source.children.map(o=>o.value),['CHAN1','CHAN2']);
const bar = new Element('div'); mountSummary(bar,domStore); assert.equal(bar.children[0].title,bar.children[0].textContent);
assert.match(bar.children[0].textContent,/來源 CHAN2/);
const trackStore = createStore(), trackBar = new Element('div');
const tracked = {available:true,position:{x1:0.1,x2:0.6,y1:8,y2:-4},points:[],delta_x:0.5,inverse_delta_x:2,delta_y:-12};
const tc = createController({store:trackStore,bridge:{call:async()=>tracked}},{delay:1});
trackStore.set({file:{gen:5},channels,markerMode:'Track Waveforms'}); mountSummary(trackBar,trackStore); await tc.refresh();
assert.equal(trackBar.children[0].textContent,summaryText('Track Waveforms',channels[0],{x1:0.11,x2:0.61},{y1:8,y2:-4}));
let redraws = 0;
const canvas = new Element('canvas'); domStore.set({cursors:{x1:0.5,x2:0.56,y1:null,y2:null}});
const gestures = bindGestures(canvas,{store:domStore},()=>r,()=>{redraws++;});
canvas.listeners.pointermove({clientX:55,clientY:30}); assert.equal(canvas.style.cursor,'ew-resize'); assert.equal(gestures.hovered(),'x2');
domStore.command('cursor.intent',{which:'x2',value:0.9}); assert.equal(gestures.hovered(),'x1','鍵盤／意圖更新後重算');
canvas.listeners.pointerdown({clientX:51,clientY:30,button:0,pointerId:1});
canvas.listeners.pointermove({clientX:80,clientY:30,pointerId:1});
canvas.listeners.pointerup({pointerId:1}); assert.equal(gestures.hovered(),'x1','拖曳結束重算');
canvas.listeners.pointerleave(); assert.equal(gestures.hovered(),null);
const afterLeave = redraws; canvas.listeners.pointerleave(); assert.equal(redraws,afterLeave,'重複離開不重繪');
canvas.listeners.pointermove({clientX:80,clientY:30}); domStore.set({file:null}); assert.equal(gestures.hovered(),null,'換檔清 hover');
// 實際繪圖攔截 stroke 的線寬，確認 hover 加粗。
const strokes = [], context = new Proxy({}, {get:(t,k)=>k==='measureText'?()=>({width:0}):k==='stroke'?()=>strokes.push(t.lineWidth):t[k]??(()=>{}),set:(t,k,v)=>{t[k]=v;return true;}});
Element.prototype.getContext = () => context;
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const plotStore = createStore(); plotStore.set({file:{gen:6},cursors:{x1:0.5,x2:null,y1:null,y2:null}});
const host = new Element('div'), plot = mountPlot(host,{store:plotStore,bridge:{},ui:{toast(){}}});
await new Promise(resolve=>queueMicrotask(resolve));
strokes.length = 0; host.children[0].listeners.pointermove({clientX:287,clientY:100});
assert.ok(strokes.includes(3),'hover 必須實際用粗線繪製'); plot.dispose();

const css = readFileSync(new URL('../../css/analysis.css',import.meta.url),'utf8');
assert.match(css,/\.cursors__field--y \{[^}]*flex: 1 1 11ch;[^}]*min-width: 11ch;/,'Y 物理值須保留負號、小數與單位寬度');
assert.match(css,/\.analysis__cursorSummary \{[^}]*overflow: hidden;[^}]*text-overflow: ellipsis;[^}]*white-space: nowrap;/);
const toolbar = readFileSync(new URL('./toolbar.js',import.meta.url),'utf8'); assert.match(toolbar,/disableTrackMeasurements\(marker\)/);
console.log('P3a self-check OK：物理往返／來源脫鉤／重投影／隱藏與移除／格意圖／最近命中／DOM／摘要／防迴圈');
if (process.argv.includes('--mutations')) {
  const mutations = [
    ['Y 欄退回格數寬度','../../css/analysis.css','flex: 1 1 11ch; min-width: 11ch;','flex: 1 1 5ch; min-width: 5ch;'],
    ['以新縮放重取舊值','cursors.js','else setSnap(Object.fromEntries','else { capture(ch); } if (!written && !changedUnit) setSnap(Object.fromEntries'],
    ['selected 改來源','cursors.js','const mode = st.markerMode, ch = source.channel;','const mode = st.markerMode, ch = st.channels.find(c => c.name === st.selected);'],
    ['固定 X1 先贏','gestures.js','d < distance','false'],
    ['零 ΔX 未處理','summary.js',"dx ? fmt(1/dx,'Hz') : '—'","String(1/dx)"],
    ['隱藏不退回','cursors.js','c.visible && c.name === preferred','c.name === preferred'],
    ['Y 顯示格數','cursors.js','fmt.fmt(src[k], src.channel?.unit ?? "")','String(cursors[k])'],
    ['移除差異保護','cursors.js','Object.keys(patch).some((k) => differs(cur[k], patch[k]))','true'],
    ['異單位硬套數值','cursors.js','(!explicit && changedUnit)','false'],
    ['忘記原選來源','cursors.js','c.name === preferred','c.name === source.channel?.name'],
    ['覆蓋同批游標','cursors.js','if (written ||','if (false ||'],
    ['反頻率用間隔','summary.js',"fmt(1/dx,'Hz')","fmt(dx,'Hz')"],
    ['差值正負顛倒','summary.js','values.y2 - values.y1','values.y1 - values.y2'],
    ['hover 不加粗','mainplot.js','? 3 : 1','? 1 : 1'],
    ['換檔未清偏好','cursors.js','preferred = unit = null;','unit = null;'],
    ['下拉漏訂閱通道','cursors.js','["cursors", "markerMode", "channels"], syncInputs','["cursors", "markerMode"], syncInputs'],
    ['摘要不用追蹤讀值','summary.js',"s.markerMode === 'Track Waveforms' &&","false &&"],
    ['可選隱藏來源','cursors.js','c.visible && c.name === name','c.name === name'],
    ['圖框外命中','gestures.js','if (x < r.l ||','if (false && x < r.l ||'],
    ['畫面外 X 可抓','gestures.js','if (k[0] === "x" &&','if (false && k[0] === "x" &&'],
    ['重複真值通知','cursors.js','if (!force && signature === notified) return;','if (false) return;'],
    ['結束不重算 hover','gestures.js','if (!updateHover() && d) draw();','if (d) draw();'],
  ];
  const temp = mkdtempSync(join(tmpdir(),'scope-p3-'));
  try {
    cpSync(fileURLToPath(new URL('../',import.meta.url)),join(temp,'js'),{recursive:true});
    cpSync(fileURLToPath(new URL('../../css/',import.meta.url)),join(temp,'css'),{recursive:true});
    for (const [name,file,old,next] of mutations) {
      const path = join(temp,'js/analysis',file), original = readFileSync(path,'utf8'); assert.ok(original.includes(old),name);
      try {
        writeFileSync(path,original.replace(old,next));
        const result = spawnSync(process.execPath,[join(temp,'js/analysis/p3_check.mjs')],{encoding:'utf8',timeout:10000});
        assert.notEqual(result.status,0,`${name} 未抓到`); assert.match(result.stderr,/AssertionError/); console.log(`${name}：如預期失敗`);
      } finally { writeFileSync(path,original); }
    }
  } finally { rmSync(temp,{recursive:true,force:true}); }
  console.log(`P3a 變異 ${mutations.length}/${mutations.length} self-check OK（暫存副本已還原）`);
}
