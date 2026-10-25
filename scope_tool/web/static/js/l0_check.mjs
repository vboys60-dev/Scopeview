// L0 自檢：node --experimental-default-type=module scope_tool/web/static/js/l0_check.mjs
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import { createStore } from "./analysis/store.js";
import * as S from "./analysis/scales.js";
import { fmt, parseSI } from "./fmt.js";
import bridgeHttp, { makeBridge, decodeWave, BridgeError } from "./bridge.js";
import { createMock, encodeWave, CATALOG } from "./mock_backend.js";

import { rd, contract, near, sleep, rej, tc } from "./l0_util.mjs";
import { runSemantics } from "./l0_sem.mjs";

// ---- 契約本身 ----
{
  assert.deepEqual(CATALOG, contract.catalog); // mock 的 CATALOG == 契約 catalog
  const c = contract.catalog;
  assert.ok(!("config_defaults" in c) && !c.fft_units.includes("W") && !c.marker_modes.includes("Track RF") && c.marker_modes.length === 5);
  assert.equal(c.channel_colors.length, 6); assert.equal(c.fft_impedances.length, 5); assert.deepEqual(c.fft_impedances.map((x) => x[1]), [50, 50, 100, 25, null]);
  assert.deepEqual(Object.keys(contract.intents).sort(), ["channel.scale_intent", "channel.shift_intent", "cursor.intent", "rf.intent", "viewport.intent"]);
  for (const i of Object.values(contract.intents)) assert.ok(i.mode === "absolute" && i.handler && i.payload);
  for (const code of ["REMOTE_DESKTOP", "BUSY", "SCOPE_ERROR", "UNSUPPORTED", "STALE", "BAD_REQUEST", "UNEXPECTED", "FORBIDDEN", "NOT_FOUND", "NETWORK", "BAD_BINARY"]) assert.ok(contract.errors[code], code);
  const m = createMock();
  const own = Object.entries(contract.methods);
  assert.deepEqual(own.filter(([, v]) => v.owner !== "server").map(([k]) => k).sort(), m.methods.filter((k) => k !== "wait_events").sort()); // owner∈{Api,Analysis} == mock
  assert.equal(contract.methods.wait_events.owner, "server");
  for (const [k, v] of own) {
    assert.ok(["Api", "Analysis", "server"].includes(v.owner) && typeof v.returns === "string", k);
    assert.deepEqual(v.params.map((p) => p.name).sort(), m.keys[k].split(" ").filter(Boolean).sort(), `${k} 參數名`);
    for (const p of v.params) assert.ok(p.required === true && typeof p.nullable === "boolean" && typeof p.type === "string", `${k}.${p.name}`);
  }
  for (const k of ["connect", "disconnect", "search", "capture_info", "screenshot", "capture"]) assert.ok(contract.methods[k].lock && contract.methods[k].job, k);
  assert.equal(contract.events._ring, 500);
  for (const f of readdirSync(new URL(".", import.meta.url))) if (/\.(js|mjs)$/.test(f)) {
    const src = rd(f); assert.ok(src.split("\n").length <= 300, `${f} 超過 300 行`); assert.ok(!/https?:\/\//.test(src) || f === "l0_check.mjs", `${f} 含外部 URL`);
  }
}

// 可選欄位省略／null 與存在時的型別、列舉值仍要驗證。
{
  const entry = { channel: "CH1", name: "Vavg", rising: true };
  tc(entry, "MeasureEntry"); tc({ ...entry, mode: "cycles" }, "MeasureEntry");
  for (const mode of [null, 1, "bad"]) assert.throws(() => tc({ ...entry, mode }, "MeasureEntry"));
  const row = { channel: "CH1", name: "上升時間", unit: "s", ok: false, stats: null, reason: "x", gen: 1, revision: 1 };
  for (const bound of [null, "<", ">"]) tc({ ...row, bound }, "MeasureResult");
  tc(row, "MeasureResult"); tc({...row, channel2:"CH2"}, "MeasureResult");
  tc({...entry, channel2:"CH2", rising2:false}, "MeasureEntry");
  for (const channel2 of [null, 2]) assert.throws(() => tc({...entry, channel2}, "MeasureEntry"));
  for (const rising2 of [null, 1]) assert.throws(() => tc({...entry, rising2}, "MeasureEntry"));
  assert.deepEqual(CATALOG.measurements.filter(m => m.sources === 2).map(m => m.name), ["延遲", "相位", "電壓比"]);
  for (const bound of [1, true, "bad"]) assert.throws(() => tc({ ...row, bound }, "MeasureResult"));
}

// ---- store ----
{
  const st = createStore(), seen = [];
  st.on(["view"], (_s, keys, origin) => seen.push([keys.join(), origin]));
  st.set({ view: { t0: 0, t1: 2 } }, "user");
  st.set({ markerMode: "x" }); // 不在訂閱鍵內
  assert.deepEqual(seen, [["view", "user"]]);
  st.set({ view: st.get().view }, "snap"); assert.equal(seen.length, 1); // 同一個物件不通知
  st.set({ view: { t0: 0, t1: 2 } }, "user"); assert.equal(seen.length, 1); // 同值新物件不通知（plain object 淺比較）
  st.set({ view: { t0: 0, t1: 3 } }, "user"); assert.equal(seen.length, 2);
  assert.throws(() => st.set({ view: 1 }, "bogus"));
  assert.equal(st.get().rangeMode, "all"); assert.equal(st.get().rfPos, null);
  st.set({ rfPos: { x: 1000.123456789, y: -10 } }); st.set({ rfPos: { x: 1000.123456789, y: -10 } }, "user");
  const mk = (n) => ({ name: n, color: "#fff", unit: "V", visible: true, scale: 1, position: 0, time_offset: 0, vmin: -1, vmax: 1, derived: false });
  const chSeen = [];
  st.on(["channels", "selected"], (_s, keys) => chSeen.push(keys.join()));
  st.setChannels(["CHAN1", "F1", "F2", "F3"].map(mk));
  assert.deepEqual(chSeen, ["channels,selected"]); // 一次 set、一次通知
  assert.equal(st.get().selected, "CHAN1");
  st.set({ selected: "F2" });
  st.setChannels(["CHAN1", "F2", "F3"].map(mk)); assert.equal(st.get().selected, "F2");
  st.removeChannel("F2"); assert.equal(st.get().selected, "F3");
  st.updateChannel("F3", { scale: 0.5, time_offset: 1e-3 }, "user"); assert.equal(st.get().channels[1].time_offset, 1e-3);
  st.removeChannel("CHAN1"); st.removeChannel("F3"); assert.equal(st.get().selected, null);
  let got = null; const off = st.onCommand("x", (p) => { got = p; });
  st.command("x", 7); assert.equal(got, 7); off(); st.command("x", 8); assert.equal(got, 7);
}

// ---- scales ----
{
  assert.deepEqual(S.autoScale(-1, 3, "V"), [0.5, -2]); assert.deepEqual(S.autoScale(0, 0, "V"), [1, 0]);
  assert.equal(S.autoScale(-100, 100, "V")[0], 10); assert.equal(S.autoScale(0, 8e6, "V/s")[0], 1e6);
  assert.ok(S.stepScale(500e-6, "V", true) === 2e-3 && S.stepScale(500e-6, "V", false) === 500e-6);
  assert.ok(S.stepScale(10, "V", true) === 10 && S.stepScale(0.1, "V", false) === 50e-3);
  assert.equal(S.stepScale(1e3, "V/s", true), 2e3);
  const [pos, ok] = S.rescale(0, 2, 0.5, -2, 0.2); assert.ok(ok); near(pos, -5);
  assert.equal(S.rescale(0, 2, 0.5, -2, 0.1)[1], false);
  assert.equal(S.V_TABLE.length, 13); assert.deepEqual(S.valueRange([NaN, 1, -2, Infinity]), [-2, 1]); assert.deepEqual(S.valueRange([NaN]), [0, 0]);
  assert.deepEqual(CATALOG.v_table, S.V_TABLE);
}

// ---- fmt（對齊 Qt：單位 ""／%／dB* 不加前綴，V²、° 照 siFormat 加前綴）----
{
  assert.equal(fmt(1.5e-6, "s"), "1.5 µs"); assert.equal(fmt(1.5e-6, "s").charCodeAt(4), 0xb5);
  assert.equal(fmt(-0.02, "dBm"), "-0.02 dBm"); assert.equal(fmt(1000, "Hz"), "1 kHz"); assert.equal(fmt(0.9999999, "V"), "1 V");
  assert.equal(fmt(500e-6, "V/格"), "500 µV/格"); assert.equal(fmt(null, "V"), "—");
  assert.equal(fmt(0.5, "V²"), "500 mV²"); assert.equal(fmt(1500, ""), "1500"); assert.equal(fmt(0.0123, "%"), "0.0123 %"); assert.equal(fmt(2500, "dBµV"), "2500 dBµV");
  near(parseSI("200u"), 2e-4, 1e-18); near(parseSI("1.5 ms"), 1.5e-3, 1e-18); near(parseSI("10k"), 1e4); near(parseSI("1e-3"), 1e-3, 1e-18);
  near(parseSI("2 mV/格"), 2e-3, 1e-18); near(parseSI("500 µV/格"), 5e-4, 1e-18); near(parseSI("500 μV"), 5e-4, 1e-18); near(parseSI("5 V/格"), 5);
  assert.ok(Number.isNaN(parseSI("abc")));
}

// ---- 二進位解碼 ----
{
  const n = 3, buf = new ArrayBuffer(16 + 16 * n), dv = new DataView(buf);
  dv.setUint32(0, n, true); dv.setUint32(4, 1, true);
  [0.5, 1.5, 1e-9].forEach((x, i) => dv.setFloat64(16 + 8 * i, x, true));
  [-1, -2, -3].forEach((x, i) => dv.setFloat32(16 + 8 * n + 4 * i, x, true));
  [1, 2, 3].forEach((x, i) => dv.setFloat32(16 + 12 * n + 4 * i, x, true));
  const w = decodeWave(buf);
  assert.deepEqual([...w.x], [0.5, 1.5, 1e-9]); assert.deepEqual([...w.lo], [-1, -2, -3]); assert.deepEqual([...w.hi], [1, 2, 3]);
  assert.equal(w.x.byteOffset, 16); assert.equal(w.lo.byteOffset, 16 + 8 * n); assert.equal(w.hi.byteOffset, 16 + 12 * n);
  assert.throws(() => decodeWave(buf.slice(0, 20)), BridgeError);
  const bad1 = buf.slice(0); new DataView(bad1).setUint32(4, 2, true); assert.throws(() => decodeWave(bad1), (e) => e.code === "BAD_BINARY");
  const bad2 = buf.slice(0); new DataView(bad2).setUint32(12, 1, true); assert.throws(() => decodeWave(bad2), (e) => e.code === "BAD_BINARY");
  assert.deepEqual([...decodeWave(encodeWave(Float64Array.of(1, 2), Float32Array.of(3, 4), Float32Array.of(5, 6), 0)).hi], [5, 6]);
}

// ---- HTTP bridge：非 200 一律轉 BridgeError（stub fetch）----
{
  let mode = "ok";
  const res = (status, body, json = true) => ({ ok: status === 200, status, json: async () => { if (!json) throw new SyntaxError("not json"); return body; }, arrayBuffer: async () => body });
  globalThis.fetch = (url) => {
    if (url.includes("get_state")) return Promise.resolve(res(200, { ok: true, result: { seq: 0 } }));
    if (url.includes("wait_events")) return new Promise(() => {});
    if (mode === "net") return Promise.reject(new TypeError("fail"));
    if (mode === "500") return Promise.resolve(res(500, "<html>", false));
    if (mode === "stale") return Promise.resolve(res(409, { ok: false, error: { code: "STALE", message: "世代不符", retryable: false } }));
    if (mode === "403" || mode === "404") return Promise.resolve(res(+mode, "x", false));
    if (mode === "rpcText") return Promise.resolve(res(200, "x", false));
    if (mode === "badmode") { const b = encodeWave(Float64Array.of(1), Float32Array.of(1), Float32Array.of(1), 0); new DataView(b).setUint32(4, 9, true); return Promise.resolve(res(200, b)); }
    return Promise.resolve(res(200, encodeWave(Float64Array.of(1), Float32Array.of(2), Float32Array.of(2), 0)));
  };
  const q = { ch: "CHAN1", t0: 0, t1: 1, px: 10, gen: 1 };
  assert.equal((await bridgeHttp.fetchWave(q)).n, 1);
  for (const [m, code] of [["500", "UNEXPECTED"], ["stale", "STALE"], ["403", "FORBIDDEN"], ["404", "NOT_FOUND"], ["net", "NETWORK"], ["badmode", "BAD_BINARY"]]) {
    mode = m; const e = await rej(bridgeHttp.fetchWave(q), code); assert.ok(e instanceof BridgeError);
  }
  mode = "rpcText"; await rej(bridgeHttp.call("save_config", { patch: {} }), "UNEXPECTED");
  mode = "500"; await rej(bridgeHttp.call("save_config", { patch: {} }), "UNEXPECTED");
  delete globalThis.fetch;
}

// ---- 事件：亂序、重複、斷層、listener 例外、早到暫存超限（fake transport）----
{
  const fake = () => { const t = { handler: null, q: [], delay: 0, async rpc(m) { if (m === "get_state") return { ok: true, result: { seq: 10 } }; if (t.delay) { const j = t.q.shift(); await sleep(t.delay); return { ok: true, result: { job: j } }; } return { ok: true, result: { job: t.q.shift() } }; }, subscribe(h, since) { t.handler = h; t.since = since; }, binary() {}, url() {} }; return t; };
  const t = fake(), b = makeBridge(t, true, { gapMs: 30, earlyMax: 2 });
  const ce = console.error; console.error = () => {}; // 預期會印壞 listener 的例外
  await b.call("get_state"); assert.equal(t.since, 10); // 從目前 seq 起收
  const log = []; b.on("driver", () => { throw new Error("壞 listener"); }); b.on("driver", (e) => log.push(e.seq));
  const jev = (seq, id, ok = true) => ({ seq, type: "job", id, kind: "x", ok, result: id, error: { code: "SCOPE_ERROR", message: "壞", retryable: false } });
  t.q.push("ja"); const pa = b.job("x", {});
  await sleep(1);
  t.handler(jev(12, "ja")); t.handler({ seq: 11, type: "driver", connected: true, model: "m", series: "s" }); // 亂序
  t.handler({ seq: 11, type: "driver" }); t.handler({ seq: 3, type: "driver" }); // 重複、過舊
  assert.equal(await pa, "ja"); assert.deepEqual(log, [11]);
  // 斷層：13 缺，14 到；等待中的 jb 以 NETWORK 失敗，jc 的事件在 14 → 仍送達
  t.q.push("jb", "jc"); const pb = b.job("x", {}); const pc = b.job("x", {}); await sleep(1);
  const desync = []; b.on("desync", (e) => desync.push(e));
  t.handler(jev(14, "jc"));
  const eb = await rej(pb, "NETWORK"); assert.ok(eb.retryable && /重新整理/.test(eb.message));
  assert.equal(await pc, "jc"); assert.equal(desync.length, 1);
  // 早到暫存超限：ja1 被擠出 → job() 明確失敗；ja3 仍可取得
  ["e1", "e2", "e3"].forEach((id, i) => t.handler(jev(15 + i, id)));
  t.q.push("e1"); await rej(b.job("x", {}), "NETWORK"); t.q.push("e3"); assert.equal(await b.job("x", {}), "e3");
  // RPC 期間發生 desync（回應延遲）：RPC 回來後不可永遠等待
  t.delay = 80; t.q.push("late1"); const pl = b.job("x", {}); await sleep(5);
  t.handler(jev(20, "zz")); await sleep(50); // 缺 18、19 → desync
  await rej(Promise.race([pl, sleep(300).then(() => { throw Object.assign(new Error("hang"), { code: "HANG" }); })]), "NETWORK");
  t.delay = 0; t.q.push("late2"); const pl2 = b.job("x", {}); await sleep(1); t.handler(jev(21, "late2")); assert.equal(await pl2, "late2"); // desync 後恢復正常
  console.error = ce;
}

await runSemantics();

console.log("l0 self-check OK");
process.exit(0);
