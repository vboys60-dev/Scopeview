// L5 自檢：node --experimental-default-type=module scope_tool/web/static/js/analysis/l5_check.mjs
// 只測純邏輯與 mock 後端（座標換算、dx 讀值、防迴圈、過期丟棄、量測防抖）；DOM／手感待真人驗證。
import '../mock_current_check.mjs';
import assert from "node:assert/strict";
import { createStore } from "./store.js";
import * as scales from "./scales.js";
import * as F from "../fmt.js";
import { createMock, CATALOG } from "../mock_backend.js";
import { toSource, toDisplay, defaultCursors, createController, MODE_AXES, cursorRows } from "./cursors.js";
import { createMeasure, rangeOf, unitFor } from "./measure.js";
import { rowState, exportable, rowCells } from "./results.js";
import { channelRecord, csvRange, fftParams, createFft } from "./toolbar.js";
import { scaleChange, signature } from "./chanbar.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
/** 以 mock 後端組 bridge；calls 記錄每次呼叫；hook(method) 可回傳 Promise 以延後回應。 */
function makeBridge(mock, hook) {
  const calls = [];
  const wait = (id) => new Promise((res, rej) => { const off = mock.subscribe((ev) => { if (ev.type === "job" && ev.id === id) { off(); ev.ok ? res(ev.result) : rej(Object.assign(new Error(ev.error.message), ev.error)); } }); });
  const call = async (m, p) => {
    calls.push([m, p]);
    if (hook) await hook(m, p); // 延後送出（job 事件可能早於訂閱，故不能放在 rpc 之後）
    const r = await mock.rpc(m, p);
    if (!r.ok) throw Object.assign(new Error(r.error.message), r.error);
    return r.result;
  };
  return { calls, call, job: async (m, p) => { const id = (await call(m, p)).job; return wait(id); } };
}
async function setup(hook) {
  const mock = createMock(), bridge = makeBridge(mock), store = createStore();
  const sum = await bridge.job("open_waveform", { path: "/x/a.h5" });
  bridge.hook = hook; // 之後的呼叫才套延遲
  const b2 = makeBridge(mock, hook);
  const channels = sum.channels.map((c, i) => channelRecord(c, i, CATALOG.channel_colors, scales));
  return { mock, bridge: b2, store, sum, channels };
}

// 1. 座標換算：x_src = x − dx；y_src = (y − position) × scale，且可逆
{
  const ch = { time_offset: 0.002, position: 1.5, scale: 0.5 };
  const s = toSource({ x1: 0.01, x2: null, y1: 3, y2: null }, ch);
  assert.ok(Math.abs(s.x1 - 0.008) < 1e-15 && s.y1 === 0.75 && s.x2 === null && s.y2 === null);
  const [x, y] = toDisplay(s.x1, s.y1, ch);
  assert.ok(Math.abs(x - 0.01) < 1e-15 && y === 3);
  assert.deepEqual(MODE_AXES(null), { x: true, y: true });
  assert.deepEqual(MODE_AXES("Manual Y only"), { x: false, y: true });
  assert.deepEqual(defaultCursors({ t0: 0, t1: 4 }), { x1: 1, x2: 3, y1: 2, y2: -2 });
}

// 2. 傳統游標：dx 傳給後端、吸附第一通道、snap 回寫不再觸發（防迴圈）、預設游標
{
  const { bridge, store, sum, channels } = await setup();
  const ctl = createController({ store, bridge }, { delay: 5 });
  store.set({ file: sum, channels, selected: "CHAN2" }, "program");
  store.set({ channels: store.get().channels.map((c) => (c.name === "CHAN2" ? { ...c, time_offset: 0.0002 } : c)) }, "user");
  await sleep(30);
  assert.ok(store.get().cursors.x1 !== null, "新檔後放預設游標");
  bridge.calls.length = 0;
  store.command("cursor.intent", { which: "x1", value: 0.00123456 });
  store.command("cursor.intent", { which: "x2", value: 0.0021 });
  await sleep(40);
  const rd = bridge.calls.filter(([m]) => m === "cursor_readout");
  assert.equal(rd.length, 1, "兩次意圖合併、snap 回寫不再觸發");
  assert.equal(rd[0][1].dx.CHAN2, 0.0002); assert.equal(rd[0][1].dx.CHAN1, 0);
  const c = store.get().cursors;
  assert.equal(c.x1, ctl.readout.t1); assert.notEqual(c.x1, 0.00123456); // 已吸附到取樣點
  await sleep(40);
  assert.equal(bridge.calls.filter(([m]) => m === "cursor_readout").length, 1, "穩定後不再呼叫");
  assert.ok(ctl.readout.y.CHAN2 && "y1" in ctl.readout.y.CHAN2, "各通道讀值");
  // 非法意圖忽略
  store.command("cursor.intent", { which: "z9", value: 1 });
  store.command("cursor.intent", { which: "x1", value: NaN });
  assert.equal(store.get().cursors.x1, c.x1);
}

// 3. Marker：送後端前換來源座標；Track Waveforms 回寫 snap；markerResult 為顯示座標
{
  const { bridge, store, sum, channels } = await setup();
  const ctl = createController({ store, bridge }, { delay: 5 });
  channels[1].time_offset = 0.0002; channels[1].scale = 0.5; channels[1].position = 1;
  store.set({ file: sum, channels, selected: "CHAN2" }, "program");
  ctl.setSource("CHAN2"); // P3a：明確指定來源，不再跟著 selected
  store.set({ cursors: { x1: 0.0012, x2: 0.0031, y1: 3, y2: -1 } }, "user");
  store.set({ markerMode: "Track Waveforms" }, "user");
  await sleep(50);
  const ev = bridge.calls.filter(([m]) => m === "marker_eval").at(-1)[1];
  assert.equal(ev.channel, "CHAN2");
  assert.ok(Math.abs(ev.x1 - (0.0012 - 0.0002)) < 1e-12 && ev.y1 === (3 - 1) * 0.5 && ev.y2 === (-1 - 1) * 0.5);
  assert.ok(ev.screen_width > 0 && Array.isArray(ev.measurements));
  const mr = store.get().markerResult;
  assert.equal(mr.mode, "Track Waveforms"); assert.equal(mr.points.length, 2);
  assert.ok(Math.abs(mr.points[0].x - store.get().cursors.x1) < 1e-12, "標記點在顯示座標，與吸附後游標一致");
  const n = bridge.calls.length;
  await sleep(40);
  assert.equal(bridge.calls.length, n, "Track Waveforms 吸附後穩定，無迴圈");
  store.set({ markerMode: null }, "user"); await sleep(30);
  assert.equal(store.get().markerResult, null);
}

// 4. 過期丟棄：較早送出但較晚回來的游標讀值不得覆蓋新的
{
  let slow = true;
  const { bridge, store, sum, channels } = await setup(async (m, p) => { if (m === "cursor_readout" && slow) { slow = false; await sleep(60); } });
  const ctl = createController({ store, bridge }, { delay: 1 });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  await sleep(120); // 預設游標那次（慢）完成
  slow = true;
  store.command("cursor.intent", { which: "x1", value: 0.0005 }); await sleep(10); // 慢
  store.command("cursor.intent", { which: "x1", value: 0.0015 }); await sleep(120);
  assert.ok(Math.abs(store.get().cursors.x1 - 0.0015) < 1e-4, "以最新游標為準");
  assert.ok(Math.abs(ctl.readout.t1 - 0.0015) < 1e-4);
}

// 5. RF：spectrum_id 過期丟棄；成功寫 rfPos
{
  const { bridge, store, mock } = await setup();
  createController({ store, bridge });
  const p = { source: "CHAN1", range: null, dx: { CHAN1: 0, CHAN2: 0 }, window: "Hanning", unit: "dBm", r_ohm: 50, peak_count: 5, peak_level: -40, peak_sort: "Decreasing Magnitude" };
  const r = await bridge.job("fft", p);
  store.set({ file: { gen: r.gen }, fftResult: { ...r, peak_level: -40 } }, "program");
  store.command("rf.intent", { direction: 0, x: r.peaks[0].x }); await sleep(20);
  assert.ok(store.get().rfPos && store.get().rfPos.x === r.peaks[0].x);
  store.set({ rfPos: null }, "program");
  store.command("rf.intent", { direction: 1, x: 1 });
  store.set({ fftResult: { ...r, spectrum_id: "other" } }, "program"); // 飛行中換了頻譜
  await sleep(20);
  assert.equal(store.get().rfPos, null, "過期頻譜的結果丟棄");
  store.command("rf.intent", { direction: 7, x: 1 }); await sleep(5);
}

// 6. 量測：防抖 150 ms 合併、範圍／dx／閾值、過期丟棄、results 的 revision／gen 比對
{
  const { bridge, store, sum, channels } = await setup();
  const m = createMeasure({ store, bridge }, { delay: 30 });
  store.set({ file: sum, channels, selected: "CHAN1", rangeMode: "cursors", cursors: { x1: 0.002, x2: 0.001, y1: null, y2: null } }, "program");
  m.add("Vmax", "CHAN1", true); m.add("Vp-p", "CHAN2", true);
  assert.equal(store.get().measurements[0].result, null);
  for (let i = 0; i < 5; i++) store.set({ cursors: { ...store.get().cursors, x1: 0.002 + i * 1e-5 } }, "user");
  await sleep(100);
  const calls = bridge.calls.filter(([c]) => c === "measure");
  assert.equal(calls.length, 1, "連續變動只算一次");
  assert.deepEqual(calls[0][1].range, [0.00204, 0.001]); assert.equal(calls[0][1].threshold, "10/50/90 %");
  assert.equal(calls[0][1].entries.length, 2); assert.equal(calls[0][1].dx.CHAN2, 0);
  const list = store.get().measurements, file = store.get().file;
  assert.ok(list.every((e) => rowState(e, file) === "ok"));
  const ex = exportable(list, file);
  assert.ok(ex && ex.rows.length === 2 && ex.revision === list[0].result.revision);
  assert.equal(exportable([{ ...list[0], result: { ...list[0].result, revision: 99 } }, list[1]], file), null, "revision 不一致不可匯出");
  assert.equal(rowState(list[0], { gen: file.gen + 1 }), "pending", "gen 過期＝計算中");
  assert.equal(rowCells(list[0], "ok", "V", F)[6], "1");
  // 改 dx → 重算並帶 dx；通道 scale 變動不重算
  const n = calls.length;
  store.updateChannel("CHAN2", { scale: 2 }, "user"); await sleep(60);
  assert.equal(bridge.calls.filter(([c]) => c === "measure").length, n);
  store.updateChannel("CHAN2", { time_offset: 0.0003 }, "user"); await sleep(80);
  assert.equal(bridge.calls.filter(([c]) => c === "measure").at(-1)[1].dx.CHAN2, 0.0003);
  // 刪通道 → 該列「來源通道已刪除」
  assert.equal(rangeOf({ rangeMode: "all", cursors: { x1: 1, x2: 2 } }), null);
  assert.equal(unitFor("{u}/s", "V"), "V/s");
  store.set({ file: { ...store.get().file, gen: 99 } }, "program"); // 換檔 → 清空
  assert.equal(store.get().measurements.length, 0);
}
{ // 量測過期：慢回應期間再變動 → 舊結果不寫入
  let slow = true;
  const { bridge, store, sum, channels } = await setup(async (m) => { if (m === "measure" && slow) { slow = false; await sleep(80); } });
  const m = createMeasure({ store, bridge }, { delay: 5 });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  m.add("Vmax", "CHAN1", true); await sleep(30); // 第一次（慢）已送出
  store.set({ threshold: "20/50/80 %" }, "user"); await sleep(200);
  const calls = bridge.calls.filter(([c]) => c === "measure");
  assert.equal(calls.length, 2);
  assert.ok(store.get().measurements[0].result?.ok);
}

// 7. 工具列純函式 / FFT 防抖與過期
{
  const { bridge, store, sum, channels } = await setup();
  store.set({ file: sum, channels, selected: "CHAN1", cursors: { x1: 0.003, x2: 0.001, y1: null, y2: null } }, "program");
  store.updateChannel("CHAN1", { time_offset: 0.0001 }, "user");
  assert.deepEqual(csvRange(store.get()), [0.003, 0.001], "CSV 範圍：游標顯示時間直接切原始軸，不扣 dx");
  const p = { on: true, source: "CHAN1", window: "Hanning", unit: "dBm", imp: 2, manualR: 50, peakCount: 5, peakLevel: -40, peakSort: "Decreasing Magnitude" };
  assert.equal(fftParams(store.get(), p, CATALOG).r_ohm, 100);
  assert.equal(fftParams(store.get(), { ...p, imp: 4, manualR: 0 }, CATALOG), null, "手動阻抗需 > 0");
  assert.equal(fftParams(store.get(), { ...p, imp: 4, manualR: 75 }, CATALOG).r_ohm, 75);
  store.set({ rangeMode: "cursors" }, "user");
  assert.deepEqual(fftParams(store.get(), p, CATALOG).range, [0.003, 0.001]);
  const f = createFft({ store, bridge }, CATALOG, p, { delay: 10 });
  for (let i = 0; i < 4; i++) f.schedule();
  await sleep(80);
  assert.equal(bridge.calls.filter(([c]) => c === "fft").length, 1, "FFT 防抖");
  const fr = store.get().fftResult;
  assert.ok(fr.spectrum_id && fr.peak_level === -40, "結果帶 peak_level 供 RF");
  const rec = channelRecord({ name: "F1", unit: "V", derived: true, points: 3, t0: 0, t1: 1, vmin: null, vmax: null, gen: 1 }, 7, CATALOG.channel_colors, scales);
  assert.deepEqual([rec.scale, rec.position, rec.color], [1, 0, CATALOG.channel_colors[1]]);
}

// 8. chanbar 純函式
{
  const ch = { vmin: 0, vmax: 2, scale: 0.5, position: -2, unit: "V" };
  const r = scaleChange(ch, 0.2, scales);
  assert.equal(r.scale, 0.2); assert.ok(Math.abs(r.position - -5) < 1e-9);
  assert.deepEqual(scaleChange({ ...ch, vmin: null }, 0.2, scales), { scale: 0.2, position: -5 });
  assert.equal(signature([{ name: "A", unit: "V", derived: false }]), "A|V|0");
}

// 9. 修正：前端自產失敗列（通道已刪）視為失敗且可匯出；關檔呼叫 close_waveform；取消 FFT 使 job 失效；Phase 清 rfPos；Track Measurements 提示
{
  const { bridge, store, sum, channels } = await setup();
  const m = createMeasure({ store, bridge }, { delay: 5 });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  m.add("Vmax", "CHAN1", true); m.add("Vmin", "CHAN2", true); await sleep(40);
  store.set({ channels: store.get().channels.filter((c) => c.name !== "CHAN2") }, "program"); await sleep(60);
  const list = store.get().measurements, file = store.get().file;
  assert.equal(list[1].result.reason, "來源通道已刪除");
  assert.equal(rowState(list[1], file), "fail", "自產失敗列是失敗而非計算中");
  assert.ok(exportable(list, file), "不鎖匯出");
  assert.equal(list[1].result.revision, list[0].result.revision);
  // 關檔
  const { closeFile } = await import("./toolbar.js");
  const seen = [];
  await closeFile(store, { call: async (m) => { seen.push(m); return null; } });
  assert.deepEqual(seen, ["close_waveform"], "關檔先呼叫後端");
  assert.equal(store.get().file, null);
}
{
  const { bridge, store, sum, channels } = await setup(async (m) => { if (m === "fft") await sleep(60); });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  const p = { on: true, source: "CHAN1", window: "Hanning", unit: "dBm", imp: 0, manualR: 50, peakCount: 5, peakLevel: -40, peakSort: "Decreasing Magnitude" };
  const f = createFft({ store, bridge }, CATALOG, p, { delay: 1 });
  const run = f.run(); await sleep(10);
  p.on = false; f.invalidate(); await run;
  assert.equal(store.get().fftResult, null, "取消後完成的 job 不寫回");
  p.on = true; p.unit = "Phase"; store.set({ rfPos: { x: 1, y: 1 } }, "program");
  await f.run();
  assert.equal(store.get().rfPos, null, "Phase 清 rfPos");
}
{
  const { bridge, store, sum, channels } = await setup();
  const ctl = createController({ store, bridge }, { delay: 5 });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  store.set({ markerMode: "Track Measurements" }, "user"); await sleep(40);
  assert.equal(ctl.readout.kind, "unsupported"); assert.match(ctl.readout.reason, /尚未支援/);
  assert.ok(!bridge.calls.some(([c, q]) => c === "marker_eval" && q.mode === "Track Measurements"), "不靜默送空陣列");
}

// 10. 自動 FFT 失敗不用 modal；換檔重置 FFT 勾選
{
  const { bridge, store, sum, channels } = await setup();
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  const p = { on: true, source: "CHAN1", window: "Hanning", unit: "dBm", imp: 0, manualR: 50, peakCount: 5, peakLevel: -40, peakSort: "Decreasing Magnitude" };
  const errs = []; let resets = 0;
  const bad = { ...bridge, job: async () => { throw Object.assign(new Error("資料含 NaN 或無限大。"), { code: "SCOPE_ERROR" }); } };
  const f = createFft({ store, bridge: bad }, CATALOG, p, { delay: 5, onError: (e, manual) => errs.push(manual), onReset: () => { resets++; } });
  f.schedule(); await sleep(30);
  assert.deepEqual(errs, [false], "自動重跑標記為非手動（toast，不開 modal）");
  assert.equal(store.get().fftResult.ok, false); assert.match(store.get().fftResult.reason, /NaN/, "錯誤文字留在 fftResult 供窗格顯示");
  await f.run(true); assert.deepEqual(errs, [false, true], "手動才標記 manual");
  store.set({ file: { ...sum, gen: sum.gen + 1 } }, "program");
  assert.equal(p.on, false); assert.equal(resets, 1, "換檔重置勾選");
  await sleep(30); assert.equal(errs.length, 2, "換檔後不自動重跑");
  p.on = true; store.set({ file: null }, "program");
  assert.equal(p.on, false); assert.equal(resets, 2, "關檔也重置");
}
// 11. 游標表斜率：傳統／Marker 都保留正負號與來源單位，無效值顯示破折號。
{
  for (const kind of ["legacy", "marker"]) {
    const row = (dx, dy, unit = "V") => cursorRows({ kind, t1: 0, t2: dx, v1: 0, v2: dy, dx, dy, unit, source: "CHAN1" }, F.fmt);
    for (const [dx, dy, want] of [[2, 4, "2 V/s"], [-2, 4, "-2 V/s"], [2, -4, "-2 V/s"], [2, 0, "0 V/s"],
      [0, 4, ""], [null, 4, ""], [undefined, 4, ""], [2, null, ""], [2, undefined, ""],
      [Infinity, 4, ""], [2, Infinity, ""], [NaN, 4, ""], [2, NaN, ""], [1e-308, 1e308, ""]]) {
      const rows = row(dx, dy);
      assert.deepEqual(rows[7], ["ΔY/ΔX", want || "—"]);
      assert.deepEqual(rows[8], ["換算來源", "CHAN1"]);
      assert.equal(rows.length, kind === "marker" ? 10 : 9);
    }
    assert.deepEqual(row(2, 4, "A")[7], ["ΔY/ΔX", "2 A/s"]);
    assert.deepEqual(row(2, 4, "dB")[7], ["ΔY/ΔX", "2 dB/s"]);
  }
  assert.deepEqual(cursorRows(null, F.fmt), []);
}
// 區間隨項目固定並送出；界限值全部統計欄帶前綴，次數保持整數。
{
  const { bridge, store, sum, channels } = await setup();
  const m = createMeasure({ store, bridge }, { delay: 5 });
  store.set({ file: sum, channels, selected: "CHAN1" }, "program");
  m.add("Vavg", "CHAN1", false, "cycles"); m.add("上升時間", "CHAN1", true); await sleep(50);
  const entries = bridge.calls.find(([name]) => name === "measure")[1].entries;
  assert.equal(entries[0].mode, "cycles"); assert.equal(entries[0].rising, false); assert.equal(entries[1].mode, "full");
  const e = store.get().measurements[1], cells = rowCells(e, "ok", "s", F);
  assert.ok(cells.slice(0, 6).every(x => x.startsWith("< "))); assert.equal(cells[6], "9");
}
// 雙來源欄位隨同整批結果送出；來源 2 已刪除則保留失敗列。
{
  const { bridge, store, sum, channels } = await setup(), m = createMeasure({store,bridge,appState:{catalog:CATALOG}},{delay:5});
  store.set({file:sum,channels,selected:"CHAN1"}); m.add("延遲","CHAN1",true,"full","CHAN2",false); await sleep(50);
  assert.equal(bridge.calls.find(([n]) => n === "measure")[1].entries[0].rising2,false);
  store.set({channels:channels.slice(0,1)}); await sleep(50);
  assert.equal(store.get().measurements[0].result.reason,"來源通道已刪除");
}
console.log("l5 self-check OK");
