// 瀏覽器內的假後端：公開語義盡量對齊真後端（docs/web-api契約.md）；方法名與參數名必須與 api_contract.json 一致（l0_check.mjs 驗證）。
// 資料：CHAN1＝1 kHz 方波（20000 點）、CHAN2＝1 kHz 正弦（16000 點、起點不同、中間有 NaN 缺口）。不得在各頁自行發明假 API。
import { BridgeError } from "./bridge.js";
import { CATALOG } from "./mock_catalog.js";
import { encodeWave, envelope, span, nearest, makeFile, makeSpectrum, peakBins } from "./mock_dsp.js";
import { singleResult } from "./mock_measure.js";
import { isDual, dualResult } from "./mock_measure2.js";
import { makeDecode } from "./mock_decode.js";
export { CATALOG, encodeWave };

// 每個方法的參數名（body 必須帶齊、不得多帶）；與契約 params 的名稱一致，由 l0_check 比對。
const KEYS = {
  decode: "protocol channels thresholds options", decode_frames: "decode_id", decode_bits: "decode_id t0 t1", export_decode: "decode_id directory",
  get_state: "", save_config: "patch", pick_folder: "initial", pick_waveform_file: "initial", search: "", add_manual_ip: "ip",
  connect: "resource series_override", connect_fake: "", disconnect: "", capture_info: "",
  screenshot: "directory name image_format inverted area", capture: "directory name channels points retrigger",
  add_waveform: "path slot channels", remove_slot: "slot", open_waveform: "path", close_waveform: "", cursor_readout: "t1 t2 dx", marker_eval: "mode channel x1 x2 y1 y2 screen_width measurements",
  measure: "entries range dx threshold", math: "op a b param", remove_channel: "name",
  fft: "source range dx window unit r_ohm peak_count peak_level peak_sort rbw vbw", fft_track_rf: "spectrum_id x direction level",
  export_csv: "range max_points directory", export_measurements: "rows gen revision directory", export_report: "html directory", wait_events: "since timeout",
};
const err = (code, msg, retry = false) => new BridgeError(code, msg, retry);
const fail = (m) => { throw err("SCOPE_ERROR", m); };
const bad = (m) => { throw err("BAD_REQUEST", m); };
const num = (v) => (Number.isFinite(v) ? v : null);
const NS = "http:/" + "/www.w3.org/2000/svg"; // SVG 命名空間（非網路請求；拆開以通過「無外部 URL」grep）
const toErr = (e) => ({ code: e.code ?? "UNEXPECTED", message: e.code ? e.message : `未預期錯誤：${e.message}`, retryable: !!e.retryable });

/** 建立 mock 傳輸。opts：eventFirst＝job 事件比 RPC 回應先到；delay＝工作延遲毫秒；busy＝注入 BUSY（亦可用 setBusy）。 */
export function createMock(opts = {}) {
  let connected = false, model = null, series = null, gen = 0, fnum = 0, specNo = 0, seq = 0, jobNo = 0, rev = 0, shots = 0, instBusy = false, cur = null;
  let busy = !!opts.busy, spec = null, last = null; // spec：最近一次頻譜；last：最近一次量測快照
  let data = {}, slots = {}, decoded = null, staleDecode = null;
  const manual = []; // 手動新增的儀器清單（整份回傳）
  const events = [], subs = new Set(), dedupe = new Map();
  const config = { screenshot_dir: "/mock/Desktop", screenshot_name: "scope", image_format: "PNG", inverted: false, area: "full", waveform_dir: "/mock/Desktop",
    waveform_name: "wave", waveform_format: "CSV", points: 10000, retrigger: false, last_resource: "", manual_resources: [], series_overrides: {} };

  const emit = (ev) => { ev.seq = ++seq; events.push(ev); if (events.length > 500) events.shift(); subs.forEach((f) => f(ev)); };
  const needConn = () => { if (!connected) fail("尚未連線儀器"); };
  const needFile = () => { if (!Object.keys(data).length) fail("尚未開啟波形檔"); };
  const chan = (n) => data[n] ?? bad(`通道不存在：${n}`);
  const drv = () => emit({ type: "driver", connected, model, series });
  /** 工作型：立即回 {job}，結果稍後以 job 事件送出。lock＝要拿儀器鎖（搶不到同步回 BUSY，且不登記 request_id）。 */
  const job = (kind, fn, lock = false) => {
    if (lock) { if (busy || instBusy) throw err("BUSY", "儀器忙碌中，請等目前操作完成", true); instBusy = true; }
    const ent = { id: `j${++jobNo}`, sig: cur.sig, finished: null };
    if (cur.rid) { dedupe.set(cur.rid, ent); if (dedupe.size > 256) dedupe.delete(dedupe.keys().next().value); }
    const run = () => {
      try { ent.finished = { ok: true, result: fn() }; } catch (e) { ent.finished = { ok: false, error: toErr(e) }; }
      if (kind === "decode" && ent.finished.result?.decode_id) { decoded = ent.finished.result; staleDecode = null; }
      if (lock) instBusy = false;
      emit({ type: "job", id: ent.id, kind, ...ent.finished });
    };
    if (opts.eventFirst) run(); else setTimeout(run, opts.delay ?? 5);
    return { job: ent.id };
  };
  const info = (name) => {
    const c = data[name], v = c.v.filter(Number.isFinite);
    return { name, unit: c.unit, derived: !!c.derived, points: c.t.length, t0: c.t[0], t1: c.t[c.t.length - 1],
      vmin: v.length ? v.reduce((a, b) => Math.min(a, b)) : null, vmax: v.length ? v.reduce((a, b) => Math.max(a, b)) : null, gen };
  };
  /** 顯示時間範圍（可反序，兩端含）→ 該通道來源索引 [a,b)；先扣自己的 dx。 */
  const cut = (name, range, dx) => {
    const c = chan(name);
    if (!range) return [0, c.t.length];
    const [lo, hi] = [...range].sort((p, q) => p - q), d = dx[name] ?? 0;
    return span(c.t, lo - d, hi - d);
  };
  const checkRange = (r) => { if (r !== null && !(Array.isArray(r) && r.length === 2 && r.every(Number.isFinite))) bad("range 必須是 [t0,t1] 或 null"); };
  const inCat = (v, list, what) => { if (!list.includes(v)) bad(`未知${what}：${v}`); };

  const FN = { 加: (x, y) => x + y, 減: (x, y) => x - y, 乘: (x, y) => x * y, 除: (x, y) => x / y, 反相: (x) => -x, 絕對值: Math.abs, 平方: (x) => x * x, 開根號: Math.sqrt, log10: Math.log10 };
  const MEAS = { Vmax: (v) => v.reduce((a, b) => Math.max(a, b)), Vmin: (v) => v.reduce((a, b) => Math.min(a, b)),
    "Vp-p": (v) => MEAS.Vmax(v) - MEAS.Vmin(v), Vavg: (v) => v.reduce((a, b) => a + b, 0) / v.length,
    "Vrms(DC)": v => Math.sqrt(MEAS.Vavg(v.map(x => x * x))),
    "Vrms(AC)": v => { const avg = MEAS.Vavg(v); return Math.sqrt(MEAS.Vavg(v.map(x => (x - avg) ** 2))); } };
  const specInfo = (p, extra) => ({ ok: true, reason: null, gen, spectrum_id: null, source: p.source, unit: p.unit, window: p.window, df: 100, rbw: 150, enbw: 150, enbw_bins: 1.5, cg: 0.5,
    segments: 1, vbw: null, n: 20000, effective_n: 32768, r_ohm: p.r_ohm, f_min: 0, f_max: 1e6, peaks: [], ...extra });

  const validSlot = (slot) => { if (!["Mem1", "Mem2", "Mem3", "Mem4"].includes(slot)) bad("槽位必須為 Mem1～Mem4"); };
  const dropSlot = (slot) => {
    const names = slots[slot] ?? [];
    if (last?.results.some(r => names.includes(r.channel) || names.includes(r.channel2))) last = null;
    if (names.includes(spec?.source)) spec = null;
    if (Object.values(decoded?.channels ?? {}).some(n => names.includes(n))) staleDecode = decoded.decode_id;
    names.forEach(n => delete data[n]); delete slots[slot];
  };
  const H = {
    ...makeDecode({ job, needFile, chan, generation: () => gen }),
    get_state: () => ({ config: { ...config }, connected, model, series, catalog: CATALOG, native_dialogs: false, seq }),
    save_config: ({ patch }) => { for (const k of Object.keys(patch ?? {})) if (!(k in config)) bad(`未知設定鍵：${k}`); return Object.assign(config, patch) && { ...config }; },
    pick_folder: () => null,
    pick_waveform_file: () => null,
    search: () => job("search", () => [{ resource: "MOCK::INSTR", source: "visa", label: "模擬儀器 (mock)" }], true),
    add_manual_ip: ({ ip }) => { if (!ip) bad("IP 不可為空"); if (!manual.some((x) => x.label === ip)) manual.push({ resource: `TCPIP0::${ip}::hislip0::INSTR`, source: "manual", label: ip }); return manual.map((x) => ({ ...x })); },
    connect: ({ resource, series_override: so }) => job("connect", () => {
      if (!resource) fail("未指定資源");
      if (/UNKNOWN/.test(resource) && !so) throw err("UNSUPPORTED", "無法判斷儀器系列，請手動指定");
      if (connected) { connected = false; model = series = null; drv(); } // 先關舊連線
      connected = true; model = "DSO-X 3014G"; series = so ?? "InfiniiVision";
      if (so) config.series_overrides[model] = so; // 由後端回寫
      drv(); // driver 事件早於本工作的 job 事件
      return { model, series };
    }, true),
    connect_fake: () => { connected = true; model = "FAKE-SCOPE"; series = "InfiniiVision"; drv(); return { model, series }; },
    disconnect: () => job("disconnect", () => { connected = false; model = series = null; drv(); return null; }, true),
    capture_info: () => job("capture_info", () => { needConn(); return { channels: ["CHAN1", "CHAN2"], max_points: 4000000 }; }, true),
    screenshot: (p) => { inCat(p.image_format, CATALOG.image_formats, "圖片格式"); return job("screenshot", () => { needConn(); return { path: `${p.directory}/${p.name}.${p.image_format.toLowerCase()}`, preview: ++shots }; }, true); },
    capture: (p) => job("capture", () => {
      needConn();
      if (p.points > 4000000) fail("點數超過上限");
      return { path: `${p.directory}/${p.name}.h5`, got_points: p.points, requested: p.points };
    }, true),
    open_waveform: ({ path }) => job("open_waveform", () => {
      data = makeFile(); slots = {}; decoded = null; gen++; fnum = 0; spec = last = null;
      return { path, gen, model: "DSO-X 3014G", series: "InfiniiVision", captured_at: "2026-10-22T12:00:00", info: [["檔名", path.split("/").pop()], ["通道", "CHAN1, CHAN2"]],
        channels: Object.keys(data).map(info), pyramid: false };
    }),
    add_waveform: ({ path, slot, channels }) => {
      validSlot(slot); if (!Object.keys(data).length) fail("請先開啟主檔"); const started = gen;
      return job("add_waveform", () => {
        if (gen !== started) throw err("STALE", "開檔世代已變更");
        const waves = makeFile(), all = Object.keys(waves);
        if (!Array.isArray(channels) || channels.some(n => !all.includes(n))) bad("channels 含檔案裡沒有的通道");
        const selected = all.filter(n => !channels.length || channels.includes(n)), names = selected.map(n => `${slot}.${n}`);
        if (names.some(n => data[n] && !(slots[slot] ?? []).includes(n))) bad("比對檔通道與現有通道撞名");
        dropSlot(slot); selected.forEach((n, i) => { data[names[i]] = waves[n]; }); slots[slot] = names;
        return { slot, path, gen, all, info: [["檔名", path.split("/").pop()], ["通道", names.join(", ")]], channels: names.map(info) };
      });
    },
    remove_slot: ({ slot }) => { validSlot(slot); dropSlot(slot); return null; },
    cursor_readout: ({ t1, t2, dx }) => {
      needFile();
      if (!dx || typeof dx !== "object") bad("dx 必須是物件");
      const first = Object.keys(data)[0], d0 = dx[first] ?? 0, c0 = data[first];
      const i1 = nearest(c0.t, t1 - d0), i2 = nearest(c0.t, t2 - d0), s1 = c0.t[i1] + d0, s2 = c0.t[i2] + d0, y = {};
      for (const [k, c] of Object.entries(data)) {
        const at = (s) => { const x = s - (dx[k] ?? 0); return x < c.t[0] || x > c.t[c.t.length - 1] ? null : num(c.v[nearest(c.t, x)]); };
        y[k] = { y1: at(s1), y2: at(s2) };
      }
      return { t1: s1, t2: s2, index1: i1, index2: i2, y };
    },
    marker_eval: ({ mode, channel, x1, x2, y1, y2, measurements }) => {
      if (mode === "Track RF") bad("Track RF 只走 fft_track_rf");
      inCat(mode, CATALOG.marker_modes, " Marker 模式");
      needFile();
      let p = { x1, x2, y1, y2 }, pts = [], ro = false, avail = true, reason = "";
      if (mode === "Manual X only") p.y1 = p.y2 = null;
      else if (mode === "Manual Y only") p.x1 = p.x2 = null;
      else if (mode === "Track Waveforms") {
        const c = chan(channel);
        for (const k of ["1", "2"]) { const x = p["x" + k]; if (x == null) continue; const i = nearest(c.t, x); p["x" + k] = c.t[i]; p["y" + k] = num(c.v[i]); pts.push([c.t[i], p["y" + k], "X" + k]); }
      } else if (mode === "Track Measurements") {
        ro = true;
        if ((measurements ?? []).length < 2) { avail = false; reason = "尚無量測結果可追蹤"; } else { p = { x1: measurements[0][0], y1: measurements[0][1], x2: measurements[1][0], y2: measurements[1][1] }; pts = measurements; }
      }
      const d = (a, b) => (a != null && b != null ? b - a : null), dxv = d(p.x1, p.x2);
      return { position: p, available: avail, reason, read_only: ro, points: pts, versus: false, delta_x: dxv, inverse_delta_x: dxv ? 1 / dxv : null, delta_y: d(p.y1, p.y2) };
    },
    measure: ({ entries, range, dx, threshold }) => {
      inCat(threshold, Object.keys(CATALOG.thresholds), "閾值"); checkRange(range);
      for (const e of entries) {
        inCat(e.mode === undefined ? "full" : e.mode, ["full", "cycles"], "區間模式");
        if (isDual(e.name) && !("channel2" in e)) bad("雙來源量測必須指定 channel2");
        if ("channel2" in e && typeof e.channel2 !== "string") bad("channel2 必須為字串");
        if ("rising2" in e && typeof e.rising2 !== "boolean") bad("rising2 必須為布林值");
      }
      return job("measure", () => {
        needFile();
        const r = ++rev, results = entries.map((e) => {
          const base = { channel: e.channel, name: e.name, unit: (CATALOG.measurements.find((m) => m.name === e.name)?.unit ?? "").replace("{u}", data[e.channel]?.unit ?? "V"), gen, revision: r };
          if (isDual(e.name)) return dualResult(e, data, range, dx, CATALOG.thresholds[threshold], base);
          if (!data[e.channel]) return { ...base, ok: false, stats: null, reason: "來源通道已刪除" };
          const [a, b] = cut(e.channel, range, dx), t = data[e.channel].t.subarray(a, b);
          let v = data[e.channel].v.subarray(a, b);
          if (!v.some(Number.isFinite)) return { ...base, ok: false, stats: null, reason: "所選範圍內沒有資料" };
          if (v.some(x => !Number.isFinite(x))) return { ...base, ok: false, stats: null, reason: "資料含 NaN 或無限大。" };
          return singleResult(e, t, v, CATALOG.thresholds[threshold], base, MEAS, dx[e.channel] ?? 0);
        });
        last = { gen, revision: r, results };
        return { gen, revision: r, results };
      });
    },
    math: ({ op, a, b, param }) => {
      const all = [...CATALOG.math_ops.binary, ...CATALOG.math_ops.unary, ...CATALOG.math_ops.filters];
      inCat(op, all, "運算");
      if (CATALOG.math_ops.binary.includes(op) && !b) bad("二元運算需要來源 b");
      if (CATALOG.math_ops.filters.includes(op) && !(param > 0)) bad("濾波／平滑參數必須 > 0");
      return job("math", () => {
        needFile();
        if (!FN[op]) fail(`mock 不支援運算：${op}`);
        const ca = chan(a), cb = b ? chan(b) : null, name = `F${++fnum}`;
        const at = (c, t) => (t < c.t[0] || t > c.t[c.t.length - 1] ? NaN : c.v[nearest(c.t, t)]); // 各通道時間軸不同：依時間取樣
        data[name] = { t: ca.t, v: Float64Array.from(ca.v, (x, i) => FN[op](x, cb ? at(cb, ca.t[i]) : undefined)), unit: ["乘", "平方"].includes(op) ? "V²" : ca.unit, derived: true };
        return info(name);
      });
    },
    close_waveform: () => { data = {}; slots = {}; decoded = null; gen++; spec = last = null; return null; },
    remove_channel: ({ name }) => { if (!data[name]?.derived) fail("只能刪除衍生通道"); delete data[name]; return null; },
    fft: (p) => {
      checkRange(p.range); inCat(p.window, Object.keys(CATALOG.fft_windows), "視窗"); inCat(p.unit, CATALOG.fft_units, "單位"); inCat(p.peak_sort, CATALOG.peak_sorts, "峰排序");
      if (!(p.r_ohm > 0) || !Number.isFinite(p.peak_level) || !(p.peak_count >= 1)) bad("r_ohm／peak_level／peak_count 無效");
      for (const v of [p.rbw, p.vbw]) if (v !== null && (!Number.isFinite(v) || v <= 0)) bad("rbw／vbw 必須是有限正數或 null");
      if (p.unit === "Phase" && (p.rbw !== null || p.vbw !== null)) bad("Phase 的 rbw／vbw 必須為 null");
      return job("fft", () => {
        needFile();
        const [a, b] = cut(p.source, p.range, p.dx), c = data[p.source];
        const unit = p.unit === "Phase" ? "°" : c.derived ? `${c.unit} rms` : p.unit;
        if (b - a < 2) { spec = null; return specInfo({ ...p, unit }, { ok: false, reason: "所選範圍內資料不足，無法計算 FFT", df: null, rbw: null, enbw: null, enbw_bins: null, cg: null, segments: null, vbw: null, n: null, effective_n: null, r_ohm: null, f_min: null, f_max: null }); }
        spec = { id: `s${++specNo}`, gen, source: p.source, ...makeSpectrum() };
        const idx = p.unit === "Phase" ? [] : peakBins(spec.y, p.peak_level);
        const sorts = { "Decreasing Magnitude": (i, j) => spec.y[j] - spec.y[i], "Increasing Magnitude": (i, j) => spec.y[i] - spec.y[j], "Increasing Frequency": (i, j) => i - j, "Decreasing Frequency": (i, j) => j - i };
        const peaks = idx.sort(sorts[p.peak_sort]).slice(0, p.peak_count).map((i) => ({ x: spec.x[i], y: spec.y[i] }));
        const rbw = p.rbw === null ? 150 : Math.max(p.rbw, 150);
        return specInfo({ ...p, unit }, { spectrum_id: spec.id, n: b - a, peaks, rbw, enbw: rbw,
          segments: p.rbw === null ? 1 : Math.max(1, Math.round(p.rbw / 150)), vbw: p.vbw !== null && p.vbw < rbw ? p.vbw : null });
      });
    },
    fft_track_rf: ({ spectrum_id: id, x, direction, level }) => {
      if (![-1, 0, 1].includes(direction)) bad("direction 必須是 -1、0 或 1");
      if (!spec || spec.id !== id) throw err("STALE", "頻譜已過期，請重新計算 FFT");
      const i0 = nearest(spec.x, x), at = (i) => ({ x: spec.x[i], y: spec.y[i], available: true, reason: "" });
      if (direction === 0) return at(i0);
      const pk = peakBins(spec.y, level), i = direction > 0 ? pk.find((k) => spec.x[k] > x) : pk.reverse().find((k) => spec.x[k] < x);
      return i === undefined ? { ...at(i0), available: false, reason: "該方向沒有高於門檻的峰" } : at(i);
    },
    export_csv: ({ range, max_points, directory }) => {
      checkRange(range);
      if (max_points !== null && !(max_points >= 1)) bad("max_points 必須 ≥ 1 或 null");
      return job("export_csv", () => { needFile(); return { path: `${directory ?? "/mock/Desktop"}/wave_20261022_120000.csv` }; });
    },
    export_measurements: ({ rows, gen: g, revision, directory }) => {
      if (!Array.isArray(rows)) bad("rows 必須是陣列");
      if (g !== gen || !last || revision !== last.revision) throw err("STALE", "量測結果已過期，請重新量測");
      return { path: `${directory ?? "/mock/Desktop"}/measurements_20261022_120000.csv` };
    },
    export_report: ({ html, directory }) => {
      if (typeof html !== "string" || !html) bad("html 必須是非空字串");
      needFile(); globalThis.__lastReport = html; // 供瀏覽器自檢讀回
      return { path: `${directory ?? "/mock/Desktop"}/demo_報告_20261022_120000.html` };
    },
    wait_events: ({ since }) => ({ seq, events: events.filter((e) => e.seq > since) }),
  };

  const q = (v) => Number(v);
  const px = (v) => { if (!Number.isInteger(q(v)) || q(v) < 1 || q(v) > 16384) bad("px 必須是 1 ~ 16384 的整數"); return q(v); };
  return {
    async rpc(method, params = {}, rid) {
      const h = H[method];
      if (!h) return { ok: false, error: { code: "NOT_FOUND", message: `方法不存在：${method}`, retryable: false } };
      try {
        const got = Object.keys(params).sort().join(" "), want = KEYS[method].split(" ").filter(Boolean).sort().join(" ");
        if (got !== want) bad(`參數不符：需要 [${want}]，收到 [${got}]`);
        const sig = method + JSON.stringify(params), d = rid && dedupe.get(rid);
        if (d) { if (d.sig !== sig) bad("同一個 request_id 的參數不同"); return { ok: true, result: d.finished ? { job: d.id, done: d.finished } : { job: d.id } }; }
        cur = { rid, sig };
        try {
          if (["decode_frames", "decode_bits", "export_decode"].includes(method) && staleDecode !== null && staleDecode === params.decode_id) throw err("STALE", "解碼結果已過期");
          return { ok: true, result: h(params) }; } finally { cur = null; }
      } catch (e) { return { ok: false, error: toErr(e) }; }
    },
    async binary(path, a) {
      if (path === "/wave" && q(a.gen) !== gen) throw err("STALE", "開檔世代已變更");
      needFile();
      if (path === "/wave") {
        const c = chan(a.ch), n = px(a.px);
        if (!(q(a.t0) <= q(a.t1))) bad("t0 必須 ≤ t1");
        return envelope(c.t, c.v, q(a.t0), q(a.t1), n);
      }
      if (path === "/fft") {
        const n = px(a.px), log = q(a.log) === 1;
        if (!spec || spec.id !== a.id) throw err("STALE", "頻譜已過期");
        if (!(q(a.f0) <= q(a.f1)) || (log && !(q(a.f0) > 0))) bad("f0／f1 無效（log=1 時 f0 必須 > 0）");
        return envelope(spec.x, spec.y, q(a.f0), q(a.f1), n, log);
      }
      throw err("NOT_FOUND", `未知端點：${path}`);
    },
    url: (path, a) => `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="${NS}" width="640" height="400"><rect width="640" height="400" fill="#111"/><text x="20" y="40" fill="#0f0" font-size="24">mock 截圖 #${a.n ?? ""}</text></svg>`)}`,
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    setBusy(v) { busy = !!v; }, // 測試：注入 BUSY
    pushRaw(ev) { subs.forEach((f) => f(ev)); }, // 測試：原樣送出事件（可亂序、跳號、重複）
    emit, // 測試用：產生帶序號的事件
    methods: Object.keys(H), // 契約比對用：mock 實作的方法名集合
    keys: KEYS,
  };
}
