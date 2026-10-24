// L8：B 區實際 DOM 接線、偏好往返與暫存副本變異檢查。
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { COLUMNS, load, save, validate, useTabs, mountTabs } from './bpanel.js';
import { mount as mountResults } from './results.js';
import { mount as mountMeasure } from './measure.js';
import { mount as mountCursors } from './cursors.js';
import { createStore } from './store.js';
import { lowerSummary } from './tab_analysis.js';
import { clampLayout, defaults } from './layout.js';
import * as fmt from '../fmt.js';
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.hidden = false; this.className = ''; }
  get classList() { return { add:(c) => { this.className += ' '+c; } }; }
  append(...nodes) { for (const n of nodes) { if (n.parentNode) n.parentNode.children = n.parentNode.children.filter(c => c !== n); this.children.push(n); n.parentNode = this; } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children.at(-1); }
  setAttribute(k,v) { this.attrs[k] = v; }
  addEventListener(k,v) { this.listeners[k] = v; }
}
globalThis.document = { activeElement:null, createElement:(tag) => new Element(tag) };
globalThis.Option = function(text,value) { const e = new Element('option'); e.textContent = text; e.value = value; return e; };
let stored = null, lastKey;
const storage = () => ({ getItem:() => stored, setItem:(k,v) => { lastKey = k; stored = v; } });
globalThis.localStorage = storage();
const expected = ['current','mean','min','max','std'];
assert.deepEqual(load().columns,expected);
assert.deepEqual(validate({ version:1, columns:['count','bogus','count'], tab:'bad' }),{ version:1, columns:['count'], tab:'measure' });
assert.deepEqual(validate({ version:99 }),{ version:1, columns:expected, tab:'measure' });
save({ version:1, columns:['count','std'], tab:'peaks' });
assert.match(lastKey,/\.v1$/); assert.equal(JSON.parse(stored).tab,'peaks');
assert.deepEqual(load(),{ version:1, columns:['std','count'], tab:'peaks' });
const denied = () => { throw Error('私密儲存拒絕'); };
save({ version:1, columns:expected, tab:'cursor' },denied); assert.equal(load(denied).tab,'cursor');
save({ version:1, columns:expected, tab:'measure' });
assert.equal(useTabs(819,180),true); assert.equal(useTabs(820,150),false);
assert.equal(useTabs(1400,149),true); assert.equal(useTabs(900,120),true);
for (const fftOn of [false,true]) {
  const e = clampLayout({ W:1336,H:700,vw:1360,vh:860,prefs:defaults(),fftOn });
  assert.equal(e.lower,150); assert.ok(e.mainGrid >= 240); assert.ok(!fftOn || e.fft >= 160);
  // 同一版面預算，B 少 10px，繪圖區合計多 10px。
  const old = clampLayout({ W:1336,H:700,vw:1360,vh:860,prefs:{ ...defaults(),lower:160 },fftOn });
  assert.equal(e.main+e.fft,old.main+old.fft+10);
}
const body = new Element('div'), header = new Element('div');
const panels = Object.fromEntries(['measure','cursor','peaks'].map(k => [k,new Element('div')])); body.append(...Object.values(panels));
const panelActions = new Element('div');
const tabs = mountTabs(header,panels,{ actions:panelActions });
const tabButtons = header.firstChild.children;
tabs.update({ width:800,height:150 });
assert.deepEqual(Object.values(panels).map(p => p.hidden),[false,true,true]);
for (const [i,key] of ['measure','cursor','peaks'].entries()) {
  tabButtons[i].onclick(); assert.equal(tabs.tab,key); assert.equal(load().tab,key); assert.equal(JSON.parse(stored).tab,key);
  assert.deepEqual(Object.values(panels).map(p => p.hidden),['measure','cursor','peaks'].map(k => k !== key));
  assert.equal(panelActions.hidden,key !== 'measure');
}
const reopened = mountTabs(new Element('div'),panels); assert.equal(reopened.tab,'peaks');
tabs.update({ width:1360,height:150,count:3,fftOn:true }); assert.equal(tabButtons[2].textContent,'FFT 峰值 (3)');
assert.deepEqual(Object.values(panels).map(p => p.hidden),[true,true,false],'寬版 peaks 獨佔');
tabs.update({ width:1360,height:150,count:3,fftOn:false }); assert.equal(tabButtons[2].textContent,'FFT 峰值');
tabButtons[0].onclick(); assert.deepEqual(Object.values(panels).map(p => p.hidden),[false,false,true]);
assert.deepEqual(tabButtons.map(b => b.attrs['aria-selected']),['true','true','false']);
assert.equal(panelActions.hidden,false);
tabs.update({ width:1360,height:120,lowerCollapsed:true }); assert.ok(header.firstChild.hidden);
assert.equal(load().tab,'measure');
const actions = new Element('div'), store = createStore(), calls = [];
const ctx = { store, fmt, resultActions:actions, fftPeaks:panels.peaks,
  ui:{ toast:() => {},showError:() => {} }, appState:{ catalog:{ measurements:[] } },
  bridge:{ call:async (method,args) => { calls.push([method,args]); return method === 'cursor_readout' ? { t1:1,t2:2,y:{} } : { path:'/tmp/results.csv' }; } } };
mountMeasure(new Element('div'),ctx); mountResults(panels.measure,ctx);
const table = panels.measure.firstChild;
assert.ok(table.className.includes('results__table'));
assert.deepEqual(table.firstChild.children.map(c => c.textContent),['量測','目前','平均','最小','最大','標準差','']);
const menu = actions.children[1], boxes = menu.children[1].children.map(l => l.firstChild);
assert.deepEqual(boxes.filter(b => b.checked).map(b => b.dataset.column),expected);
tabButtons[2].onclick();
const count = boxes.find(b => b.dataset.column === 'count'); count.checked = true; count.onchange();
assert.ok(table.firstChild.children.some(c => c.textContent === '次數'));
assert.equal(load().tab,'peaks','欄位選單不可覆寫頁籤偏好');
assert.deepEqual(load().columns,[...expected,'count'].sort((a,b) => COLUMNS.indexOf(a)-COLUMNS.indexOf(b)));
const otherActions = new Element('div'); mountResults(new Element('div'),{ ...ctx,resultActions:otherActions });
assert.ok(otherActions.children[1].children[1].lastChild.firstChild.checked,'選單重新掛載保留次數');
store.set({ file:{ gen:1 },channels:[{ name:'CH1',unit:'V',scale:1,position:0,time_offset:0 }],selected:'CH1' });
const stats = { current:954.126,mean:954,min:950,max:960,range:10,std:1,count:42 };
store.set({ measurements:[1,2].map(id => ({ id,name:'上升時間',channel:'CH1',result:{ ok:true,gen:1,revision:2,unit:'ps',stats } })) });
assert.equal(table.children.length,3);
function checkRows(keys) {
  const labels = { current:'目前',mean:'平均',min:'最小',max:'最大',range:'範圍',std:'標準差',count:'次數' };
  assert.deepEqual(table.firstChild.children.map(c => c.textContent),['量測',...keys.map(k => labels[k]),'']);
  for (const row of table.children.slice(1)) {
    assert.deepEqual(row.children.map(c => c.textContent),['上升時間(CH1)',...keys.map(k => k === 'count' ? '42' : fmt.fmt(stats[k],'ps')),'×']);
    assert.equal(row.firstChild.title,'上升時間(CH1)');
  }
}
checkRows([...expected,'count']);
// 非連續欄位組合，完整比對每格，避免表頭正確但資料錯位。
for (const box of boxes) { box.checked = ['mean','range','count'].includes(box.dataset.column); box.onchange(); }
checkRows(['mean','range','count']);
const clear = actions.children.find(e => e.className.includes('results__clear')), exp = actions.children.find(e => e.className.includes('results__export'));
assert.ok(clear.title && exp.title); assert.equal(exp.textContent,'匯出結果');
assert.equal(actions.firstChild.attrs['aria-label'],actions.firstChild.title); assert.equal(exp.disabled,false); await exp.onclick();
assert.equal(calls[0][0],'export_measurements'); assert.equal(calls[0][1].rows.length,2);
clear.onclick(); assert.deepEqual(store.get().measurements,[]); assert.equal(table.children.length,1); assert.equal(exp.disabled,true);
store.set({ fftResult:{ ok:true,unit:'dBV',peaks:[{ x:100,y:2 }] } });
assert.equal(panels.peaks.lastChild.children.length,2); assert.equal(panels.measure.children.length,1,'FFT 表不能回到量測面板');
let readoutDone;
const done = new Promise(resolve => { readoutDone = resolve; });
const originalCall = ctx.bridge.call;
ctx.bridge.call = async (...args) => {
  const r = await originalCall(...args);
  if (args[0] === 'cursor_readout') queueMicrotask(() => queueMicrotask(readoutDone));
  return r;
};
const cursor = new Element('div'); mountCursors(cursor,ctx);
assert.equal(cursor.children[2].tagName,'table','各通道讀值優先放在摘要前');
assert.equal(cursor.children[0].className,'cursors__inputs'); assert.equal(cursor.children[0].children.length,6);
assert.deepEqual(cursor.children[0].children.slice(0,4).map(e => e.textContent),['X1 ','X2 ','Y1(格) ','Y2(格) ']);
store.command('cursor.intent',{ which:'x1',value:1 }); store.command('cursor.intent',{ which:'x2',value:2 });
await done;
assert.equal(cursor.children[3].className,'cursors__readout');
assert.equal(cursor.children[3].children.length,8); assert.ok(cursor.children[3].children[4].className.includes('newrow'));
const css = readFileSync(new URL('../../css/analysis.css',import.meta.url),'utf8');
assert.match(css,/\.results__table th, \.results__table td \{ white-space: nowrap;/);
assert.match(css,/\.results__table th, \.results__table td \{[^}]*height: 26px;[^}]*font-size: 13px;/);
assert.match(css,/\.cursors__readout \{ display: grid; grid-template-columns: repeat\(4/);
assert.match(css,/\.cursors__field \.input \{[^}]*height: 24px;[^}]*font-size: 13px;/);
// Node 端對 B 所有文字類型的 CSS 規則檢查；browser 另逐一掃描文字節點。
const fontRules = [
  '.analysis__lower', '.analysis__splitter--lower > button', '.analysis__lower .btn, .analysis__lower summary',
  '.analysis__lowerbody > *', '.results__table th, .results__table td', '.results__choices label',
  '.results__info', '.results__fftinfo', '.cursors__field', '.cursors__field .input',
  '.cursors__value', '.cursors__number', '.analysis__cursors .table th, .analysis__cursors .table td',
  '.analysis__lower .analysis__placeholder',
];
for (const selector of fontRules) {
  const rule = css.slice(css.indexOf(selector+' {')).split('}')[0];
  const size = rule.match(/font-size:\s*([\d.]+)px|font:\s*([\d.]+)px/);
  assert.ok(size && Number(size[1] ?? size[2]) >= 12.5,`${selector} 字體不得縮小`);
}
assert.match(css,/\.cursors__field--x \{[^}]*min-width: 10ch/);
assert.match(css,/repeat\(2,minmax\(0,1fr\)\)/);
// 依實測 358 > 347 的寬度預算，驗四欄省下的 padding 足以消除溢出；實際排版仍交 browser_check。
const tableSelector = '.analysis__cursors .table th, .analysis__cursors .table td {';
const baseTable = css.split(tableSelector)[1].split('}')[0];
const narrowTable = css.split('@container (max-width: 430px) {')[1]?.split(tableSelector)[1]?.split('}')[0] ?? '';
const horizontalPadding = rule => Number(rule.match(/padding:\s*[\d.]+px\s+([\d.]+)px/)?.[1]);
const savedWidth = 4 * 2 * (horizontalPadding(baseTable) - horizontalPadding(narrowTable));
assert.ok(Number.isFinite(savedWidth) && 358 - savedWidth <= 347 + 1,'窄版通道表四欄須收回至少 10px padding');
assert.ok(!/font(?:-size)?\s*:|white-space\s*:/.test(narrowTable),'窄版保留原字級與完整單位');
assert.match(css,/td:first-child \{[^}]*max-width:[^}]*text-overflow: ellipsis/);
assert.match(css,/td:last-child \{[^}]*position: sticky; right: 0/);
const summaryState = { measurements:[{},{}], fftResult:{ok:true,peaks:[{},{},{}]}, cursors:{x1:1,x2:2} };
assert.match(lowerSummary(summaryState,true),/^量測 2／FFT 峰值 3／ΔX 1\.000 s$/);
assert.match(lowerSummary(summaryState,false),/^量測 2／FFT 峰值 0／ΔX/);
const source = readFileSync(new URL('./tab_analysis.js',import.meta.url),'utf8');
assert.match(source,/buttons\.lower\.setAttribute\('aria-label',buttons\.lower\.title\)/);
assert.match(source,/Object\.create\(ctx\)/); assert.ok(!source.includes('q("results__actions")'));
assert.match(source,/\$\{lowerSummary\(st,fftOn\)\}/);
// 執行產品 renderLayout 的真正 update 呼叫，給 viewport、B 寬度和高度不同的值。
const wiring = source.match(/resultTabs\.update\(([^;]+)\);/);
assert.ok(wiring,'resultTabs.update 必須接線');
for (const width of [700,819,820,1000]) {
  let received;
  Function('resultTabs','q','e','store','fftOn','innerWidth',`resultTabs.update(${wiring[1]});`)(
    {update:args => { received = args; tabs.update(args); }},
    name => { assert.equal(name,'analysis__lowerbody'); return {clientWidth:width}; },
    {lower:150,lowerBody:122,lowerCollapsed:false},store,false,1100);
  assert.equal(received.width,width,'使用實際 B 寬度，不能用視窗或 e.lowerBody 高度');
  assert.equal(body.dataset.resultTabbed,String(width < 820));
}
console.log('P2b3 self-check OK：欄位／分頁往返／DOM 切換／清除與匯出／游標網格／nowrap／高度預算');
if (process.argv.includes('--mutations')) {
  const mutations = [
    ['欄位預設錯','bpanel.js',"DEFAULT_COLUMNS = ['current','mean','min','max','std']","DEFAULT_COLUMNS = ['current','mean','min','max','std','count']"],
    ['頁籤狀態不存','bpanel.js','persist(prefs); render();','render();'],
    ['清除全部不作用','results.js','store.command("measure.clear")','store.command("measure.noop")'],
    ['nowrap 拿掉','../../css/analysis.css','.results__table th, .results__table td { white-space: nowrap;','.results__table th, .results__table td { white-space: normal;'],
    ['分頁判定錯','bpanel.js','width < 820 || height < 150','width < 900 || height < 120'],
    ['選單不保存','results.js','save(prefs); renderMeas();','renderMeas();'],
    ['匯出失去資料','results.js','rows: ex.rows','rows: []'],
  ];
  mutations.push(
    ['M1 欄位資料錯位','results.js','prefs.columns.includes(COLUMNS[i])','prefs.columns.includes(COLUMNS[(i+1)%7])'],
    ['M2 寬版峰值混入其他面板','bpanel.js',"!tabbed && tab !== 'peaks' && panel !== 'peaks'","!tabbed && panel !== 'peaks'"],
    ['M3 FFT 關閉仍顯示計數','bpanel.js','fftOn && count','count'],
    ['M4 游標文字縮小','../../css/analysis.css','.cursors__value { display: flex; flex-direction: column; font-size: 12.5px;','.cursors__value { display: flex; flex-direction: column; font-size: 11px;'],
    ['M5 收折摘要錯誤','tab_analysis.js','量測 ${st.measurements.length}／FFT 峰值','量測／FFT 峰值'],
    ['M6 以 lowerBody 高度判定分頁','tab_analysis.js',"width:q('analysis__lowerbody').clientWidth",'width:e.lowerBody'],
    ['M7 欄位覆寫頁籤偏好','results.js','prefs = { ...load(), columns:','prefs = { ...prefs, columns:'],
    ['M8 移除 update 接線','tab_analysis.js','resultTabs.update({','resultTabs.disconnected({'],
    ['操作列未隨分頁隱藏','bpanel.js',"collapsed || !panelVisible('measure',prefs.tab,tabbed)",'collapsed'],
    ['收折摘要 FFT 關閉仍計數','tab_analysis.js','fftOn && st.fftResult?.ok','st.fftResult?.ok'],
    ['窄版通道表恢復過寬 padding','../../css/analysis.css','{ padding: 2px 2px; }','{ padding: 2px 4px; }'],
  );
  const temp = mkdtempSync(join(tmpdir(),'scope-p2b3-'));
  try {
    cpSync(fileURLToPath(new URL('../',import.meta.url)),join(temp,'js'),{ recursive:true });
    cpSync(fileURLToPath(new URL('../../css/',import.meta.url)),join(temp,'css'),{ recursive:true });
    for (const [name,file,old,changed] of mutations) {
      const path = join(temp,'js/analysis',file), original = readFileSync(path,'utf8'); assert.ok(original.includes(old),name);
      try {
        writeFileSync(path,original.replace(old,changed));
        const r = spawnSync(process.execPath,[join(temp,'js/analysis/p2b3_check.mjs')],{ encoding:'utf8' });
        assert.notEqual(r.status,0,`${name}：未抓到變異`); assert.match(r.stderr,/AssertionError/); console.log(`${name}：如預期失敗`);
      } finally { writeFileSync(path,original); }
    }
  } finally { rmSync(temp,{ recursive:true,force:true }); }
  console.log(`P2b3 變異驗證 ${mutations.length}/${mutations.length} self-check OK（暫存副本，已還原）`);
}
