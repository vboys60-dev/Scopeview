// 無框架斷言：換算公式、前端峰表、補抓條件與真實基準線事件。
import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { FFT_UNITS, convertLevel, selectPeaks, needsRefetch, peaksTruncated, fftMarkerModel } from './fft_markers.js';
import { fftGesture, createFftMarkerLayer } from './fft_marker_layer.js';
import { createFft } from './toolbar.js';
import { bindFftMarkerControls } from './fft_marker_controls.js';
import { mountFftMarkerTable } from './fft_marker_table.js';
import { createController } from './cursors.js';
import { linear } from './plotcore.js';
import * as fmt from '../fmt.js';
const near = (a, b) => assert.ok(Math.abs(a - b) <= 1e-10 * Math.max(1e-12, Math.abs(b)), `${a} ≈ ${b}`);
for (const r of [25, 50, 75, 100, 200]) {
  near(convertLevel(0, 'dBm', 'Watt', r), 0.001);
  near(convertLevel(0, 'dBm', 'Vrms', r), Math.sqrt(0.001 * r));
  near(convertLevel(1, 'Vrms', 'Watt', r), 1 / r);
  near(convertLevel(1, 'Watt', 'dBm', r), 30);
  near(convertLevel(1, 'Vrms', 'dBm', r), 10 * Math.log10(1 / r / 0.001));
  near(convertLevel(1, 'Vrms', 'dBV', r), 0);
  near(convertLevel(1, 'Vrms', 'dBmV', r), 60);
  near(convertLevel(1, 'Vrms', 'dBµV', r), 120);
  for (const from of FFT_UNITS) for (const to of FFT_UNITS) {
    for (const v of [1e-5, 0.002, 0.7, 10]) {
      const a = convertLevel(v, 'Vrms', from, r);
      near(convertLevel(convertLevel(a, from, to, r), to, from, r), a);
    }
  }
}
assert.ok(Number.isNaN(convertLevel(-1, 'Watt', 'dBm')));
const peaks = [{ x: 30, y: 3 }, { x: 10, y: 3 }, { x: 20, y: 2 }, { x: 40, y: 1 }];
const params = { level: 1, count: 2, sort: 'Decreasing Magnitude' };
assert.deepEqual(selectPeaks(peaks, params).map(p => p.x), [10, 30]);
assert.deepEqual(selectPeaks(peaks, { ...params, sort: 'Increasing Frequency' }).map(p => p.x), [10, 20]);
assert.deepEqual(selectPeaks(peaks, { ...params, sort: 'Decreasing Frequency' }).map(p => p.x), [30, 20]);
assert.deepEqual(selectPeaks(peaks, { ...params, sort: 'Increasing Magnitude' }).map(p => p.x), [20, 10]);
assert.equal(selectPeaks(peaks, { ...params, level: 3 }).length, 0);
assert.deepEqual(peaks.map(p => p.x), [30, 10, 20, 40]);
assert.equal(needsRefetch({ key: 'k', floor: -40 }, 'k', -40), false);
assert.equal(needsRefetch({ key: 'k', floor: -40 }, 'k', -20), false);
assert.equal(needsRefetch({ key: 'k', floor: -40 }, 'k', -41), true);
assert.equal(needsRefetch({ key: 'k', floor: -40 }, 'other', -20), true);
assert.equal(needsRefetch(null, 'k', -20), true);
assert.equal(peaksTruncated(Array(999).fill({ y: 0 })), false);
assert.equal(peaksTruncated(Array(1000).fill({ y: 0 })), true);
assert.equal(peaksTruncated(Array(1001).fill({ y: 0 })), true);
const rect = { l: 0, t: 0, w: 100, h: 100 };
assert.equal(fftGesture(rect, 50, 54, 50), 'baseline');
assert.equal(fftGesture(rect, 50, 46, 50), 'baseline');
assert.equal(fftGesture(rect, 50, 54.01, 50), 'pan');
assert.equal(fftGesture(rect, -1, 50, 50), null);
assert.equal(fftGesture(rect, 50, 2, -1), 'pan');
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.style = {}; this.listeners = {}; this.attrs = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, fn) { (this.listeners[k] ??= []).push(fn); }
  removeEventListener(k, fn) { this.listeners[k] = this.listeners[k]?.filter(f => f !== fn); }
  emit(k, e) { for (const fn of [...this.listeners[k] ?? []]) fn(e); }
  getBoundingClientRect() { return { left: 0, top: 0 }; }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture() { this.capture = null; }
}
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.window = new Element();
const store = createStore(), calls = [], p = { on: true, source: 'CH1', window: 'Hanning', unit: 'dBm', imp: 0, manualR: 50, peakLevel: -40, peakCount: 5, peakSort: 'Decreasing Magnitude' };
store.set({ file: { gen: 1 }, channels: [{ name: 'CH1', time_offset: 0 }] });
const bridge = { async job(method, args) {
  calls.push([method, args]);
  return { ok: true, spectrum_id: `s${calls.length}`, gen: 1, unit: args.unit, r_ohm: args.r_ohm,
    peaks: [{ x: 10, y: -10 }, { x: 20, y: -20 }, { x: 30, y: -30 }] };
} };
const ctx = { store, bridge, fmt }, fft = createFft(ctx, { fft_impedances: [['50Ω', 50]] }, p, { delay: 1 });
const model = fftMarkerModel(ctx), wait = () => new Promise(resolve => setTimeout(resolve, 15));
await fft.run();
assert.equal(calls.length, 1);
assert.equal(calls[0][1].peak_count, 1000);
assert.equal(calls[0][1].peak_sort, 'Decreasing Magnitude');
assert.equal(calls[0][1].peak_level, -40);
p.peakCount = 1; p.peakSort = 'Increasing Frequency'; p.peakLevel = -20; await wait();
assert.equal(calls.length, 1); assert.deepEqual(model.rows(), [{ x: 10, y: -10 }]);
p.peakLevel = -40; await wait(); assert.equal(calls.length, 1);
p.peakLevel = -45; await wait(); assert.equal(calls.length, 2); assert.equal(calls[1][1].peak_level, -45);
p.peakLevel = -42; p.peakCount = 2000; await wait(); assert.equal(calls.length, 2);
const controls = Object.fromEntries(['unit', 'lvl', 'cnt', 'sort'].map(k => [k, new Element('input')]));
bindFftMarkerControls(ctx, p, controls);
model.resistance(100); p.unit = 'Vrms'; near(p.peakLevel, convertLevel(-42, 'dBm', 'Vrms', 100));
p.unit = 'dBm'; model.resistance(50);
store.command('fftMarker.level', -25); assert.equal(controls.lvl.value, '-25'); assert.equal(p.peakLevel, -25);
controls.cnt.value = '2'; controls.cnt.onchange(); assert.equal(model.state().count, 2);
controls.lvl.value = '-30'; controls.lvl.onchange(); assert.equal(model.state().level, -30);
controls.unit.value = 'Vrms'; controls.unit.onchange(); near(model.state().level, Math.sqrt(50 * 0.001 * 10 ** (-30 / 10)));
await wait(); assert.equal(calls.length, 3); assert.equal(calls.at(-1)[1].unit, 'Vrms');
controls.lvl.value = '-1'; controls.lvl.onchange(); assert.ok(model.state().level >= 0);
controls.cnt.value = '1.5'; controls.cnt.onchange(); assert.equal(model.state().count, 2);
// 回到 dBm，實際事件驗證：命中線不准進入平移，放開才補抓；Esc／取消復原。
p.unit = 'dBm'; p.peakLevel = -40; await fft.run();
const canvas = new Element('canvas'), Y = linear(0, -100, 0, 100);
const layer = createFftMarkerLayer(canvas, ctx, () => rect, () => Y, () => store.get().fftResult, () => {});
let pans = 0, pan = false;
canvas.addEventListener('pointerdown', e => { if (!layer.owns() && !layer.hit(e)) pan = true; });
canvas.addEventListener('pointermove', () => { if (pan) pans++; });
canvas.addEventListener('pointerup', () => { pan = false; });
const ev = y => ({ button: 0, pointerId: 1, clientX: 50, clientY: y, preventDefault() {} });
const before = calls.length;
canvas.emit('pointerdown', ev(44)); canvas.emit('pointermove', ev(60));
assert.equal(pans, 0); assert.equal(model.state().preview, -60); assert.equal(model.state().level, -40);
assert.equal(controls.lvl.value, '-60'); await wait(); assert.equal(calls.length, before);
canvas.emit('pointerup', ev(60)); assert.equal(model.state().level, -60); await wait(); assert.equal(calls.length, before + 1);
canvas.emit('pointerdown', ev(60)); canvas.emit('pointermove', ev(80)); window.emit('keydown', { key: 'Escape' });
assert.equal(model.state().preview, null); assert.equal(model.state().level, -60); await wait(); assert.equal(calls.length, before + 1);
canvas.emit('pointerdown', ev(60)); canvas.emit('pointermove', ev(80)); canvas.emit('pointercancel', ev(80));
assert.equal(model.state().level, -60); assert.equal(model.state().preview, null);
canvas.emit('pointerdown', ev(65)); canvas.emit('pointermove', ev(70)); canvas.emit('pointerup', ev(70)); assert.equal(pans, 1);
// 表格只有一份，含差值／內插／截斷提示；點列沿用 rf.intent，RF 使用定案門檻。
const tableHost = new Element(); mountFftMarkerTable(tableHost, ctx, () => '頻譜');
let selected;
store.onCommand('rf.intent', value => { selected = value; });
store.set({ fftResult: { ok: true, unit: 'dBm', spectrum_id: 'table', peaks: [{ x: 10, y: -10 }, { x: 20, y: -20 }] } });
const table = tableHost.children.find(e => e.tagName === 'table');
assert.deepEqual(table.children[0].children.map(e => e.textContent), ['#', '頻率', '振幅', '高於基準線']);
assert.equal(table.children[1].children[3].textContent, '50 dB');
table.children[1].onclick(); assert.deepEqual(selected, { direction: 0, x: 10 });
assert.match(tableHost.children.at(-1).textContent, /頻率已內插/);
store.set({ fftResult: { ok: true, unit: 'dBm', spectrum_id: 'table', peaks: Array.from({ length: 1000 }, (_, x) => ({ x, y: -10 })) } });
assert.match(tableHost.children.at(-1).textContent, /已截斷/);
let rfArgs;
createController({ store, bridge: { async call(method, args) { if (method === 'fft_track_rf') rfArgs = args; return { x: args.x, y: -10 }; } } });
model.preview(-80); store.command('rf.intent', { direction: 1, x: 10 });
assert.equal(rfArgs.level, -60); model.preview(null);
layer.dispose(); fft.invalidate();
// 在途快取：提高門檻／n／排序不丟棄可用工作，低於抓取值才重抓。
let release;
bridge.job = (method, args) => { calls.push([method, args]); return new Promise(resolve => { release = () => resolve({ ok: true, gen: 1, unit: args.unit, spectrum_id: 'pending', peaks: [] }); }); };
const pending = fft.run(); const pendingCount = calls.length;
p.peakLevel = -50; p.peakCount = 3; p.peakSort = 'Increasing Magnitude'; await wait();
assert.equal(calls.length, pendingCount); release(); await pending;
assert.equal(store.get().fftResult.spectrum_id, 'pending');
store.set({ file: { gen: 2 } }); assert.equal(p.on, false); assert.equal(model.state().preview, null);
fft.invalidate();
// 審查修正：截斷判斷看基準線、unit 指令拒絕 Phase、失敗後可重抓。
const big = Array.from({ length: 1000 }, (_, i) => ({ x: i, y: -50 - i / 100 }));
assert.equal(peaksTruncated(big, -55), false); assert.equal(peaksTruncated(big, -70), true);
const u0 = model.state().unit; store.command('fftMarker.unit', 'Phase'); store.command('fftMarker.unit', 'foo');
assert.equal(model.state().unit, u0);
model.accept({ ok: true, spectrum_id: 'x' }, { source: 'CH1', peak_level: -40 }); model.fail();
assert.equal(model.needs({ source: 'CH1' }), true);
console.log('fft_marker self-check OK');
// P2：真實分頁掛載＋兩組控制列，單一 runner 的開關／dirty／換檔生命週期。
{
  const { getFftState, mountFftControls } = await import('./fft_state.js');
  const { mount: mountTab } = await import('./tab_fft.js');
  const { mount: mountPane } = await import('./fftpane.js');
  Element.prototype.querySelector = function(k) { return (this.nodes ??= {})[k] ??= new Element(); };
  Element.prototype.getContext = () => new Proxy({}, { get: () => () => {}, set: () => true });
  Element.prototype.getBoundingClientRect = () => ({ left: 0, top: 0, width: 600, height: 320 });
  Object.defineProperty(Element.prototype, 'options', { get() { return this.children; } });
  globalThis.Option = class extends Element { constructor(text, value) { super('option'); this.textContent = text; this.value = String(value); } };
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '#333' });
  const s = createStore(), jobs = [], fetches = [];
  const cat = { fft_windows: { Hanning: 1, Hamming: 1 }, fft_units: ['dBm', 'Vrms'],
    fft_impedances: [['50 Ω', 50], ['手動 Ω', null]], peak_sorts: ['Decreasing Magnitude', 'Increasing Frequency'] };
  const c = { store: s, fmt, activeTab: 'analysis', appState: { catalog: cat }, ui: { toast() {}, showError() {} }, bridge: {
    async job(method, args) { jobs.push(args); return { ok: true, gen: s.get().file.gen, spectrum_id: `p2-${jobs.length}`, unit: args.unit, f_max: 100, peaks: [{ x: 10, y: -10 }] }; },
    async fetchSpectrum(args) { fetches.push(args); return { n: 0, x: [], lo: [], hi: [] }; },
  } };
  s.set({ file: { gen: 1 }, channels: [{ name: 'CH1' }, { name: 'CH2' }] });
  const toolbarControls = mountFftControls(new Element(), c), page = new Element();
  mountTab(page, c);
  const state = getFftState(c), tick = () => new Promise(resolve => setTimeout(resolve, 230));
  assert.equal(state, getFftState(c));
  s.command('tab.activated', 'analysis');
  s.set({ cursors: { ...s.get().cursors, x1: 0.1 } }); await tick();
  assert.equal(jobs.length, 0); assert.equal(state.runner.dirty, true);
  s.command('tab.activated', 'fft'); await tick(); assert.equal(jobs.length, 1);
  const result = s.get().fftResult;
  s.command('tab.activated', 'analysis'); assert.equal(state.p.on, false); assert.equal(s.get().fftResult, result);
  s.command('tab.activated', 'fft'); await tick(); assert.equal(jobs.length, 1);
  const root = page.children[0], sourceRow = root.children[1], paramsRow = root.children[2];
  const controls = [sourceRow.children[0].children[0], paramsRow.children[0].children[0], paramsRow.children[1].children[0], paramsRow.children[2].children[0], paramsRow.children[3]];
  for (const [a, b, value] of [[toolbarControls.src, controls[0], 'CH2'], [controls[1], toolbarControls.win, 'Hamming'],
    [toolbarControls.imp, controls[3], '1'], [controls[4], toolbarControls.man, '75'], [toolbarControls.unit, controls[2], 'Vrms']]) {
    a.value = value; a.onchange(); assert.equal(b.value, value);
  }
  const markerRow = root.children[3].children[1].children[0];
  const [sort2, lvl2, cnt2] = markerRow.children.map(label => label.children[0]);
  toolbarControls.cnt.value = '9'; toolbarControls.cnt.onchange(); assert.equal(cnt2.value, '9');
  lvl2.value = '0.1'; lvl2.onchange(); assert.equal(toolbarControls.lvl.value, '0.1');
  sort2.value = 'Increasing Frequency'; sort2.onchange(); assert.equal(toolbarControls.sort.value, sort2.value);
  await tick(); const n = jobs.length;
  // 勾選開時，切出 FFT 仍計算；關時只 dirty，回分頁才補一次。
  state.setAnalysisOn(true); s.command('tab.activated', 'analysis'); assert.equal(state.p.on, true);
  s.set({ rangeMode: 'cursors' }); await tick(); assert.equal(jobs.length, n + 1);
  state.setAnalysisOn(false); const kept = s.get().fftResult;
  s.set({ cursors: { ...s.get().cursors, x2: 0.2 } }); await tick();
  assert.equal(jobs.length, n + 1); assert.equal(s.get().fftResult, kept);
  s.command('tab.activated', 'fft'); await tick(); assert.equal(jobs.length, n + 2);
  assert.deepEqual(jobs.at(-1).range, [0.1, 0.2]);
  s.set({ file: { gen: 2 } }); assert.equal(s.get().fftResult, null); assert.equal(state.p.on, true);
  await tick(); assert.equal(jobs.length, n + 3);
  // 第二張圖有各自的視窗／請求取消器；縮放一張不會改另一張。
  const other = new Element(), pane = mountPane(other, c); await tick();
  const otherCanvas = other.querySelector('.analysis__fftplot').children[0];
  otherCanvas.emit('wheel', { clientX: 64, deltaY: -120, preventDefault() {} }); await tick();
  assert.ok(fetches.at(-1).f1 < 100);
  const pageCanvas = root.children[3].children[0].querySelector('.analysis__fftplot').children[0];
  pageCanvas.emit('wheel', { clientX: 64, deltaY: 120, preventDefault() {} }); await tick();
  assert.ok(fetches.at(-1).f1 > 100);
  s.command('tab.activated', 'analysis'); s.set({ file: { gen: 3 } });
  assert.equal(s.get().fftResult, null); await tick(); assert.equal(jobs.length, n + 3);
  // 停算期間改參數仍同步另一處，卻不發工作。
  toolbarControls.win.value = 'Hanning'; toolbarControls.win.onchange();
  assert.equal(controls[1].value, 'Hanning'); await tick(); assert.equal(jobs.length, n + 3);
  // 切出時取消在途工作；舊結果回來也不得污染新工作／新檔。
  let finishOld;
  c.bridge.job = (method, args) => new Promise(resolve => { finishOld = () => resolve({ ok: true, gen: 3, spectrum_id: 'old', unit: args.unit, peaks: [] }); });
  s.command('tab.activated', 'fft'); await tick();
  s.command('tab.activated', 'analysis'); assert.equal(state.runner.dirty, true);
  finishOld(); await tick(); assert.equal(s.get().fftResult, null);
  pane.dispose(); state.runner.invalidate();
  console.log('fft P2 shared state / controls / two panes self-check OK');
}
