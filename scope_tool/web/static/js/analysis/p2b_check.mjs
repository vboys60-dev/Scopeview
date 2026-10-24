// L8：純版面矩陣、偏好儲存與真正 splitter 事件；變異只改暫存副本。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { FFT_BAR_HEIGHT, FFT_PLOT_MIN, FFT_MIN_HEIGHT, clampLayout, defaults, validatePrefs, loadPrefs, savePrefs, resizeValue, resetPref } from './layout.js';
import { mountSplitter } from './splitter.js';
import { createStore } from './store.js';
import { createController } from './cursors.js';
import { bindViewport } from './gestures.js';
import { bindLayoutCommands } from './tab_analysis.js';
// 核對 CSS 與純尺寸計算的共用預算，避免調整控制列後吃掉繪圖下限。
assert.equal(FFT_BAR_HEIGHT,40); assert.equal(FFT_PLOT_MIN,120);
assert.equal(FFT_MIN_HEIGHT,FFT_BAR_HEIGHT+FFT_PLOT_MIN);
const css = readFileSync(new URL('../../css/analysis.css',import.meta.url),'utf8');
const rule = (selector) => css.split(selector+' {')[1]?.split('}')[0] ?? '';
assert.ok(rule('.analysis__fftbar').includes(`height: ${FFT_BAR_HEIGHT}px; flex: 0 0 ${FFT_BAR_HEIGHT}px;`));
assert.ok(rule('.analysis__fft').includes(`min-height: ${FFT_MIN_HEIGHT}px;`));
assert.ok(rule('.analysis__fftplot').includes(`min-height: ${FFT_PLOT_MIN}px;`));
assert.match(rule('.analysis__fftbar .field'),/flex-direction: row;/);
assert.match(rule('.analysis__fftbar .field'),/margin-bottom: 0;/);
assert.match(rule('.analysis__fftbar .field'),/font-size: 12px;/);
assert.match(rule('.analysis__splitter--lower'),/padding-left: 10px;/,'B 左側保留不被標題列控件覆蓋的拖曳帶');
const prefs = Object.freeze({ ...defaults(), side:280, lower:180, fft:220, sideCollapsed:false });
const layout = (vw,vh,p = defaults(),fftOn = false,extra = {}) => clampLayout({ W:vw-24,H:vh-200,vw,vh,prefs:p,fftOn,...extra });
for (const [vw,vh] of [[1360,860],[1280,800],[1366,768],[1024,768],[900,600],[923,768],[1100,860],[1123,860]]) for (const fftOn of [true,false]) {
  const before = JSON.stringify(prefs), e = layout(vw,vh,prefs,fftOn);
  assert.ok(e.mainGrid >= 240); assert.ok(!fftOn || e.fftCollapsed || e.fft >= 160);
  if (fftOn && !e.fftCollapsed) assert.ok(e.fft - FFT_BAR_HEIGHT >= FFT_PLOT_MIN);
  assert.ok(e.side+10+e.plotWidth <= vw-24);
  assert.ok(e.lowerCollapsed || e.lower >= 120); assert.equal(JSON.stringify(prefs),before);
  assert.equal(e.scroll,e.usedHeight > vh-200);
  if (vw >= 900) assert.equal(e.drawer,false);
}
assert.equal(layout(1360,860).overview,56);
for (const vw of [900,923]) assert.equal(layout(vw,860,{ ...defaults(),sideCollapsed:false }).side,240);
for (const vw of [1100,1123]) assert.equal(layout(vw,1000,defaults(),true).tabbed,false);
assert.equal(layout(1024,768).side,36);
const drawer = layout(880,900,prefs,false,{ drawerOpen:true });
assert.equal(drawer.side,36); assert.equal(drawer.drawer,true); assert.equal(drawer.drawerWidth,280); assert.equal(drawer.sideCollapsed,false);
assert.equal(layout(880,900,prefs).drawer,false);
const large = layout(1360,1200,prefs,true);
layout(900,400,prefs,true); assert.deepEqual(layout(1360,1200,prefs,true),large);
assert.equal(large.fft,220); assert.equal(large.lower,180); assert.equal(large.overview,40);
// 明確展開 B 時跳過 lower，改壓 FFT／分頁／捲動。
const forced = { ...prefs,lower:200,fft:240 };
assert.deepEqual(layout(1360,1020,forced,true).steps,['overview']);
assert.deepEqual(layout(1360,900,forced,true).steps,['overview','lower']);
assert.deepEqual(layout(1360,800,forced,true).steps,['overview','lower','fft']);
const expanded = layout(1360,860,{ ...forced,lowerCollapsed:false },true);
assert.equal(expanded.lower,200); assert.equal(expanded.lowerCollapsed,false); assert.ok(expanded.tabbed);
// overview 的 330/270 門檻不因設定尺寸與否而變；分頁只用一份 28px 預算。
for (const [vh,fftOn,lower,fft,expected] of [[960,true,174.8,160,0],[750,false,160,null,56]]) {
 assert.equal(layout(1360,vh,defaults(),fftOn).overview,expected);
 assert.equal(layout(1360,vh,{ ...defaults(),lower,fft },fftOn).overview,expected);
}
const tab = layout(900,900,defaults(),true);
assert.equal(tab.usedHeight,700);
assert.ok(layout(500,300,prefs,false).mainGrid >= 240);
const tiny = layout(500,400,prefs,true);
assert.ok(tiny.scroll && tiny.tabbed && tiny.mainGrid >= 240); assert.equal(tiny.steps.at(-1),'scroll');
assert.equal(layout(1360,1200,{ ...prefs,fftCollapsed:true },true).fft,0);
for (const bad of [null,[],42,'bad',{ version:2,side:200 },{ version:1,side:'250',lower:NaN,overview:1 }]) assert.deepEqual(validatePrefs(bad),defaults());
assert.deepEqual(validatePrefs({ version:1,side:999,lower:-4,fft:9999 }),{ ...defaults(),side:360,lower:120,fft:900 });
let stored = null;
const storage = () => ({ getItem:() => stored,setItem:(_k,v) => { stored = v; } });
savePrefs({ ...prefs,overview:true,side:999,lower:-1,fft:9999 },storage);
assert.equal(JSON.parse(stored).side,360); assert.equal(JSON.parse(stored).lower,120); assert.equal(JSON.parse(stored).fft,900);
assert.deepEqual(loadPrefs(storage),{ ...prefs,side:360,lower:120,fft:900 });
assert.ok(!stored.includes('overview'));
savePrefs(prefs,storage); assert.deepEqual(loadPrefs(storage),prefs);
assert.ok(!stored.includes('effective')); stored = '{bad'; assert.deepEqual(loadPrefs(storage),defaults());
stored = '{"version":99}'; assert.deepEqual(loadPrefs(storage),defaults());
const denied = () => { throw Error('拒絕儲存'); };
savePrefs(prefs,denied); assert.deepEqual(loadPrefs(denied),prefs);
for (const [kind,min] of [['side',180],['lower',120],['fft',160]]) {
  assert.equal(resizeValue(kind,250,-10000),min); assert.equal(resizeValue(kind,250,10000,300),300);
  assert.equal(resetPref(prefs,kind)[kind],defaults()[kind]);
}
function element() {
  return { listeners:{}, attrs:{}, style:{}, children:[], append(b) { this.children.push(b); },
    setAttribute(k,v) { this.attrs[k] = v; }, addEventListener(k,fn) { this.listeners[k] = fn; },removeEventListener() {},
    getBoundingClientRect() { return { top:86,height:28 }; },setPointerCapture() { this.captured = true; },hasPointerCapture() { return this.captured; },releasePointerCapture() { this.captured = false; } };
}
globalThis.window = element();
let frames = new Map(), next = 1;
globalThis.requestAnimationFrame = (f) => { frames.set(next,f); return next++; };
globalThis.cancelAnimationFrame = (id) => frames.delete(id);
const flush = () => { const jobs = [...frames.values()]; frames.clear(); jobs.forEach(f => f()); };
for (const kind of ['side','lower','fft']) {
  const host = element(), button = element(), store = createStore(); let updates = 0, dragging = false;
  const ctl = bindLayoutCommands(store,{ initial:{ ...prefs,lowerCollapsed:false },persist:() => { updates++; },schedule:() => {},dragging:(v) => { dragging = v; },viewport:() => 1360 });
  ctl.update({ ...large,main:500,lowerCollapsed:false });
  const value = () => ctl.prefs[kind] ?? (kind === 'side' ? 240 : 180);
  const api = mountSplitter(host,{ kind,button,store,getState:() => ctl.state(kind) });
  const refresh = () => ctl.update({ ...large,main:500,[kind+'Collapsed']:!!ctl.prefs[kind+'Collapsed'] });
  const fire = (name,extra = {}) => host.listeners[name]({ target:host,button:0,pointerId:1,clientX:100,clientY:100,preventDefault() {},...extra });
  const old = value(); fire('keydown',{ key:kind === 'side' ? 'ArrowRight' : 'ArrowUp' }); assert.equal(value(),old+10);
  fire('keydown',{ key:kind === 'side' ? 'ArrowRight' : 'ArrowUp',shiftKey:true }); assert.equal(value(),old+50);
  fire('keydown',{ key:'Enter' }); refresh(); assert.equal(ctl.prefs[kind+'Collapsed'],true);
  const frozen = JSON.stringify(ctl.prefs); fire('keydown',{ key:kind === 'side' ? 'ArrowRight' : 'ArrowUp' }); fire('pointerdown'); fire('pointermove',{ clientX:200,clientY:20 }); fire('pointerup'); flush(); assert.equal(JSON.stringify(ctl.prefs),frozen); assert.equal(dragging,false);
  button.onclick(); refresh(); assert.equal(ctl.prefs[kind+'Collapsed'],false);
  if (kind !== 'side') { fire('pointerdown',{ clientY:85 }); assert.equal(dragging,false); }

  fire('pointerdown'); assert.ok(host.captured && dragging);
  const move = kind === 'side' ? { clientX:-9999 } : { clientY:9999 };
  const before = updates; for (let i=0;i<30;i++) fire('pointermove',move);
  assert.equal(updates,before); flush(); assert.equal(updates,before+1);
  assert.equal(value(),kind === 'side' ? 180 : kind === 'lower' ? 120 : 160); assert.equal(ctl.prefs[kind+'Collapsed'],false);
  window.listeners.keydown({ key:'Escape' }); assert.equal(value(),old+50); assert.equal(dragging,false); assert.equal(host.captured,false);
  fire('pointermove',move); flush(); assert.equal(value(),old+50);
  fire('pointerdown'); fire('pointermove',move); fire('pointerup'); assert.equal(value(),kind === 'side' ? 180 : kind === 'lower' ? 120 : 160);
  const committed = value(); fire('pointerdown'); fire('pointermove',kind === 'side' ? { clientX:150 } : { clientY:50 }); flush(); fire('pointercancel'); assert.equal(value(),committed);
  fire('dblclick'); assert.equal(ctl.prefs[kind],defaults()[kind]); assert.equal(ctl.prefs[kind+'Collapsed'],defaults()[kind+'Collapsed']);
  api.update({ value:240,collapsed:false,max:360 }); assert.equal(host.attrs['aria-valuenow'],'240'); assert.equal(button.attrs['aria-expanded'],'true');
  assert.equal(host.attrs['aria-valuemin'],String(kind === 'side' ? 180 : kind === 'lower' ? 120 : 160));
  assert.equal(host.attrs['aria-orientation'],kind === 'side' ? 'vertical' : 'horizontal'); api.dispose();
}
// B 有足夠空間時，真正 pointer 事件向上拖 30px，偏好／版面／ARIA 都要變高。
{
 const store = createStore(), host = element(), button = element();
 const ctl = bindLayoutCommands(store,{ initial:{ ...defaults(),lower:180,lowerCollapsed:false },persist:() => {},schedule:() => {},viewport:() => 1360 });
 const compute = () => layout(1360,860,ctl.prefs,false);
 ctl.update(compute());
 const api = mountSplitter(host,{ kind:'lower',button,store,getState:() => ctl.state('lower') });
 api.update(ctl.state('lower'));
 assert.ok(ctl.state('lower').max >= 210,'起點 180 尚有至少 30px 長高空間');
 const fire = (name,y,target = host) => host.listeners[name]({ target,button:0,pointerId:1,clientY:y,preventDefault() {} });
 fire('pointerdown',100,button); assert.ok(!host.captured,'收折鈕不啟動拖曳');
 fire('pointerdown',100); assert.ok(host.captured);
 fire('pointermove',70); fire('pointerup',70); flush();
 const e = compute(); ctl.update(e); api.update(ctl.state('lower'));
 assert.equal(ctl.prefs.lower,210); assert.equal(e.lower,210);
 assert.equal(host.attrs['aria-valuenow'],'210'); assert.ok(e.mainGrid >= 240);
 api.dispose();
}
// 實際 tab_analysis state/max/toggle/resize 接線。
{
 const store = createStore(); let saves = 0, scheduled = 0, report;
 store.onCommand('layout.state',v => { report = v; });
 const ctl = bindLayoutCommands(store,{ initial:{ ...defaults(),side:280,lower:250,fft:240 },persist:() => saves++,schedule:() => scheduled++,viewport:() => 880 });
 ctl.update({ ...large,side:36,drawer:false,lower:28,fft:160,main:300,lowerCollapsed:true,fftCollapsed:false });
 assert.equal(ctl.state('lower').value,250); assert.equal(ctl.state('fft').value,240); assert.equal(ctl.state('fft').max,190);
 store.command('layout.toggle','lower'); assert.equal(ctl.prefs.lowerCollapsed,false);
 store.command('layout.toggle','side'); assert.equal(ctl.drawerOpen,true); assert.equal(ctl.prefs.sideCollapsed,null);
 store.command('layout.resize',{ kind:'fft',value:200 }); assert.equal(ctl.prefs.fft,200);
 ctl.update({ ...large,tabbed:true,overview:0 }); assert.deepEqual(report,{ overview:false });
 const host = element(), button = element(); const api = mountSplitter(host,{ kind:'fft',button,store,getState:() => ctl.state('fft') });
 api.update(ctl.state('fft')); assert.equal(host.hidden,true); assert.equal(host.attrs['aria-disabled'],'true');
 const before = JSON.stringify(ctl.prefs);
 host.listeners.pointerdown({ button:0,target:host,pointerId:1,clientY:100,preventDefault() {} }); assert.ok(!host.captured);
 host.listeners.keydown({ target:host,key:'ArrowUp',preventDefault() {} });
 store.command('layout.resize',{ kind:'fft',value:400 }); store.command('layout.toggle','fft'); assert.equal(JSON.stringify(ctl.prefs),before);
 const saved = saves; store.command('preview.visible',true); assert.equal(ctl.prefs.overview,true); assert.equal(saves,saved); assert.ok(scheduled); api.dispose();
}
// 從自動退讓狀態按「展開」：使用真正 toggle 與 clamp，持續重算也不得壓回 B。
{
 const store = createStore();
 const ctl = bindLayoutCommands(store,{ initial:defaults(),persist:() => {},schedule:() => {},viewport:() => 1360 });
 const compute = () => layout(1360,600,ctl.prefs,true);
 ctl.update(compute()); assert.equal(compute().lowerCollapsed,true);
 store.command('layout.toggle','lower'); assert.equal(ctl.prefs.lowerCollapsed,false);
 for (let i=0;i<3;i++) {
   const e = compute(); ctl.update(e);
   assert.equal(e.lowerCollapsed,false); assert.ok(e.lowerBody > 0); assert.ok(!e.steps.includes('lower'));
 }
}
// 真正主圖與縮圖：拖曳期間包含寬度變動也不抓 /wave，純高度變動不抓。
const { mount:mountPlot } = await import('./mainplot.js');
const { mount:mountOverview } = await import('./overview.js');
const g = new Proxy({}, { get:(o,k) => k === 'measureText' ? () => ({ width:0 }) : o[k] ?? (() => {}),set:(o,k,v) => ((o[k]=v),true) });
let width = 800, height = 330, fetches = 0;
const observers = [];
globalThis.ResizeObserver = class { constructor(fn) { this.fn = fn; observers.push(this); } observe() {} disconnect() {} };
globalThis.document = { activeElement:null,createElement:() => ({ ...element(),getContext:() => g }) };
window.devicePixelRatio = 2;
const source = createStore();
source.set({ file:{ gen:1,channels:[{ name:'CH1',t0:0,t1:1 }] },view:{ t0:0,t1:1 },channels:[{ name:'CH1',visible:true,derived:false,scale:1,position:0,time_offset:0,vmin:-1,vmax:1 }] });
let finishReadout, reads = 0;
const bridge = {
 fetchWave:async () => { fetches++; return { n:0,mode:0,x:[],lo:[],hi:[] }; },
 call:() => { reads++; return new Promise(resolve => { finishReadout = resolve; }); }
};
const plotHost = { ...element(),getBoundingClientRect:() => ({ width,height }) };
const overviewHost = { ...element(),getBoundingClientRect:() => ({ width,height:56 }) };
const plot = mountPlot(plotHost,{ store:source,bridge,ui:{} }), overview = mountOverview(overviewHost,{ store:source,bridge });
await Promise.resolve(); flush(); await new Promise(r => setTimeout(r,170));
assert.equal(fetches,2); assert.equal(plotHost.children[0].width,1600);
source.command('layout.dragging',true); width = 650;
observers.forEach(o => o.fn()); flush(); await new Promise(r => setTimeout(r,170));
assert.equal(fetches,2); assert.equal(plotHost.children[0].width,1300);
source.command('layout.dragging',false); await new Promise(r => setTimeout(r,170)); assert.equal(fetches,4);
height = 270; observers.forEach(o => o.fn()); flush(); await new Promise(r => setTimeout(r,170)); assert.equal(fetches,4);
assert.equal(plotHost.children[0].height,540);
source.command('layout.dragging',true); source.set({ file:{ ...source.get().file,gen:2 } });
await new Promise(r => setTimeout(r,170)); assert.equal(fetches,4);
source.command('layout.dragging',false); await new Promise(r => setTimeout(r,170)); assert.equal(fetches,6);
const cursors = createController({ store:source,bridge },{ delay:1 });
bindViewport(source);
// 回中央的 user 寫入是同步，真正取樣點吸附在 RPC 回來後才寫；重現前後快照差異。
source.set({ cursors:{ x1:-2.0004e-6,x2:1.9994e-6,y1:1,y2:-1 } });
cursors.reset();
const beforeSnap = { ...source.get().cursors };
await new Promise(r => setTimeout(r,5)); assert.equal(reads,1);
finishReadout({ t1:beforeSnap.x1+4e-10,t2:beforeSnap.x2-4e-10,y:{} });
await Promise.resolve(); await Promise.resolve();
assert.notDeepEqual(source.get().cursors,beforeSnap,'未等待回中央 RPC 就取快照，會觀察到稍後的合法吸附');
const settled = { ...source.get().cursors }, channels = structuredClone(source.get().channels);
const cursorWrites = [];
source.on(['cursors'],(_s,_keys,origin) => cursorWrites.push(origin));
// 已有游標控制器時，再走寬／高 resize 與同寬 missed 補取。
source.command('layout.dragging',true); width = 600;
observers.forEach(o => o.fn()); flush(); await new Promise(r => setTimeout(r,170));
source.command('layout.dragging',false); await new Promise(r => setTimeout(r,170));
height = 300; observers.forEach(o => o.fn()); flush(); await new Promise(r => setTimeout(r,170));
source.command('layout.dragging',true); source.set({ view:{ t0:.1,t1:.9 } });
await new Promise(r => setTimeout(r,170));
source.command('layout.dragging',false); await new Promise(r => setTimeout(r,170));
// 同一控制器已吸附後，框選範圍／Undo／20n view 更新與完成的 /wave 不得再吸附。
for (const view of [{ t0:.2,t1:.7 },null,{ t0:.5-100e-9,t1:.5+100e-9 }]) {
 if (view) source.command('viewport.intent',view); else source.command('view.undo');
 await new Promise(r => setTimeout(r,170));
 assert.deepEqual(source.get().cursors,settled); assert.deepEqual(source.get().channels,channels);
}
assert.equal(reads,1,'resize／missed 補取／view 不得觸發傳統游標讀值');
assert.deepEqual(cursorWrites,[],'包含 /wave 完成重繪也不得寫游標');
plot.dispose(); overview.dispose();
console.log('P2b self-check OK：尺寸矩陣／退讓順序／偏好往返與驗證／儲存失敗／splitter 真實鍵盤拖曳與取消');
if (process.argv.includes('--mutations')) {
  const { readFileSync,writeFileSync,cpSync,mkdtempSync,rmSync } = await import('node:fs');
  const { spawnSync } = await import('node:child_process');
  const { fileURLToPath } = await import('node:url'); const { tmpdir } = await import('node:os'); const { join } = await import('node:path');
  const mutations = [
    ['B 標題列覆蓋拖曳帶','../../css/analysis.css','padding-left: 10px; justify-content: flex-start;','padding-left: 0; justify-content: flex-start;'],
    ['B 向上拖不長高','splitter.js','(coordinate(e)-drag.at)*(vertical ? 1 : -1)',"(coordinate(e)-drag.at)*(vertical || kind === 'lower' ? 1 : -1)"],
    ['FFT 標籤恢復垂直','../../css/analysis.css','flex-direction: row; align-items: center; margin-bottom: 0;','flex-direction: column; align-items: center; margin-bottom: 0;'],
    ['FFT 標籤恢復留白','../../css/analysis.css','margin-bottom: 0; font-size: 12px;','margin-bottom: 12px; font-size: 12px;'],
    ['FFT 標籤字體縮小','../../css/analysis.css','margin-bottom: 0; font-size: 12px;','margin-bottom: 0; font-size: 10px;'],
    ['FFT 控制列預算漂移','layout.js','FFT_BAR_HEIGHT = 40','FFT_BAR_HEIGHT = 56'],
    ['FFT 繪圖下限不足','layout.js','FFT_PLOT_MIN = 120','FFT_PLOT_MIN = 100'],
    ['FFT 總高度漏控制列','layout.js','FFT_MIN_HEIGHT = FFT_BAR_HEIGHT + FFT_PLOT_MIN','FFT_MIN_HEIGHT = FFT_PLOT_MIN'],
    ['拿掉硬下限','layout.js','Math.max(270, room())','Math.max(0, room())'],
    ['退讓次序錯','layout.js',"if (room() < (fftOn ? 330 : 270) && overview)","if (false && overview)"],
    ['覆寫偏好','layout.js','const p = validatePrefs(prefs), steps = [];','prefs.side = 36; const p = validatePrefs(prefs), steps = [];'],
    ['拖曳穿越下限','layout.js','clip(start + delta, min,','clip(start + delta, 0,'],
    ['雙擊不回預設','splitter.js',"store.command('layout.reset',kind)","store.command('layout.toggle',kind)"],
    ['收折仍可拖','splitter.js','if (s.collapsed || s.disabled) return;','if (s.disabled) return;'],
    ['收折方向鍵','splitter.js','if (s.collapsed) return;',''],
    ['水平命中帶','splitter.js','> 5) return;','> 50) return;'],
    ['pointercancel 提交','splitter.js',"host.addEventListener(name, () => end(true))","host.addEventListener(name, () => end(false))"],
    ['savePrefs 未驗證','layout.js','memory = validatePrefs(p);','memory = p;'],
    ['drawerWidth 遺失','layout.js','drawerWidth:p.side','drawerWidth:36'],
    ['Shift 步長','splitter.js','e.shiftKey ? 40 : 10','e.shiftKey ? 10 : 10'],
    ['aria 下限','splitter.js',": kind === 'lower' ? 120 : 160",": kind === 'lower' ? 100 : 100"],
    ['toggle 接線','tab_analysis.js',"!effective[kind+'Collapsed']","effective[kind+'Collapsed']"],
    ['resize 接線','tab_analysis.js','[kind]:value','[kind]:180'],
    ['state 誤取 effective','tab_analysis.js',"prefs[kind] ?? (kind === 'side' ? 240 : kind === 'lower' ? 180 : 180)","e[kind]"],
    ['max 接線','tab_analysis.js','shown + Math.max(0,e.main-270)','900'],
    ['分頁 splitter 啟用','tab_analysis.js',"kind === 'fft' && e.tabbed","false"],
    ['傳統游標跟 view 重算','cursors.js',"s.markerMode === \"Track Waveforms\"",'true'],
    ['F 主圖漏補取','mainplot.js','missed || w !== lastWidth','w !== lastWidth'],
    ['F 縮圖漏補取','overview.js','missed || W !== loadedWidth','W !== loadedWidth'],
    ['視窗寬門檻','layout.js','vw <= 899','W <= 899'],
    ['視窗高門檻','layout.js','vh > 700','H > 700'],
    ['1100 門檻','layout.js','|| vw < 1100','|| W < 1100'],
    ['明確展開仍退讓','layout.js',' && p.lowerCollapsed !== false',''],
    ['窄版自動開抽屜','layout.js','narrow && drawerOpen','narrow && p.sideCollapsed === false'],
    ['分頁重扣 28','layout.js','H - chrome - separators - lower - overview);','H - chrome - separators - lower - overview - 28);'],
    ['overview 門檻依賴偏好','layout.js','(fftOn ? 330 : 270)','(p.fft === null && p.lower === null ? 330 : 270)'],
    ['overview 被持久化','layout.js','JSON.stringify({ ...memory, overview:undefined })','JSON.stringify({ ...memory,overview:true })'],
  ];
  const temp = mkdtempSync(join(tmpdir(),'scope-p2b-'));
  try {
    cpSync(fileURLToPath(new URL('../',import.meta.url)),join(temp,'js'),{ recursive:true });
    cpSync(fileURLToPath(new URL('../../css/',import.meta.url)),join(temp,'css'),{ recursive:true });
    for (const [name,file,old,changed] of mutations) {
      const path = join(temp,'js/analysis',file), original = readFileSync(path,'utf8'); assert.ok(original.includes(old));
      try { writeFileSync(path,original.replace(old,changed));
        const result = spawnSync(process.execPath,[join(temp,'js/analysis/p2b_check.mjs')],{ encoding:'utf8' });
        assert.notEqual(result.status,0,`${name}：未抓到變異`); assert.match(result.stderr,/AssertionError|TypeError/); console.log(`${name}：如預期失敗`);
      } finally { writeFileSync(path,original); }
    }
  } finally { rmSync(temp,{ recursive:true,force:true }); }
  console.log(`P2b 變異驗證 ${mutations.length}/${mutations.length} self-check OK（暫存副本）`);
}
