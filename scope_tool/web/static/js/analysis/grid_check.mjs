import assert from 'node:assert/strict';
import { GRID_COUNTS, GRID_GAP, GRIDS_KEY, gridsOf, gridIndex, gridRows, withGrids, rowOf, rowAt, setCount, assignGrid, loadGrids, saveGrids, bindGrids, groupByGrid, gridMenuItems, gridSelect } from './grids.js';
import { channelHandles, handlePosition, handleDrop, cursorEdges } from './handles.js';
import { markerPixels } from './mainplot.js';
import { bindViewport, bindGestures, nearestCursor } from './gestures.js';
import { verticalRect } from './vzoom.js';
import { nearestChannel, markerPoints } from './marker_layer.js';
import { stackLayout } from './vertical.js';
import * as scales from './scales.js';
import { createStore } from './store.js';
const base = { l: 84, t: 8, w: 800, h: 500 };
const channels = Array.from({ length: 8 }, (_, i) => ({ name: `CH${i + 1}`, visible: i !== 1, color: '#fff', position: 0, scale: 1 }));
const one = { n: 1, assign: {} }, two = { n: 2, assign: {} };
for (const n of GRID_COUNTS) {
  const g = { n, assign: {} }, rows = gridRows(base, g, channels);
  channels.forEach((c, i) => assert.equal(gridIndex(g, channels, c.name), i % n));
  assert.equal(rows.length, n);
  assert.ok(rows.every(r => r.h === rows[0].h));
  assert.equal(rows.reduce((sum, r) => sum + r.h, 0) + GRID_GAP * (n - 1), base.h);
}
const first = gridRows(base, one, channels)[0];
assert.deepEqual({ l: first.l, t: first.t, w: first.w, h: first.h }, base);
assert.deepEqual(first.names, channels.map(c => c.name));
assert.deepEqual(gridsOf({ grids: { n: 3, assign: {} } }), one);
for (const grids of [null, {}, { n: 2, assign: null }, { n: 2, assign: [] }]) assert.deepEqual(gridsOf({ grids }), one);
assert.equal(gridIndex({ n: 2, assign: { CH1: 1 } }, channels, 'CH1'), 1);
for (const k of [2, -1, 0.5, '1', NaN]) assert.equal(gridIndex({ n: 2, assign: { CH2: k } }, channels, 'CH2'), 1);
assert.equal(gridIndex(two, channels.map(c => ({ ...c, visible: true })), 'CH3'), 0);
const r = withGrids(base, two, channels, 'CH2');
assert.equal(r.of('CH2'), r.rows[1]); assert.equal(r.cy, r.rows[1]);
assert.equal(withGrids(base, two, channels).cy.index, 0);
assert.equal(r.at(-999), r.rows[0]); assert.equal(r.at(9999), r.rows[1]);
assert.equal(r.at(r.rows[0].t + r.rows[0].h + 2), r.rows[0]);
assert.equal(r.at(r.rows[1].t), r.rows[1]);
assert.equal(rowOf(base, 'CH1'), base); assert.equal(rowAt(base, 20), base);
assert.equal(rowOf(r, 'CH2'), r.rows[1]); assert.equal(rowAt(r, 999), r.rows[1]);
const snapshot = JSON.stringify(two), counted = setCount(two, 8), assigned = assignGrid(two, 'CH1', 1);
assert.deepEqual(counted, { n: 8, assign: {} }); assert.deepEqual(assigned, { n: 2, assign: { CH1: 1 } });
assert.equal(JSON.stringify(two), snapshot); assert.notEqual(counted.assign, two.assign);
assert.deepEqual(assignGrid(assigned, 'CH1', -1), two);
let raw = null;
const storage = { getItem: k => { assert.equal(k, GRIDS_KEY); return raw; }, setItem: (k, v) => { assert.equal(k, GRIDS_KEY); raw = v; } };
for (const bad of ['{', '{"n":3,"assign":{}}', 'null']) { raw = bad; assert.deepEqual(loadGrids(storage), one); }
raw = '{"n":2,"assign":{"CH1":9,"CH2":1,"CH3":-1,"CH4":0.5}}';
assert.deepEqual(loadGrids(storage), { n: 2, assign: { CH2: 1 } });
saveGrids(assigned, storage); assert.deepEqual(loadGrids(storage), assigned);
const denied = { getItem() { throw Error(); }, setItem() { throw Error(); } };
assert.deepEqual(loadGrids(denied), one); saveGrids(two, denied);
const store = createStore(), origins = [];
store.on(['grids'], (_s, _keys, origin) => origins.push(origin));
const off = bindGrids(store, storage); assert.deepEqual(store.get().grids, assigned); assert.deepEqual(origins, ['program']);
store.set({ grids: two }, 'user'); assert.deepEqual(loadGrids(storage), two);
off(); store.set({ grids: one }); assert.deepEqual(loadGrids(storage), two);
const visible = channels.map(c => ({ ...c, visible: true }));
const b = channelHandles(visible, r).find(b => b.name === 'CH2');
assert.ok(b.anchorY >= r.rows[1].t && b.anchorY <= r.rows[1].t + r.rows[1].h);
// 固定舊版普通 rect 的欄位與避讓結果，並比對單格包裝。
const old = [{ name: 'CH1', title: 'CH1', color: '#fff', position: 0, label: '●1', anchorY: 258, x: 2, y: 248, w: 24, h: 20 },
  { name: 'CH2', title: 'CH2', color: '#fff', position: 0, label: '▲2', anchorY: 258, x: 2, y: 272, w: 24, h: 20 }];
assert.deepEqual(channelHandles(visible.slice(0, 2), base), old);
assert.deepEqual(channelHandles(visible, withGrids(base, one, visible)), channelHandles(visible, base));
assert.equal(handlePosition(2, 25, base), 1.5);
assert.equal(handlePosition(2, 25, r, 'CH2'), 2 - 250 / r.rows[1].h);
const pixels = markerPixels({ points: [{ x: 1, y: 0, ch: 'CH1' }, { x: 2, y: 0, ch: 'CH2' }, { x: 3, y: 0 }] }, x => x, r);
assert.equal(pixels[0].py, r.rows[0].t + r.rows[0].h / 2);
assert.equal(pixels[1].py, r.rows[1].t + r.rows[1].h / 2); assert.equal(pixels[2].py, pixels[1].py);
assert.equal(cursorEdges({ y1: 6 }, {}, r)[0].y, r.cy.t + 54);
const cache = new Map(visible.map(c => [c.name, { px: { x: [10], top: [r.rows[1].t], bot: [r.rows[1].t], mode: 0 } }]));
assert.equal(nearestChannel(visible, cache, 10, r.rows[1].t, null, r), 'CH2');
// 分格指派與垂直縮放共用一次歷史；不變的指派不得新增歷史。
const viewport = createStore(), history = bindViewport(viewport);
const pair = visible.slice(0, 2).map(c => ({ ...c, unit: 'V' }));
viewport.set({ channels: pair, grids: one });
viewport.onCommand('channel.scale_intent', ({ name, ...patch }) => viewport.updateChannel(name, patch, 'user'));
viewport.command('view.zoomRect', { grids: two });
assert.deepEqual(history.status(), { undo: 1, redo: 0 }); assert.deepEqual(viewport.get().grids, two);
viewport.command('view.undo'); assert.deepEqual(viewport.get().grids, one);
viewport.command('view.redo'); assert.deepEqual(viewport.get().grids, two);
viewport.command('view.zoomRect', { grids: { n: 2, assign: {} } });
assert.deepEqual(history.status(), { undo: 1, redo: 0 });
viewport.command('view.undo');
viewport.command('view.zoomRect', { grids: assigned, channels: [{ name: 'CH2', scale: 0.5, position: 2 }] });
assert.deepEqual(history.status(), { undo: 1, redo: 0 });
assert.deepEqual(viewport.get().grids, assigned); assert.equal(viewport.get().channels[1].scale, 0.5);
viewport.command('view.undo');
assert.deepEqual(viewport.get().grids, one); assert.deepEqual(viewport.get().channels, pair);
viewport.command('view.redo');
assert.deepEqual(viewport.get().grids, assigned); assert.equal(viewport.get().channels[1].position, 2);
const unset = createStore(), unsetHistory = bindViewport(unset);
assert.equal(unset.get().grids, undefined);
unset.command('view.zoomRect', { grids: two }); unset.command('view.undo');
assert.deepEqual(unset.get().grids, one); assert.deepEqual(unsetHistory.status(), { undo: 0, redo: 1 });
unset.command('view.redo'); assert.deepEqual(unset.get().grids, two);
// 第 1 格（index=1）內框選以該格高度換算，並排除其他格通道。
const split = withGrids(base, two, pair, 'CH2'), second = split.rows[1];
const zoom = verticalRect(pair, second.t + second.h / 4, second.t + second.h * 3 / 4, split, 6);
assert.deepEqual(zoom, [{ name: 'CH2', scale: 0.5, position: 0 }]);
assert.deepEqual(verticalRect(pair, second.t + second.h / 4, base.t + base.h + 100, split, 6),
  [{ name: 'CH2', scale: 0.75, position: 5 / 3 }]);
const ordinary = verticalRect(pair, base.t + base.h / 4, base.t + base.h * 3 / 4, base, 6);
assert.deepEqual(ordinary, pair.map(c => ({ name: c.name, scale: 0.5, position: 0 })));
assert.deepEqual(verticalRect(pair, base.t + base.h / 4, base.t + base.h * 3 / 4, withGrids(base, one, pair), 6), ordinary);
const view = { t0: 0, t1: 10 }, mid = row => row.t + row.h / 2;
assert.equal(nearestCursor({ y1: 0 }, view, split, 400, mid(second), 'mouse'), 'y1');
assert.equal(nearestCursor({ y1: 0 }, view, split, 400, mid(split.rows[0]), 'mouse'), null);
assert.equal(nearestCursor({ y1: 0 }, view, base, 400, mid(base), 'mouse'), 'y1');
assert.equal(nearestCursor({ x1: 5 }, view, split, base.l + base.w / 2, mid(split.rows[0]), 'mouse'), 'x1');
// 刻意讓另一格通道距離更近，仍只命中目前格內通道。
const overlapping = new Map(pair.map(c => [c.name, { px: { x: [400], top: [mid(second)], bot: [mid(second)], mode: 0 } }]));
assert.equal(nearestChannel(pair, overlapping, 400, mid(second), null, split), 'CH2');
assert.equal(nearestChannel(pair, overlapping, 400, mid(second), null, base), 'CH1');
const model = { rows: () => pair.flatMap(channel => [0, 6, -6].map(value => ({ channel, value, t: 5 }))) };
const points = markerPoints(model, { view }, split);
assert.deepEqual(points.map(p => [p.channel.name, p.x, p.y]), [['CH1', 484, mid(split.rows[0])], ['CH2', 484, mid(second)]]);
assert.equal(markerPoints(model, { view }, base).length, 2);
assert.deepEqual(markerPoints(model, { view }, withGrids(base, one, pair)), markerPoints(model, { view }, base));
// 格數選單與通道選擇器直接使用產品函式及真實歷史接線。
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; }
  setAttribute(k, v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  replaceChildren(...nodes) { this.children = nodes; }
  get options() { return this.children; }
}
globalThis.document = { createElement: tag => new Element(tag) };
globalThis.Option = class extends Element {
  constructor(text, value) { super('option'); this.textContent = text; this.value = value; }
};
const uiStore = createStore(), uiHistory = bindViewport(uiStore), sent = [];
uiStore.set({ channels: pair, grids: one });
uiStore.onCommand('view.zoomRect', payload => sent.push(payload));
const items = gridMenuItems(uiStore, (text, fn) => {
  const el = new Element('button'); el.textContent = text; el.onclick = fn; return el;
});
assert.deepEqual(items.map(el => el.textContent), ['1 格', '2 格', '4 格', '8 格']);
assert.ok(items.every(el => el.getAttribute('role') === 'menuitem'));
for (const [i, n] of GRID_COUNTS.entries()) {
  uiStore.set({ grids: setCount(one, n) });
  assert.deepEqual(items.map(el => el.getAttribute('aria-current')), GRID_COUNTS.map((_, j) => i === j ? 'true' : null));
}
uiStore.set({ grids: one });
items[2].onclick(); assert.deepEqual(sent.at(-1), { grids: { n: 4, assign: {} } });
assert.deepEqual(uiHistory.status(), { undo: 1, redo: 0 });
uiStore.command('view.undo'); assert.deepEqual(uiStore.get().grids, one);
assert.equal(items[0].getAttribute('aria-current'), 'true');
const chooser = gridSelect(uiStore, 'CH1'); assert.equal(chooser.el.hidden, true);
assert.equal(chooser.el.className, 'chip__grid'); assert.equal(chooser.el.getAttribute('aria-label'), '所在格');
uiStore.set({ grids: setCount(one, 4) }); chooser.sync();
assert.equal(chooser.el.hidden, false); assert.equal(chooser.el.options.length, 4);
assert.deepEqual(chooser.el.options.map(el => [el.textContent, el.value]), ['格 1', '格 2', '格 3', '格 4'].map((text, i) => [text, String(i)]));
assert.equal(chooser.el.value, '0');
chooser.el.value = '3'; chooser.el.onchange();
assert.deepEqual(sent.at(-1), { grids: { n: 4, assign: { CH1: 3 } } });
assert.deepEqual(uiStore.get().grids.assign, { CH1: 3 });
uiStore.command('view.undo'); chooser.sync(); assert.equal(chooser.el.value, '0');
uiStore.set({ grids: one }); chooser.sync(); assert.equal(chooser.el.hidden, true);
const stackPair = pair.map(c => ({ ...c, vmin: -1, vmax: 1 }));
const sameGrid = { n: 2, assign: { CH1: 0, CH2: 0 } };
assert.deepEqual(groupByGrid(sameGrid, stackPair), [stackPair, []]);
const stacked = groupByGrid(sameGrid, stackPair).flatMap(g => stackLayout(g, scales));
assert.notEqual(stacked[0].position, stacked[1].position);
assert.deepEqual(groupByGrid(two, stackPair).flatMap(g => stackLayout(g, scales)), stackPair.flatMap(c => stackLayout([c], scales)));
assert.deepEqual(groupByGrid(one, stackPair).flatMap(g => stackLayout(g, scales)), stackLayout(stackPair, scales));
assert.deepEqual(groupByGrid(two, channels).flat(), [...channels.filter((_, i) => i % 2 === 0), ...channels.filter((_, i) => i % 2 === 1)]);
// 純幾何：抓取偏移、間隙最近格、圖外、夾限與舊單格行為。
const target = r.rows[1], center = mid(target), near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9);
assert.deepEqual(handleDrop(r, 'CH1', center), { row: target, same: false, position: 0 });
near(handleDrop(r, 'CH1', center, 6).position, 60 / target.h);
for (const offset of [1, 3]) assert.equal(handleDrop(r, 'CH1', r.rows[0].t + r.rows[0].h + offset).row.index, offset === 1 ? 0 : 1);
for (const y of [base.t - 1, base.t + base.h + 1]) assert.equal(handleDrop(r, 'CH1', y), null);
for (const grab of [-9999, 9999]) assert.equal(handleDrop(r, 'CH1', center, grab).position, Math.sign(grab) * 5);
for (const rect of [base, withGrids(base, one, pair)]) for (const y of [-999, 9999]) assert.equal(handleDrop(rect, 'CH1', y).same, true);
const savedDOM = [globalThis.document, globalThis.window];
function element() { return { style: {}, listeners: {}, addEventListener(k, fn) { this.listeners[k] = fn; }, removeEventListener(k) { delete this.listeners[k]; },
  setPointerCapture() { this.captured = true; }, hasPointerCapture() { return this.captured; }, releasePointerCapture() { this.captured = false; }, getBoundingClientRect: () => ({ left: 0, top: 0 }) }; }
globalThis.document = { activeElement: null }; globalThis.window = element();
function gestureCase(action, n = 2) {
  const st = createStore(); st.set({ channels: pair.map(c => ({ ...c, position: 1 })), grids: { n, assign: {} } });
  const hist = bindViewport(st), intents = [], commits = [], cv = element(), rect = () => withGrids(base, st.get().grids, st.get().channels);
  st.onCommand('channel.scale_intent', ({ name, ...patch }) => { intents.push(patch); st.updateChannel(name, patch, 'user'); }); st.onCommand('view.zoomRect', p => commits.push(p));
  const gs = bindGestures(cv, { store: st, ui: {} }, rect, () => {}), h = channelHandles(st.get().channels, rect()).find(b => b.name === 'CH2'), start = h.y + h.h / 2 + 6;
  const fire = (type, y) => cv.listeners[type]({ clientX: h.x + h.w / 2, clientY: y, pointerId: 1, button: 0, preventDefault() {} });
  const initial = structuredClone(st.get()), row = rect().rows[0], y = mid(row), pos = () => st.get().channels[1].position, check = () => { assert.deepEqual(st.get(), initial); assert.equal(hist.status().undo, 0); assert.equal(commits.length, 0); };
  fire('pointerdown', start); fire('pointermove', start + 20); near(pos(), 1 - 200 / rect().of('CH2').h);
  if (action === 'same') { fire('pointerup', start + 20); assert.deepEqual(st.get().grids, initial.grids); assert.equal(hist.status().undo, 0); }
  else if (action === 'single') { fire('pointermove', -100); fire('pointerup', -100); assert.ok(pos() > 5); assert.equal(hist.status().undo, 0); }
  else {
    fire('pointermove', y); assert.equal(pos(), 1); assert.deepEqual(st.get().grids, initial.grids);
    const count = intents.length; fire('pointermove', y); assert.equal(intents.length, count);
    const fills = [], g = { save() {}, restore() {}, fillRect(...args) { fills.push(args); } }; gs.overlay(g); assert.deepEqual(fills, [[row.l, row.t, row.w, row.h]]);
    if (action === 'commit') { fire('pointerup', y); assert.deepEqual(st.get().grids, assignGrid(initial.grids, 'CH2', 0)); near(pos(), 60 / row.h); assert.equal(commits.length, 1); assert.equal(hist.status().undo, 1);
      const after = structuredClone(st.get()); st.command('view.undo'); assert.deepEqual(st.get(), initial); st.command('view.redo'); assert.deepEqual(st.get(), after); }
    else { if (action === 'return') fire('pointermove', start); else if (action === 'outside') { fire('pointermove', base.t - 1); fills.length = 0; gs.overlay(g); assert.deepEqual(fills, []); }
      else if (action === 'Escape') window.listeners.keydown({ key: 'Escape' }); else if (action === 'blur') window.listeners.blur(); else fire(action, y);
      fire('pointerup', action === 'return' ? start : base.t - 1); check(); }
  }
  gs.dispose();
}
for (const action of ['commit', 'same', 'return', 'Escape', 'pointercancel', 'lostpointercapture', 'blur', 'outside']) gestureCase(action);
gestureCase('single', 1); [globalThis.document, globalThis.window] = savedDOM;
console.log('grid self-check OK');
