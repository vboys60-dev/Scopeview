// 無框架斷言：實際模型、非同步競態與生命週期。
import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { fftManualModel } from './fft_manual.js';
const store = createStore(), calls = [];
let impl = async a => ({ x: Math.round(a.x), y: -20 });
const ctx = { store, bridge: { call(method, args) { calls.push([method, args]); return impl(args); } } };
const result = (id, extra = {}) => ({ ok: true, spectrum_id: id, source: 'CH1', unit: 'dBm', peaks: [], ...extra });
store.set({ file: { gen: 1 }, fftResult: result('a') });
const model = fftManualModel(ctx), tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
assert.equal(model, fftManualModel(ctx));
assert.equal(await model.add(1.2), null);
assert.deepEqual(calls[0], ['fft_track_rf', { spectrum_id: 'a', x: 1.2, direction: 0, level: -40 }]);
assert.deepEqual(model.points(), [{ id: 1, x: 1, y: -20 }]);
assert.equal(await model.add(1.3), '此頻率已有 M1');
const burst = await Promise.all(Array.from({ length: 11 }, (_, i) => model.add(i + 2))); assert.equal(burst.filter(r => /上限 10/.test(r)).length, 2);
assert.match(await model.add(11), /上限 10/); assert.equal(model.points().length, 10);
model.remove(2); await model.add(22); assert.equal(model.points().at(-1).id, 2);
impl = async a => ({ x: a.x + 0.5, y: -30 });
const frequencies = model.points().map(p => p.x);
store.set({ fftResult: result('b') }); await tick();
assert.deepEqual(model.points().map(p => p.x), frequencies); assert.ok(model.points().every(p => p.y === -30));
model.remove(2); assert.equal(await model.add(1), '此頻率已有 M1'); await model.add(22);
const releases = []; impl = a => new Promise(resolve => releases.push(() => resolve({ x: a.x, y: 99 })));
store.set({ fftResult: result('c') });
impl = async a => ({ x: a.x, y: -50 }); store.set({ fftResult: result('d') }); await tick();
releases.forEach(f => f()); await tick(); assert.ok(model.points().every(p => p.y === -50));
impl = async () => { throw { code: 'ERROR' }; }; store.set({ fftResult: result('e') }); await tick();
assert.ok(model.points().every(p => p.y === null));
store.set({ fftResult: null }); assert.equal(model.points().length, 10);
store.set({ fftResult: result('phase', { unit: '°' }) }); assert.match(await model.add(33), /Phase/);
store.set({ fftResult: result('other', { source: 'CH2' }) }); assert.equal(model.points().length, 0);
impl = async a => ({ x: a.x, y: -20 }); await model.add(2);
store.set({ file: { gen: 2 } }); assert.equal(model.points().length, 0);
await model.add(3); store.set({ file: null }); assert.equal(model.points().length, 0);
console.log('fft_manual model self-check OK');
// 最小 DOM 只提供產品表格、控制列與指標事件實際使用的介面。
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.style = {}; this.attrs = {}; this.listeners = {}; this.textContent = ''; }
  append(...els) { this.children.push(...els); }
  replaceChildren(...els) { this.children = els; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, f) { (this.listeners[k] ??= []).push(f); }
  removeEventListener(k, f) { this.listeners[k] = (this.listeners[k] ?? []).filter(fn => fn !== f); }
  emit(k, e) { for (const f of this.listeners[k] ?? []) f(e); }
  getBoundingClientRect() { return { left: 0, top: 0 }; }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture() { this.capture = null; }
  querySelector() { return null; }
  get rows() { return this.children; }
  get cells() { return this.children; }
  get options() { return this.children; }
}
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.window = new Element();
globalThis.Option = class extends Element { constructor(text, value) { super('option'); this.textContent = text; this.value = String(value); } };
const { linear } = await import('./plotcore.js');
const { createFftMarkerLayer } = await import('./fft_marker_layer.js');
const { mountFftMarkerTable } = await import('./fft_marker_table.js');
const { fftMarkerModel } = await import('./fft_markers.js');
const { tableData } = await import('./report.js');
const { mountFftControls, getFftState } = await import('./fft_state.js');
const fmt = await import('../fmt.js'); ctx.fmt = fmt;
store.set({ file: { gen: 3 }, fftResult: result('layer') }); await model.add(30);
const canvas = new Element('canvas'), rect = { l: 0, t: 0, w: 100, h: 100 };
const layer = createFftMarkerLayer(canvas, ctx, () => rect, () => linear(0, -100, 0, 100), () => store.get().fftResult, () => {}, () => linear(0, 100, 0, 100));
let pans = 0;
canvas.addEventListener('pointerdown', e => { if (!layer.owns() && !layer.hit(e)) pans++; });
const ev = (x, y = 20) => ({ button: 0, pointerId: 1, clientX: x, clientY: y, preventDefault() {} });
canvas.emit('pointerdown', ev(39, 28)); assert.equal(layer.owns(), false); assert.equal(pans, 1); pans = 0;
const beforeDrag = calls.length;
canvas.emit('pointerdown', ev(38, 28)); assert.equal(layer.owns(), true); assert.equal(pans, 0);
canvas.emit('pointermove', ev(60)); assert.equal(model.points()[0].x, 30); assert.equal(calls.length, beforeDrag);
canvas.emit('pointerup', ev(60)); await tick(); assert.equal(calls.length, beforeDrag + 1); assert.equal(model.points()[0].x, 60);
await model.add(70); assert.equal(await model.move(1, 70), '此頻率已有 M2'); assert.equal(model.points()[0].x, 60); model.remove(2);
for (const cancel of ['Escape', 'pointercancel', 'spectrum']) {
  canvas.emit('pointerdown', ev(60)); canvas.emit('pointermove', ev(80));
  if (cancel === 'Escape') window.emit('keydown', { key: 'Escape' });
  else if (cancel === 'spectrum') { store.set({ fftResult: result('cancel') }); await tick(); }
  else canvas.emit(cancel, ev(80));
  assert.equal(layer.owns(), false); assert.equal(model.points()[0].x, 60);
}
const beforeClick = calls.length;
canvas.emit('pointerdown', ev(60)); canvas.emit('pointerup', ev(62)); await tick(); assert.equal(calls.length, beforeClick);
canvas.emit('pointerdown', ev(10, 40)); canvas.emit('pointermove', ev(10, 50));
assert.equal(fftMarkerModel(ctx).state().preview, -50); assert.equal(pans, 0);
canvas.emit('pointerup', ev(10, 50)); assert.equal(fftMarkerModel(ctx).state().level, -50);
let diamonds = 0;
const g = new Proxy({}, { get: (_, k) => k === 'closePath' ? () => diamonds++ : () => {}, set: () => true });
layer.draw(g); assert.equal(diamonds, 1);
const host = new Element(), mounted = mountFftMarkerTable(host, ctx, () => '頻譜'), table = host.children[1];
assert.deepEqual(table.children[0].children.map(c => c.textContent), ['#', '頻率', '振幅', '高於 Peak Line', '刪除']);
const row = () => table.children.find(r => r.children[0].textContent === 'M1');
assert.ok(row()); let selected;
store.onCommand('rf.intent', v => { selected = v; }); row().onclick(); assert.deepEqual(selected, { direction: 0, x: 60 });
store.set({ fftView: { f0: 0, f1: 10 } }); assert.ok(row());
assert.deepEqual(tableData(table).head, ['#', '頻率', '振幅', '高於 Peak Line']);
assert.equal(tableData(table).rows[0][0], 'M1');
store.set({ fftResult: result('phase2', { unit: '°' }) }); layer.draw(g); assert.equal(diamonds, 1); assert.equal(row(), undefined);
store.set({ fftResult: result('back') }); await tick(); assert.ok(row());
row().children[4].children[0].onclick({ stopPropagation() {} }); assert.equal(model.points().length, 0);
const controlsHost = new Element(), controlCtx = { store: createStore(), fmt, ui: {}, appState: { catalog: {} } };
mountFftControls(controlsHost, controlCtx);
assert.ok(controlsHost.children.some(e => e.textContent.includes('Peak Line')));
assert.ok(controlsHost.children.every(e => !e.textContent.includes('基準線')));
getFftState(controlCtx).runner.invalidate(); layer.dispose(); mounted.dispose();
console.log('fft_manual gestures / table / report / Peak Line self-check OK');
// 清除／移除在途讀值不得復活；STALE 保持原點且不顯示錯誤。
store.set({ fftResult: result('race') });
let releaseAdd; impl = a => new Promise(resolve => { releaseAdd = () => resolve({ x: a.x, y: -12 }); });
const pendingAdd = model.add(10); await tick(); model.clear(); releaseAdd(); await pendingAdd;
assert.equal(model.points().length, 0);
const queuedAdd = model.add(11); model.clear(); await queuedAdd; assert.equal(model.points().length, 0);
impl = async a => ({ x: a.x, y: -12 }); await model.add(12);
impl = async () => { throw { code: 'STALE' }; }; store.set({ fftResult: result('stale') }); await tick();
assert.equal(model.points()[0].y, -12);
// 真實窗格按鈕的 RF／中心回退、計數、清除與 Phase 停用。
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#333' });
Element.prototype.getContext = () => new Proxy({}, { get: (_, k) => k === 'measureText' ? () => ({ width: 0 }) : () => {}, set: () => true });
class PaneHost extends Element { querySelector(k) { return (this.nodes ??= {})[k] ??= new Element(); } }
const { mount } = await import('./fftpane.js');
const paneHost = new PaneHost(), notices = [];
ctx.ui = { toast: (...args) => notices.push(args) }; ctx.bridge.fetchSpectrum = async () => ({ n: 0, x: [], lo: [], hi: [] });
impl = async a => ({ x: a.x, y: -12 }); model.clear();
store.set({ fftView: { f0: 10, f1: 90 }, rfPos: null, fftResult: result('buttons', { f_max: 100 }) });
const pane = mount(paneHost, ctx), add = paneHost.querySelector('[data-add-marker]'), clear = paneHost.querySelector('[data-clear-marker]');
assert.equal(clear.disabled, true); assert.equal(add.title, '手動 Marker 0/10');
add.emit('click', {}); await tick(); assert.equal(model.points()[0].x, 50); assert.equal(clear.disabled, false);
store.set({ rfPos: { x: 20, y: -12 } }); add.emit('click', {}); await tick(); assert.equal(model.points()[1].x, 20);
for (let i = 1; i <= 8; i++) await model.add(i);
assert.equal(add.disabled, false); assert.equal(add.title, '手動 Marker 10/10');
add.emit('click', {}); await tick(); assert.match(notices.at(-1)[0], /上限 10/); assert.equal(notices.at(-1)[1], 'warning');
store.set({ fftResult: result('phase-buttons', { unit: '°' }) });
assert.equal(add.disabled, true); assert.equal(add.title, 'Phase 模式不支援手動 Marker');
clear.emit('click', {}); assert.equal(model.points().length, 0); assert.equal(clear.disabled, true);
pane.dispose();
console.log('fft_manual in-flight / toolbar / Phase self-check OK');
