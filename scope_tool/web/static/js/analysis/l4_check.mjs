// L4 純邏輯自測：node --experimental-default-type=module l4_check.mjs
import assert from "node:assert/strict";
import { linear, logmap, divTicks, niceTicks, logTicks, envPixels, drawPixels, nearestDist, makeLatest, debounce } from "./plotcore.js";
import { layoutRect, markerPixels, fetchTargets, divY, yToDiv, valueY, panView, zoomView, waveKey } from "./mainplot.js";
import { fullRange, hitRegion, dragRegion } from "./overview.js";
import { freqWindow, yRange } from "./fftpane.js";
import { channelsFromFile, cleanView, bindOpen, openPatch } from "./tab_analysis.js";

const near = (a, b, e = 1e-9) => assert.ok(Math.abs(a - b) < e, `${a} != ${b}`);

// 座標轉換
const f = linear(0, 10, 100, 200); near(f(5), 150); near(f.inv(150), 5);
const lg = logmap(1, 1000, 0, 300); near(lg(10), 100); near(lg.inv(200), 100);
const r = layoutRect(544, 308); assert.deepEqual([r.l, r.t, r.w, r.h], [84, 8, 450, 278]);
near(divY(r, 5), r.t); near(divY(r, -5), r.t + r.h); near(yToDiv(r, divY(r, 2.5)), 2.5);
near(valueY(r, 0.5, 1)(1), divY(r, 3)); // 1V/0.5 + 1 = 3 格
// 刻度
const dt = divTicks(0, 1); assert.equal(dt.length, 11); near(dt[1], 0.1);
assert.deepEqual(niceTicks(0, 100, 5), [0, 20, 40, 60, 80, 100]);
assert.deepEqual(logTicks(1, 100), [1, 2, 5, 10, 20, 50, 100]);
// 平移縮放
const p = panView({ t0: 0, t1: 1 }, 49, 490); near(p.t0, -0.1); near(p.t1, 0.9);
const z = zoomView({ t0: 0, t1: 10 }, 5, 0.5); near(z.t0, 2.5); near(z.t1, 7.5);
// 包絡 → 像素（含 dx、scale、position、NaN）
const env = { n: 3, mode: 1, x: Float64Array.of(0, 1, 2), lo: Float32Array.of(-1, NaN, 0), hi: Float32Array.of(1, NaN, 2) };
const px = envPixels(env, (t) => 10 + (t + 0.5) * 100, valueY(r, 1, 0));
near(px.x[0], 60, 1e-3); near(px.top[0], divY(r, 1), 1e-3); near(px.bot[0], divY(r, -1), 1e-3);
assert.ok(Number.isNaN(px.top[1]) && px.top[0] < px.bot[0]);
// 假 Canvas 計數：mode 1 NaN 桶不畫；mode 0 NaN 斷線
const calls = []; const g = new Proxy({}, { get: (_, k) => (...a) => calls.push([k, ...a]), set: () => true });
drawPixels(g, px, "#fff");
assert.equal(calls.filter((c) => c[0] === "moveTo").length, 2);
calls.length = 0;
drawPixels(g, { x: Float32Array.of(0, 1, 2, 3), top: Float32Array.of(5, NaN, 6, 7), bot: Float32Array.of(5, NaN, 6, 7), mode: 0 }, "#fff");
assert.equal(calls.filter((c) => c[0] === "moveTo").length, 2); assert.equal(calls.filter((c) => c[0] === "lineTo").length, 1);
// 命中測試
assert.equal(nearestDist(px, 60, divY(r, 0)), 0); // 在 lo~hi 之間
assert.equal(nearestDist(px, 60, divY(r, 4)), Infinity);
// 過期序號丟棄
const lt = makeLatest(); const a = lt.begin(), b = lt.begin();
assert.ok(!a.ok() && b.ok()); lt.cancel(); assert.ok(!b.ok());
assert.equal(waveKey("C", { t0: 1, t1: 2 }, 0.5, 100, 3), "C|0.5|1.5|100|3");
// 防抖
let n = 0; const d = debounce(() => n++, 10); d(); d(); d();
await new Promise((s) => setTimeout(s, 40)); assert.equal(n, 1);
// 縮圖
const file = { gen: 1, channels: [{ t0: 0, t1: 5, unit: "V", vmin: -1, vmax: 3 }, { t0: -1, t1: 4 }] };
assert.deepEqual(fullRange(file), { t0: -1, t1: 5 });
assert.equal(hitRegion(10, 10, 50), "edge0"); assert.equal(hitRegion(30, 10, 50), "move"); assert.equal(hitRegion(90, 10, 50), "jump");
assert.deepEqual(dragRegion("move", { t0: 1, t1: 3 }, 1, 0, 0.1), { t0: 2, t1: 4 });
assert.deepEqual(dragRegion("edge1", { t0: 1, t1: 3 }, -5, 0, 0.1), { t0: 1, t1: 1.1 });
assert.deepEqual(dragRegion("jump", { t0: 1, t1: 3 }, 0, 10, 0.1), { t0: 9, t1: 11 });
// FFT
near(freqWindow({ f_min: 0, f_max: 1000, df: 10 }, null, true).f0, 10);
assert.deepEqual(freqWindow({ f_min: 0, f_max: 1000 }, { f0: 5, f1: 50 }, false), { f0: 5, f1: 50 });
const [lo, hi] = yRange({ n: 2, lo: Float32Array.of(-100, NaN), hi: Float32Array.of(-20, NaN) }); assert.ok(lo < -100 && hi > -20);
assert.deepEqual(yRange({ n: 0, lo: [], hi: [] }), [0, 1]);
// 開檔 → 通道記錄
const cs = channelsFromFile({ channels: [{ name: "CHAN1", unit: "V", derived: false, vmin: -1, vmax: 3, t0: 0, t1: 2 }] });
assert.equal(cs[0].t1, 2); assert.equal(cs[0].scale, 0.5); near(cs[0].position, -2); assert.equal(cs[0].time_offset, 0);
assert.equal(cleanView({ t0: 2, t1: 1 }), null); assert.deepEqual(cleanView({ t0: 1, t1: 2 }), { t0: 1, t1: 2 });
// open_waveform／file.open 皆綁到同一處理者
const bound = []; bindOpen({ onCommand: (n) => bound.push(n) }, () => {});
assert.deepEqual(bound, ["file.open", "open_waveform"]);
// Marker 點：顯示座標 → 像素，缺值略過
const mk = markerPixels({ mode: "Track Waveforms", points: [{ x: 0.5, y: 2, label: "A" }, { x: NaN, y: 1, label: "B" }, { x: 1, y: null }] }, linear(0, 1, r.l, r.l + r.w), r);
assert.equal(mk.length, 1); near(mk[0].px, r.l + r.w / 2); near(mk[0].py, divY(r, 2)); assert.equal(mk[0].label, "A");
assert.deepEqual(markerPixels(null, f, r), []);
// 開檔 patch：file 與 channels／selected 同一次 set；fetchTargets 只含新檔內的通道
const info = { gen: 2, channels: [{ name: "CHAN1", unit: "V", vmin: 0, vmax: 1, t0: 0, t1: 1 }] };
const patch = openPatch(info); assert.equal(patch.file, info); assert.equal(patch.selected, "CHAN1"); assert.equal(patch.channels.length, 1);
assert.deepEqual(fetchTargets({ file: info, channels: [{ name: "OLD", visible: true }, { name: "CHAN1", visible: true }, { name: "CHAN2", visible: false }] }).map((c) => c.name), ["CHAN1"]);
// 可見狀態掛載：RO 同步觸發也不得 ReferenceError；以假 DOM 掛載三個圖表
{
  const mkCtx = () => new Proxy({ paths: [], texts: [], path: [], textWidth: 0 }, { get: (t, k) => {
    if (k === "measureText") return () => ({ width: t.textWidth });
    if (k === "beginPath") return () => { t.path = []; };
    if (k === "moveTo" || k === "lineTo") return (x, y) => t.path.push({ x, y });
    if (k === "stroke") return () => t.paths.push({ color: t.strokeStyle, points: [...t.path] });
    if (k === "fillText") return (text, x, y) => t.texts.push({ text, x, y });
    return t[k] ??= () => {};
  }, set: (t, k, v) => ((t[k] = v), true) });
  const mkEl = () => ({ className: "", style: {}, width: 0, height: 0, listeners: {}, getContext() { return this.ctx ??= mkCtx(); }, addEventListener(k, fn) { this.listeners[k] = fn; }, setPointerCapture() {},
    getBoundingClientRect: () => ({ width: 500, height: 300, left: 0, top: 0 }), append(child) { this.child = child; }, querySelector(k) { return (this.nodes ??= {})[k] ??= mkEl(); }, innerHTML: "" });
  globalThis.window = { devicePixelRatio: 2 };
  globalThis.document = { createElement: mkEl };
  globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; } observe() { this.cb(); } disconnect() {} }; // 同步觸發（最壞情況）
  const { createStore } = await import("./store.js");
  const store = createStore(); let fetched = 0; const spectra = [];
  const bridge = { fetchWave: async () => { fetched++; return { n: 1, mode: 0, x: Float64Array.of(0), lo: Float32Array.of(0), hi: Float32Array.of(0) }; }, fetchSpectrum: async (p) => { spectra.push(p); return { n: 0, mode: 0, x: new Float64Array(0), lo: new Float32Array(0), hi: new Float32Array(0) }; } };
  const c = { store, bridge, ui: { toast() {} } };
  store.set(openPatch(info), "program");
  const hosts = [];
  for (const m of ["./mainplot.js", "./overview.js", "./fftpane.js"]) {
    const host = mkEl(); hosts.push(host); host.plot = (await import(m)).mount(host, c);
  }
  await new Promise((s) => setTimeout(s, 250));
  assert.ok(fetched >= 1);
  // 實際主圖事件：曲線上拖曳（含 Shift）只發時間平移，滾輪只發時間縮放。
  const canvas = hosts[0].child, sent = [];
  store.onCommand("viewport.intent", p => sent.push(["view", p]));
  store.onCommand("cursor.intent", p => sent.push(["cursor", p]));
  store.onCommand("channel.shift_intent", () => assert.fail("拖曳不得改 dx"));
  store.onCommand("channel.scale_intent", () => assert.fail("主圖手勢不得改垂直尺度／位置"));
  const before = structuredClone(store.get().channels);
  const curve = canvas.ctx.paths.filter(p => p.color === before[0].color && p.points.length).at(-1).points[0];
  const hit = { x: Float32Array.of(curve.x), top: Float32Array.of(curve.y), bot: Float32Array.of(curve.y), mode: 0 };
  assert.equal(nearestDist(hit, curve.x, curve.y), 0, "手勢起點必須命中已繪製曲線");
  assert.ok(curve.x >= 44 && curve.y >= 8 && curve.y <= 278);
  console.log(`gesture hit: (${curve.x}, ${curve.y}), distance=0`);
  const event = (x, y, extra = {}) => ({ clientX: x, clientY: y, button: 0, pointerId: 1, preventDefault() {}, ...extra });
  for (const shiftKey of [false, true]) {
    canvas.listeners.pointerdown(event(curve.x, curve.y, { shiftKey }));
    canvas.listeners.pointermove(event(curve.x + 50, curve.y - 30));
    assert.equal(sent.at(-1)[0], "view");
    assert.ok(sent.at(-1)[1].t0 < 0);
    canvas.listeners.pointerup(event(curve.x + 50, curve.y - 30, { type: "pointerup" }));
  }
  const n = sent.length;
  canvas.listeners.wheel(event(curve.x, curve.y, { deltaY: 0 }));
  assert.equal(sent.length, n);
  canvas.listeners.wheel(event(curve.x, curve.y, { deltaY: -120 }));
  const zoom = sent.at(-1)[1];
  assert.equal(sent.at(-1)[0], "view"); near(zoom.t0, 0);
  assert.ok(zoom.t1 < 1); // 游標時間為錨，曲線在畫面內外皆可放大
  assert.deepEqual(store.get().channels, before);
  // 點曲線不得改選取通道。
  store.set({ selected: "OTHER" });
  canvas.listeners.pointerdown(event(curve.x, curve.y));
  canvas.listeners.pointerup(event(curve.x, curve.y, { type: "pointerup" }));
  assert.equal(store.get().selected, "OTHER");
  // 文字過密時只畫隔格文字，仍保留全部 11 條垂直格線。
  canvas.ctx.textWidth = 100; canvas.ctx.paths.length = 0; canvas.ctx.texts.length = 0;
  hosts[0].plot.draw();
  assert.equal(canvas.ctx.texts.filter(t => t.y === 282).length, 5);
  assert.equal(canvas.ctx.paths.find(p => p.color === "#333").points.length, 44);
  canvas.ctx.textWidth = 0;
  // overview 必須在真正繪製路徑套用 dx；拿掉 dx 時此斷言會失敗。
  const overview = hosts[1].child;
  const overviewX = () => overview.ctx.paths.filter(p => p.color === before[0].color && p.points.length).at(-1).points[0].x;
  const x0 = overviewX();
  store.updateChannel(before[0].name, { time_offset: 0.2 }, "user");
  near(overviewX() - x0, 100, 1e-4);
  console.log(`overview dx self-check OK: ${x0} → ${overviewX()} px (dx=0.2 s)`);
  store.updateChannel(before[0].name, { time_offset: before[0].time_offset }, "user");
  for (const which of ["x1", "x2", "y1", "y2"]) {
    store.set({ cursors: { x1: null, x2: null, y1: null, y2: null, [which]: which[0] === "x" ? 0.5 : 0 } });
    const center = layoutRect(500, 300);
    canvas.listeners.pointerdown(event(center.l + center.w / 2, center.t + center.h / 2));
    canvas.listeners.pointermove(event(280, 150));
    assert.equal(sent.at(-1)[0], "cursor"); assert.equal(sent.at(-1)[1].which, which);
    canvas.listeners.pointercancel(event(280, 150, { type: "pointercancel" }));
  }
  store.set({ fftResult: { ok: true, spectrum_id: "test", f_min: 0, f_max: 100, unit: "V" } });
  await new Promise(s => setTimeout(s, 220));
  const fftCanvas = hosts[2].querySelector(".analysis__fftplot").child, count = spectra.length;
  fftCanvas.listeners.wheel(event(64, 100, { deltaY: 0 }));
  await new Promise(s => setTimeout(s, 220));
  assert.equal(spectra.length, count, "FFT deltaY=0 不得縮放或重抓");
  fftCanvas.listeners.wheel(event(64, 100, { deltaY: -120 }));
  await new Promise(s => setTimeout(s, 220));
  near(spectra.at(-1).f1, 100 * (2 ** (-120 / 480)));
  console.log(`FFT wheel self-check OK: zero requests=0, f1=${spectra.at(-1).f1}`);
  console.log("mainplot gestures self-check OK");
  hosts.forEach(host => host.plot.dispose());
}
console.log("l4 self-check OK");
