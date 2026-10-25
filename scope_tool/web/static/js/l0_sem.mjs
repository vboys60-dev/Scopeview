// L0 自檢：以 mock 驗證契約公開語義（連線／BUSY／冪等／游標／Marker／量測／FFT／RF／波形包絡／匯出）。
import './mock_current_check.mjs';
import { dualResult } from './mock_measure2.js';
import assert from "node:assert/strict";
import { makeBridge } from "./bridge.js";
import { createMock } from "./mock_backend.js";
import { near, sleep, rej, call } from "./l0_util.mjs";

export async function runSemantics() {
  // ---- 契約行為（mock）----
  {
    const m = createMock({ delay: 2 }), b = makeBridge(m, true), seen = [];
    m.subscribe((e) => seen.push(e));
    const st = await call(b, "get_state", {});
    assert.equal(st.native_dialogs, false); assert.ok(!("config_defaults" in st.catalog)); assert.ok(st.config.screenshot_dir.startsWith("/"));
    await rej(b.call("get_state", { x: 1 }), "BAD_REQUEST"); await rej(b.call("save_config", {}), "BAD_REQUEST"); await rej(b.call("nope"), "NOT_FOUND");
    await rej(b.call("save_config", { patch: { bogus: 1 } }), "BAD_REQUEST");
    assert.equal((await call(b, "save_config", { patch: { points: 5 } })).points, 5);
    assert.equal(await call(b, "pick_folder", { initial: null }), null); await call(b, "pick_waveform_file", { initial: "/x" });
    assert.equal((await call(b, "connect_fake", {})).model, "FAKE-SCOPE");
    await call(b, "search", {});
  await call(b, "add_manual_ip", { ip: "1.2.3.4" }); assert.deepEqual((await call(b, "add_manual_ip", { ip: "5.6.7.8" })).map((x) => x.label), ["1.2.3.4", "5.6.7.8"]); // 整份清單、保留既有

    // connect：先關舊連線；driver 事件早於 job 事件；series_override 由後端回寫；UNSUPPORTED
    seen.length = 0;
    await rej(call(b, "connect", { resource: "UNKNOWN::1", series_override: null }), "UNSUPPORTED");
    assert.equal((await call(b, "connect", { resource: "MOCK::INSTR", series_override: "Infiniium" })).series, "Infiniium");
    assert.equal((await call(b, "get_state", {})).config.series_overrides["DSO-X 3014G"], "Infiniium");
    const iJob = seen.findIndex((e) => e.type === "job" && e.kind === "connect" && e.ok), iDrv = seen.findIndex((e) => e.type === "driver" && e.connected);
    assert.ok(iDrv >= 0 && iDrv < iJob, "driver 事件須早於 connect 的 job 事件");
    await call(b, "capture_info", {}); await call(b, "screenshot", { directory: "/d", name: "n", image_format: "PNG", inverted: false, area: "full" });
    const cap = await call(b, "capture", { directory: "/d", name: "n", channels: ["CHAN1"], points: 100, retrigger: false }); assert.equal(cap.got_points, 100);
    await rej(call(b, "capture", { directory: "/d", name: "n", channels: [], points: 9e9, retrigger: false }), "SCOPE_ERROR");
    assert.equal(await call(b, "disconnect", {}), null); await rej(call(b, "capture_info", {}), "SCOPE_ERROR");
    await call(b, "connect_fake", {});

    // BUSY：同步 ok:false（不走 job 事件）；實際鎖；分析工作不被擋；request_id 規則
    m.setBusy(true); seen.length = 0;
    await rej(b.job("search", {}), "BUSY"); assert.ok(!seen.some((e) => e.type === "job")); assert.equal((await m.rpc("search", {}, "z")).error.code, "BUSY");
    m.setBusy(false); const r0 = await m.rpc("search", {}, "z"); assert.ok(r0.ok && !r0.result.done); // BUSY 未登記
    assert.equal((await m.rpc("search", {}, "z")).result.job, r0.result.job); // 同 ID 回原工作
    await sleep(10); const r1 = await m.rpc("search", {}, "z"); assert.equal(r1.result.done.ok, true); assert.equal(r1.result.done.result[0].resource, "MOCK::INSTR"); // 完成後保留結果
    assert.equal((await m.rpc("connect", { resource: "x" }, "y")).error.code, "BAD_REQUEST"); // 參數錯誤不登記
    const r2 = await m.rpc("connect", { resource: "MOCK::INSTR", series_override: null }, "y"); assert.ok(r2.ok);
    assert.equal((await m.rpc("connect", { resource: "OTHER", series_override: null }, "y")).error.code, "BAD_REQUEST"); // 同 ID 不同參數
    await sleep(10);
    const slow = createMock({ delay: 30 }), bs = makeBridge(slow, true);
    slow.rpc("connect_fake", {}); const p1 = bs.job("search", {}); await sleep(1);
    await rej(bs.job("capture_info", {}), "BUSY"); const op = bs.job("open_waveform", { path: "/a.h5" }); assert.equal((await p1).length, 1); await op; await bs.job("capture_info", {});

    // bridge 冪等：並行與事後重送共用 Promise，不重複執行
    seen.length = 0;
    const pa = b.job("search", {}, { requestId: "same" }), pb = b.job("search", {}, { requestId: "same" }); assert.equal(pa, pb);
    await pa; assert.equal(b.job("search", {}, { requestId: "same" }), pa); await sleep(5); assert.equal(seen.filter((e) => e.type === "job").length, 1);

    // 環形緩衝 500
    for (let i = 0; i < 600; i++) m.emit({ type: "driver", connected: true, model: "m", series: "s" });
    const ev = (await m.rpc("wait_events", { since: 0, timeout: 1 })).result; assert.equal(ev.events.length, 500); assert.equal(ev.events[0].seq, ev.seq - 499);

    // 開檔與游標
    const fs = await call(b, "open_waveform", { path: "/x/a.h5" });
    assert.deepEqual(fs.channels.map((c) => c.name), ["CHAN1", "CHAN2"]); assert.ok(fs.channels[1].t0 > fs.channels[0].t0 && fs.channels[1].points !== fs.channels[0].points); // 各通道時間軸不同
    const g = fs.gen, DX = {};
    let cr = await call(b, "cursor_readout", { t1: 0.5e-3, t2: 0.5e-3, dx: { CHAN2: 0.25e-3 } }); near(cr.y.CHAN2.y1, 0.5, 2e-3); // 扣自己的 dx
    cr = await call(b, "cursor_readout", { t1: -4.9e-3, t2: 0, dx: DX }); assert.equal(cr.y.CHAN2.y1, null); assert.ok(cr.y.CHAN1.y1 !== null); // 超出該通道時間軸
    cr = await call(b, "cursor_readout", { t1: 0.1e-3, t2: 0.2e-3, dx: { CHAN1: 5e-3 } }); near(cr.t1, 0.1e-3, 0.3e-6); // 第一通道吸附，回顯示時間
    assert.equal(cr.index1, Math.round((0.1e-3 - 5e-3 + 5e-3) / 0.5e-6));

    // marker
    const mk = (mode, o = {}) => call(b, "marker_eval", { mode, channel: "CHAN1", x1: 1e-4, x2: 3e-4, y1: 0.2, y2: 0.8, screen_width: 1e-3, measurements: null, ...o });
    let mr = await mk("Manual X only"); assert.deepEqual(mr.position, { x1: 1e-4, x2: 3e-4, y1: null, y2: null }); near(mr.delta_x, 2e-4); near(mr.inverse_delta_x, 5000, 1e-6); assert.equal(mr.delta_y, null);
    mr = await mk("Manual Y only"); assert.equal(mr.position.x1, null); near(mr.delta_y, 0.6);
    mr = await mk("Manual X and Y"); near(mr.delta_y, 0.6); near(mr.delta_x, 2e-4);
    mr = await mk("Track Waveforms"); assert.equal(mr.position.y1, 1); assert.equal(mr.points.length, 2); near(mr.position.x1, 1e-4, 0.3e-6);
    mr = await mk("Track Measurements", { measurements: [[0, 1, "a"], [1e-3, -1, "b"]] }); assert.ok(mr.read_only && mr.points.length === 2); near(mr.delta_y, -2);
    mr = await mk("Track Measurements"); assert.equal(mr.available, false); assert.ok(mr.reason);
    await rej(mk("Track RF"), "BAD_REQUEST"); await rej(b.call("marker_eval", { mode: null, channel: null, x1: 0, x2: 1, y1: null, y2: null, screen_width: null, measurements: null }), "BAD_REQUEST"); await rej(mk("???"), "BAD_REQUEST");

    // measure：range 排序、含兩端、先扣 dx、空區間與 NaN 缺口
    const me = (name, ch, range, dx = DX) => call(b, "measure", { entries: [{ channel: ch, name, rising: true }], range, dx, threshold: "10/50/90 %" });
    let r = await me("Vmax", "CHAN1", [-1e-3, 1e-3]); assert.equal(r.results[0].stats.current, 1); assert.equal(r.results[0].gen, g); assert.equal(r.results[0].revision, r.revision);
    assert.equal((await me("Vmax", "CHAN1", [1e-3, -1e-3])).results[0].stats.current, 1); // 反序
    r = await me("Vmax", "CHAN1", [5, 6]); assert.ok(!r.results[0].ok && r.results[0].stats === null && r.results[0].reason); // 空區間：具名失敗
    r = await me("Vmax", "CHAN2", [9.9999, 10.0001], { CHAN2: 10 }); assert.ok(r.results[0].ok); near(r.results[0].stats.current, 0.5 * Math.sin(2 * Math.PI * 1000 * 1e-4), 1e-3);
    assert.ok(!(await me("Vmax", "CHAN2", [9.9999, 10.0001])).results[0].ok); // 沒扣 dx 時該區間無資料
    assert.equal((await me("Vmax", "CHAN2", [-1.0002e-3, -0.9910e-3])).results[0].reason, "所選範圍內沒有資料"); // 區間只有 NaN
    assert.ok(!(await me("頻譜不存在", "CHAN1", null)).results[0].ok);
    const bounded = await me("上升時間", "CHAN1", null); assert.equal(bounded.results[0].bound, "<");
    const down = await me("下降斜率", "CHAN1", null); assert.equal(down.results[0].bound, "<"); assert.ok(down.results[0].stats.current < 0);
    const modeMe = (name, mode, range = null) => call(b, "measure", { entries: [{ channel: "CHAN1", name, rising: true, mode }], range, dx: DX, threshold: "10/50/90 %" });
    for (const name of ["Vavg", "Vrms(DC)", "Vrms(AC)"]) {
      assert.ok((await modeMe(name, "full")).results[0].ok);
      assert.ok((await modeMe(name, "cycles")).results[0].ok);
      assert.match((await modeMe(name, "cycles", [0, 1e-4])).results[0].reason, /No edges/);
    }
    await rej(b.job("measure", { entries: [{ channel: "CHAN1", name: "Vavg", rising: true, mode: null }], range: null, dx: DX, threshold: "10/50/90 %" }), "BAD_REQUEST");
    const up = await me("上升斜率", "CHAN1", null); assert.equal(up.results[0].bound, ">");
    const pos = await me("工作週期", "CHAN1", null), neg = await me("-工作週期", "CHAN1", null);
    near(pos.results[0].stats.current + neg.results[0].stats.current, 100);
    const dual = (name, extra = {}, range = [0, .003], dx = {}) => call(b, "measure", {entries:[{channel:"CHAN1", channel2:"CHAN2", name, rising:true, ...extra}],range,dx,threshold:"10/50/90 %"});
    for (const [name, unit] of [["延遲","s"],["相位","°"],["電壓比","dB"]]) {
      const r = await dual(name); assert.equal(r.results[0].channel2,"CHAN2"); assert.equal(r.results[0].unit,unit); assert.ok(r.results[0].ok);
    }
    const d0 = (await dual("延遲")).results[0], d1 = (await dual("延遲",{},[0,.003],{CHAN2:.00002})).results[0];
    near(d1.stats.current-d0.stats.current,.00002,1e-10);
    assert.equal((await dual("延遲",{channel2:"deleted"})).results[0].reason,"來源通道已刪除");
    assert.match((await dual("延遲",{},[10,11])).results[0].reason,/沒有資料/);
    for (const extra of [{channel2:null}, {rising2:null}]) await rej(b.job("measure",{entries:[{channel:"CHAN1",channel2:"CHAN2",name:"延遲",rising:true,...extra}],range:null,dx:{},threshold:"10/50/90 %"}),"BAD_REQUEST");
    await rej(b.job("measure",{entries:[{channel:"CHAN1",name:"延遲",rising:true}],range:null,dx:{},threshold:"10/50/90 %"}),"BAD_REQUEST");
    // mock 與後端一致：先驗通道，再驗空範圍；配對只採顯示時間交集內事件。
    assert.equal((await dual("延遲",{channel2:"deleted"},[10,11])).results[0].reason,"來源通道已刪除");
    assert.equal((await dual("延遲",{},[10,11])).results[0].reason,"來源 1：所選範圍內沒有資料");
    const t = Float64Array.from({length:4000},(_,i) => i/1000);
    const v = Float64Array.from(t,(_,i) => i%200 < 100 ? 0 : 1);
    const data = {A:{t,v}, B:{t:t.slice(1000,2000).map(x => x+.05),v:v.slice(1000,2000)}};
    for (const [name,count,value] of [["延遲",5,.05],["相位",4,90]]) {
      const entry = {channel:"A",channel2:"B",name,rising:true};
      const result = dualResult(entry,data,null,{},[10,50,90],{});
      assert.equal(result.stats.count,count); near(result.stats.mean,value,1e-10);
      const apart = dualResult(entry,data,null,{B:10},[10,50,90],{});
      assert.equal(apart.reason,"兩來源時間範圍沒有重疊");
    }
    const full = await me("Vp-p", "CHAN1", null); near(full.results[0].stats.current, 2);

    // math
    await rej(call(b, "math", { op: "加", a: "CHAN1", b: null, param: 0 }), "BAD_REQUEST"); await rej(call(b, "math", { op: "低通", a: "CHAN1", b: null, param: 0 }), "BAD_REQUEST");
    const f1 = await call(b, "math", { op: "加", a: "CHAN1", b: "CHAN2", param: 0 }); assert.ok(f1.name === "F1" && f1.derived && f1.gen === g);
    assert.equal(await call(b, "remove_channel", { name: "F1" }), null); await rej(call(b, "remove_channel", { name: "CHAN1" }), "SCOPE_ERROR");
    const f2 = await call(b, "math", { op: "平方", a: "CHAN1", b: null, param: 0 }); assert.equal(f2.name, "F2"); assert.equal(f2.unit, "V²");

    // fft
    const ff = (o = {}) => call(b, "fft", { source: "CHAN1", range: null, dx: DX, window: "Hanning", unit: "dBm", r_ohm: 50, peak_count: 5, peak_level: -100, peak_sort: "Decreasing Magnitude", ...o });
    let fr = await ff(); assert.ok(fr.ok && fr.peaks.length === 5 && fr.gen === g && fr.peaks[0].x === 1000);
    assert.equal((await ff({ peak_level: -40 })).peaks.length, 4); assert.equal((await ff({ peak_level: -40, peak_sort: "Decreasing Frequency" })).peaks[0].x, 7000);
    const ph = await ff({ unit: "Phase" }); assert.ok(ph.unit === "°" && ph.peaks.length === 0 && ph.ok);
    assert.equal((await ff({ source: "F2" })).unit, "V² rms");
    const ef = await ff({ range: [5, 6] }); assert.ok(!ef.ok && ef.reason && ef.spectrum_id === null && ef.peaks.length === 0);
    assert.ok((await ff({ range: [1e-3, -1e-3] })).ok);
    await rej(ff({ r_ohm: 0 }), "BAD_REQUEST"); await rej(ff({ unit: "W" }), "BAD_REQUEST");
    fr = await ff({ peak_level: -100 });
    const sp = await b.fetchSpectrum({ id: fr.spectrum_id, f0: 0, f1: 1e6, px: 100 });
    assert.equal(sp.mode, 1); assert.ok(sp.n <= 202 && sp.x[0] === 0); assert.ok(Math.max(...sp.hi) > -11); // 峰沒被抽掉
    const spl = await b.fetchSpectrum({ id: fr.spectrum_id, f0: 100, f1: 1e6, px: 100, log: true });
    assert.ok(spl.n <= 202 && spl.x.every((x) => x > 0) && spl.x.every((x, i) => i === 0 || x > spl.x[i - 1]));
    const spz = await b.fetchSpectrum({ id: fr.spectrum_id, f0: 900, f1: 1100, px: 100 }); assert.equal(spz.mode, 0); assert.ok(spz.x.includes(1000));
    await rej(b.fetchSpectrum({ id: fr.spectrum_id, f0: 0, f1: 1e6, px: 100, log: true }), "BAD_REQUEST"); await rej(b.fetchSpectrum({ id: "s0", f0: 0, f1: 1, px: 10 }), "STALE");
    // fft_track_rf
    const rf = (x, direction, level = -100, id = fr.spectrum_id) => call(b, "fft_track_rf", { spectrum_id: id, x, direction, level });
    assert.equal((await rf(0, 1)).x, 1000); assert.equal((await rf(1000, 1)).x, 3000); assert.equal((await rf(3000, -1)).x, 1000);
    assert.equal((await rf(1040, 0)).x, 1000); assert.equal((await rf(1050, 0)).x, 1100); // 同距取右
    let rr = await rf(1000, -1); assert.deepEqual([rr.available, rr.x, rr.y], [false, 1000, -10]); assert.ok(rr.reason);
    rr = await rf(7000, 1, -40); assert.deepEqual([rr.available, rr.x], [false, 7000]); assert.equal(rr.y, -38.5);
    await rej(rf(0, 2), "BAD_REQUEST"); await rej(rf(0, 1, -100, "s0"), "STALE");

    // /wave
    const wv = (o = {}) => b.fetchWave({ ch: "CHAN1", t0: -5e-3, t1: 5e-3, px: 500, gen: g, ...o });
    let w = await wv(); assert.ok(w.mode === 1 && w.n <= 502 && w.lo.every((v, i) => v <= w.hi[i]));
    w = await wv({ ch: "CHAN2", px: 100 }); assert.ok(w.x[0] < -4.0e-3 && w.x[0] > -4.1e-3); // x 為來源時間（CHAN2 自己的起點）
    assert.ok(w.lo.some(Number.isNaN) && w.lo.every((v, i) => Number.isNaN(v) === Number.isNaN(w.hi[i])) && ![...w.lo, ...w.hi].some((v) => !Number.isFinite(v) && !Number.isNaN(v))); // NaN 桶：lo／hi 皆 NaN，無 ±Infinity
    w = await wv({ t0: 0, t1: 1e-5, px: 500 }); assert.equal(w.mode, 0); assert.ok(w.n <= 1002 && w.x[0] <= 0 && w.x[w.n - 1] >= 1e-5);
    await rej(wv({ gen: g + 1 }), "STALE"); await rej(wv({ px: 0 }), "BAD_REQUEST"); await rej(wv({ px: 20000 }), "BAD_REQUEST"); await rej(wv({ ch: "ZZ" }), "BAD_REQUEST");

    // 匯出
    const exm = (o) => call(b, "export_measurements", { rows: full.results, gen: full.gen, revision: full.revision, directory: null, ...o });
    assert.ok((await exm({})).path); await me("Vmax", "CHAN1", null); await rej(exm({}), "STALE"); // 舊 revision 被拒
    assert.ok((await call(b, "export_csv", { range: null, max_points: null, directory: null })).path);
    await rej(call(b, "export_csv", { range: [0, 1], max_points: 0, directory: "/d" }), "BAD_REQUEST");
    const ef2 = await ff({ range: [5, 6] }); assert.ok(!ef2.ok); await rej(b.fetchSpectrum({ id: fr.spectrum_id, f0: 0, f1: 1e6, px: 100 }), "STALE"); await rej(rf(0, 0), "STALE"); // 失敗清除舊頻譜
  const idA = (await ff()).spectrum_id; await call(b, "open_waveform", { path: "/x/c.h5" }); assert.notEqual((await ff()).spectrum_id, idA); // 換檔不重用 id
  assert.equal(await call(b, "close_waveform", {}), null); await rej(wv(), "STALE"); await rej(call(b, "cursor_readout", { t1: 0, t2: 0, dx: DX }), "SCOPE_ERROR");
  await call(b, "open_waveform", { path: "/x/b.h5" }); await rej(exm({}), "STALE"); await rej(wv(), "STALE"); // 開新檔後舊世代全失效
  }
}
