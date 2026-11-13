// B 組：別名只影響表格顯示，來源值與量測工作維持原名。
import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { mount as mountMeasure } from './measure.js';
import { mount as mountResults } from './results.js';
import { mount as mountCursors, cursorRows } from './cursors.js';
import { mountCursorTable } from './cursor_table.js';
import { mount as mountMarker } from './marker_table.js';
import * as fmt from '../fmt.js';
import { mount as mountPlot } from './mainplot.js';
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.attrs = {}; this.value = ''; this.textContent = ''; this.className = ''; }
  get classList() { return { add: () => {}, toggle: () => {}, remove: () => {} }; }
  append(...nodes) { for (const n of nodes) { if (n.parentNode) n.parentNode.children = n.parentNode.children.filter(c => c !== n); this.children.push(n); n.parentNode = this; } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children.at(-1); }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener() {}
}
globalThis.document = { activeElement: null, createElement: tag => new Element(tag) };
globalThis.Option = function(text, value) { const o = new Element('option'); o.textContent = text; o.value = value; return o; };
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
const store = createStore(), calls = [], toasts = [];
const channels = ['CH1', 'CH2'].map((name, i) => ({ name, visible: i === 0, unit: 'V', scale: 1, position: 0, time_offset: 0, t0: 0, t1: 1 }));
store.set({ file: { gen: 1 }, channels, selected: 'CH1', cursors: { x1: 0.2, x2: 0.8, y1: 1, y2: -1 } });
const ctx = { store, fmt, appState: { catalog: { measurements: [{ name: 'Delta Time', sources: 2, category: '雙來源', tip: '' }] } },
  ui: { toast: (...args) => toasts.push(args) }, bridge: { job: async (...args) => { calls.push(args); return { gen: 1, results: [], revision: 1 }; }, call: async (...args) => { calls.push(args); return { t1: 0.2, t2: 0.8, y: { CH1: { y1: 1, y2: 2 } } }; } } };
const measure = new Element('div'), results = new Element('div'), cursors = new Element('div'), marker = new Element('div');
mountMeasure(measure, ctx); mountResults(results, ctx); mountCursors(cursors, ctx); mountMarker(marker, ctx);
const source = measure.children[0].children[1], source2 = measure.children.find(e => e.children.some(c => c.textContent === '來源 2')).children[2];
const cursorSelect = cursors.children[0].lastChild.lastChild, markerPick = marker.firstChild.children[2];
const readout = { kind: 'legacy', t1: 0.2, t2: 0.8, v1: 1, v2: 2, unit: 'V', source: 'CH1', y: { CH1: { y1: 1, y2: 2 } } };
const cursorTable = mountCursorTable(ctx); cursorTable.render(readout);
store.set({ measurements: [{ id: 1, name: 'Delta Time', channel: 'CH1', channel2: 'CH2', rising: true, result: null }] });
store.command('marker.add', { ch: 'CH1', t: 0.5 });
await new Promise(resolve => setTimeout(resolve, 80));
const beforeJobs = calls.filter(([name]) => name === 'measure').length;
store.updateChannel('CH1', { alias: 'SDA' }, 'user'); store.updateChannel('CH2', { alias: 'SCL' }, 'user');
assert.deepEqual(source.children.map(o => [o.textContent, o.value]), [['SDA', 'CH1'], ['SCL', 'CH2']]);
assert.deepEqual(source2.children.map(o => [o.textContent, o.value]), [['SDA', 'CH1'], ['SCL', 'CH2']]);
assert.match(results.children.find(e => e.className.includes('results__table')).children[1].firstChild.textContent, /SDA.*SCL/);
assert.deepEqual(cursorSelect.children.map(o => [o.textContent, o.value]), [['SDA', 'CH1']]);
assert.match(cursorSelect.title, /SDA/);
assert.equal(cursorRows(readout, fmt.fmt, n => n === 'CH1' ? 'SDA' : n).find(r => r[0] === '換算來源')[1], 'SDA');
assert.equal(cursorRows(readout, fmt.fmt).find(r => r[0] === '換算來源')[1], 'CH1');
assert.match(cursorTable.el.firstChild.firstChild.textContent, /SDA/);
assert.deepEqual(markerPick.children.map(o => [o.textContent, o.value]), [['目前通道（SDA）', ''], ['SDA', 'CH1'], ['SCL（隱藏）', 'CH2']]);
assert.equal(marker.children[1].children[1].children[1].textContent, 'SDA');
markerPick.value = 'CH2'; marker.firstChild.lastChild.onclick();
assert.equal(store.get().markerTable.at(-1).ch, 'CH2'); assert.match(toasts.at(-1)[0], /SCL/);
await new Promise(resolve => setTimeout(resolve, 200));
assert.equal(calls.filter(([name]) => name === 'measure').length, beforeJobs);
assert.equal(store.get().measurements[0].channel, 'CH1'); assert.equal(store.get().measurements[0].channel2, 'CH2');
assert.equal(cursors.children[2].children[1].firstChild.textContent, 'SDA');
// 真正掛載主圖並填入快取，再確認別名更新不重新抓取波形。
const g = new Proxy({}, { get: (t, k) => t[k] ?? (k === 'measureText' ? () => ({ width: 10 }) : () => {}) });
const element = () => ({ style: {}, dataset: {}, addEventListener() {}, removeEventListener() {}, append(c) { this.child = c; },
  getContext: () => g, getBoundingClientRect: () => ({ width: 800, height: 400, left: 0, top: 0 }) });
globalThis.document = { createElement: element };
globalThis.window = { devicePixelRatio: 1, addEventListener() {}, removeEventListener() {} };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const plotStore = createStore(); plotStore.set({ file: { gen: 1, channels }, channels, selected: 'CH1', markerTable: [] });
let fetched = 0;
const plot = mountPlot(element(), { store: plotStore, ui: { toast() {} }, bridge: { fetchWave: async () => { fetched++; return { n: 0, mode: 0, x: [], lo: [], hi: [] }; } } });
await new Promise(resolve => setTimeout(resolve, 200)); assert.ok(fetched > 0);
const beforeFetch = fetched; plotStore.updateChannel('CH1', { alias: 'SDA' });
await new Promise(resolve => setTimeout(resolve, 200)); assert.equal(fetched, beforeFetch);
plot.destroy?.();
console.log('alias tables self-check OK');
