// 直接測產品控制器、DOM 接線、標註列與世代競態。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createStore } from './store.js';
import { REASONS } from './decode_i3c.js';
import { jumpView, parseAddresses, createDecode, decodeParams, defaultConfig } from './decode.js';
import { mount, frameContent, tableFrames } from './decode_table.js';
import { BAND_H, visibleFrames, bandLayout, bitCells, ninthLabel, drawBand, mount as mountBand } from './decode_band.js';
import { mountTabs, validate } from './bpanel.js';
const contract = JSON.parse(fs.readFileSync(new URL('../../api_contract.json',import.meta.url)));
assert.deepEqual(Object.keys(REASONS).sort(),contract.types_doc['DecodeFrame.reasons.i3c'].split(' ').sort());
assert.deepEqual(parseAddresses('50, 0x51,50'),[80,81]); assert.deepEqual(parseAddresses(''),[]);
for (const s of ['80','-1','50,','xyz']) assert.throws(() => parseAddresses(s));
assert.throws(() => decodeParams(defaultConfig([])));
const channels = ['CH1','CH2'].map((name,i) => ({ name, time_offset:i*.1 }));
const view = { t0:0,t1:10 }, frame = { i:1,t0:2,t1:3,kind:'private_write',addr:8,rw:0,status:'error',reasons:['parity'],fields:[{ kind:'data',value:129,nbits:8,ok:false }] };
function checkJump(fn) {
  for (const f of [frame,{ ...frame,t1:22 }]) {
    const v = fn(f,view,.5), span = v.t1-v.t0;
    assert.ok(Math.abs((v.t0+v.t1)/2-((f.t0+f.t1)/2+.5)) < 1e-9*span);
    assert.equal(span,f.t1-f.t0 <= 8 ? 10 : (f.t1-f.t0)*1.25);
  }
}
checkJump(jumpView); assert.match(frameContent(frame),/⚠0x81/);
const makeStore = () => { const s = createStore(); s.set({ file:{ gen:1 },channels }); return s; };
const summary = { ok:true,gen:1,decode_id:'d1',counts:{ frames:1,errors:1,warns:0 },thresholds:{ scl:[.673917,1.04878],sda:[.8,1] },warnings:[] };
const data = { frames:[frame],addresses:[{ da:8,pid:null,bcr:null,dcr:null,t_from:null,t_to:null,how:'observed' }] };
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise,resolve }; };
async function runnerChecks(factory) {
  const store = makeStore(), jobs = [], calls = [];
  const bridge = { job() { const d = deferred(); jobs.push(d); return d.promise; },
    async call(name) { calls.push(name); return data; } };
  const m = factory({ store,bridge });
  let pending = m.run(); jobs.at(-1).resolve(summary); await pending;
  assert.equal(store.get().decodeResult.frames[0],frame);
  m.change({ band:false }); assert.equal(store.get().decodeResult.stale,false);
  m.change({ opt:{ i2c_addrs:[80] } }); assert.equal(store.get().decodeResult.stale,true); assert.equal(jobs.length,1);
  pending = m.run(); m.change(); jobs.at(-1).resolve(summary); await pending;
  assert.equal(store.get().decodeResult,null); assert.equal(calls.length,1);
  pending = m.run(); store.set({ file:{ gen:2 } }); jobs.at(-1).resolve(summary); await pending;
  assert.equal(store.get().decodeResult,null); assert.equal(store.get().decodeSel,null);
  store.set({ file:{ gen:1 } });
  pending = m.run(); jobs.at(-1).resolve({ ...summary,ok:false,reason:'SDA 無轉態' }); await pending;
  assert.equal(m.message,'SDA 無轉態'); assert.equal(calls.length,1);
  pending = m.run(); jobs.at(-1).resolve({ ...summary,gen:9 }); await pending;
  assert.equal(store.get().decodeResult,null);
  // 已開始取 frames 後換設定，仍不得寫入。
  const late = deferred(); bridge.call = () => late.promise;
  pending = m.run(); jobs.at(-1).resolve(summary); await Promise.resolve(); m.change(); late.resolve(data); await pending;
  assert.equal(store.get().decodeResult,null);
  // 連按兩次：先回來的舊工作也不能覆蓋最新工作。
  bridge.call = async () => data;
  const first = m.run(), a = jobs.at(-1), second = m.run(), b = jobs.at(-1);
  b.resolve(summary); await second; const latest = store.get().decodeResult;
  a.resolve(summary); await first; assert.equal(store.get().decodeResult,latest);
  store.set({ file:null }); assert.equal(store.get().decodeResult,null);
}
await runnerChecks(createDecode);
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.value = ''; this.textContent = ''; this.className = ''; this.style = {};
    this.classList = { add:k => { this.className += ' '+k; }, toggle:(k,on) => { const set = new Set(this.className.split(' ')); on ? set.add(k) : set.delete(k); this.className = [...set].join(' '); } }; }
  append(...nodes) { for (const n of nodes) { n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(k,f) { this.listeners[k] = f; }
  setCustomValidity(s) { this.validityMessage = s; }
  reportValidity() { return !this.validityMessage; }
}
globalThis.document = { createElement:t => new Element(t) };
const find = (e,fn) => fn(e) ? e : e.children.map(c => find(c,fn)).find(Boolean);
const store = makeStore(), host = new Element('div'), labels = [], toasts = [], exports = [];
const ctx = { store, bridge:{ async job() { return summary; }, async call(n,p) { if (n === 'export_decode') { exports.push(p); return { path:'/tmp/test.csv' }; } return data; } },
  ui:{ toast:(...a) => toasts.push(a) }, resultTabs:{ label:(...a) => labels.push(a) } };
const panel = mount(host,ctx); await panel.model.run();
assert.deepEqual(labels.at(-1),['decode','解碼 (1)']);
assert.equal(find(host,e => e.attrs['aria-label'] === 'SCL lo').value,'674 mV');
assert.equal(find(host,e => e.attrs['aria-label'] === 'SCL hi').value,'1.05 V');
assert.ok(find(host,e => String(e.textContent).includes('I3C Basic SDR')).textContent.includes('SCL 674 mV / 1.05 V'));
let intents = 0; store.onCommand('viewport.intent',() => intents++);
let row = find(host,e => e.dataset.decodeFrame === '1'); row.onclick();
assert.equal(row.children[0].textContent,2); // 顯示從 1 起算，點列仍用原始 i。
assert.equal(intents,1); assert.equal(store.get().decodeSel,1); assert.match(row.className,/is-selected/);
row.onkeydown({ key:'Enter',preventDefault() {} }); assert.equal(intents,2);
assert.equal(find(host,e => e.tagName === 'td' && e.textContent === '同位錯').className,'decode__error');
await panel.model.exportCsv(); assert.deepEqual(exports,[{ decode_id:'d1',directory:null }]);
ctx.bridge.call = async () => { throw { code:'STALE' }; }; await panel.model.exportCsv(); assert.match(toasts.at(-1)[0],/解碼結果已過期/);
panel.model.change(); await panel.model.exportCsv(); assert.equal(exports.length,1);
const many = Array.from({ length:2105 },(_,i) => ({ ...frame,i,status:i%2 ? 'ok' : 'warn' }));
store.set({ decodeResult:{ summary:{ ...summary,counts:{ ...summary.counts,frames:many.length } },frames:many,addresses:[],base:'CH1',protocol:'i3c',stale:false } });
const tbody = find(host,e => e.tagName === 'tbody'); assert.equal(tbody.children.length,2000);
assert.equal(tbody.children[0].children[0].textContent,1); assert.equal(tbody.children[0].dataset.decodeFrame,'0');
assert.ok(find(host,e => e.className === 'decode__foot').textContent.includes('僅顯示前 2000 筆'));
find(host,e => e.tagName === 'button' && e.textContent === '只錯誤／警告').onclick(); assert.equal(tbody.children.length,1053);
assert.equal(tableFrames(many,true).total,1053);
// 頁籤可還原，在浮動／停靠尺寸可見；舊宿主不提供 decode panel 也能掛載。
for (const include of [false,true]) {
  const body = new Element('div'), panels = Object.fromEntries(['measure','cursor','marker','peaks',...(include ? ['decode'] : [])].map(k => [k,new Element('div')]));
  body.append(...Object.values(panels)); const tabHost = new Element('div');
  const tabs = mountTabs(tabHost,panels,{ initial:{ version:1,tab:include ? 'decode' : 'measure' },persist() {} });
  for (const dims of [{ width:450,height:400 },{ width:1400,height:180,docked:true }]) { tabs.update(dims); if (include) assert.equal(panels.decode.hidden,false); }
  tabs.label('decode','解碼 (7)'); if (include) assert.equal(find(tabHost,e => e.dataset.resultTab === 'decode').textContent,'解碼 (7)');
}
assert.equal(validate({ version:1,tab:'decode' }).tab,'decode');
// P4：排序區間查找、裁切、合併、真實取樣點與精確 10px 門檻。
const spans = Array.from({ length:1000 },(_,i) => ({ ...frame,i,t0:i*3,t1:i*3+2,fields:[] }));
spans[0] = { ...spans[0],t0:-100,t1:2 };
function rangeChecks(findVisible) {
  let seed = 31;
  for (let i = 0; i < 1000; i++) {
    seed = (seed*16807)%2147483647; const a = seed%3000-100, b = a+seed%120;
    assert.deepEqual(findVisible(spans,a,b),spans.filter(f => f.t1 >= a && f.t0 <= b));
  }
  assert.deepEqual(findVisible(spans,2,2),[spans[0]]);
}
rangeChecks(visibleFrames);
const field = { t0:0,t1:8,nbits:9,value:0x5A,ninth:1,ninth_kind:'parity',ok:true };
const transaction = { ...frame,i:0,t0:-1,t1:10,label:'私有寫',fields:[field] };
const rect = { l:113,w:800 }, bitView = { t0:0,t1:80 };
assert.equal(bandLayout([transaction],bitView,rect).fields[0].bitMode,true);
assert.equal(bandLayout([transaction],{ t0:0,t1:80.01 },rect).fields[0].bitMode,false);
const layout = bandLayout([transaction],{ t0:0,t1:10 },rect);
assert.equal(layout.bars[0].x0,rect.l); assert.equal(layout.bars[0].label,transaction.label);
assert.equal(bandLayout([transaction],{ t0:0,t1:1000 },rect).bars[0].label,'');
const tiny = bandLayout(spans.slice(1,30),{ t0:0,t1:30000 },rect);
assert.equal(tiny.bars.length,1); assert.equal(tiny.bars[0].label,'');
const samples = Array.from({ length:9 },(_,i) => [i,i%2]);
const cells9 = bitCells(field,samples,t => t*10,2);
assert.equal(cells9.length,9); assert.equal(cells9[8].label,'P✓'); assert.equal(cells9[0].sample,20);
assert.equal(bitCells(field,[[0,0],[1,1],[3,0],[8,1]],t => t)[1].x1,2);
assert.deepEqual(['ack','ack','parity','parity','tbit','tbit'].map((kind,i) => ninthLabel({ ninth_kind:kind,ninth:i%2,ok:i!==3 })),['A','N','P✓','P✗','T0','T1']);
const css = fs.readFileSync(new URL('../../css/analysis.css',import.meta.url),'utf8');
assert.equal(+css.match(/\.analysis__decodeband \{[^}]*height: (\d+)px/)[1],BAND_H);
// 假 Canvas 掛載真 mount：debounce、dx、快取、過期 RPC、點選與 dispose。
const originalDocument = globalThis.document, realTimeout = globalThis.setTimeout, realClear = globalThis.clearTimeout;
const ops = [], g = new Proxy({}, { get:(o,k) => o[k] ?? ((...a) => ops.push([k,...a])),set:(o,k,v) => (o[k]=v,true) });
const canvas = { dataset:{},style:{},getContext:() => g,getBoundingClientRect:() => ({ left:0,top:0 }) };
globalThis.document = { createElement:() => canvas };
globalThis.window = { devicePixelRatio:1 };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const timers = new Map(); let timerId = 0;
globalThis.setTimeout = fn => { timers.set(++timerId,fn); return timerId; };
globalThis.clearTimeout = id => timers.delete(id);
const flush = async () => { const fns = [...timers.values()]; timers.clear(); fns.forEach(fn => fn()); await Promise.resolve(); await Promise.resolve(); };
const bs = makeStore(), requests = [], hostBand = { hidden:false,append() {},getBoundingClientRect:() => ({ width:1000,height:40 }) };
const bc = { store:bs,bridge:{ call(name,p) { const d = deferred(); requests.push({ name,p,...d }); return d.promise; } } };
const bm = mountBand(hostBand,bc);
bs.set({ view:{ t0:1,t1:11 },channels:[{ name:'CH1',time_offset:2 }],plotRect:rect,
  decodeResult:{ summary,frames:[transaction],addresses:[],base:'CH1',protocol:'i3c',stale:false } });
await Promise.resolve(); await flush();
assert.equal(requests.length,1); assert.deepEqual(requests[0].p,{ decode_id:'d1',t0:-1,t1:9 });
bs.set({ view:{ t0:2,t1:12 } }); await flush();
requests[0].resolve({ bits:samples }); await Promise.resolve(); assert.equal(canvas.dataset.bits,'0');
requests[1].resolve({ bits:samples }); await Promise.resolve(); await Promise.resolve();
assert.equal(canvas.dataset.bits,'9'); bm.draw(); await flush(); assert.equal(requests.length,2);
canvas.onclick({ clientX:rect.l+rect.w/2,clientY:8 }); assert.equal(bs.get().decodeSel,0);
assert.ok(ops.some(op => op[0] === 'fillText' && op[1] === 'P✓'));
bs.set({ decodeResult:null }); bm.draw(); assert.equal(canvas.dataset.bits,'0');
bm.dispose();
globalThis.document = originalDocument; globalThis.setTimeout = realTimeout; globalThis.clearTimeout = realClear;
delete globalThis.window; delete globalThis.ResizeObserver;
// 精準變異產品原文，驗證置中／token 守門的測試確實能抓錯。
if (process.argv.includes('--mutations')) {
  const { mutate } = await import('./decode_proto_check.mjs');
  for (const [from,to,check] of [
    ['(frame.t0+frame.t1)/2+dx','frame.t0+dx',m => checkJump(m.jumpView)],
    ['t === token && g ===','true && g ===',m => runnerChecks(m.createDecode)],
  ]) {
    const mutated = await mutate('./decode.js',from,to);
    await assert.rejects(async () => check(mutated));
  }
  const mutatedBand = await mutate('./decode_band.js','frames[mid].t1 < t0','frames[mid].t1 <= t0');
  assert.throws(() => rangeChecks(mutatedBand.visibleFrames));
  console.log('decode mutations self-check OK');
}
console.log('decode self-check OK');
