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
const r = layoutRect(544, 308); assert.deepEqual([r.l, r.t, r.w, r.h], [44, 8, 490, 278]);
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
  const mkCtx = () => new Proxy({}, { get: (t, k) => (k === "measureText" ? () => ({ width: 0 }) : (t[k] ??= () => {})), set: (t, k, v) => ((t[k] = v), true) });
  const mkEl = () => ({ className: "", style: {}, width: 0, height: 0, listeners: {}, getContext: mkCtx, addEventListener() {}, setPointerCapture() {},
    getBoundingClientRect: () => ({ width: 500, height: 300, left: 0, top: 0 }), append() {}, querySelector: () => mkEl(), innerHTML: "" });
  globalThis.window = { devicePixelRatio: 2 };
  globalThis.document = { createElement: mkEl };
  globalThis.ResizeObserver = class { constructor(cb) { this.cb = cb; } observe() { this.cb(); } disconnect() {} }; // 同步觸發（最壞情況）
  const { createStore } = await import("./store.js");
  const store = createStore(); let fetched = 0;
  const bridge = { fetchWave: async () => { fetched++; return { n: 1, mode: 0, x: Float64Array.of(0), lo: Float32Array.of(0), hi: Float32Array.of(0) }; }, fetchSpectrum: async () => ({ n: 0, mode: 0, x: new Float64Array(0), lo: new Float32Array(0), hi: new Float32Array(0) }) };
  const c = { store, bridge, ui: { toast() {} } };
  store.set(openPatch(info), "program");
  for (const m of ["./mainplot.js", "./overview.js", "./fftpane.js"]) (await import(m)).mount(mkEl(), c);
  await new Promise((s) => setTimeout(s, 250));
  assert.ok(fetched >= 1);
}
console.log("l4 self-check OK");
