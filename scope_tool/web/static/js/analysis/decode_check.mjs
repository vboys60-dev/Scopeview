// P3：直接測產品控制器、DOM 接線與世代競態；P4 再追加標註列／報告。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createStore } from './store.js';
import { REASONS, jumpView, parseAddresses, createDecode, decodeParams, defaultConfig } from './decode.js';
import { mount, frameContent, tableFrames } from './decode_table.js';
import { mountTabs, validate } from './bpanel.js';
const contract = JSON.parse(fs.readFileSync(new URL('../../api_contract.json',import.meta.url)));
assert.deepEqual(Object.keys(REASONS).sort(),contract.types_doc['DecodeFrame.reasons'].split(' ').sort());
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
  m.change({ band:false }); assert.equal(store.get().decodeResult.stale,true); assert.equal(jobs.length,1);
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
store.set({ decodeResult:{ summary:{ ...summary,counts:{ ...summary.counts,frames:many.length } },frames:many,addresses:[],scl:'CH1',stale:false } });
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
// 精準變異產品原文，驗證置中／token 守門的測試確實能抓錯。
if (process.argv.includes('--mutations')) {
  const source = fs.readFileSync(new URL('./decode.js',import.meta.url),'utf8');
  for (const [from,to,check] of [
    ['(frame.t0+frame.t1)/2+dx','frame.t0+dx',m => checkJump(m.jumpView)],
    ['t === token && g ===','true && g ===',m => runnerChecks(m.createDecode)],
  ]) {
    assert.ok(source.includes(from));
    const mutated = await import('data:text/javascript;base64,'+Buffer.from(source.replace(from,to)).toString('base64'));
    await assert.rejects(async () => check(mutated));
  }
  console.log('decode mutations self-check OK');
}
console.log('decode self-check OK');
