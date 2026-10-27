// 通道配色：實際 chip 事件、各來源建立／還原、重設與零位拖曳回歸。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createStore } from './store.js';
import { openPatch } from './tab_analysis.js';
import { applyMathChannel } from './toolbar.js';
import { slotPatch } from './slots.js';
import { mount } from './chanbar.js';
import { channelColors, setChannelColor, resetChannelColor } from './channel_colors.js';
import { channelHandles, drawHandles, hitHandle, handlePosition, moveHandle } from './handles.js';
import { voltageAxis } from './voltage.js';
import * as scales from './scales.js';
import * as fmt from '../fmt.js';

const colors = JSON.parse(readFileSync(new URL('../../api_contract.json', import.meta.url))).catalog.channel_colors;
const saved = new Map();
globalThis.localStorage = {
  getItem: key => saved.get(key) ?? null,
  setItem: (key, value) => saved.set(key, value),
  removeItem: key => saved.delete(key),
};
function element(tag = 'div') {
  return { tag, tagName: tag.toUpperCase(), children: [], dataset: {}, style: {}, attrs: {},
    classList: { add() {}, toggle() {} },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    setAttribute(key, value) { this.attrs[key] = value; },
    closest(selectors) { return selectors.split(',').includes(tag) ? this : null; },
  };
}
globalThis.document = { createElement: element, activeElement: null };
const info = name => ({ name, unit: 'V', t0: 0, t1: 1, vmin: -1, vmax: 1, points: 100 });
const file = { gen: 1, channels: [info('CHAN1'), info('CHAN2')] };
const summary = { gen: 1, slot: 'Mem1', channels: [info('Mem1.CHAN1')], all: ['CHAN1'] };
function populate(store) {
  store.set(openPatch(file, colors));
  store.set(slotPatch(store.get(), 'Mem1', summary, colors, scales));
  applyMathChannel(store, { ...info('F1'), derived: true, gen: 1 }, colors, scales);
}
const store = createStore(); populate(store);
assert.deepEqual(store.get().channels.map(c => c.color), colors.slice(0, 4), '契約預設配色不變');
const bar = element();
mount(bar, { store, scales, fmt });
const columns = () => bar.children.filter(e => e.className === 'chanbar__col');
const chips = () => columns().map(e => e.children[0]);
const pickers = () => chips().map(e => e.children.find(e => e.type === 'color'));
const resets = () => chips().map(e => e.children.find(e => e.attrs['aria-label'] === '重設顏色'));
const names = store.get().channels.map(c => c.name);
const custom = ['#123456', '#abcdef', '#345678', '#987654'];
const updates = [];
store.on(['channels'], (_s, _keys, origin) => updates.push(origin));
for (const [i, name] of names.entries()) {
  const picker = pickers()[i];
  assert.equal(picker.attrs['aria-label'], '通道顏色');
  assert.ok(!picker.hidden && columns()[i].children[1].hidden, '收折時色塊仍顯示');
  const before = store.get().channels.filter(c => c.name !== name);
  picker.value = custom[i]; picker.oninput();
  assert.equal(store.get().channels[i].color, custom[i]);
  assert.deepEqual(store.get().channels.filter(c => c.name !== name), before, '改色只影響該通道');
  assert.equal(saved.get(`scopeChanColor:${name}`), custom[i]);
  assert.equal(chips()[i].children[1].style.color, custom[i], 'chip 即時更新');
  assert.equal(voltageAxis(store.get().channels[i]).color, custom[i], '電壓軸讀取最新顏色');
  const selected = store.get().selected;
  chips()[i].onclick({ target: picker }); chips()[i].onclick({ target: resets()[i] });
  assert.equal(store.get().selected, selected, '色塊與重設鈕不改選取');
}
assert.ok(updates.every(o => o === 'user'));
const restored = createStore(); populate(restored);
assert.deepEqual(restored.get().channels.map(c => c.color), custom, '新開檔／加 Mem／加 F1 還原同名偏好');
assert.notEqual(restored.get().channels[0].color, restored.get().channels[2].color, 'Mem 與主檔偏好分開');
// 同名槽位仍優先保留舊記錄 color，即使儲存偏好不同。
store.updateChannel('Mem1.CHAN1', { color: '#112233' });
store.set(slotPatch(store.get(), 'Mem1', summary, colors, scales));
assert.equal(store.get().channels.find(c => c.name === 'Mem1.CHAN1').color, '#112233');
// slotPatch 將替換槽位移到末尾；依名稱找對應控制項。
for (const name of names) {
  const idx = store.get().channels.findIndex(c => c.name === name), c = store.get().channels[idx];
  resets()[idx].onclick();
  assert.equal(store.get().channels[idx].color, c.defaultColor);
  assert.ok(!saved.has(`scopeChanColor:${name}`));
  assert.equal(pickers()[idx].value, c.defaultColor);
}
const clean = createStore(); populate(clean);
assert.deepEqual(clean.get().channels.map(c => c.color), colors.slice(0, 4), '重設後再次建立回契約預設');
// change 事件也能獨立提交，壞偏好不得傳給原生選色器。
pickers()[0].value = '#aabbcc'; pickers()[0].onchange();
assert.equal(store.get().channels[0].color, '#aabbcc');
saved.set('scopeChanColor:CHAN2', 'invalid');
assert.deepEqual(channelColors('CHAN2', colors[1]), { color: colors[1], defaultColor: colors[1] });
const previous = store.get().channels[0].color;
setChannelColor(store, 'CHAN1', 'bad');
assert.equal(store.get().channels[0].color, previous);
// 瀏覽器封鎖 localStorage（包含取得屬性就拋錯）仍可換色、重設及開檔。
Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw Error('封鎖儲存'); } });
setChannelColor(store, 'CHAN1', '#fedcba');
assert.equal(store.get().channels[0].color, '#fedcba');
resetChannelColor(store, 'CHAN1');
assert.equal(store.get().channels[0].color, colors[0]);
assert.equal(openPatch(file, colors).channels[0].color, colors[0]);

// 零位標籤重疊避讓後完全不畫連線；命中與相對拖曳仍更新同一通道。
const channels = clean.get().channels.map(c => ({ ...c, position: 0 }));
clean.set({ channels });
const rect = { l: 100, t: 20, w: 700, h: 300 };
const handles = channelHandles(channels, rect);
assert.ok(handles.some(b => b.y + b.h / 2 !== b.anchorY));
const fills = [], g = new Proxy({}, { get: (target, key) => {
  if (key === 'stroke') return () => assert.fail('零位標籤不應畫連線');
  if (key === 'fillRect') return () => fills.push(target.fillStyle);
  return target[key] ?? (() => {});
} });
drawHandles(g, channels, {}, clean.get().view, rect);
assert.deepEqual(fills, channels.map(c => c.color));
const b = handles[2];
assert.equal(hitHandle(channels, rect, b.x + b.w / 2, b.y + b.h / 2).name, b.name);
clean.onCommand('channel.scale_intent', ({ name, position }) => clean.updateChannel(name, { position }));
const nextPosition = handlePosition(0, 30, rect);
moveHandle(clean, b.name, nextPosition);
assert.equal(clean.get().channels[2].position, -1);
assert.equal(clean.get().channels[0].position, 0);
console.log('channel color self-check OK：chip 即時換色／各來源偏好還原／重設／儲存失敗／槽位保色／零位無連線與拖曳');
