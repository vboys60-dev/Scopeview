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
  prepend(...nodes) { for (const n of nodes.reverse()) { this.children = this.children.filter(c => c !== n); n.parentNode = this; this.children.unshift(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(k,f) { this.listeners[k] = f; }
  setCustomValidity(s) { this.validityMessage = s; }
  dispatchEvent(e) { this['on'+e.type]?.(e); this.listeners[e.type]?.(e); }
  reportValidity() { return !this.validityMessage; }
}
const walk = e => [e,...e.children.flatMap(walk)];
const find = (e,f) => walk(e).find(f);
const oldDocument = globalThis.document;
globalThis.document = { createElement:t => new Element(t) };
const channels = ['CH1','CH2','CH3','CH4'].map(name => ({ name,time_offset:0 }));
// 優先使用角色標籤，回退時保持順序且不重複使用通道。
const namedChannels = names => names.map(name => ({ name }));
assert.deepEqual(defaultConfig(namedChannels(['CHAN1','SCL1','SDA1']),protocols.i2c).ch,{ scl:'SCL1',sda:'SDA1' });
assert.deepEqual(defaultConfig(namedChannels(['CHAN1','CHAN2']),protocols.i2c).ch,{ scl:'CHAN1',sda:'CHAN2' });
assert.deepEqual(defaultConfig(namedChannels(['SCL1','CHAN2']),protocols.i2c).ch,{ scl:'SCL1',sda:'CHAN2' });
assert.deepEqual(defaultConfig(namedChannels(['CHAN1','SCL1','CHAN3']),protocols.i2c).ch,{ scl:'SCL1',sda:'CHAN3' });
assert.deepEqual(defaultConfig([{ name:'SCL1',derived:true },...namedChannels(['CHAN1','SDA1'])],protocols.i2c).ch,{ scl:'CHAN1',sda:'SDA1' });
assert.deepEqual(defaultConfig(namedChannels(['CANL1','CANH1']),protocols.can).ch,{ can:'CANL1',canl:'' });
assert.deepEqual(defaultConfig(namedChannels(['CHAN1','CANL1','CANH1']),protocols.can).ch,{ can:'CHAN1',canl:'CANL1' });
assert.deepEqual(defaultConfig(namedChannels(['TX1','RX1']),protocols.uart).ch,{ tx:'TX1',rx:'RX1',tx_n:'',rx_n:'' });
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
// I2C 顯示取送出快照；切表單後舊結果仍保留原位址文字。
{
  const def = protocols.i2c, { store,host,panel,jobs } = await panelCheck(def);
  assert.equal(jobs[0].options.addr_bits,7);
  const original = structuredClone(def.sample.frames);
  for (const bits of [undefined,7,8]) {
    const opt = bits == null ? {} : { addr_bits:bits }, r = result(def,opt);
    store.set({ decodeResult:r,view:{ t0:0,t1:120 } });
    const rows = walk(host).filter(e => e.dataset.decodeFrame != null);
    const report = decodeSection(store.get(),{ querySelector:() => null },String,false)[0];
    const { g,ops } = canvas(); drawBand(g,1000,store.get());
    for (const [i,raw] of [[0,'A0'],[1,'A1']]) {
      const f = r.frames[i], expected = bits === 8 ? '0x'+raw : '0x50';
      assert.equal(def.columns[0].cell(f,opt),expected);
      assert.equal(rows[i].children[3].textContent,expected);
      assert.equal(report.tables[0].rows[i][3],expected);
      const tag = bits === 8 ? raw : '50 '+(i ? 'R' : 'W');
      assert.equal(def.fieldText(f.fields[0],opt,f),tag);
      assert.ok(ops.some(x => x[0] === 'fillText' && x[1] === tag));
      assert.equal(def.content(f,opt),i ? '⚠0xAB' : '0x12');
      assert.equal(rows[i].children[4].textContent,i ? 'R' : 'W');
    }
    panel.model.change({ opt:{ addr_bits:bits === 8 ? 7 : 8 } });
    assert.equal(walk(host).find(e => e.dataset.decodeFrame === '0').children[3].textContent,bits === 8 ? '0xA0' : '0x50');
    assert.deepEqual(r.frames,original);
  }
  const f = original[0];
  for (const special of [original[2],...['start_byte','hs_code','partial'].map(kind => ({ ...f,kind })),
    { ...f,addr:0x7C },{ ...f,addr:0x02 },{ ...f,addr:0x50,fields:[{ ...f.fields[0],value:0xF0 },{ ...f.fields[0],kind:'addr_lo' }] },
    { ...f,addr:null },{ ...f,addr:0x250 }]) {
    assert.equal(def.columns[0].cell(special,{ addr_bits:8 }),def.columns[0].cell(special,{}));
    assert.equal(def.content(special,{ addr_bits:8 }),def.content(special,{}));
    for (const x of special.fields) assert.equal(def.fieldText(x,{ addr_bits:8 },special),def.fieldText(x,{},special));
  }
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
  `import { decodeModel, definition, selectFrame, withAscii } from '${decodeURL}';\nexport const MAX_ROWS = 2000;\n${registry}\n`);
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
{ // ASCII 顯示：只對 8 位元資料欄位；位址不算；關閉時不加
  const { withAscii, isByteField, asciiChar } = await import('./decode.js');
  const f = { fields:[{ kind:'addr',value:0xA0,nbits:9,ninth_kind:'ack' },{ kind:'data',value:0x48,nbits:9,ninth_kind:'ack' },{ kind:'data',value:0x01,nbits:9,ninth_kind:'ack' },{ kind:'tx',value:0x69,nbits:8,ninth_kind:null }] };
  assert.equal(withAscii(f,'X',true),'X "H.i"'); assert.equal(withAscii(f,'X',false),'X');
  assert.ok(!isByteField(f.fields[0]) && isByteField(f.fields[1])); assert.equal(asciiChar(0x7F),'.');
  assert.equal(withAscii({ fields:[f.fields[0]] },'X',true),'X');
}
// UART 估計使用真按鈕與控制器；等待、失敗與過期均保留既有結果。
{
  const { estimatedBaud } = await import('./decode_uart.js');
  assert.equal(estimatedBaud({ ok:false,reason:'估計鮑率 19200' }),19200);
  assert.equal(estimatedBaud({ ok:false,reason:'估計鮑率 19200；估計值取最短脈寬，請確認' }),19200);
  for (const reason of ['無法估計鮑率：邊緣太少','錯誤 19200','估計鮑率 0','估計鮑率 19200xyz','估計鮑率 1e6']) assert.equal(estimatedBaud({ ok:false,reason }),null);
  assert.equal(estimatedBaud({ ok:true,reason:'估計鮑率 19200' }),null);
  const us = makeStore(), host = new Element('div'); let finish, sent;
  const panel = mount(host,{ store:us,bridge:{ job:(n,p) => { sent = p; return new Promise(r => { finish = r; }); } } });
  panel.model.change({ protocol:'uart' });
  const snapshot = result(protocols.uart); us.set({ decodeResult:snapshot,decodeSel:0 });
  const button = find(host,e => e.dataset.decodeAction === 'estimate'), input = find(host,e => e.dataset.option === 'baud');
  const pending = button.onclick();
  assert.equal(button.disabled,true); assert.equal(us.get().decodeResult,snapshot); assert.equal(us.get().decodeSel,0);
  assert.equal(sent.options.estimate,true); assert.equal(panel.model.config.opt.estimate,undefined);
  finish({ gen:1,ok:false,reason:'估計鮑率 19200' }); await pending;
  assert.equal(input.value,'19200'); assert.equal(panel.model.config.opt.baud,19200);
  assert.equal(us.get().decodeResult.frames,snapshot.frames); assert.equal(us.get().decodeResult.stale,true);
  assert.equal(us.get().decodeSel,0); assert.match(panel.model.message,/已填入 19200，請確認後解碼/);
  const before = us.get().decodeResult, fail = button.onclick();
  finish({ gen:1,ok:false,reason:'無法估計鮑率：邊緣太少' }); await fail;
  assert.equal(us.get().decodeResult,before); assert.equal(input.value,'19200'); assert.match(panel.model.message,/邊緣太少/);
  const old = button.onclick(); panel.model.change({ opt:{ ...panel.model.config.opt,baud:38400 } });
  finish({ gen:1,ok:false,reason:'估計鮑率 9600' }); await old; assert.equal(input.value,'19200');
  const wrongGen = button.onclick(); finish({ gen:9,ok:false,reason:'估計鮑率 9600' }); await wrongGen;
  assert.match(panel.model.message,/估計結果已過期/); assert.equal(input.value,'19200');
  panel.model.change({ ch:{ tx:'',rx:'' } }); assert.equal(button.disabled,true);
  panel.model.change({ ch:{ tx:'',rx:'CH1' } }); assert.equal(button.disabled,false);
  const rx = button.onclick(); assert.deepEqual(sent.channels,{ rx:'CH1' });
  finish({ gen:1,ok:false,reason:'估計鮑率 9600' }); await rx;
  const late = button.onclick(); us.set({ file:{ gen:2 } });
  finish({ gen:1,ok:false,reason:'估計鮑率 38400' }); await late;
  panel.model.change({ protocol:'uart' });
  assert.equal(find(host,e => e.dataset.option === 'baud').value,'115200');
  us.set({ file:null }); assert.equal(find(host,e => e.dataset.decodeAction === 'estimate')?.disabled ?? true,true);
  const { makeDecode } = await import('../mock_decode.js');
  const mock = makeDecode({ job:(n,fn) => fn(),needFile() {},chan() {},generation:() => 1 });
  const params = decodeParams(defaultConfig(channels,protocols.uart));
  const original = mock.decode(params), mockBefore = mock.decode_frames({ decode_id:original.decode_id });
  const response = mock.decode({ ...params,channels:{ rx:'CH1' },thresholds:{ rx:null },options:{ estimate:true } });
  assert.equal(estimatedBaud(response),9600); assert.deepEqual(mock.decode_frames({ decode_id:original.decode_id }),mockBefore);
}
// I2C 真按鈕：DOM 與 model 同步，手動門檻跟著通道，其他結果保持設定。
{
  const { estimatedRoles } = await import('./decode_i2c.js');
  const messages = ['角色建議：對調（有位址封包 11 對 0）','角色建議：維持（有位址封包 48 對 0）','無法判斷 SCL／SDA（SDA 無有限高低平台）'];
  messages.forEach((reason,i) => assert.equal(estimatedRoles({ ok:false,reason }),['對調','維持','無法判斷'][i]));
  for (const reason of ['亂字串','角色建議：對調（有位址封包 11 對 0）尾巴']) assert.equal(estimatedRoles({ ok:false,reason }),null);
  assert.equal(estimatedRoles({ ok:true,reason:messages[0] }),null);
  const store = makeStore(), host = new Element('div'); let reason = messages[0], sent;
  const panel = mount(host,{ store,bridge:{ job:async (n,p) => { sent = p; return { gen:1,ok:false,reason }; } } }); panel.model.change({ protocol:'i2c' });
  const input = find(host,e => e.dataset.option === 'addr_bits'), root = find(host,e => e.className === 'decode');
  root.querySelectorAll = selector => walk(root).filter(e => selector.includes('select') ? e.dataset.role === /"(.+)"/.exec(selector)[1] : e.dataset.line === /"(.+)"/.exec(selector)[1]);
  root.querySelector = selector => root.querySelectorAll(selector)[0]; input.closest = () => root;
  const button = find(host,e => e.dataset.decodeAction === 'roles'), scl = find(host,e => e.dataset.role === 'scl'), sda = find(host,e => e.dataset.role === 'sda');
  for (const manual of [false,true]) {
    if (manual) { const fields = walk(host).filter(e => e.dataset.line); fields.forEach((e,i) => { e.value = String(i+1); }); find(host,e => e.textContent === '手動').onclick(); }
    const old = [scl.value,sda.value], th = structuredClone(panel.model.config.thr); await button.onclick();
    assert.equal(sent.options.estimate,true); assert.deepEqual([scl.value,sda.value],[old[1],old[0]]); assert.deepEqual(panel.model.config.ch,{ scl:old[1],sda:old[0] });
    assert.deepEqual(panel.model.config.thr,{ scl:th.sda,sda:th.scl }); assert.equal(panel.model.config.opt.estimate,undefined);
    assert.equal(panel.model.message,`已對調：SCL=${old[1]}、SDA=${old[0]}（原 SCL=${old[0]}）；可在下拉選單改回`);
  }
  for (reason of messages.slice(1)) { const before = structuredClone(panel.model.config); await button.onclick(); assert.deepEqual(panel.model.config,before); assert.equal(panel.model.message,reason); }
  const { makeDecode } = await import('../mock_decode.js'), mock = makeDecode({ job:(n,f) => f(),needFile() {},chan() {},generation:() => 1 });
  const params = decodeParams(defaultConfig(channels,protocols.i2c)), original = mock.decode(params), before = mock.decode_frames({ decode_id:original.decode_id });
  assert.equal(estimatedRoles(mock.decode({ ...params,options:{ estimate:true } })),'維持'); assert.deepEqual(mock.decode_frames({ decode_id:original.decode_id }),before);
}
globalThis.document = oldDocument; delete globalThis.__decodeFake;
console.log('decode_proto self-check OK');
