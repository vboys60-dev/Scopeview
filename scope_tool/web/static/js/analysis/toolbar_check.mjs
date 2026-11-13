// 掛載真實工具列，驗證順序、狀態與關檔確認。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { bindLayoutCommands } from './tab_analysis.js';
import { clampLayout, defaults } from './layout.js';
import { createStore } from './store.js';
import { mount } from './toolbar.js';
import { mountTabs } from './bpanel.js';
import * as fmt from '../fmt.js';
import * as scales from './scales.js';
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.classList = { add() {} }; }
  append(...nodes) { for (const n of nodes) { if (typeof n === "string") { this.textContent = (this.textContent ?? "") + n; continue; } n.parentNode = this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  addEventListener(k, fn) { (this.listeners[k] ??= []).push(fn); }
  closest() { return root; }
  querySelector(s) { return s === '.analysis__fftbar' ? bar : s === '[data-result-tab=decode]' ? decodeTab : s === '.analysis__lowerbody' ? body : null; }
  click() { if (this.disabled) return; this.onclick?.(); for (const fn of this.listeners.click ?? []) fn(); }
  get options() { return this.children; }
  getBoundingClientRect() { return { left: 0, bottom: 0, width: 0, height: 0 }; }
  hidePopover() {}
}
const page = new Element(), root = new Element(), bar = new Element(), body = new Element(); page.append(root);
let decodeTab;
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.Option = class extends Element { constructor(text, value) { super('option'); this.textContent = text; this.value = value; } };
globalThis.MutationObserver = class { observe() {} disconnect() {} };
globalThis.window = new Element();
const store = createStore(), calls = []; let answer = true, confirms = 0;
const ctx = { store, fmt, scales, appState: { catalog: {} }, bridge: { async call(...args) { calls.push(args); } },
  ui: { async confirm() { confirms++; return answer; }, showError(e) { throw e; } } };
const tabHost = new Element(), panels = Object.fromEntries(['measure', 'cursor', 'marker', 'peaks', 'decode'].map(k => [k, new Element()]));
for (const panel of Object.values(panels)) body.append(panel);
const tabs = mountTabs(tabHost, panels); decodeTab = tabHost.children[0].children.find(b => b.dataset.resultTab === 'decode');
const host = new Element(); mount(host, ctx);
const [open, file, filePanel, analysis, analysisPanel, fft, marker, center] = host.children;
assert.deepEqual(host.children.map(e => e.textContent ?? e.tagName), ['開啟', '檔案 ▾', 'div', '分析 ▾', 'div', 'FFT 計算 ', 'Marker ', '游標置中']);
assert.deepEqual(filePanel.children.map(e => e.textContent ?? e.tagName), ['比對…', '檔案資訊', '匯出波形 CSV…', '匯出 HTML 報告…', 'hr', '關閉']);
assert.deepEqual(analysisPanel.children.map(e => e.textContent ?? e.tagName), ['FFT 頻譜 ↗', 'Math…', '解碼…', '分開堆疊', '疊圖（自動縮放）', 'hr', '1 格', '2 格', '4 格', '8 格']);
assert.equal(filePanel.getAttribute('role'), 'menu'); assert.equal(analysisPanel.getAttribute('role'), 'menu');
assert.equal(file.getAttribute('aria-haspopup'), 'menu');
const items = [...filePanel.children, ...analysisPanel.children].filter(e => e.tagName === 'button');
assert.ok(analysisPanel.children.slice(-4).every(e => e.disabled));
assert.ok(items.every(e => e.getAttribute('role') === 'menuitem' && e.disabled));
const decode = analysisPanel.children[2]; assert.equal(decode.disabled, true);
store.set({ file: { gen: 1 } }); assert.ok(items.every(e => !e.disabled));
let unfolded = 0, effective, floatPanel = { floating: false };
const controller = bindLayoutCommands(store, { initial: defaults(), schedule() {}, persist() {}, lowerLocked: () => effective?.docked || floatPanel.floating });
// 掛載產品實際頁籤監聽，與 bpanel 的 onclick 一起測收折、停靠及窄版流程。
const source = readFileSync(new URL('./tab_analysis.js', import.meta.url), 'utf8');
const hook = source.split('\n').find(line => line.includes("lowerHeader.querySelector('[data-result-tab=decode]')"));
const bindDecodeClick = new Function('lowerHeader', 'store', 'effective', 'floatPanel', hook);
store.onCommand('layout.float.collapse', () => { unfolded++; body.hidden = false; });
for (const scenario of [{ vw: 1400, W: 1400 }, { vw: 1600, W: 1600, docked: true }, { vw: 700, W: 700 }, { vw: 1400, W: 1400, floating: true }]) {
  floatPanel = { floating: !!scenario.floating };
  const prefs = { ...defaults(), lowerCollapsed: true, markerSide: !!scenario.docked };
  store.command('layout.restore', prefs);
  effective = clampLayout({ ...scenario, H: 700, vh: 860, prefs, lowerFloating: floatPanel.floating, fftOn: false }); controller.update(effective);
  decodeTab.listeners.click = []; bindDecodeClick({ querySelector: () => decodeTab }, store, effective, floatPanel);
  decodeTab.closest = () => floatPanel.floating ? {} : null;
  // 浮動時頁籤搬到 .analysis 之外；工具列必須從共用父節點尋找。
  root.querySelector = s => s === '[data-result-tab=decode]' && floatPanel.floating ? null : page.querySelector(s);
  body.hidden = effective.lowerCollapsed;
  decode.click();
  const after = clampLayout({ ...scenario, H: 700, vh: 860, prefs: controller.prefs, lowerFloating: floatPanel.floating, fftOn: false });
  if (!floatPanel.floating) body.hidden = after.lowerCollapsed;
  if (!floatPanel.floating && !after.docked) assert.ok(after.lowerBody >= 212);
  assert.equal(tabs.tab, 'decode'); assert.equal(decodeTab.getAttribute('aria-selected'), 'true'); assert.equal(panels.decode.hidden, false); assert.equal(body.hidden, false);
}
assert.equal(unfolded, 1); assert.equal(calls.length, 0);

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
