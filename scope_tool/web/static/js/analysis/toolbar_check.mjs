// 掛載真實工具列，驗證順序、狀態與關檔確認。
import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { mount } from './toolbar.js';
import * as fmt from '../fmt.js';
import * as scales from './scales.js';
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.style = {}; this.attrs = {}; this.listeners = {}; this.classList = { add() {} }; }
  append(...nodes) { for (const n of nodes) { if (typeof n === "string") { this.textContent = (this.textContent ?? "") + n; continue; } n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  addEventListener(k, fn) { (this.listeners[k] ??= []).push(fn); }
  closest() { return root; }
  querySelector(s) { return s === '.analysis__fftbar' ? bar : null; }
  get options() { return this.children; }
  getBoundingClientRect() { return { left: 0, bottom: 0, width: 0, height: 0 }; }
  hidePopover() {}
}
const root = new Element(), bar = new Element();
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.Option = class extends Element { constructor(text, value) { super('option'); this.textContent = text; this.value = value; } };
globalThis.MutationObserver = class { observe() {} disconnect() {} };
globalThis.window = new Element();
const store = createStore(), calls = []; let answer = true, confirms = 0;
const ctx = { store, fmt, scales, appState: { catalog: {} }, bridge: { async call(...args) { calls.push(args); } },
  ui: { async confirm() { confirms++; return answer; }, showError(e) { throw e; } } };
const host = new Element(); mount(host, ctx);
const [open, file, filePanel, analysis, analysisPanel, fft, marker, center] = host.children;
assert.deepEqual(host.children.map(e => e.textContent ?? e.tagName), ['開啟', '檔案 ▾', 'div', '分析 ▾', 'div', 'FFT 計算 ', 'Marker ', '游標置中']);
assert.deepEqual(filePanel.children.map(e => e.textContent ?? e.tagName), ['比對…', '檔案資訊', '匯出波形 CSV…', '匯出 HTML 報告…', 'hr', '關閉']);
assert.deepEqual(analysisPanel.children.map(e => e.textContent), ['FFT 頻譜 ↗', 'Math…', '分開堆疊', '疊圖（自動縮放）']);
assert.equal(filePanel.getAttribute('role'), 'menu'); assert.equal(analysisPanel.getAttribute('role'), 'menu');
assert.equal(file.getAttribute('aria-haspopup'), 'menu');
const items = [...filePanel.children, ...analysisPanel.children].filter(e => e.tagName === 'button');
assert.ok(items.every(e => e.getAttribute('role') === 'menuitem' && e.disabled));
store.set({ file: { gen: 1 } }); assert.ok(items.every(e => !e.disabled));
store.set({ opening: true }); assert.equal(filePanel.children.at(-1).disabled, true);
store.set({ opening: false }); assert.equal(filePanel.children.at(-1).disabled, false);
let selected; store.onCommand('tab.select', x => { selected = x; }); analysisPanel.children[0].onclick(); assert.equal(selected, 'fft');
const close = filePanel.children.at(-1), tick = () => new Promise(r => setTimeout(r, 0));
await close.onclick(); await tick(); assert.equal(confirms, 0); assert.equal(calls.length, 1); assert.equal(store.get().file, null);
for (const patch of [{ measurements: [{}] }, { channels: [{ name: 'D', derived: true }] }, { slots: [{}] }]) {
  store.set({ file: { gen: 1 }, measurements: [], channels: [], slots: [], ...patch });
  const before = confirms, callCount = calls.length; answer = false; await close.onclick(); await tick();
  assert.equal(confirms, before + 1); assert.equal(calls.length, callCount); assert.ok(store.get().file);
  answer = true; await close.onclick(); await tick(); assert.equal(confirms, before + 2);
  assert.equal(calls.at(-1)[0], 'close_waveform'); assert.equal(store.get().file, null);
  assert.deepEqual([store.get().measurements, store.get().channels, store.get().slots], [[], [], []]);
}
assert.equal(calls.length, 4);
console.log('toolbar self-check OK');
