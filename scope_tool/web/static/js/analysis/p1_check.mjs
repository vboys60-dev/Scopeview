// P1 實機回饋回歸：產品掛載、實際事件與繪製；不另寫手勢實作。
import assert from "node:assert/strict";
import { createStore } from "./store.js";
import * as scales from "./scales.js";
import * as fmt from "../fmt.js";
import { mount as mountChanbar, fineScale, clampScale, coarseScale } from "./chanbar.js";
import { mount as mountPlot, layoutRect, divY } from "./mainplot.js";
import { mount as mountCursors, centerButton } from "./cursors.js";
import { channelHandles, hitHandle, outsideCursors, cursorEdges } from "./handles.js";
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);
const texts = [], textPositions = [];
const g = new Proxy({}, { get: (t, k) => k === "measureText" ? () => ({ width: 0 })
  : k === "fillText" ? (text, x, y, maxWidth) => { texts.push(text); textPositions.push({ text, x, y, maxWidth, font: t.font }); } : t[k] ?? (() => {}), set: (t, k, v) => ((t[k] = v), true) });
function el(tag = "div") {
  return { tag, tagName: tag.toUpperCase(), dataset: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, children: [], style: {}, classList: { add() {}, toggle() {} }, listeners: {}, value: "",
    append(...cs) { for (const c of cs) { this.children.push(c); c.parentNode = this; } },
    replaceChildren(...cs) { this.children = []; this.append(...cs); },
    addEventListener(k, f) { this.listeners[k] = f; }, setPointerCapture() {}, getContext: () => g,
    getBoundingClientRect: () => ({ width: 544, height: 308, left: 0, top: 0 }) };
}
globalThis.document = { createElement: el, activeElement: null };
globalThis.window = { devicePixelRatio: 1 };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const store = createStore(), commands = [], messages = [];
const ctx = { store, scales, fmt, bridge: { call: async () => ({ t1: 1, t2: 3, y: {} }) }, ui: { toast: (t) => messages.push(t) } };
store.set({ channels: [
  { name: "CHAN1", unit: "V", scale: 0.2, position: 0, visible: true, vmin: 0, vmax: 2, color: "#f00", time_offset: 0 },
  { name: "CHAN2", unit: "V²", scale: 1.234, position: 0, visible: true, vmin: null, vmax: null, color: "#0f0", time_offset: 0 },
  { name: "F1", unit: "V", scale: 1, position: 0, visible: false, color: "#00f" },
], selected: "CHAN1", view: { t0: 0, t1: 4 } });
store.onCommand("viewport.intent", (v) => { commands.push(["view", v]); store.set({ view: v }, "user"); });
store.onCommand("channel.scale_intent", (p) => commands.push(["channel", p]));
const saved = new Map();
globalThis.localStorage = { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) };
const bar = el(); mountChanbar(bar, ctx);
const columns = () => bar.children.filter(e => e.className === "chanbar__col");
assert.ok(columns().every(e => e.children[1].hidden));
bar.children[0].onclick();
assert.ok(columns().every(e => !e.children[1].hidden));
assert.equal(bar.children[0].attrs["aria-expanded"], "true");
const restored = el(); mountChanbar(restored, { ...ctx, store: createStore() });
assert.equal(restored.children[0].attrs["aria-expanded"], "true");
bar.children[0].onclick();
assert.ok(columns().every(e => e.children[1].hidden));
assert.equal(saved.get("analysis.vertical.expanded"), "false");
bar.children[0].onclick();
// 儲存被封鎖時仍預設收折，且按鈕可正常切換。
globalThis.localStorage = { getItem() { throw Error("blocked"); }, setItem() { throw Error("blocked"); } };
const fallbackStore = createStore(); fallbackStore.set({ channels: store.get().channels });
const fallback = el(); mountChanbar(fallback, { ...ctx, store: fallbackStore });
assert.ok(fallback.children.slice(1).every(e => e.children[1].hidden));
fallback.children[0].onclick();
assert.ok(fallback.children.slice(1).every(e => !e.children[1].hidden));
delete globalThis.localStorage;

const vertical = columns()[0].children[1], row = vertical.children[0], input = row.children[2];
input.value = "137m"; input.onchange(); near(store.get().channels[0].scale, 0.137);
assert.equal(input.value, "137 mV");
for (const [value, want] of [["0", 0.0005], ["-5m", 0.0005], ["1p", 0.0005], ["100", 10]]) {
  input.value = value; input.onchange(); near(store.get().channels[0].scale, want);
}
input.value = "bad"; input.onchange(); near(store.get().channels[0].scale, 10);
input.value = "137m"; input.onchange();
row.children.find((c) => c.textContent === "+").onclick(); near(store.get().channels[0].scale, 0.147);
row.children.find((c) => c.textContent === "−").onclick(); near(store.get().channels[0].scale, 0.137);
const key = (key, shiftKey = false) => ({ key, shiftKey, preventDefault() { this.prevented = true; } });
const up = key("ArrowUp"); input.onkeydown(up); assert.ok(up.prevented); near(store.get().channels[0].scale, 0.147);
input.onkeydown(key("ArrowDown")); near(store.get().channels[0].scale, 0.137);
input.onkeydown(key("ArrowUp", true)); assert.equal(store.get().channels[0].scale, 0.2);
near(fineScale(0.005, "V", false, scales), 0.0005);
// 粗調使用具體預期，不以凍結的 stepScale 自比。
assert.equal(coarseScale(0.147, "V", true, scales), 0.2);
assert.equal(coarseScale(0.137, "V", false, scales), 0.1);
for (const up of [true, false]) {
  assert.equal(coarseScale(up ? 10 : 0.0005, "V", up, scales), up ? 10 : 0.0005);
  assert.equal(coarseScale(0.1 * (1 + (up ? -1 : 1) * 1e-10), "V", up, scales), up ? 0.2 : 0.05);
}
input.value = "500u"; input.onchange(); assert.equal(store.get().channels[0].scale, 0.0005);
for (const label of ["−", "▼"]) {
  row.children.find((c) => c.textContent === label).onclick(); assert.equal(store.get().channels[0].scale, 0.0005);
}
input.value = "100m"; input.onchange();
row.children.find((c) => c.textContent === "+").onclick();
assert.equal(store.get().channels[0].scale, 0.11, "0.1 微調 + 必須嚴格等於 0.11");
input.value = "237m"; input.onchange();
row.children.find((c) => c.textContent === "+").onclick();
assert.equal(store.get().channels[0].scale, 0.247, "toPrecision(15) 必須消除微調浮點尾數");
for (const [typed, direction, shift, want] of [["237m", "ArrowUp", false, 0.247], ["237m", "ArrowDown", false, 0.227], ["147m", "ArrowUp", true, 0.2], ["137m", "ArrowDown", true, 0.1]]) {
  input.value = typed; input.onkeydown(key(direction, shift)); assert.equal(store.get().channels[0].scale, want);
}
for (const modifier of ["isComposing", "altKey", "metaKey", "ctrlKey"]) {
  input.value = "237m"; const e = { ...key("ArrowUp"), [modifier]: true };
  input.onkeydown(e); assert.equal(e.prevented, undefined); assert.equal(store.get().channels[0].scale, 0.1);
}
input.value = "bad"; input.onkeydown(key("ArrowUp")); assert.equal(store.get().channels[0].scale, 0.11);
near(fineScale(10, "V", true, scales), 10);
near(fineScale(1.234, "V²", true, scales), 1.296); // 5%=0.0617 → 0.062
near(fineScale(1e-12, "V/s", false, scales), 1e-12);
near(fineScale(5e12, "V/s", true, scales), 5e12);
near(clampScale(0.137, "V", scales), 0.137);
store.set({ selected: "CHAN2" });
assert.equal(columns()[1].dataset.selected, "true"); assert.equal(columns()[0].dataset.selected, "false");
const derivedRow = columns()[1].children[1].children[0];
derivedRow.children.find((c) => c.textContent === "+").onclick(); near(store.get().channels[1].scale, 1.296);
const derivedInput = derivedRow.children[2]; derivedInput.value = "2.317 V²"; derivedInput.onchange();
near(store.get().channels[1].scale, 2.317);
// P2b：換檔改為保留畫面中心的物理值，與整檔資料中心無關。
store.set({ selected: "CHAN1" });
assert.equal(columns()[0].dataset.selected, "true"); assert.equal(columns()[1].dataset.selected, "false");
store.updateChannel("CHAN1", { scale: 0.2, position: -1 });
row.children.find((c) => c.textContent === "+").onclick();
near(-store.get().channels[0].position * store.get().channels[0].scale, 0.2);
store.updateChannel("CHAN1", { position: 0 });
const host = el(), plot = mountPlot(host, ctx); await new Promise((r) => setTimeout(r, 0));
const canvas = host.children[0], rect = layoutRect(544, 308);
let timeStamp = 1000;
const event = (x, y) => ({ clientX: x, clientY: y, button: 0, pointerId: 1, timeStamp });
const fire = (name, x, y) => canvas.listeners[name](event(x, y));
let hs = channelHandles(store.get().channels, rect);
assert.equal(hs.length, 2);
const many = Array.from({ length: 8 }, (_, i) => ({ name: `CH${i + 1}`, position: i - 4, visible: true }));
const separate = channelHandles(many, rect); assert.ok(separate.every((h) => h.w >= 12 && h.x === separate[0].x));
const overlap = channelHandles(many.map((c) => ({ ...c, position: 0 })), rect);
assert.equal(new Set(overlap.map((h) => h.y)).size, 8);
assert.ok(hs.every((h) => h.x + h.w <= rect.l - 24), "把手須與刻度數字分離"); assert.ok(texts.includes("●1") && texts.includes("▲2"));
// 把手與 Y 游標重疊仍優先；兩個相同零位的通道各可操作。
store.set({ cursors: { x1: null, x2: null, y1: 0, y2: null } });
for (const initial of hs) {
  const h = channelHandles(store.get().channels, rect).find((h) => h.name === initial.name);
  const x = h.x + h.w / 2, y = h.y + 10;
  fire("pointerdown", x, y); fire("pointermove", x + 80, y - 27.8); fire("pointerup", x + 80, y - 27.8);
  assert.equal(commands.at(-1)?.[0], "channel"); assert.equal(commands.at(-1)[1].name, h.name);
  near(store.get().channels.find((c) => c.name === h.name).position, 1);
}
// 雙擊零位只改通道 position，不發 view.reset。
let resets = 0; store.onCommand("view.reset", () => resets++);
hs = channelHandles(store.get().channels, rect);
fire("dblclick", hs[0].x + hs[0].w / 2, hs[0].y + 10); near(store.get().channels[0].position, 0); assert.equal(resets, 0);
store.updateChannel("CHAN1", { position: 8 });
assert.match(channelHandles(store.get().channels, rect)[0].label, /▲/);
store.updateChannel("CHAN1", { position: -8 });
assert.match(channelHandles(store.get().channels, rect)[0].label, /▼/);
store.set({ cursors: { x1: null, x2: null, y1: null, y2: null } });
fire("pointerdown", rect.l + 1, divY(rect, 1)); fire("pointermove", rect.l + 51, divY(rect, 2)); fire("pointerup", 95, 80);
assert.equal(commands.at(-1)?.[0], "view", "繪圖區即使靠左也只能平移時間");
near(store.get().view.t0, -50 * 4 / rect.w);
// 零位窄區內但未命中把手也不搶時間平移；取消後不得再拖動。
const count = commands.length; fire("pointerdown", 2, rect.t + 80); fire("pointermove", 90, rect.t + 90);
assert.equal(commands.length, count);
fire("pointerdown", hs[1].x + 2, hs[1].y + 5); fire("pointercancel", 0, 0); fire("pointermove", 300, 300);
assert.equal(commands.length, count);
// 重現：縮放與平移使 X 跑出畫面；Y 的格數與線的像素位置完全不變。
store.set({ view: { t0: 0, t1: 4 }, cursors: { x1: 1, x2: 3, y1: 2, y2: -2 } });
const before = { ...store.get().cursors }, yBefore = divY(rect, before.y1);
const drawnY = textPositions.findLast((p) => p.text === "v1");
assert.deepEqual(outsideCursors(before, store.get().view), []);
store.set({ view: { t0: 1.8, t1: 2.2 } });
assert.deepEqual(outsideCursors(store.get().cursors, store.get().view).map((c) => c.which), ["x1", "x2"]);
assert.ok(texts.includes("◀ x1") && texts.includes("▶ x2"));
store.set({ view: { t0: 20, t1: 24 } });
assert.deepEqual(store.get().cursors, before); near(divY(rect, store.get().cursors.y1), yBefore);
assert.deepEqual(textPositions.findLast((p) => p.text === "v1"), drawnY, "真正繪製的 Y 游標標籤也維持同一像素");
assert.ok(texts.includes("◀ x1") && texts.includes("◀ x2"));
const edge = cursorEdges(before, store.get().view, rect)[0];
fire("pointerdown", edge.x + 5, edge.y + 5);
assert.ok(!cursorEdges(store.get().cursors, store.get().view, rect).some((e) => e.which === edge.which));
timeStamp += 100;
fire("pointerup", edge.x + 5, edge.y + 5);
fire("pointerdown", edge.x + 5, edge.y + 5); fire("pointerup", edge.x + 5, edge.y + 5);
fire("dblclick", edge.x + 5, edge.y + 5); assert.equal(resets, 0, "箭頭消失後的雙擊不得重設視圖");
timeStamp += 500;
fire("dblclick", rect.l + rect.w / 2, rect.t + rect.h / 2); assert.equal(resets, 1, "超過 500ms 可正常重設");
near((store.get().view.t0 + store.get().view.t1) / 2, before.x1);
assert.deepEqual(store.get().cursors, before, "點 X 提示只搬動視窗");
store.set({ cursors: { ...before, y1: 7, y2: -9 } });
const sameSide = cursorEdges({ y1: 7, y2: 9 }, store.get().view, rect);
assert.ok(Math.abs(sameSide[0].y - sameSide[1].y) >= 24, "同側越界提示不可互相遮住");
assert.ok(texts.includes("▲ y1") && texts.includes("▼ y2"));
const yEdge = cursorEdges(store.get().cursors, store.get().view, rect).find((e) => e.which === "y1");
const panel = el(); mountCursors(panel, ctx);
assert.ok(!panel.children[0].children.some((c) => c.textContent === "游標置中"), "游標面板不再有歸位鈕");
const topReset = centerButton(store), reset = topReset;
assert.equal(topReset.disabled, true);
assert.equal(reset.title, "t1／t2 回到目前畫面中間");
assert.equal(topReset.title, reset.title);
assert.equal(reset.disabled, true);
const noFileCursors = { ...store.get().cursors }; reset.onclick(); assert.deepEqual(store.get().cursors, noFileCursors);
const intents = []; store.onCommand("cursor.intent", (p) => intents.push(p));
fire("pointerdown", yEdge.x + 5, yEdge.y + 5);
assert.deepEqual(intents.at(-1), { which: "y1", value: 2 }); assert.equal(store.get().cursors.y1, 2);
const y2Edge = cursorEdges(store.get().cursors, store.get().view, rect).find((e) => e.which === "y2");
fire("pointerdown", y2Edge.x + 5, y2Edge.y + 5);
assert.deepEqual(intents.at(-1), { which: "y2", value: -2 }); assert.equal(store.get().cursors.y2, -2);
assert.equal(messages.length, 0);
assert.deepEqual(outsideCursors({ x1: 0, x2: 4, y1: 5, y2: -5 }, { t0: 0, t1: 4 }), []);
assert.deepEqual(outsideCursors({ x1: null, x2: NaN, y1: Infinity }, { t0: 0, t1: 4 }), []);
// 兩處實際按鈕共用回中央；通道列獨立於 B 區，收折數值面板仍可按。
store.set({ file: { gen: 1, channels: [] } });
assert.equal(reset.disabled, false); assert.equal(topReset.disabled, false);
panel.hidden = true;
const origins = []; store.on(["cursors"], (_s, _keys, origin) => origins.push(origin));
for (const button of [reset, topReset]) {
  for (const [view, initial, expected] of [
    [{ t0: 20, t1: 28 }, { x1: 1, x2: 3, y1: 1, y2: -3 }, { x1: 23, x2: 25, y1: 1, y2: -3 }],
    [{ t0: 21, t1: 25 }, { x1: 1, x2: 3, y1: 5, y2: -5 }, { x1: 22, x2: 24, y1: 5, y2: -5 }],
    [{ t0: -8, t1: -4 }, { x1: 3, x2: 1, y1: 7, y2: -9 }, { x1: -5, x2: -7, y1: 2, y2: -2 }],
    [{ t0: 20, t1: 24 }, { x1: 0, x2: 4, y1: null, y2: Infinity }, { x1: 21, x2: 23, y1: 2, y2: -2 }],
    [{ t0: 0, t1: 10 }, { x1: 0, x2: 9, y1: NaN, y2: -2 }, { x1: 2.5, x2: 7.5, y1: 2, y2: -2 }],
    [{ t0: 0, t1: 10 }, { x1: 0, x2: 8.9, y1: 0, y2: 0 }, { x1: 0.55, x2: 9.45, y1: 0, y2: 0 }],
    [{ t0: 20, t1: 24 }, { x1: 3, x2: 3, y1: 0, y2: 4 }, { x1: 22, x2: 22, y1: 0, y2: 4 }],
  ]) {
    store.set({ view, cursors: initial }); button.onclick();
    const cur = store.get().cursors;
    for (const k of Object.keys(expected)) near(cur[k], expected[k]);
    near((cur.x1 + cur.x2) / 2, (view.t0 + view.t1) / 2);
    assert.equal(origins.at(-1), "user");
    assert.deepEqual(outsideCursors(cur, view), []);
  }
  for (const [x1, x2] of [[null, 1], [NaN, 1], [1, Infinity], [-1e308, 1e308]]) {
    store.set({ view: { t0: 20, t1: 24 }, cursors: { x1, x2, y1: 1, y2: -1 } });
    button.onclick(); assert.deepEqual(store.get().cursors, { x1: 21, x2: 23, y1: 1, y2: -1 });
  }
}
// 回中央後仍排程讀值、吸附回寫；snap 不得形成重算迴圈。
const reads = [];
ctx.bridge.call = async (method, args) => { reads.push({ method, args }); return { t1: args.t1 + 0.01, t2: args.t2 + 0.01, y: {} }; };
store.set({ view: { t0: 20, t1: 28 }, cursors: { x1: 1, x2: 3, y1: 1, y2: -1 } });
topReset.onclick();
await new Promise((r) => setTimeout(r, 100));
assert.equal(reads.length, 1); assert.equal(reads[0].method, "cursor_readout");
assert.equal(reads[0].args.t1, 23); assert.equal(reads[0].args.t2, 25);
assert.deepEqual(store.get().cursors, { x1: 23.01, x2: 25.01, y1: 1, y2: -1 });
assert.equal(origins.at(-1), "snap");
await new Promise((r) => setTimeout(r, 100)); assert.equal(reads.length, 1);
store.set({ file: null }); assert.equal(reset.disabled, true); assert.equal(topReset.disabled, true);
const closed = { ...store.get().cursors }; reset.onclick(); topReset.onclick();
assert.deepEqual(store.get().cursors, closed);
// 主檔＋四個槽位共十通道：同零位、兩端越界及矮圖均無方塊重疊。
const ten = Array.from({ length: 10 }, (_, i) => ({ ...store.get().channels[0],
  name: i < 2 ? `CHAN${i + 1}` : `Mem${Math.floor(i / 2)}.CHAN${i % 2 + 1}`, position: 0 }));
for (const r of [rect, { ...rect, h: 60 }]) for (const position of [0, 8, -8]) {
  const channels = ten.map(c => ({ ...c, position })), boxes = channelHandles(channels, r);
  for (const [i, b] of boxes.entries()) {
    assert.ok(b.y >= 0 && b.y + b.h <= r.t + r.h);
    assert.equal(hitHandle(channels, r, b.x + b.w / 2, b.y + b.h / 2)?.name, b.name);
    assert.ok(boxes.slice(i + 1).every(a => a.x >= b.x + b.w || b.x >= a.x + a.w || a.y >= b.y + b.h || b.y >= a.y + a.h));
  }
}
store.set({ channels: ten, cursors: { x1: null, x2: null, y1: null, y2: null } });
assert.deepEqual(channelHandles(ten, rect).map(b => b.label), ["●1", "▲2", "■3", "◆4", "●5", "▲6", "■7", "◆8", "●9", "▲10"]);
assert.equal(new Set(channelHandles(ten, rect).map(b => b.x)).size, 1);
assert.ok(textPositions.filter(p => /^[●▲■◆]\d+$/.test(p.text)).every(p => p.font === "12.5px sans-serif" && p.maxWidth === undefined));
// 實際 hover／拖曳每一個避讓後的把手，名稱仍為完整通道名，位移沒有跳位。
for (const c of ten) {
  const b = channelHandles(store.get().channels, rect).find(b => b.name === c.name);
  const x = b.x + b.w / 2, y = b.y + b.h / 2;
  fire("pointermove", x, y); assert.equal(canvas.title, c.name);
  fire("pointerdown", x, y); fire("pointermove", x, y - 27.8); fire("pointerup", x, y - 27.8);
  assert.equal(commands.at(-1)[1].name, c.name);
  near(store.get().channels.find(ch => ch.name === c.name).position, 1);
}
canvas.listeners.pointerleave(); assert.equal(canvas.title, "");
// 清空通道也移除所有通道欄與垂直控制。
store.set({ channels: [] }); assert.deepEqual(columns(), []);
plot.dispose();
console.log("P1 feedback self-check OK：微調／任意輸入、把手實際事件、X 越界復現、Y 時間軸不變、雙處回中央／有號間距／Y 保留／吸附");
