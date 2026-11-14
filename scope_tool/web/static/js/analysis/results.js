import { chLabel } from "./alias.js";
import { T } from "./terms.js";
export { fftInfo } from './fft_marker_table.js';
import { fftInfo, mountFftMarkerTable } from './fft_marker_table.js';
// 量測結果表與 FFT 峰值表（讀 store.measurements／fftResult）。對照 ui/analysis_results.py。
// 過期丟棄：result.gen ≠ 目前檔案 gen 的列一律顯示「…」；匯出只在整批同 gen／同 revision 時才送（後端另驗 STALE）。

import { COLUMNS, load, save } from "./bpanel.js";
import { popMenu } from "./marker_menu.js";

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

/** 列狀態：pending（計算中或已過期）／fail／ok。 */
export function rowState(e, file) {
  const r = e.result;
  if (!r || !file || r.gen !== file.gen) return "pending";
  return r.ok && r.stats ? "ok" : "fail";
}
/** 可匯出的整批：全部有結果、同 gen 同 revision 才回 {gen, revision, rows}，否則 null。 */
export function exportable(list, file) {
  if (!file || !list.length || list.some((e) => rowState(e, file) === "pending")) return null;
  const { gen, revision } = list[0].result;
  return list.every((e) => e.result.gen === gen && e.result.revision === revision) ? { gen, revision, rows: list.map((e) => e.result) } : null;
}
export const STAT_KEYS = ["current", "mean", "min", "max", "range", "std"];
/** 一列的文字格（標籤除外）。 */
export function rowCells(e, state, unit, fmt) {
  if (state === "pending") return Array(7).fill("…");
  if (state === "fail") return Array(7).fill("—");
  const s = e.result.stats;
  return [...STAT_KEYS.map((k) => (e.result.bound ? `${e.result.bound} ` : "") + fmt.fmt(s[k], unit)), String(s.count)];
}

export function mount(el, ctx) {
  const { store, bridge, ui, fmt } = ctx, cat = () => ctx.appState?.catalog ?? {};
  el.classList.add("results");
  let prefs = load(), floating = !!el.closest?.('.analysis__float'), floatColumns = [...COLUMNS];
  const visibleColumns = () => floating ? floatColumns : prefs.columns;
  const labels = () => (cat().stat_columns ?? ["目前", "平均", "最小", "最大", "範圍", "標準差", "次數"]).map(T);
  const cols = () => [T("量測"), ...COLUMNS.filter(k => visibleColumns().includes(k)).map(k => labels()[COLUMNS.indexOf(k)]), ""];
  const meas = h("table", "table table--num results__table");
  const NOTE = "『目前』＝最靠近顯示時間 t=0 的事件；範圍不含 0 時用範圍中點，同距取較早；無事件時間時取首事件（離線單檔）";
  const bClear = h("button", "btn btn--small results__clear results__clear--sep", "清除全部"), bExp = h("button", "btn btn--small results__export", "匯出結果");
  bClear.title = "清除全部量測"; bExp.title = "匯出結果 CSV";
  const menu = h("span", "results__menu"), toggle = h("button", "btn btn--small", "⋮"); toggle.title = "選擇量測欄位";
  const place = () => {
    const r = toggle.getBoundingClientRect();
    choices.style.boxSizing = 'border-box'; choices.style.maxHeight = `${innerHeight}px`;
    const height = Math.min(choices.getBoundingClientRect().height,innerHeight);
    choices.style.bottom = 'auto';
    choices.style.top = `${Math.max(0,Math.min(innerHeight-height,r.top >= height ? r.top-height : r.bottom))}px`;
    choices.style.overflowY = 'auto';
    choices.style.right = `${Math.max(0,innerWidth-r.right)}px`;
  };
  const choices = h("div", "results__choices"); menu.append(toggle, choices); popMenu(toggle, choices, place);
  const columnBoxes = [];
  for (const key of COLUMNS) {
    const label = h("label", "check"), box = h("input"); box.type = "checkbox"; box.dataset.column = key;
    columnBoxes.push(box); box.checked = visibleColumns().includes(key); label.append(box, h("span", "", labels()[COLUMNS.indexOf(key)])); choices.append(label);
    box.onchange = () => {
      prefs = { ...load(), columns:COLUMNS.filter(k => k === key ? box.checked : visibleColumns().includes(k)) };
      if (floating) floatColumns = [...prefs.columns]; else save(prefs);
      renderMeas();
    };
  }
  const bar = ctx.resultActions ?? h("div", "results__actions"); bar.append(menu, bExp, bClear);
  if (!ctx.resultActions) el.append(bar);
  const fftBox = ctx.fftPeaks ?? h("div", "analysis__peaks");
  mountFftMarkerTable(fftBox, ctx, fftInfo);
  const empty = h("p", "analysis__placeholder results__empty", "尚無量測：在左欄選來源後按量測項目"); el.append(meas, empty);
  if (!ctx.fftPeaks) el.append(fftBox);

  function tr(cells, tag = "td", title) { const r = h("tr"); cells.forEach((c) => { const d = h(tag, "", c); r.append(d); }); if (title) r.title = title; return r; }
  function renderMeas() {
    const { measurements: list, file, channels } = store.get(), defs = Object.fromEntries((cat().measurements ?? []).map((m) => [m.name, m]));
    for (const box of columnBoxes) box.checked = visibleColumns().includes(box.dataset.column);
    const rows = [tr(cols(), "th")];
    const ci = COLUMNS.filter(k => visibleColumns().includes(k)).indexOf("current");
    if (ci >= 0) { const th = rows[0].children[ci + 1]; th.title = NOTE; th.setAttribute("aria-label", `${th.textContent}：${NOTE}`); }
    for (const e of list) {
      const ch = channels.find((c) => c.name === e.channel), state = rowState(e, file);
      const unit = e.result?.unit || unitFor(defs[e.name]?.unit, ch?.unit ?? "V");
      // 區間量測名稱依 analysis/measure.py 的 INTERVAL；catalog 尚無區間欄位。
      const cycles = ["Vavg", "Vrms(DC)", "Vrms(AC)"].includes(e.name) && e.mode === "cycles";
      const dual = defs[e.name]?.sources === 2;
      const cycle = ["Vavg", "Vrms(DC)", "Vrms(AC)"].includes(e.name) && e.mode === "cycle";
      const arrow = dual ? (e.name === "電壓比" ? "" : ` ${e.rising ? "↑" : "↓"}${(e.rising2 ?? e.rising) ? "↑" : "↓"}`) : (defs[e.name]?.sloped && e.all_edges !== false) || cycles ? (e.rising ? " ↑" : " ↓") : "";
      const deltaLabel = e.name === "Delta Time" ? `Delta Time(${chLabel(channels, e.channel)}#${e.edge_num ?? 1}${e.rising ? "↑" : "↓"}→${chLabel(channels, e.channel2)}#${e.edge_num2 ?? 1}${(e.rising2 ?? e.rising) ? "↑" : "↓"} ${{lower:"下",middle:"中",upper:"上"}[e.edge_level ?? "middle"]}／${{lower:"下",middle:"中",upper:"上"}[e.edge_level2 ?? "middle"]})` : null;
      const row = tr([deltaLabel ?? `${T(e.name)}(${chLabel(channels, e.channel)}${dual ? `→${chLabel(channels, e.channel2)}` : ""}${cycles ? " N Cycles" : cycle ? " One Cycle" : ""}${arrow}${e.all_edges === false ? (e.name === "相位" ? " All Edges" : " Single Event") : ""})`, ...rowCells(e, state, unit, fmt).filter((_v,i) => visibleColumns().includes(COLUMNS[i])), ""], "td", state === "fail" ? e.result.reason : state === "pending" ? "計算中" : "");
      if (store.get().markerMode === "Track Measurements") { row.classList.toggle("is-selected", !!e.track); row.onclick = () => store.command("measure.track", e.id); }
      row.firstChild.title = row.firstChild.textContent;
      row.firstChild.style.color = ch?.color ?? "";
      const x = h("button", "results__remove", "×"); x.type = "button"; x.setAttribute("aria-label", "刪除此量測"); x.title = "刪除此量測"; x.onclick = (event) => { event?.stopPropagation(); store.command("measure.remove", e.id); }; row.lastChild.append(x);
      rows.push(row);
    }
    meas.replaceChildren(...rows); empty.hidden = list.length > 0;
    bExp.disabled = !exportable(list, file); bClear.disabled = !list.length;
  }
  const unitFor = (tpl, u) => String(tpl ?? "").replace("{u}", u);
  bClear.onclick = async () => { const n = store.get().measurements.length; if (n && await ui.confirm(`清除全部 ${n} 筆量測？`, "清除量測")) store.command("measure.clear"); };
  bExp.onclick = async () => {
    const { measurements: list, file } = store.get(), ex = exportable(list, file);
    if (!ex) return ui.toast("量測計算中或結果已過期，請稍後再匯出", "error");
    const dir = await ui.pickPath(ctx, "folder", store.get().file?.path?.replace(/[\\/][^\\/]*$/, "") ?? null); if (!dir) return;
    try {
      const r = await bridge.call("export_measurements", { rows: ex.rows, gen: ex.gen, revision: ex.revision, directory: dir });
      ui.toast(`已匯出：${r.path}`, "ok", 6000);
    } catch (e) { if (e.code === "STALE") ui.toast("結果已過期，等量測重新計算後再匯出", "error"); else ui.showError(e, "匯出失敗"); }
  };
  store.on(["measurements", "file", "channels", "markerMode"], renderMeas);
  store.onCommand('layout.float.state',on=>{ floating=on; if (!on) prefs=load(); renderMeas(); });
  renderMeas();
}
