import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { getFftState, mountFftControls } from './fft_state.js';
import { fftParams } from './fft_runner.js';
import { bindViewport } from './gestures.js';
import { stackLayout } from './vertical.js';
import * as scales from './scales.js';
import * as fmt from '../fmt.js';
class Element {
  constructor() { this.children = []; this.style = {}; this.options = []; }
  append(...nodes) { this.children.push(...nodes); if (this.isSelect) this.options.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this.options = nodes; }
  setAttribute() {}
}
globalThis.document = { createElement: tag => Object.assign(new Element(), { isSelect: tag === 'select' }) };
globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
const store = createStore(), jobs = [], catalog = { fft_windows: { Hanning: [] }, fft_units: ['dBm', 'Phase'], fft_impedances: [['50', 50]], peak_sorts: ['Decreasing Magnitude'] };
store.set({ file: { gen: 1 }, channels: [{ name: 'CH1', time_offset: 0.001 }] });
const ctx = { store, fmt, activeTab: 'fft', appState: { catalog }, ui: {}, bridge: { async job(_, args) { jobs.push(args); return { ok: true, gen: 1, unit: args.unit, peaks: [] }; } } };
const state = getFftState(ctx), controls = mountFftControls(new Element(), ctx);
assert.equal(controls.ref.disabled, true); assert.equal(controls.unwrap.disabled, true);
controls.unit.value = 'Phase'; controls.unit.onchange();
assert.equal(controls.ref.disabled, false); assert.equal(controls.unwrap.disabled, false);
controls.ref.value = '2 ms'; controls.ref.onchange(); controls.unwrap.checked = true; controls.unwrap.onchange();
await new Promise(resolve => setTimeout(resolve, 200));
assert.equal(jobs.at(-1).phase_ref, 0.002); assert.equal(jobs.at(-1).unwrap, true);
controls.ref.value = 'bad'; controls.ref.onchange(); assert.equal(state.p.phaseRef, 0.002);
controls.ref.value = ''; controls.ref.onchange(); assert.equal(state.p.phaseRef, null);
controls.unit.value = 'dBm'; controls.unit.onchange();
assert.equal(controls.ref.disabled, true); assert.equal(controls.unwrap.disabled, true);
assert.equal(fftParams(store.get(), state.p, catalog).phase_ref, null); assert.equal(fftParams(store.get(), state.p, catalog).unwrap, false);
store.set({ file: null }); assert.equal(controls.ref.disabled, true); state.runner.invalidate(); controls.dispose();
console.log('view more Phase controls self-check OK');

for (let n = 1; n <= 8; n++) {
  const channels = Array.from({ length: n }, (_, i) => ({ name: `C${i}`, visible: true, unit: 'V', vmin: -1, vmax: 1 }));
  const result = stackLayout(channels, scales);
  assert.equal(result.length, n);
  result.forEach((c, i) => { assert.ok(Math.abs(c.position - (5 - (i + 0.5) * 10 / n)) < 1e-12); assert.ok(2 / c.scale <= 10 / n); });
}
const varied = stackLayout([
  { name: 'A', visible: true, unit: 'A', vmin: -0.3, vmax: 0.7 },
  { name: 'min', visible: true, unit: 'V', vmin: 0, vmax: 0 },
  { name: 'max', visible: true, unit: 'V', vmin: -1e6, vmax: 1e6 },
  { name: 'nan', visible: true, unit: 'V', vmin: null, vmax: null },
  { name: 'hidden', visible: false, unit: 'V', vmin: -1, vmax: 1 },
], scales);
assert.deepEqual(varied.map(c => c.name), ['A', 'min', 'max']);
assert.equal(varied[0].scale, 0.5); assert.equal(varied[1].scale, scales.V_TABLE[0]); assert.equal(varied[2].scale, scales.V_TABLE.at(-1));
assert.ok(Math.abs(varied[0].position + 0.2 / varied[0].scale - (5 - 5 / 3)) < 1e-12);
console.log('view more stack layout self-check OK');

const historyStore = createStore();
const initial = Array.from({ length: 3 }, (_, i) => ({ name: `H${i}`, visible: true, unit: 'V', vmin: -1, vmax: 1, scale: 1, position: 0 }));
historyStore.set({ channels: initial });
historyStore.onCommand('channel.scale_intent', ({ name, scale, position }) => historyStore.updateChannel(name, { scale, position }, 'user'));
bindViewport(historyStore);
historyStore.command('view.historyGroup', { key: 'arrange', continuous: true });
historyStore.command('view.zoomRect', { channels: stackLayout(initial, scales) });
historyStore.command('view.historyGroup', { end: true });
assert.notDeepEqual(historyStore.get().channels, initial);
historyStore.command('view.undo'); assert.deepEqual(historyStore.get().channels, initial);
console.log('view more grouped undo self-check OK');
