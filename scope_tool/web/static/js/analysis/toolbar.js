import { createFft } from './fft_runner.js';
export { createFft, fftParams } from './fft_runner.js';
import { bindFftMarkerControls } from './fft_marker_controls.js';
import { disableTrackMeasurements } from "./summary.js";
// 分析頁工具列：開檔／關閉／檔案資訊／數學／匯出 CSV、Marker 模式、範圍與閾值、FFT 與 Track RF 控制。
// 對照 ui/analysis_controls.py、analysis_math.py、analysis_export.py。DOM／對話框手感待真人驗證。
// 開檔由 L4 處理（按鈕只發 file.open）；本檔負責關檔重設、數學通道、匯出、FFT job。FFT 參數列掛進 L4 的 .analysis__fftbar。

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const num = (v) => typeof v === "number" && Number.isFinite(v);
const fieldOf = (label, ctl) => { const f = h("label", "field", label ? label + " " : ""); f.append(ctl); return f; };
const select = (opts, cls = "select") => { const s = h("select", cls); for (const [v, t] of opts) s.append(new Option(t, v)); return s; };

/** ChannelInfo → store 通道記錄；V/格與位置依 autoScale（全 NaN 時 1 V、0 格）。 */
export function channelRecord(info, idx, colors, scales) {
  const [scale, position] = info.vmin === null || info.vmax === null ? [1, 0] : scales.autoScale(info.vmin, info.vmax, info.unit);
  return { name: info.name, unit: info.unit, derived: !!info.derived, color: colors[idx % colors.length], visible: true, scale, position,
    vmin: info.vmin, vmax: info.vmax, time_offset: 0, t0: info.t0, t1: info.t1, points: info.points };
}
/** 關檔：先通知後端釋放資料（gen+1），再一次重設所有相依狀態（開檔由 L4 處理）。mock 缺此方法（NOT_FOUND）時略過。 */
export async function closeFile(store, bridge) {
  try { await bridge.call("close_waveform", {}); } catch (e) { if (e.code !== "NOT_FOUND") throw e; }
  store.set({ file: null, channels: [], selected: null, measurements: [], fftResult: null, rfPos: null, markerResult: null }, "program");
}
/** CSV 範圍：游標顯示時間直接切原始軸、不扣 dx（與 Qt、契約一致）；無游標值＝全部。 */
export function csvRange(st) {
  const [a, b] = [st.cursors.x1, st.cursors.x2];
  return num(a) && num(b) ? [a, b] : null;
}

function modal(title, build, ok = "確定") {
  return new Promise((resolve) => {
    const d = h("dialog", "dlg"), body = h("div", "dlg__body"), msg = h("p", "dlg__msg"), act = h("div", "dlg__actions");
    body.append(h("h2", "dlg__title", title));
    const get = build(body);
    const done = (v) => { d.close(); d.remove(); resolve(v); };
    const cancel = h("button", "btn", ok ? "取消" : "關閉"); cancel.type = "button"; cancel.onclick = () => done(null);
    act.append(cancel);
    if (ok) {
      const b = h("button", "btn btn--primary", ok); b.type = "button";
      b.onclick = () => { try { done(get()); } catch (e) { msg.textContent = e.message; } };
      act.append(b);
    }
    d.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
    d.append(body, msg, act); document.body.append(d); d.showModal();
  });
}

export function mount(el, ctx) {
  const { store, bridge, ui, fmt, scales } = ctx, catalog = ctx.appState?.catalog ?? {};
  const colors = catalog.channel_colors ?? ["#ffcc00"], fail = (e, t) => ui.showError(e, t);
  el.classList.add("analysis__toolbar");
  const btn = (t, fn, cls = "btn") => { const b = h("button", cls, t); b.type = "button"; b.onclick = fn; return b; };
  const loaded = [];

  const info = () => modal("檔案資訊", (b) => { const t = h("table", "table"); for (const [k, v] of store.get().file.info) { const r = h("tr"); r.append(h("td", "", k), h("td", "", v)); t.append(r); } b.append(t); }, null);

  async function math() {
    const st = store.get(), names = st.channels.map((c) => c.name), ops = catalog.math_ops ?? { binary: [], unary: [], filters: [] };
    const spec = await modal("數學函式", (b) => {
      const op = select([...ops.binary, ...ops.unary, ...ops.filters].map((o) => [o, o])), a = select(names.map((n) => [n, n])), bb = select(names.map((n) => [n, n]));
      const fc = h("input", "input"), pts = h("input", "input"); fc.value = "1M"; pts.value = "5"; a.value = st.selected; bb.value = names[Math.min(1, names.length - 1)];
      const upd = () => { bb.disabled = !ops.binary.includes(op.value); fc.disabled = !ops.filters.slice(0, 2).includes(op.value); pts.disabled = op.value !== "平滑"; };
      op.onchange = upd; upd();
      b.append(fieldOf("運算", op), fieldOf("來源 A", a), fieldOf("來源 B", bb), fieldOf("截止頻率 Hz（-3 dB）", fc), fieldOf("平滑點數", pts));
      return () => {
        let param = 0;
        if (!fc.disabled) { param = fmt.parseSI(fc.value); if (!(param > 0)) throw new Error("截止頻率必須是正數（如 1M、200k）"); }
        if (!pts.disabled) { param = Number(pts.value); if (!Number.isInteger(param) || param < 2) throw new Error("平滑點數必須是 ≥2 的整數"); }
        return { op: op.value, a: a.value, b: bb.disabled ? null : bb.value, param };
      };
    });
    if (!spec) return;
    try {
      const r = await bridge.job("math", spec), cur = store.get();
      if (r.gen !== cur.file?.gen) return; // 已換檔
      store.setChannels([...cur.channels, channelRecord(r, cur.channels.length, colors, scales)]);
    } catch (e) { fail(e, "數學運算失敗"); }
  }

  async function exportCsv() {
    const o = await modal("匯出 CSV", (b) => {
      const rg = select([["all", "全部"], ["cur", "游標區間"]]), red = h("input", "check"), lim = h("input", "input");
      red.type = "checkbox"; lim.value = String(catalog.csv_max_points_default ?? 10000000); lim.disabled = true; red.onchange = () => { lim.disabled = !red.checked; };
      b.append(fieldOf("範圍", rg), fieldOf("縮點", red), fieldOf("上限點數", lim));
      return () => {
        const n = Number(lim.value);
        if (red.checked && !(Number.isInteger(n) && n >= 1)) throw new Error("上限點數必須是正整數");
        const range = rg.value === "cur" ? csvRange(store.get()) : null;
        if (rg.value === "cur" && !range) throw new Error("請先設定 X1、X2 游標");
        return { range, max_points: red.checked ? n : null, directory: null };
      };
    }, "匯出");
    if (!o) return;
    try { ui.toast(`已匯出：${(await bridge.job("export_csv", o)).path}`, "ok", 6000); } catch (e) { fail(e, "匯出失敗"); }
  }

  // ── 一般控制 ──
  const marker = select([["", "傳統游標 X1/X2"], ...(catalog.marker_modes ?? []).map((m) => [m, m])]);
  disableTrackMeasurements(marker);
  marker.title = "傳統游標：吸附第一通道；其餘為 Marker 模式"; marker.onchange = () => { if (marker.value !== "Track Measurements") store.set({ markerMode: marker.value || null }, "user"); };
  const range = select([["all", "全部"], ["cursors", "游標區間"]]); range.title = "量測／FFT 範圍"; range.onchange = () => store.set({ rangeMode: range.value }, "user");
  const thr = select(Object.keys(catalog.thresholds ?? { "10/50/90 %": 0 }).map((k) => [k, k])); thr.onchange = () => store.set({ threshold: thr.value }, "user");
  const bOpen = btn("開啟", () => store.command("file.open"), "btn btn--primary"), bClose = btn("關閉", () => closeFile(store, bridge).catch((e) => fail(e, "關閉失敗"))), bReset = btn("完整時間", () => store.command("view.reset")), bInfo = btn("檔案資訊", info), bMath = btn("數學…", math), bCsv = btn("匯出 CSV…", exportCsv);
  loaded.push(bClose, bInfo, bMath, bCsv, marker, bReset);
  const prev = h("input", "check"); prev.type = "checkbox"; prev.checked = true; prev.onchange = () => store.command("preview.visible", prev.checked);
  store.onCommand('layout.state', (s) => { prev.checked = s.overview; });
  store.command('layout.query');
  el.append(bOpen, bClose, bInfo, bReset, fieldOf("預覽", prev), fieldOf("Marker", marker), fieldOf("範圍", range), fieldOf("閾值", thr), bCsv, bMath);

  // ── FFT ──
  const p = { on: false, source: null, window: "Hanning", unit: "dBm", imp: 0, manualR: 50, peakCount: 5, peakLevel: -40, peakSort: (catalog.peak_sorts ?? [""])[0] };
  const fft = createFft(ctx, catalog, p, { onError: (e, manual) => (manual ? fail(e, "FFT 失敗") : ui.toast(`FFT 失敗：${e.message}`, "error", 6000)),
    onReset: () => { on.checked = false; store.command("fft.visible", false); syncFft(); } });
  const on = h("input", "check"); on.type = "checkbox";
  const src = select([]), win = select(Object.keys(catalog.fft_windows ?? {}).map((k) => [k, k])), unit = select((catalog.fft_units ?? []).filter(k => k !== "Phase").map((k) => [k, k]));
  const imp = select((catalog.fft_impedances ?? []).map(([t], i) => [i, t])), man = h("input", "input"), sort = select((catalog.peak_sorts ?? []).map((k) => [k, k]));
  const lvl = h("input", "input"), cnt = h("input", "input"); man.value = "50"; lvl.value = "-40"; cnt.value = "5"; [man, lvl, cnt].forEach((i) => { i.style.width = "5em"; });
  const nums = (inp, key, ok) => { inp.onchange = () => { const v = Number(inp.value); if (ok(v)) p[key] = v; else inp.value = String(p[key]); fft.schedule(); }; };
  nums(man, "manualR", (v) => v > 0);
  const sel = (s, key, conv = (x) => x) => { s.onchange = () => { p[key] = conv(s.value); syncFft(); fft.schedule(); }; };
  sel(src, "source"); sel(win, "window"); sel(imp, "imp", Number);
  bindFftMarkerControls(ctx, p, { unit, lvl, cnt, sort, imp, man }, catalog);
  on.onchange = () => { p.on = on.checked; store.command("fft.visible", on.checked); if (on.checked) fft.run(true); else { fft.invalidate(); store.set({ fftResult: null, rfPos: null }, "program"); } syncFft(); };
  function syncFft() {
    man.disabled = (catalog.fft_impedances ?? [])[p.imp]?.[1] !== null;
    const ph = p.unit === "Phase"; [sort, lvl, cnt].forEach((c) => { c.disabled = ph; });
  }
  const fftRow = h("div", "row"); // 掛進 L4 fftpane 的 .analysis__fftbar
  const loadedAll = [on, src, win, unit, imp, man, sort, lvl, cnt];
  el.append(fieldOf("FFT 計算", on));
  fftRow.append(fieldOf("來源", src), fieldOf("視窗", win), fieldOf("單位", unit), imp, man, fieldOf("排序", sort), fieldOf("基準線", lvl), fieldOf("顯示數量 n", cnt));
  const root = el.closest(".analysis") ?? el.parentNode, place = () => { const bar = root.querySelector(".analysis__fftbar"); if (bar) bar.append(fftRow); return !!bar; };
  if (!place()) { const mo = new MutationObserver(() => { if (place()) mo.disconnect(); }); mo.observe(root, { childList: true, subtree: true }); setTimeout(() => { if (!fftRow.parentNode) el.append(fftRow); }, 3000); }

  function sync() {
    const st = store.get(), has = !!st.file, names = st.channels.map((c) => c.name);
    [...loaded, ...loadedAll].forEach((c) => { c.disabled = !has; });
    bClose.disabled = !has || !!st.opening; // 開檔進行中不可關檔
    if (src.options.length !== names.length || [...src.options].some((o, i) => o.value !== names[i])) { src.replaceChildren(...names.map((n) => new Option(n, n))); }
    if (!names.includes(p.source)) { p.source = names[0] ?? null; }
    src.value = p.source ?? ""; marker.value = st.markerMode ?? ""; range.value = st.rangeMode; thr.value = st.threshold;
    if (!has && on.checked) { on.checked = false; p.on = false; store.command("fft.visible", false); }
    syncFft();
  }
  store.on(["file", "channels", "markerMode", "rangeMode", "threshold", "opening"], sync);
  store.on(["fftResult"], (st) => { // 新頻譜（spectrum_id 已換）→ 已有 RF 位置就重新吸附（按鈕在 L4 fftpane）
    const r = st.fftResult;
    if (st.rfPos && r?.ok && r.unit !== "°") store.command("rf.intent", { direction: 0, x: st.rfPos.x }); else if (st.rfPos && !r?.ok) store.set({ rfPos: null }, "program");
  });
  sync();
}
