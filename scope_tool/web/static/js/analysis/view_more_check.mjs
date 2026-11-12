import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { getFftState, mountFftControls } from './fft_state.js';
import { fftParams } from './fft_runner.js';
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
