// 無框架驗證：資料上限、全精度後端路徑、換檔與手勢優先序。
import assert from 'node:assert/strict';
import { createStore } from './store.js';
import { markerMenuItems, menuPosition } from './marker_menu.js';
import { markerModel } from './markers.js';
import { markerCells, mount as mountTable } from './marker_table.js';
import { gestureFor, bindGestures, bindViewport } from './gestures.js';
import { createMarkerLayer, hitMarker, nearestChannel, markerPoints } from './marker_layer.js';
import { panelVisible, TABS, mountTabs, PAIR_MIN_WIDTH } from './bpanel.js';
const store = createStore(), calls = [];
const channels = ['CH1', 'CH2'].map((name, i) => ({ name, visible: true, t0: 0, t1: 10, time_offset: i, scale: 1, position: 0, unit: 'V', color: '#fff' }));
store.set({ file: { gen: 1, channels: channels.map(c => ({ ...c, points: 11 })) }, channels, selected: 'CH1', view: { t0: 0, t1: 10 } });
const bridge = { async call(name, p) {
  calls.push([name, p]);
  if (name === 'cursor_readout') return { t1: Math.round(p.t1), y: {} };
  return { available: true, position: { x1: Math.round(p.x1), y1: p.channel === 'CH1' ? 1 : 2 } };
} };
const ctx = { store, bridge }, model = markerModel(ctx); bindViewport(store);
assert.ok(model.add({ ch: 'CH1', t: 3, link: true }));
await model.refresh();
assert.deepEqual(model.rows().map(r => [r.id, r.ch, r.t, r.value]), [['M1', 'CH1', 3, 1], ['M1', 'CH2', 3, 2]]);
assert.ok(calls.some(([n]) => n === 'cursor_readout'));
assert.equal(calls.filter(([n]) => n === 'marker_eval').length, 2);
assert.equal(calls.find(([n, p]) => n === 'marker_eval' && p.channel === 'CH2')[1].x1, 2);
for (let i = 0; i < 10; i++) assert.ok(model.add({ ch: 'CH1', t: i }));
assert.equal(model.add({ ch: 'CH1', t: 2 }), false);
assert.ok(model.add({ ch: 'CH2', t: 2 }));
await model.refresh();
model.note({ id: 'M1', note: '連動註記' });
assert.ok(model.rows().filter(r => r.link).every(r => r.note === '連動註記'));
// 純註記保留快取且完全不重讀；位置與外觀更新期間圖點不得消失。
const noteCalls = calls.length;
await new Promise(resolve => setTimeout(resolve, 60));
assert.equal(calls.length, noteCalls);
const cached = model.rows().map(r => r.value);
model.move({ id: 'M2', t: 3.4 });
assert.deepEqual(model.rows().map(r => r.value), cached);
await model.refresh();
for (const patch of [{ position: 1 }, { scale: 2 }, { color: '#123456' }, { visible: false }, { visible: true }]) {
  store.updateChannel('CH1', patch);
  assert.deepEqual(model.rows().map(r => r.value), cached);
  if (patch.visible !== false) assert.ok(markerPoints(model, store.get(), { l: 0, t: 0, w: 100, h: 100 }).length);
  await model.refresh();
}
store.updateChannel('CH1', { time_offset: 0.5 });
assert.ok(model.rows().every(r => r.value === null));
await model.refresh();
store.set({ channels: [store.get().channels[0]] });
assert.ok(model.rows().every(r => r.value === null));
store.set({ channels }); await model.refresh();
// 基準可切換為獨立點或無；跨單位與刪除後的缺省基準。
model.ref({ id: 'M2', ref: 'M12' });
let delta = model.rows().find(r => r.id === 'M2');
assert.equal(delta.ref, 'M12'); assert.equal(delta.dv, -1);
store.updateChannel('CH2', { unit: 'A' });
delta = model.rows().find(r => r.id === 'M2'); assert.equal(delta.dv, null); assert.equal(markerCells(delta)[5], '—');
model.ref({ id: 'M2', ref: null }); assert.equal(model.rows().find(r => r.id === 'M2').dt, null);
model.ref({ id: 'M2', ref: 'M12' }); model.remove('M12');
delta = model.rows().find(r => r.id === 'M2'); assert.equal(delta.ref, 'M1'); assert.equal(delta.dv, 0);
store.updateChannel('CH2', { unit: 'V' });
// 放大長紀錄後仍以完整通道跨度吸附，不受觸發點附近的 ±1 秒窗夾限。
const longStore = createStore();
longStore.set({ file: { gen: 1 }, channels: [{ ...channels[0], t0: -100, t1: 100 }], view: { t0: 49.9, t1: 50.1 } });
let longCalls = 0, releaseDrag;
const longBridge = { async call(name, p) {
  longCalls++;
  assert.equal(p.screen_width, 200);
  return { available: true, position: { x1: Math.max(-p.screen_width, Math.min(p.screen_width, Math.round(p.x1))), y1: 1 } };
} };
const longModel = markerModel({ store: longStore, bridge: longBridge });
longModel.add({ ch: 'CH1', t: 50.2 }); await longModel.refresh();
assert.equal(longStore.get().markerTable[0].t_src, 50);
assert.equal(longModel.rows()[0].t, 50);
// 預覽期間主動刷新與已在途的結果都不得回寫；取消／放開才恢復吸附。
longModel.preview('M2', 70.4);
const beforeDragCalls = longCalls;
await longModel.refresh();
assert.equal(longCalls, beforeDragCalls);
assert.equal(longStore.get().markerTable[0].t_src, 50);
assert.equal(longModel.rows()[0].t, 70.4);
longModel.preview(null); await longModel.refresh();
const longCall = longBridge.call;
longBridge.call = () => new Promise(resolve => { releaseDrag = resolve; });
const draggingRead = longModel.refresh();
longModel.preview('M2', 80.4);
releaseDrag({ available: true, position: { x1: 80, y1: 2 } }); await draggingRead;
assert.equal(longStore.get().markerTable[0].t_src, 50);
assert.equal(longModel.rows()[0].t, 80.4);
assert.equal(longModel.rows()[0].value, 1);
longBridge.call = longCall;
longModel.preview(null); longModel.move({ id: 'M2', t: 80.4 }); await longModel.refresh();
assert.equal(longStore.get().markerTable[0].t_src, 80);

model.move({ id: 'M1', t: 0 }); await model.refresh();
const outside = model.rows().find(r => r.link && r.ch === 'CH2');
assert.equal(outside.value, null); assert.deepEqual(markerCells(outside).slice(2, 5), ['—', '—', '—']);
assert.equal(hitMarker([{ x: 5, y: 5, id: 'a' }], 11, 5).id, 'a');
assert.equal(hitMarker([{ x: 5, y: 5 }], 11.01, 5), null);
assert.equal(gestureFor({ handle: true, marker: true, cursor: true }), 'handle');
assert.equal(gestureFor({ edge: true, marker: true, cursor: true }), 'edge');
assert.equal(gestureFor({ marker: true, cursor: true }), 'marker');
assert.equal(gestureFor({ marker: true, mode: 'zoom' }), 'marker');
assert.equal(gestureFor({ button: 2, marker: true }), null);
assert.equal(nearestChannel(channels, new Map(), 0, 0, 'CH2'), 'CH2');
assert.ok(TABS.includes('marker'));
assert.ok(panelVisible('marker', 'cursor', false)); assert.ok(panelVisible('cursor', 'marker', false));
assert.equal(panelVisible('marker', 'cursor', true), false);
// 實際事件接線：右鍵只開選單，明確選擇才新增；拖曳不得寫入游標或平移。
class Surface {
  constructor(tag = 'div') { this.tagName = tag; this.listeners = {}; this.style = {}; this.children = []; this.dataset = {}; this.attrs = {}; }
  append(...nodes) { for (const n of nodes) { this.children.push(n); n.parentNode = this; } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = v; }
  blur() { globalThis.document.activeElement = null; this.onblur?.(); }
  addEventListener(n, fn) { (this.listeners[n] ??= []).push(fn); }
  removeEventListener(n, fn) { this.listeners[n] = this.listeners[n]?.filter(f => f !== fn); }
  emit(n, p) { for (const fn of this.listeners[n] ?? []) fn(p); }
  getBoundingClientRect() { return { left: 0, top: 0, width: 240, height: 90 }; }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(n => n !== this); }
  contains(n) { return this === n || this.children.some(c => c.contains(n)); }
  querySelector() { return this.children.find(c => !c.disabled); }
  focus() { globalThis.document.activeElement = this; }
  setPointerCapture() { this.captureCount = (this.captureCount ?? 0) + 1; } hasPointerCapture() { return false; }
}
globalThis.window = new Surface(); globalThis.innerWidth = 800; globalThis.innerHeight = 600;
globalThis.document = Object.assign(new Surface(), { activeElement: null, body: new Surface(), createElement: tag => new Surface(tag) });
const canvas = new Surface(), rect = { l: 0, t: 0, w: 100, h: 100 };
const layer = createMarkerLayer(canvas, ctx, () => rect, new Map(), () => {});
const gestures = bindGestures(canvas, ctx, () => rect, () => {}, layer);
let prevented = false;
const count = store.get().markerTable.length;
canvas.emit('contextmenu', { clientX: 30, clientY: 50, preventDefault() { prevented = true; } });
assert.ok(prevented); assert.equal(store.get().markerTable.length, count);
let menu = document.body.children.at(-1);
assert.equal(menu.children[0].textContent, '移動 M1 到此');
assert.equal(menu.children[1].disabled, true); assert.match(menu.children[1].textContent, /10/);
assert.deepEqual(menuPosition(790, 590, 240, 90, 800, 600), { left: 550, top: 500 });
assert.deepEqual(menuPosition(1, 1, 900, 700, 800, 600), { left: 0, top: 0 });
store.set({ selected: 'CH2' });
canvas.emit('contextmenu', { clientX: 30, clientY: 50, preventDefault() {} });
assert.equal(store.get().markerTable.length, count);
menu = document.body.children.at(-1);
// WebKit 按下按鈕不轉移焦點；空的焦點目標不可讓後續點擊失效。
let mousePrevented = false;
menu.emit('mousedown', { preventDefault() { mousePrevented = true; } });
assert.ok(mousePrevented);
menu.emit('focusout', { relatedTarget: null });
assert.ok(document.body.children.includes(menu));
menu.children[1].onclick();
assert.equal(store.get().markerTable.length, count + 1);
assert.equal(document.body.children.length, 0);
canvas.emit('contextmenu', { clientX: 30, clientY: 50, preventDefault() {} });
menu = document.body.children.at(-1);
menu.emit('focusout', { relatedTarget: menu.children[1] });
assert.ok(document.body.children.includes(menu));
menu.emit('focusout', { relatedTarget: canvas });
assert.equal(document.body.children.length, 0);
canvas.emit('contextmenu', { clientX: 30, clientY: 50, preventDefault() {} });
document.emit('keydown', { key: 'Escape', preventDefault() {}, stopPropagation() {} });
assert.equal(document.body.children.length, 0);
canvas.emit('contextmenu', { clientX: 30, clientY: 50, preventDefault() {} });
document.emit('pointerdown', { target: canvas }); assert.equal(document.body.children.length, 0);
assert.equal(markerMenuItems(store.get(), 'CH2', 3, { id: 'M1' }, model).at(-1).text, '刪除');
await model.refresh();
model.move({ id: 'M1', t: 4 }); await model.refresh();
const before = { ...store.get().cursors }, view = { ...store.get().view };
const event = (x, y) => ({ clientX: x, clientY: y, button: 0, pointerId: 1, preventDefault() {} });
// Ctrl＋左鍵不得攔截事件、取得焦點或啟動 Marker 拖曳與指標擷取。
const focused = document.activeElement;
canvas.emit('pointerdown', { ...event(40, 40), ctrlKey: true, preventDefault() { assert.fail('Ctrl＋左鍵不應被攔截'); } });
canvas.emit('pointermove', event(60, 70)); canvas.emit('pointerup', event(60, 70));
assert.equal(canvas.captureCount ?? 0, 0); assert.equal(document.activeElement, focused);
assert.equal(model.rows().find(r => r.id === 'M1').t, 4);
assert.deepEqual(store.get().cursors, before); assert.deepEqual(store.get().view, view);
canvas.emit('pointerdown', event(40, 40)); canvas.emit('pointermove', event(60, 70));
assert.equal(canvas.captureCount, 1);
assert.equal(model.rows().find(r => r.id === 'M1').t, 6);
canvas.emit('pointerup', event(60, 70)); await model.refresh();
assert.equal(store.get().markerTable.find(p => p.id === 'M1').t, 6);
assert.deepEqual(store.get().cursors, before); assert.deepEqual(store.get().view, view);
model.select('M1:CH1'); assert.equal(model.selected, 'M1:CH1');
const host = new Surface(); mountTable(host, ctx);
const table = host.children[1], linkedRow = table.children.find(r => r.dataset.markerKey === 'M1:CH1');
linkedRow.onclick(); assert.equal(linkedRow.className, 'is-selected');
let input = table.children.find(r => r.dataset.markerKey === 'M1:CH1').children[7].children[0];
input.onfocus(); input.value = '取消文字'; input.onkeydown({ key: 'Escape', stopPropagation() {} });
assert.equal(model.rows().find(r => r.id === 'M1').note, '連動註記');
input = table.children.find(r => r.dataset.markerKey === 'M1:CH1').children[7].children[0];
input.onfocus(); input.value = '新註記'; input.onkeydown({ key: 'Enter', stopPropagation() {} });
assert.ok(model.rows().filter(r => r.link).every(r => r.note === '新註記'));
const body = new Surface(), panels = Object.fromEntries(TABS.map(k => [k, new Surface()])); body.append(...Object.values(panels));
const tabs = mountTabs(new Surface(), panels, { initial: { version: 1, tab: 'marker' }, persist() {} });
tabs.update({ width: PAIR_MIN_WIDTH, height: 180 });
assert.equal(panels.marker.hidden, false); assert.equal(panels.cursor.hidden, false); assert.equal(panels.measure.hidden, true);
assert.equal(body.dataset.markerPaired, 'true');
tabs.update({ width: PAIR_MIN_WIDTH - 1, height: 180 }); assert.equal(panels.cursor.hidden, true); assert.equal(tabs.tab, 'marker'); assert.equal(body.dataset.markerPaired, 'false');
// 兩種刪除鍵皆接到實際事件；輸入框及文字區不得刪除 Marker。
for (const key of ['Delete', 'Backspace']) {
  for (const tag of ['input', 'textarea']) {
    const editor = new Surface(tag); editor.focus();
    const beforeDelete = store.get().markerTable.length;
    window.emit('keydown', { key, target: editor });
    const row = table.children.find(r => r.dataset.markerKey);
    row.onkeydown({ key, target: editor });
    assert.equal(store.get().markerTable.length, beforeDelete);
  }
  let row = table.children.find(r => r.dataset.markerKey && !r.dataset.markerKey.startsWith('M1:'));
  let removed = row.dataset.markerKey.split(':')[0], prevented = false;
  row.onkeydown({ key, target: row, preventDefault() { prevented = true; } });
  assert.ok(prevented); assert.ok(!store.get().markerTable.some(p => p.id === removed));
  const independent = model.rows().find(r => !r.link);
  model.select(independent.key, false); canvas.focus(); prevented = false;
  window.emit('keydown', { key, target: canvas, preventDefault() { prevented = true; } });
  assert.ok(prevented); assert.ok(!store.get().markerTable.some(p => p.id === independent.id));
}
// 開檔後才回來的舊讀值不可重新灌回。
let release; bridge.call = () => new Promise(resolve => { release = resolve; });
const pending = model.refresh();
store.set({ file: { gen: 2 }, channels });
release({ t1: 6, y: {} }); await pending;
assert.deepEqual(store.get().markerTable, []); assert.deepEqual(model.rows(), []);
assert.equal(model.selected, null);
gestures.dispose(); layer.dispose();
console.log('marker self-check OK');
