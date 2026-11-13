import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { mount as mountDecode } from './decode_table.js';
import { getFftState, mountFftControls } from './fft_state.js';
import { mount as mountToolbar } from './toolbar.js';
import { aliasRows } from './alias.js';
import { collectReport, decodeSection, buildReport } from './report.js';
import * as fmt from '../fmt.js';
import * as scales from './scales.js';
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.style = {}; this.className = ''; this.textContent = ''; this._value = ''; this.classList = { add() {}, toggle() {} }; }
  get value() { return this._value; }
  set value(v) { this._value = this.tagName === 'select' && !this.children.some(o => o.value === v) ? '' : v; }
  get text() { return this.textContent; }
  get options() { return this.children; }
  append(...nodes) { for (const n of nodes) { if (typeof n === 'string') continue; n.parentNode = this; this.children.push(n); } }
  prepend(...nodes) { for (const n of nodes.reverse()) { this.children = this.children.filter(c => c !== n); n.parentNode = this; this.children.unshift(n); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k,v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(k,fn) { (this.listeners[k] ??= []).push(fn); }
  setCustomValidity() {} reportValidity() { return true; }
  closest() { return root; }
  querySelector(s) { return s === '.analysis__fftbar' ? fftBar : null; }
  getBoundingClientRect() { return { left:0,bottom:0,width:0,height:0 }; }
  showModal() {} close() {} remove() {}
}
const root = new Element(), fftBar = new Element(), body = new Element();
globalThis.document = { createElement:t => new Element(t), body, querySelectorAll:() => [] };
globalThis.Option = class extends Element { constructor(text,value) { super('option'); this.textContent = text; this.value = value; } };
globalThis.window = new Element();
const find = (e,fn) => fn(e) ? e : e.children.map(c => find(c,fn)).find(Boolean);
const store = createStore(), jobs = [];
const channels = [{ name:'CH1',visible:true,scale:1,unit:'V',time_offset:0 },{ name:'CH2',visible:true,scale:2,unit:'V',time_offset:0 }];
store.set({ file:{ gen:1,path:'/tmp/a',info:[] },channels,selected:'CH1',fftMarker:{ manual:[{ x:1,y:2 }] } });
const ctx = { store,fmt,scales,appState:{ catalog:{ math_ops:{ binary:['Add'],unary:[],filters:[] } } },bridge:{ job(...a) { jobs.push(a); return new Promise(() => {}); },call:async () => ({}) },ui:{ toast() {},showError(e) { throw e; } } };
const host = new Element(), panel = mountDecode(host,ctx), fft = mountFftControls(new Element(),ctx);
const pick = role => find(host,e => e.dataset.role === role);
const before = { ...panel.model.config.ch };
getFftState(ctx).setAnalysisOn(true); await new Promise(r => setTimeout(r,200));
assert.equal(jobs.filter(([name]) => name === 'fft').length,1);
const manual = store.get().fftMarker.manual;
const decoded = { protocol:'i3c',base:'CH1',stale:false,options:{},frames:[],addresses:[],summary:{ ok:true,gen:1,channels:{ scl:'CH1',sda:'CH2' },thresholds:{ scl:null,sda:null },counts:{ frames:0,errors:0,warns:0 },warnings:[] } };
store.set({ decodeResult:decoded });
const jobCount = jobs.length;
store.set({ channels:channels.map(c => c.name === 'CH1' ? { ...c,alias:'Clock' } : c) });
assert.deepEqual(fft.src.options.map(o => [o.text,o.value]),[['Clock','CH1'],['CH2','CH2']]);
assert.deepEqual(pick('scl').children.map(o => [o.textContent,o.value]),[['Clock','CH1'],['CH2','CH2']]);
assert.deepEqual(panel.model.config.ch,before); assert.equal(store.get().decodeResult.stale,false);
await new Promise(r => setTimeout(r,200));
assert.equal(store.get().fftMarker.manual,manual); assert.equal(jobs.length,jobCount);
const toolbar = new Element(); mountToolbar(toolbar,ctx);
find(toolbar,e => e.textContent === 'Math…').onclick();
const dialog = body.children.at(-1), a = find(dialog,e => e.textContent === '來源 A '), b = find(dialog,e => e.textContent === '來源 B ');
for (const label of [a,b]) assert.deepEqual(label.children[0].options.map(o => [o.text,o.value]),[['Clock','CH1'],['CH2','CH2']]);
assert.deepEqual(aliasRows(store.get().channels),{ head:['別名','原名'],rows:[['Clock','CH1']] });
assert.equal(aliasRows(channels),null);
const reportRoot = { querySelector:() => null }, F = (v,u) => `${v} ${u}`;
const report = await collectReport({ store,fmt:{ fmt:F } },reportRoot,{ title:'test' });
assert.deepEqual(report.sections[0].tables,[aliasRows(store.get().channels)]);
assert.match(report.sections[0].caption,/Clock 1 V\/div/);
assert.match(decodeSection(store.get(),reportRoot,F,false)[0].caption,/SCL Clock／SDA CH2/);
assert.match(buildReport(report),/Clock<\/td><td>CH1/);
fft.dispose();
console.log('alias misc self-check OK');
