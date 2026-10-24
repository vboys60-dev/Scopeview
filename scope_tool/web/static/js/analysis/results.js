// 量測結果表與 FFT 峰值表（讀 store.measurements／fftResult）。對照 ui/analysis_results.py。
// 過期丟棄：result.gen ≠ 目前檔案 gen 的列一律顯示「…」；匯出只在整批同 gen／同 revision 時才送（後端另驗 STALE）。

import { COLUMNS, load, save } from "./bpanel.js";

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
  return [...STAT_KEYS.map((k) => fmt.fmt(s[k], unit)), String(s.count)];
}
export function fftInfo(r, fmt) {
  if (!r) return "";
  if (!r.ok) return r.reason ?? "FFT 失敗";
  return `Δf ${fmt.fmt(r.df, "Hz")}｜RBW ${fmt.fmt(r.rbw, "Hz")}｜ENBW ${fmt.fmt(r.enbw, "Hz")}｜${r.window}｜N=${r.n}（${r.effective_n}）｜R=${r.r_ohm} Ω｜${r.unit}`;
}

export function mount(el, ctx) {
  const { store, bridge, ui, fmt } = ctx, cat = () => ctx.appState?.catalog ?? {};
  el.classList.add("results");
  let prefs = load();
  const labels = () => cat().stat_columns ?? ["目前", "平均", "最小", "最大", "範圍", "標準差", "次數"];
  const cols = () => ["量測", ...COLUMNS.filter(k => prefs.columns.includes(k)).map(k => labels()[COLUMNS.indexOf(k)]), ""];
  const meas = h("table", "table table--num results__table");
  const note = h("span", "results__info", "ⓘ"); note.tabIndex = 0;
  note.title = "『目前』＝範圍內最左邊的事件（離線單檔）";
  note.setAttribute("aria-label",note.title);
  const bClear = h("button", "btn btn--small results__clear", "清除全部"), bExp = h("button", "btn btn--small results__export", "匯出結果");
  bClear.title = "清除全部量測"; bExp.title = "匯出結果 CSV";
  const menu = h("details", "results__menu"), toggle = h("summary", "btn btn--small", "⋮"); toggle.title = "選擇量測欄位";
  menu.ontoggle = () => {
    const r = toggle.getBoundingClientRect();
    choices.style.bottom = `${innerHeight-r.top}px`; choices.style.right = `${Math.max(0,innerWidth-r.right)}px`;
  };
  const choices = h("div", "results__choices"); menu.append(toggle, choices);
  for (const key of COLUMNS) {
    const label = h("label", "check"), box = h("input"); box.type = "checkbox"; box.dataset.column = key;
    box.checked = prefs.columns.includes(key); label.append(box, h("span", "", labels()[COLUMNS.indexOf(key)])); choices.append(label);
    box.onchange = () => {
      prefs = { ...load(), columns:COLUMNS.filter(k => k === key ? box.checked : prefs.columns.includes(k)) };
      save(prefs); renderMeas();
    };
  }
  const bar = ctx.resultActions ?? h("div", "results__actions"); bar.append(note, menu, bClear, bExp);
  if (!ctx.resultActions) el.append(bar);
  const fftInfoEl = h("div", "results__fftinfo muted"), fftTbl = h("table", "table table--num results__table");
  const fftBox = ctx.fftPeaks ?? h("div", "analysis__peaks");
  fftBox.append(fftInfoEl, fftTbl);
  el.append(meas);
  if (!ctx.fftPeaks) el.append(fftBox);

  function tr(cells, tag = "td", title) { const r = h("tr"); cells.forEach((c) => { const d = h(tag, "", c); r.append(d); }); if (title) r.title = title; return r; }
  function renderMeas() {
    const { measurements: list, file, channels } = store.get(), defs = Object.fromEntries((cat().measurements ?? []).map((m) => [m.name, m]));
    const rows = [tr(cols(), "th")];
    for (const e of list) {
      const ch = channels.find((c) => c.name === e.channel), state = rowState(e, file);
      const unit = e.result?.unit || unitFor(defs[e.name]?.unit, ch?.unit ?? "V");
      const arrow = defs[e.name]?.sloped ? (e.rising ? " ↑" : " ↓") : "";
      const row = tr([`${e.name}(${e.channel}${arrow})`, ...rowCells(e, state, unit, fmt).filter((_v,i) => prefs.columns.includes(COLUMNS[i])), "×"], "td", state === "fail" ? e.result.reason : state === "pending" ? "計算中" : "");
      row.firstChild.title = row.firstChild.textContent;
      row.firstChild.style.color = ch?.color ?? "";
      const x = row.lastChild; x.style.cursor = "pointer"; x.title = "刪除此量測"; x.onclick = () => store.command("measure.remove", e.id);
      rows.push(row);
    }
    meas.replaceChildren(...rows);
    bExp.disabled = !exportable(list, file);
  }
  const unitFor = (tpl, u) => String(tpl ?? "").replace("{u}", u);
  function renderFft() {
    const r = store.get().fftResult;
    fftInfoEl.textContent = fftInfo(r, fmt);
    const peaks = r?.ok ? r.peaks ?? [] : [];
    fftTbl.replaceChildren(tr(["#", "頻率", "大小"], "th"), ...peaks.map((p, i) => tr([String(i + 1), fmt.fmt(p.x, "Hz"), fmt.fmt(p.y, r.unit)])));
  }
  bClear.onclick = () => store.command("measure.clear");
  bExp.onclick = async () => {
    const { measurements: list, file } = store.get(), ex = exportable(list, file);
    if (!ex) return ui.toast("量測計算中或結果已過期，請稍後再匯出", "error");
    try {
      const r = await bridge.call("export_measurements", { rows: ex.rows, gen: ex.gen, revision: ex.revision, directory: null });
      ui.toast(`已匯出：${r.path}`, "ok", 6000);
    } catch (e) { if (e.code === "STALE") ui.toast("結果已過期，等量測重新計算後再匯出", "error"); else ui.showError(e, "匯出失敗"); }
  };
  store.on(["measurements", "file", "channels"], renderMeas);
  store.on(["fftResult"], renderFft);
  renderMeas(); renderFft();
}
