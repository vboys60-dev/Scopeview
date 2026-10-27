// 多檔比對純函式與既有量測／游標控制器的回歸檢查。
import assert from 'node:assert/strict';
import { slotPatch, staleDecode, openSlots, appendFileInfo, SLOT_LIMITS } from './slots.js';
import { createStore } from './store.js';
import { createMeasure } from './measure.js';
import { createController, defaultCursors } from './cursors.js';
import { applyMathChannel, closeFile } from './toolbar.js';
import { fetchTargets } from './mainplot.js';
import { openPatch } from './tab_analysis.js';
import * as scales from './scales.js';
const colors = ['#fff', '#aaa'];
const info = { name: 'Mem1.CHAN1', unit: 'V', derived: false, t0: -2, t1: 3, vmin: -4, vmax: 5, points: 123 };
const summary = { gen: 7, slot: 'Mem1', path: '/new.h5', info: [['檔名', 'new.h5']], all: ['CHAN1', 'CHAN2'], channels: [info] };
const original = { ...info, t0: 0, t1: 1, vmin: 0, vmax: 1, points: 20, obsolete: true,
  time_offset: .123, scale: .2, position: 3, color: '#abc', visible: false };
const st = { file: { gen: 7, channels: [{ name: 'CHAN1' }] }, channels: [{ name: 'CHAN1' }, original],
  selected: original.name, slots: [{ slot: 'Mem1', channels: [original.name] }], dataRev: 4 };
const snapshot = JSON.stringify(st), patch = slotPatch(st, 'Mem1', summary, colors, scales);
assert.equal(JSON.stringify(st), snapshot, '純函式不修改舊狀態');
assert.ok(!('file' in patch)); assert.equal(patch.dataRev, 5);
for (const key of ['time_offset', 'scale', 'position', 'color', 'visible']) assert.equal(patch.channels[1][key], original[key]);
for (const key of ['t0', 't1', 'vmin', 'vmax', 'points']) assert.equal(patch.channels[1][key], info[key]);
assert.ok(!('obsolete' in patch.channels[1]));
assert.deepEqual(patch.slots[0], { slot: 'Mem1', path: summary.path, info: summary.info, all: summary.all,
  channels: [info.name], infos: [info] });
assert.equal(slotPatch(st, 'Mem1', { ...summary, gen: 8 }, colors, scales), null);
assert.equal(slotPatch({ ...st, file: null }, 'Mem1', null, colors, scales), null);
const removed = slotPatch({ ...st, ...patch }, 'Mem1', null, colors, scales);
assert.deepEqual(removed.slots, []); assert.equal(removed.selected, 'CHAN1'); assert.equal(removed.dataRev, 6);
assert.deepEqual(removed.channels, [{ name: 'CHAN1' }]);
const fresh = slotPatch({ ...st, slots: [], channels: [{ name: 'CHAN1' }], dataRev: undefined }, 'Mem1', summary, colors, scales);
assert.equal(fresh.dataRev, 1); assert.equal(fresh.channels[1].time_offset, 0); assert.equal(fresh.channels[1].visible, true);
const decodeResult = { summary: { channels: { scl: 'Mem1.CHAN1', sda: 'Mem1.CHAN2' } }, frames: [1] };
assert.deepEqual(staleDecode({ decodeResult }, [info.name]), { decodeResult: { ...decodeResult, stale: true } });
assert.deepEqual(staleDecode({ decodeResult }, ['CHAN1']), {});
assert.deepEqual(staleDecode({}, [info.name]), {});
assert.equal(slotPatch({ ...st, decodeResult }, 'Mem1', null, colors, scales).decodeResult.stale, true);
// 使用實際 store 及控制器：加槽不觸發換檔清空；資料版本改變仍會安排重算。
{
  const store = createStore(), calls = [];
  const bridge = { call: async (_name, args) => ({ t1: args.t1, t2: args.t2, y: {} }), job: async (name, args) => {
    calls.push(name);
    if (name === 'measure') return { gen: 7, revision: calls.length, results: args.entries.map(() => ({ ok: true })) };
    return { gen: 7, t1: args.t1, t2: args.t2, y: {} };
  } };
  createController({ store, bridge }, { delay: 1 });
  const measure = createMeasure({ store, bridge }, { delay: 1 });
  store.set({ file: { gen: 7, channels: [{ name: 'CHAN1', t0: 0, t1: 1 }] }, channels: [{ name: 'CHAN1', t0: 0, t1: 1, visible: true, scale: 1, position: 0, time_offset: 0, unit: 'V' }], selected: 'CHAN1' });
  store.set({ cursors: { x1: .2, x2: .7, y1: 2, y2: -2 } }, 'snap');
  measure.add('Vmax', 'CHAN1', true);
  await new Promise(r => setTimeout(r, 25));
  const before = { ...store.get().cursors }, id = store.get().measurements[0].id, file = store.get().file;
  store.set(slotPatch(store.get(), 'Mem1', summary, colors, scales), 'program');
  assert.deepEqual(store.get().cursors, before); assert.equal(store.get().measurements[0].id, id);
  await new Promise(r => setTimeout(r, 25));
  assert.deepEqual(store.get().cursors, before); assert.equal(store.get().file, file);
  assert.equal(store.get().measurements.length, 1); assert.equal(calls.filter(n => n === 'measure').length, 2);
  // 走工具列實際採用的數學結果寫入函式，主圖仍抓得到新通道。
  const math = { ...info, name: 'F1', gen: 7, derived: true };
  const writes = []; store.on((_s, keys) => writes.push(keys));
  applyMathChannel(store, math, colors, scales);
  assert.equal(store.get().file, file);
  assert.ok(writes.every(keys => !keys.includes('file')));
  assert.deepEqual(store.get().cursors, before);
  assert.equal(store.get().measurements[0].id, id);
  assert.ok(fetchTargets(store.get()).some(c => c.name === 'F1'));
  await new Promise(r => setTimeout(r, 25));
  assert.deepEqual(store.get().cursors, before);
  assert.equal(store.get().measurements[0].id, id);
  assert.ok(store.get().measurements[0].result.ok);
  const channels = store.get().channels;
  applyMathChannel(store, { ...math, gen: 6, name: 'F2' }, colors, scales);
  assert.equal(store.get().channels, channels, '舊世代數學結果不得加入');
  assert.throws(() => applyMathChannel(store, math, colors, scales), /通道名稱重複/);
  // 真正換檔仍清量測並重新放預設游標，衍生通道不殘留。
  store.set(openPatch({ gen: 8, channels: [{ ...info, name: 'NEW', t0: 10, t1: 30 }] }), 'program');
  assert.deepEqual(store.get().measurements, []);
  assert.deepEqual(store.get().cursors, defaultCursors({ t0: 10, t1: 30 }));
  assert.deepEqual(fetchTargets(store.get()).map(c => c.name), ['NEW']);
  measure.add('Vmax', 'NEW', true);
  await closeFile(store, bridge);
  assert.deepEqual(store.get().measurements, []);
  assert.deepEqual(store.get().cursors, { x1: null, x2: null, y1: null, y2: null });
  assert.deepEqual(fetchTargets(store.get()), []);
}
// 對話框用最小 DOM 測非同步世代核對、STALE、全不勾及未改列不重送。
{
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.dataset = {}; this.disabled = false; }
    append(...children) { for (const c of children) { c.parent = this; this.children.push(c); } }
    prepend(child) { child.parent = this; this.children.unshift(child); }
    replaceChildren(...children) { this.children = []; this.append(...children); }
    closest() { return this.tag === 'dialog' ? this : this.parent?.closest(); }
    querySelectorAll(selector) {
      const all = this.children.flatMap(c => [c, ...c.querySelectorAll('*')]);
      if (selector === '*') return all;
      if (selector === 'input:checked') return all.filter(c => c.tag === 'input' && c.checked);
      return all.filter(c => selector.split(',').includes(c.tag));
    }
    querySelector(selector) { return this.querySelectorAll('*').find(c => selector === '.dlg__actions' && c.className === 'dlg__actions'); }
    addEventListener() {}
  }
  globalThis.document = { createElement: tag => new Element(tag) };
  // 資訊表：主檔在前、槽位排序、不修改輸入，且與對話框使用同一組限制文字。
  const infoBody = new Element('div');
  appendFileInfo(infoBody, { file: { info: [['檔名', 'main.h5']] }, slots: [
    { slot: 'Mem3', info: [['檔名', '<third>.h5']] },
    { slot: 'Mem1', info: [['檔名', 'first.h5'], ['通道', 'Mem1.CHAN1']] },
  ] });
  const tables = infoBody.querySelectorAll('table');
  assert.deepEqual(tables.map(t => t.dataset.fileInfo), ['main', 'Mem1', 'Mem3']);
  assert.equal(tables[1].children[1].children[1].textContent, 'Mem1.CHAN1');
  assert.equal(tables[2].children[0].children[1].textContent, '<third>.h5');
  const limits = infoBody.children.at(-1);
  assert.deepEqual(limits.children.slice(1).map(e => e.textContent), SLOT_LIMITS.map(t => `・${t}`));
  const mainOnly = new Element('div');
  appendFileInfo(mainOnly, { file: { info: [['檔名', 'main.h5']] }, slots: [] });
  assert.equal(mainOnly.children.length, 1, '沒有比對槽時只列主檔');
  const store = createStore();
  const file = { gen: 7, path: '/main.h5', channels: [{ name: 'CHAN1' }] };
  const reset = () => store.set({ file, channels: [{ name: 'CHAN1' }], slots: [], dataRev: 0 });
  reset();
  const calls = [], errors = [], writes = [], toasts = [];
  store.on((_s, keys) => writes.push(keys));
  let result = summary, remove = async () => {}, picked = '/new.h5', root;
  const ctx = { store, scales, appState: { catalog: { channel_colors: colors } },
    ui: { pickPath: async () => picked, showError: e => errors.push(e), toast: text => toasts.push(text) },
    bridge: { job: async (name, args) => { calls.push([name, args]); return await result; },
      call: async (name, args) => { calls.push([name, args]); await remove(args); } } };
  const modal = async (_title, build) => {
    root = new Element('dialog'); const body = new Element('div'), actions = new Element('div');
    actions.className = 'dlg__actions'; root.append(body, actions); build(body);
  };
  await openSlots(ctx, modal);
  const table = root.querySelectorAll('*').find(e => Object.hasOwn(e.dataset, 'slots'));
  assert.equal(table.closest(), root, 'data-slots 的 table 掛在對話框內');
  assert.equal(table.querySelectorAll('*').filter(e => e.dataset.slot).length, 4);
  const row = () => root.querySelectorAll('*').find(e => e.dataset.slot === 'Mem1');
  const pick = () => row().querySelectorAll('button')[0].onclick();
  const apply = () => root.querySelectorAll('button').find(b => b.textContent === '套用勾選').onclick();
  assert.equal(root.querySelectorAll('button').find(b => b.textContent === '套用勾選').className, 'btn btn--primary');
  result = { ...summary, gen: 8 }; await pick();
  assert.deepEqual(toasts, [], '過期回傳不消耗首次提示');
  result = summary;
  await pick(); assert.equal(store.get().slots.length, 1);
  assert.deepEqual(toasts, ['已載入 Mem1：各檔以自己的觸發點為 0，對齊請調 dx']);
  assert.equal(writes.filter(keys => keys.includes('dataRev')).length, 1);
  assert.ok(writes.every(keys => !keys.includes('file')));
  await openSlots(ctx, modal);
  assert.deepEqual(root.querySelectorAll('*').find(e => Object.hasOwn(e.dataset, 'slotLimits')).children.slice(1).map(e => e.textContent),
    SLOT_LIMITS.map(t => `・${t}`));
  await pick(); assert.equal(toasts.length, 1, '重開對話框與換槽不重複提示');
  const n = calls.length; await apply(); assert.equal(calls.length, n, '勾選未改不送 RPC');
  row().querySelectorAll('input').forEach(c => { c.checked = false; });
  await apply(); assert.equal(calls.at(-1)[0], 'remove_slot'); assert.deepEqual(store.get().slots, []);
  result = { ...summary, gen: 8 }; await pick(); assert.deepEqual(store.get().slots, [], '回傳 gen 不符不寫入');
  let complete;
  result = new Promise(resolve => { complete = resolve; });
  const pending = pick(); await Promise.resolve(); await Promise.resolve();
  assert.ok(root.querySelectorAll('button,input').every(b => b.disabled), '載入時停用對話框控制');
  store.set({ file: { ...file, gen: 8 } }); const rev = store.get().dataRev;
  complete(summary); await pending;
  assert.equal(store.get().dataRev, rev); assert.deepEqual(store.get().slots, [], '等候 add 時換主檔不寫入');
  reset(); result = summary; await pick();
  assert.equal(toasts.length, 1, '移除再加與過期請求不重複提示');
  remove = async () => { store.set({ file: { ...file, gen: 8 }, slots: [], dataRev: 0 }); };
  await row().querySelectorAll('button')[1].onclick();
  assert.equal(store.get().dataRev, 0, '等候 remove 時換主檔不寫入');
  reset(); result = Promise.reject(Object.assign(new Error('過期'), { code: 'STALE' }));
  await pick(); assert.deepEqual(errors, [], 'STALE 靜默略過');
  picked = null; await pick(); assert.deepEqual(store.get().slots, []);
  store.set({ file: { ...file, gen: 8 }, slots: [], dataRev: 0 });
  await openSlots(ctx, modal); result = { ...summary, gen: 8 }; picked = '/new.h5';
  await pick(); assert.equal(toasts.length, 2, '換主檔後首次成功重新提示');
  await pick(); assert.equal(toasts.length, 2, '新主檔內也只提示一次');
  // 批次套用：前槽 add 失敗仍繼續後槽 add／remove；STALE remove 也不擋後槽。
  reset();
  for (const slot of ['Mem1', 'Mem2', 'Mem3']) {
    const channels = ['CHAN1', 'CHAN2'].map(name => ({ ...info, name: `${slot}.${name}` }));
    store.set(slotPatch(store.get(), slot, { ...summary, slot, channels }, colors, scales));
  }
  await openSlots(ctx, modal);
  const slotRow = slot => root.querySelectorAll('*').find(e => e.dataset.slot === slot);
  const uncheck = (slot, name) => { slotRow(slot).querySelectorAll('input').find(c => c.value === name).checked = false; };
  uncheck('Mem1', 'CHAN2'); uncheck('Mem2', 'CHAN2');
  uncheck('Mem3', 'CHAN1'); uncheck('Mem3', 'CHAN2');
  const failure = new Error('Mem1 載入失敗'), batchStart = calls.length;
  ctx.bridge.job = async (name, args) => {
    calls.push([name, args]);
    assert.ok(root.querySelectorAll('button,input').every(b => b.disabled), '整批處理期間維持停用');
    if (args.slot === 'Mem1') throw failure;
    return { ...summary, slot: args.slot, channels: [{ ...info, name: `${args.slot}.CHAN1` }] };
  };
  remove = async () => {};
  await apply();
  assert.deepEqual(calls.slice(batchStart).map(([name, args]) => [name, args.slot]),
    [['add_waveform', 'Mem1'], ['add_waveform', 'Mem2'], ['remove_slot', 'Mem3']]);
  assert.deepEqual(errors, [failure], '非 STALE 逐槽使用既有錯誤提示');
  assert.deepEqual(store.get().slots.map(s => [s.slot, s.channels]),
    [['Mem1', ['Mem1.CHAN1', 'Mem1.CHAN2']], ['Mem2', ['Mem2.CHAN1']]]);
  assert.ok(slotRow('Mem1').querySelectorAll('input').every(c => c.checked), '失敗列還原實際勾選');
  assert.equal(slotRow('Mem3').querySelectorAll('button')[1].disabled, true, '空槽移除鈕仍停用');
  assert.ok(root.querySelectorAll('input').every(c => !c.disabled), '批次結束恢復控制');
  uncheck('Mem1', 'CHAN1'); uncheck('Mem1', 'CHAN2'); uncheck('Mem2', 'CHAN1');
  remove = async ({ slot }) => { if (slot === 'Mem1') throw Object.assign(new Error('過期'), { code: 'STALE' }); };
  const staleStart = calls.length;
  await apply();
  assert.deepEqual(calls.slice(staleStart).map(([name, args]) => [name, args.slot]),
    [['remove_slot', 'Mem1'], ['remove_slot', 'Mem2']]);
  assert.deepEqual(errors, [failure], '批次 STALE 靜默略過');
  assert.deepEqual(store.get().slots.map(s => s.slot), ['Mem1']);
  delete globalThis.document;
}
console.log('slot self-check OK');
