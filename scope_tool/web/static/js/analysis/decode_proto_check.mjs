// 協定註冊、真表單與繪圖的泛化檢查；假協定不加入產品註冊。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as protocols from './decode_protocols.js';
import { createStore } from './store.js';
import { createDecode, defaultConfig, decodeParams } from './decode.js';
import { mount } from './decode_table.js';
import { drawBand, bandLayout, bitCells } from './decode_band.js';
import { decodeSection } from './report.js';
/** 載入在斷言之外；相對依賴一律以產品原檔為基準。 */
export function mutatedURL(file, from, to) {
  const url = new URL(file,import.meta.url), source = fs.readFileSync(url,'utf8');
  assert.ok(source.includes(from),`找不到變異原文：${from}`);
  const changed = source.replace(from,to).replace(/((?:from\s*|import\s*)['"])(\.{1,2}\/[^'"]+)(['"])/g,
    (_,a,spec,b) => a+new URL(spec,url).href+b);
  return 'data:text/javascript;base64,'+Buffer.from(changed).toString('base64');
}
export async function mutate(file, from, to) { return import(mutatedURL(file,from,to)); }
await assert.rejects(() => mutate('./decode.js','不存在的變異原文',''),/找不到變異原文/);
const harmless = await mutate('./decode.js','// 解碼狀態','// 無害註解：解碼狀態');
assert.equal(typeof harmless.createDecode,'function');
// 依賴載入錯誤也必須直接拒絕，不能算成產品斷言抓到變異。
await assert.rejects(() => mutate('./decode.js',"'./decode_protocols.js'","'./zz_missing.js'"),/Cannot find module/);
class Element {
  constructor(tag) {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.style = {};
    this.value = ''; this.textContent = ''; this.className = '';
    this.classList = { add:k => { this.className += ' '+k; },toggle() {} };
  }
  append(...nodes) { for (const n of nodes) { n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(k,f) { this.listeners[k] = f; }
  setCustomValidity(s) { this.validityMessage = s; }
  reportValidity() { return !this.validityMessage; }
}
const walk = e => [e,...e.children.flatMap(walk)];
const find = (e,f) => walk(e).find(f);
const oldDocument = globalThis.document;
globalThis.document = { createElement:t => new Element(t) };
const channels = ['CH1','CH2','CH3'].map(name => ({ name,time_offset:0 }));
const makeStore = () => { const s = createStore(); s.set({ file:{ gen:1 },channels,view:{ t0:0,t1:60 },plotRect:{ l:100,w:900 } }); return s; };
function result(def, options = {}) {
  const config = defaultConfig(channels,def), params = decodeParams(config,def);
  const frames = structuredClone(def.sample.frames);
  return { protocol:def.name,base:params.channels[def.base],options,stale:false,frames,addresses:structuredClone(def.sample.addresses),
    summary:{ ok:true,gen:1,decode_id:'d1',protocol:def.name,channels:params.channels,thresholds:Object.fromEntries(Object.keys(params.thresholds).map(k => [k,[.4,.6]])),
      counts:{ frames:frames.length,fields:frames.reduce((n,f) => n+f.fields.length,0),errors:0,warns:0 },warnings:[],truncated:false } };
}
const canvas = () => {
  const ops = [], g = new Proxy({}, { get:(o,k) => o[k] ?? (k === 'measureText' ? () => ({ width:0 }) : (...args) => ops.push([k,...args])),set:(o,k,v) => (o[k]=v,true) });
  return { g,ops };
};
const contract = JSON.parse(fs.readFileSync(new URL('../../api_contract.json',import.meta.url))).types_doc;
async function panelCheck(def, mountPanel = mount, draw = drawBand, report = decodeSection) {
  const store = makeStore(), host = new Element('div'), labels = [], r = result(def), jobs = [];
  const ctx = { store,resultTabs:{ label:(...a) => labels.push(a) },bridge:{ async job(n,p) { jobs.push(p); return r.summary; },async call() { return r; } } };
  const panel = mountPanel(host,ctx);
  if (def.name !== 'i3c') panel.model.change({ protocol:def.name });
  assert.equal(walk(host).filter(e => e.dataset.role).length,def.roles.length);
  assert.equal(walk(host).filter(e => e.dataset.line).length,def.roles.filter(r => !def.diff?.[r.key]).length*2);
  assert.equal(walk(host).filter(e => e.dataset.option).length,def.options.length);
  for (const role of def.roles.filter(r => r.optional)) {
    const select = find(host,e => e.dataset.role === role.key);
    assert.ok(select.children.some(e => e.value === '' && e.textContent === '—不使用—'));
  }
  store.set({ decodeResult:r });
  const rows = walk(host).filter(e => e.dataset.decodeFrame != null);
  assert.equal(rows.length,r.frames.length);
  assert.ok(rows.every(e => String(e.children[3+def.columns.length].textContent).length > 0));
  assert.deepEqual(labels.at(-1),['decode',`解碼 (${r.frames.length})`]);
  const { g,ops } = canvas(); draw(g,1000,store.get()); assert.ok(ops.some(op => op[0] === 'fillText'));
  const section = report(store.get(),{ querySelector:() => null },(v,u) => `${v} ${u}`,false)[0];
  assert.equal(section.title,`解碼（${def.label}）`);
  if (def.reportSummary) assert.ok(section.caption.includes(def.summary(r.summary,r.options)));
  else assert.ok(!section.caption.includes('I3C Basic SDR'));
  for (const o of def.options.filter(o => o.parse)) {
    const input = find(host,e => e.dataset.option === o.key), before = input.value;
    input.value = '!'; input.oninput(); assert.ok(input.validityMessage);
    input.value = before; input.oninput(); assert.equal(input.validityMessage,'');
  }
  await panel.model.run();
  assert.equal(jobs.length,1);
  return { store,host,panel,jobs };
}
for (const def of Object.values(protocols)) {
  for (const [key,values] of [['DecodeFrame.reasons',def.reasons],['DecodeFrame.kind',def.kinds]]) {
    assert.deepEqual(Object.keys(values).sort(),contract[`${key}.${def.name}`].split(' ').sort());
  }
  await panelCheck(def);
}
const field = (kind,t0,t1,nbits,value = 65) => ({ kind,t0,t1,nbits,value,ninth:null,ninth_kind:null,ok:true,label:kind });
const fields = [field('tx',1,9,9),field('rx',2,10,9,66),field('ack',11,11,1,0)];
const frame = { i:0,t0:0,t1:15,kind:'txn',status:'ok',reasons:[],label:'假交易',fields };
const fake = { name:'fake',label:'假協定',order:9,base:'a',diff:{},roles:[{ key:'a',label:'A' },{ key:'b',label:'B',optional:true }],
  options:[{ key:'rate',label:'速率',type:'text',value:'8',list:[8,16],parse:s => { if (!/^\d+$/.test(s)) throw Error('請填整數'); return +s; } },
    { key:'mode',label:'模式',type:'select',value:0,choices:[[0,'零'],[1,'一']] },{ key:'invert',label:'反相',type:'check',value:false }],
  reasons:{},kinds:{ txn:'交易' },columns:[],content:f => f.label,fieldText:x => x.kind+':'+x.value,
  lanes:() => ['tx','rx'],laneLabels:{ tx:'TX',rx:'RX' },addresses:null,reportSummary:true,summary:(s,o) => `速率 ${o.rate}`,
  sample:{ frames:[frame],addresses:[] } };
globalThis.__decodeFake = fake;
const registry = `import i3c from '${new URL('./decode_i3c.js',import.meta.url).href}'; const protocols = { i3c,fake:globalThis.__decodeFake };`;
const decodeURL = mutatedURL('./decode.js',"import * as protocols from './decode_protocols.js';",registry);
const fakeDecode = await import(decodeURL);
const tableSource = fs.readFileSync(new URL('./decode_table.js',import.meta.url),'utf8');
const imports = tableSource.slice(tableSource.indexOf('import { decodeModel'),tableSource.indexOf('export function tableFrames'));
const fakeTable = await mutate('./decode_table.js',imports,
  `import { decodeModel, definition, selectFrame } from '${decodeURL}';\nexport const MAX_ROWS = 2000;\n${registry}\n`);
const fakeBand = await mutate('./decode_band.js',"from './decode.js'",`from '${decodeURL}'`);
const fakeReport = await mutate('./report.js',"from './decode.js'",`from '${decodeURL}'`);
const tested = await panelCheck(fake,fakeTable.mount,fakeBand.drawBand,fakeReport.decodeSection);
const { store,host,panel,jobs } = tested;
const r = store.get().decodeResult, snap = structuredClone(r.options);
const rate = find(host,e => e.dataset.option === 'rate'); rate.value = '16'; rate.oninput();
assert.deepEqual(store.get().decodeResult.options,snap); assert.equal(store.get().decodeResult.stale,true);
store.set({ decodeResult:{ ...store.get().decodeResult,stale:false } });
panel.model.change({ protocol:'i3c' }); assert.equal(store.get().decodeResult.stale,true); panel.model.change({ opt:{ i2c_addrs:[80] } });
panel.model.change({ protocol:'fake' }); assert.equal(panel.model.config.opt.rate,16);
panel.model.change({ protocol:'i3c' }); assert.deepEqual(panel.model.config.opt.i2c_addrs,[80]);
assert.equal(jobs.length,1);
// 送出後才修改控件，等待中的工作仍只使用送出時的深拷貝。
let resolve;
const ss = makeStore(), mm = fakeDecode.createDecode({ store:ss,bridge:{ job:() => new Promise(r => { resolve = r; }),call:async () => fake.sample } });
mm.change({ protocol:'fake' }); const pending = mm.run(); mm.config.opt.rate = 999;
resolve(result(fake).summary); await pending; assert.equal(ss.get().decodeResult.options.rate,8);
const st = { ...store.get(),decodeResult:r,decodeSel:0,view:{ t0:0,t1:15 } };
function laneCheck(draw) {
  const { g,ops } = canvas(), layout = draw(g,1000,st);
  assert.equal(layout.fields.length,2); assert.ok(layout.fields.every(f => !f.bitMode));
  assert.ok(ops.some(op => op[0] === 'fillText' && op[1] === 'tx:65' && op[3] === 14));
  assert.ok(ops.some(op => op[0] === 'fillText' && op[1] === 'rx:66' && op[3] === 34));
  assert.ok(ops.some(op => op[0] === 'strokeRect' && op[4] === 38));
}
laneCheck(fakeBand.drawBand);
function singleCheck(layoutFn) {
  const ack = layoutFn([frame],st.view,st.plotRect).fields.find(x => x.f.kind === 'ack');
  assert.ok(ack.x1-ack.x0 >= 6); assert.equal(ack.bitMode,true);
  assert.equal(layoutFn([frame],{ t0:0,t1:1000 },st.plotRect).fields.find(x => x.f.kind === 'ack').bitMode,false);
  const allSingle = { ...frame,fields:[field('ack',2,2,1),field('ctrl',4,4,1)] };
  assert.ok(layoutFn([allSingle],st.view,st.plotRect).fields.every(x => x.bitMode));
}
singleCheck(bandLayout);
function codeCheck(fn) {
  assert.deepEqual(fn(field('data',0,3,4),[[0,-1],[1,2],[2,0],[3,1]],x => x*20).map(x => x.label),['X','S','0','1']);
}
codeCheck(bitCells);
assert.equal(bitCells({ ...field('data',0,1,2),ninth_kind:'parity' },[[0,1],[1,-1]],x => x*20)[1].label,'X');
fake.lanes = () => null;
const bitState = { ...st,decodeResult:{ ...r,frames:[{ ...frame,fields:[field('data',1,4,4)] }] } };
const codeCanvas = canvas(); fakeBand.drawBand(codeCanvas.g,1000,bitState,[[1,-1],[2,2],[3,0],[4,1]]);
assert.ok(codeCanvas.ops.some(x => x[0] === 'fillText' && x[1] === 'X'));
assert.ok(codeCanvas.ops.some(x => x[0] === 'fillText' && x[1] === 'S'));
fake.lanes = () => ['tx','rx'];
// 真 mount 的雙 lane 點擊下列也必須選中 frame，不發 bit RPC。
const savedDocument = globalThis.document, savedWindow = globalThis.window, savedObserver = globalThis.ResizeObserver;
const { g } = canvas(), cv = { dataset:{},style:{},getContext:() => g,getBoundingClientRect:() => ({ left:0,top:0 }) };
globalThis.document = { createElement:() => cv }; globalThis.window = { devicePixelRatio:1 };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const bs = makeStore(); let bitCalls = 0;
const bm = fakeBand.mount({ append() {},getBoundingClientRect:() => ({ width:1000,height:40 }) },{ store:bs,bridge:{ call() { bitCalls++; } } });
bs.set({ decodeResult:r,view:st.view }); await Promise.resolve(); bm.draw();
cv.onclick({ clientX:400,clientY:30 }); assert.equal(bs.get().decodeSel,0); assert.equal(bitCalls,0); bm.dispose();
globalThis.document = savedDocument; globalThis.window = savedWindow; globalThis.ResizeObserver = savedObserver;
if (process.argv.includes('--mutations')) {
  const single = await mutate('./decode_band.js','b = Math.min(x1,a+6)','b = Math.min(x1,a+1)');
  assert.throws(() => singleCheck(single.bandLayout));
  const code = await mutate('./decode_band.js',"value === -1 ? 'X'","value === -1 ? '?' ");
  assert.throws(() => codeCheck(code.bitCells));
  const lane = await mutate('./decode_band.js','!lanes && (single','true && (single');
  assert.ok(lane.bandLayout([frame],st.view,st.plotRect,0,['tx','rx']).fields.some(x => x.bitMode));
  // 同一斷言會拒絕失去雙 lane 守門的產品。
  assert.throws(() => assert.ok(lane.bandLayout([frame],st.view,st.plotRect,0,['tx','rx']).fields.every(x => !x.bitMode)));
  console.log('decode_proto mutations self-check OK');
}
globalThis.document = oldDocument; delete globalThis.__decodeFake;
console.log('decode_proto self-check OK');
