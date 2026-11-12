import { T } from "./terms.js";
import { channelColors } from "./channel_colors.js";
import { getFftState, mountFftControls } from './fft_state.js';
export { createFft, fftParams } from './fft_runner.js';
import { centerButton } from "./cursors.js";
import { openSlots, appendFileInfo } from "./slots.js";
import { exportReport } from "./report.js";
import { popMenu } from "./marker_menu.js";
// 分析頁工具列：開檔／關閉／檔案資訊／數學／匯出 CSV、Marker 模式、FFT 與 Track RF 控制。
// 對照 ui/analysis_controls.py、analysis_math.py、analysis_export.py。DOM／對話框手感待真人驗證。
// 開檔由 L4 處理（按鈕只發 file.open）；本檔負責關檔重設、數學通道、匯出、FFT job。FFT 參數列掛進 L4 的 .analysis__fftbar，次要參數收進「更多…」。

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const num = (v) => typeof v === "number" && Number.isFinite(v);
const fieldOf = (label, ctl) => { const f = h("label", "field", label ? label + " " : ""); f.append(ctl); return f; };
const select = (opts, cls = "select") => { const s = h("select", cls); for (const [v, t] of opts) s.append(new Option(t, v)); return s; };

/** ChannelInfo → store 通道記錄；V/格與位置依 autoScale（全 NaN 時 1 V、0 格）。 */
export function channelRecord(info, idx, colors, scales) {
  const [scale, position] = info.vmin === null || info.vmax === null ? [1, 0] : scales.autoScale(info.vmin, info.vmax, info.unit);
  return { name: info.name, unit: info.unit, derived: !!info.derived, ...channelColors(info.name, colors[idx % colors.length]), visible: true, scale, position,
    vmin: info.vmin, vmax: info.vmax, time_offset: 0, t0: info.t0, t1: info.t1, points: info.points };
}
/** 數學結果只追加通道；與槽位相同，不發出換檔通知。 */
export function applyMathChannel(store, result, colors, scales) {
  const st = store.get();
  if (!st.file || result.gen !== st.file.gen) return;
  if (st.channels.some(c => c.name === result.name)) throw new Error(`通道名稱重複：${result.name}`);
  store.set({ channels: [...st.channels, channelRecord(result, st.channels.length, colors, scales)] }, "program");
}
/** 關檔：先通知後端釋放資料（gen+1），再一次重設所有相依狀態（開檔由 L4 處理）。mock 缺此方法（NOT_FOUND）時略過。 */
export async function closeFile(store, bridge) {
  try { await bridge.call("close_waveform", {}); } catch (e) { if (e.code !== "NOT_FOUND") throw e; }
  store.set({ file: null, slots: [], dataRev: 0, channels: [], selected: null, measurements: [], fftResult: null, fftView: null, rfPos: null, markerResult: null }, "program");
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
  const colors = catalog.channel_colors ?? ["#F0E442"], fail = (e, t) => ui.showError(e, t);
  el.classList.add("analysis__toolbar");
  const btn = (t, fn, cls = "btn") => { const b = h("button", cls, t); b.type = "button"; b.onclick = fn; return b; };
  const loaded = [];

  const info = () => modal("檔案資訊", b => appendFileInfo(b, store.get()), null);

  async function math() {
    const st = store.get(), names = st.channels.map((c) => c.name), ops = catalog.math_ops ?? { binary: [], unary: [], filters: [] };
    const spec = await modal("Math Functions", (b) => {
      const op = select([...ops.binary, ...ops.unary, ...ops.filters].map((o) => [o, T(o)])), a = select(names.map((n) => [n, n])), bb = select(names.map((n) => [n, n]));
      const fc = h("input", "input"), pts = h("input", "input"); fc.value = "1M"; pts.value = "5"; a.value = st.selected; bb.value = names[Math.min(1, names.length - 1)];
      const upd = () => { bb.disabled = !ops.binary.includes(op.value); fc.disabled = !ops.filters.slice(0, 2).includes(op.value); pts.disabled = op.value !== "平滑"; };
      op.onchange = upd; upd();
      b.append(fieldOf("Operation", op), fieldOf("來源 A", a), fieldOf("來源 B", bb), fieldOf("截止頻率 Hz（-3 dB）", fc), fieldOf("平滑點數", pts));
      return () => {
        let param = 0;
        if (!fc.disabled) { param = fmt.parseSI(fc.value); if (!(param > 0)) throw new Error("截止頻率必須是正數（如 1M、200k）"); }
        if (!pts.disabled) { param = Number(pts.value); if (!Number.isInteger(param) || param < 2) throw new Error("平滑點數必須是 ≥2 的整數"); }
        return { op: op.value, a: a.value, b: bb.disabled ? null : bb.value, param };
      };
    });
    if (!spec) return;
    try {
      applyMathChannel(store, await bridge.job("math", spec), colors, scales);
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
    const dir = await ui.pickPath(ctx, "folder", store.get().file?.path?.replace(/[\\/][^\\/]*$/, '') ?? null); if (!dir) return;
    o.directory = dir;
    try { ui.toast(`已匯出：${(await bridge.job("export_csv", o)).path}`, "ok", 6000); } catch (e) { fail(e, "匯出失敗"); }
  }

  // ── 一般控制 ──
  const marker = select([["", "傳統游標 X1/X2"], ...(catalog.marker_modes ?? []).map((m) => [m, m])]);
  marker.title = "傳統游標：吸附第一通道；其餘為 Marker 模式"; marker.onchange = () => { store.set({ markerMode: marker.value || null }, "user"); };
  // 工具列只留常用鈕；其餘收進「檔案 ▾／分析 ▾」Popover（panel 緊接在按鈕後，Tab 順序相鄰）。
  const item = (t, fn) => { const b = btn(t, fn, "btn"); b.setAttribute("role", "menuitem"); return b; };
  const menu = (title, ...kids) => {
    const b = btn(title + " ▾", () => {}), p = h("div", "popmenu"); p.append(...kids); popMenu(b, p); el.append(b, p); return b;
  };
  const bOpen = btn("開啟", () => store.command("file.open"), "btn btn--primary");
  const bClose = item("關閉", async () => { const st = store.get(); if ((st.measurements.length || st.channels.some(c => c.derived) || st.slots?.length) && !await ui.confirm("關閉後會清除量測、衍生通道與比對槽，確定關閉？", "關閉檔案")) return; closeFile(store, bridge).catch((e) => fail(e, "關閉失敗")); });
  const bSlots = item("比對…", () => openSlots(ctx, modal)), bInfo = item("檔案資訊", info), bMath = item("Math…", math);
  const bCsv = item("匯出波形 CSV…", exportCsv), bRep = item("匯出 HTML 報告…", () => exportReport(ctx, el.closest(".analysis") ?? document, modal));
  const bFft = item("FFT 頻譜 ↗", () => store.command("tab.select", "fft"));
  loaded.push(bSlots, bClose, bInfo, bMath, bCsv, bRep, bFft, marker);
  el.append(bOpen);
  menu("檔案", bSlots, bInfo, bCsv, bRep, h("hr"), bClose);
  const fft = getFftState(ctx), on = h("input", "check"); on.type = "checkbox";
  on.onchange = () => fft.setAnalysisOn(on.checked);
  menu("分析", bFft, bMath);
  el.append(fieldOf("FFT 計算", on), fieldOf("Marker", marker), centerButton(store));

  // ── FFT ──
  const fftRow = h("div", "row"), more = h("div", "popmenu"), bMore = btn("更多…", () => {}, "btn btn--small");
  popMenu(bMore, more); mountFftControls(fftRow, ctx, { markerHost: more, impHost: more }); fftRow.append(bMore, more); loaded.push(bMore);
  fft.subscribe(() => { on.checked = fft.analysisOn; on.disabled = !store.get().file; });
  const root = el.closest(".analysis") ?? el.parentNode, place = () => { const bar = root.querySelector(".analysis__fftbar"); if (bar) bar.append(fftRow); return !!bar; };
  if (!place()) { const mo = new MutationObserver(() => { if (place()) mo.disconnect(); }); mo.observe(root, { childList: true, subtree: true }); setTimeout(() => { if (!fftRow.parentNode) el.append(fftRow); }, 3000); }

  function sync() {
    const st = store.get(), has = !!st.file;
    loaded.forEach((c) => { c.disabled = !has; });
    bClose.disabled = !has || !!st.opening; // 開檔進行中不可關檔
    marker.value = st.markerMode ?? "";
    on.checked = fft.analysisOn; on.disabled = !has;
  }
  store.on(["file", "channels", "markerMode", "opening"], sync);
  sync();
}
