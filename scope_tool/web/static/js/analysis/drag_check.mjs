import assert from 'node:assert/strict';

class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.dataset = {}; this.listeners = {}; this.classes = new Set(); }
  get classList() { const s = this.classes; return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)), toggle: (x, on) => on ? s.add(x) : s.delete(x) }; }
  append(...nodes) { for (const n of nodes) { this.children.push(n); n.parentNode = this; } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  get firstChild() { return this.children[0]; }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(n => n !== this); this.parentNode = null; }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  fire(type, event = {}) { for (const fn of this.listeners[type] ?? []) fn({ button: 0, pointerId: 1, pointerType: 'mouse', preventDefault() {}, ...event }); }
  setPointerCapture(id) { this.capture = id; }
  hasPointerCapture(id) { return this.capture === id; }
  releasePointerCapture() { this.capture = null; }
  closest() { for (let e = this; e; e = e.parentNode) if (e.dataset.channel) return e; return null; }
}

const body = new El('body'), col = new El('div'), child = new El('span'), win = new El('window');
col.dataset.channel = 'CH2'; col.append(child);
let hit = null;
globalThis.window = win;
globalThis.document = { body, createElement: tag => new El(tag), querySelectorAll: () => [col], elementFromPoint: () => hit };
globalThis.Option = function (text, value) { const e = new El('option'); e.textContent = text; e.value = value; return e; };
const { createStore } = await import('./store.js');
const { mount, isDrag, dropChannel } = await import('./measure.js');
assert.equal(isDrag(5, 3), false); assert.equal(isDrag(6, 0), true); assert.equal(isDrag(0, -6), true);
assert.equal(dropChannel(child), 'CH2'); assert.equal(dropChannel(null), null); assert.equal(dropChannel(new El('div')), null);
const cvs = new El('canvas'); cvs.hitChannel = (x, y) => (y < 10 ? 'CH2' : null);
assert.equal(dropChannel(cvs, 5, 5), 'CH2'); assert.equal(dropChannel(cvs, 5, 50), null);
const store = createStore();
store.set({ file: { gen: 1 }, channels: [{ name: 'CH1' }, { name: 'CH2' }], selected: 'CH1' });
const root = new El('div');
mount(root, { store, bridge: { job: async () => ({ gen: 1, revision: 1, results: [] }) }, ui: { toast() {} },
  appState: { catalog: { measurements: [{ name: 'Vmax', category: '電壓', tip: '' }] } } });
const button = root.children.find(e => e.firstChild?.textContent === 'Voltage Measurements').children.find(e => e.tagName === 'button');
const entries = () => store.get().measurements.map(m => m.channel);
const down = () => button.fire('pointerdown', { clientX: 0, clientY: 0 });
// move／up 送到 window（真瀏覽器會冒泡到 window；measure.js 在 window capture 層處理，不依賴 target 是按鈕）
const move = x => win.fire('pointermove', { clientX: x, clientY: 0 });
const up = x => win.fire('pointerup', { clientX: x, clientY: 0 });
down(); move(3); up(3); button.onclick({ detail: 1 });
assert.deepEqual(entries(), ['CH1']);
hit = child; down(); move(10);
assert.ok(col.classes.has('is-droptarget') && col.classes.has('is-dropover'));
up(10); button.onclick({ detail: 1 });
assert.deepEqual(entries(), ['CH1', 'CH2']); assert.equal(store.get().selected, 'CH1');
assert.equal(col.classes.size, 0); assert.equal(body.children.length, 0);
hit = null; down(); move(10); up(10); button.onclick({ detail: 1 });
assert.deepEqual(entries(), ['CH1', 'CH2']);
hit = child; down(); move(10); win.fire('keydown', { key: 'Escape' }); up(10); button.onclick({ detail: 1 });
assert.deepEqual(entries(), ['CH1', 'CH2']); assert.equal(col.classes.size, 0); assert.equal(body.children.length, 0);
down(); move(10); win.fire('keydown', { key: 'Escape' }); button.onclick({ detail: 0 });
assert.deepEqual(entries(), ['CH1', 'CH2', 'CH1']);
// 按下後快速移出按鈕：按鈕本身收不到任何 move／up，仍要開始拖曳並在放開時新增到目標
hit = child; down(); win.fire('pointermove', { clientX: 40, clientY: 30, target: new El('canvas') });
assert.ok(col.classes.has('is-dropover') && button.capture === 1);
win.fire('pointerup', { clientX: 40, clientY: 30, target: col }); button.onclick({ detail: 1 });
assert.deepEqual(entries(), ['CH1', 'CH2', 'CH1', 'CH2']); assert.equal(col.classes.size, 0);
// id1 被取消仍按住：id2 的放開與 click 不得清掉 id1 保護。
for (const pointerId of [1, 0]) {
  down(); // 清掉前次手勢的殘留計時器版本
  button.fire('pointerdown', { pointerId,clientX:0,clientY:0 });
  win.fire('pointermove', { pointerId,clientX:10,clientY:0 }); win.fire('keydown', { key:'Escape' });
  const n = entries().length;
  win.fire('pointerup', { pointerId:2 }); await new Promise(r => setTimeout(r,5));
  button.onclick({ detail:1,pointerId:2 }); assert.equal(entries().length,n+1);
  button.onclick({ detail:1,pointerId }); assert.equal(entries().length,n+1);
}
// 舊 pointerup 計時器不得清掉同 pointerId 的新取消手勢。
down(); move(10); up(10);
down(); move(10); win.fire('keydown', { key:'Escape' });
await new Promise(r => setTimeout(r,5));
const n = entries().length; button.onclick({ detail:1,pointerId:1 }); assert.equal(entries().length,n);
// 單指正常放開會解除；鍵盤例外與無 pointerId 相容行為沿用上方斷言。
down(); move(10); up(10); await new Promise(r => setTimeout(r,5));
button.onclick({ detail:1,pointerId:1 }); assert.equal(entries().length,n+2);
console.log('drag self-check OK');
