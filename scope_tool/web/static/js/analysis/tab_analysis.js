// 離線分析頁：開檔指令 "file.open" 與 "open_waveform"（payload {path?}）等同處理；L3 擷取頁完成後會先切到本分頁再發 open_waveform。
// 佈局組裝主圖／縮圖／FFT 窗格，掛載 L5 模組（動態載入，缺檔顯示佔位），處理開檔與 viewport.intent。
import { autoScale } from "./scales.js";
import { fullRange } from "./overview.js";

const FALLBACK_COLORS = ["#ffcc00", "#00d0ff", "#ff5fbf", "#7be36b", "#ff8a3d", "#b79cff"];

/** FileSummary → 通道記錄（color 依序取用；scale／position 由 autoScale；time_offset 起始 0）。 */
export function channelsFromFile(info, colors = FALLBACK_COLORS) {
  return info.channels.map((c, i) => {
    const [scale, position] = autoScale(c.vmin ?? 0, c.vmax ?? 0, c.unit);
    return { name: c.name, unit: c.unit, derived: !!c.derived, color: colors[i % colors.length], visible: true, scale, position, vmin: c.vmin, vmax: c.vmax, t0: c.t0, t1: c.t1, time_offset: 0 };
  });
}
/** 驗證 viewport.intent：兩端為有限數且 t0<t1，否則回 null。 */
/** 開檔指令名稱（等同處理）。 */
export const OPEN_COMMANDS = ["file.open", "open_waveform"];
export const bindOpen = (store, fn) => OPEN_COMMANDS.forEach((n) => store.onCommand(n, fn));
export const cleanView = (p) => (p && Number.isFinite(p.t0) && Number.isFinite(p.t1) && p.t0 < p.t1 ? { t0: p.t0, t1: p.t1 } : null);

// L5 模組與掛載點（缺檔時顯示佔位）。cursors.js 無自己的區塊，掛在隱藏容器。
const L5 = [["toolbar", "./toolbar.js", "analysis__toolbar"], ["measure", "./measure.js", "analysis__side"],
  ["chanbar", "./chanbar.js", "analysis__chanbar"], ["results", "./results.js", "analysis__results"], ["cursors", "./cursors.js", "analysis__cursors"]];

export function mount(el, ctx) {
  const { store, bridge, ui } = ctx;
  el.innerHTML = `<div class="analysis">
    <div class="analysis__toolbar"></div>
    <div class="analysis__body">
      <div class="analysis__side"></div>
      <div class="analysis__plot">
        <div class="analysis__chanbar chanbar"></div>
        <div class="analysis__overview"></div>
        <div class="analysis__main plot"></div>
        <div class="analysis__fft" hidden></div>
      </div>
    </div>
    <div class="analysis__results"></div>
    <div class="analysis__cursors" hidden></div>
  </div>`;
  const q = (c) => el.querySelector("." + c);
  const fft = q("analysis__fft"), overview = q("analysis__overview");

  // 自家圖表
  const own = [["./mainplot.js", q("analysis__main")], ["./overview.js", overview], ["./fftpane.js", fft]];
  for (const [src, host] of own) import(src).then((m) => m.mount(host, ctx)).catch((e) => { host.textContent = `（圖表載入失敗：${e.message}）`; console.warn(src, e); });

  // L5 模組：缺檔或掛載失敗只影響該區塊
  for (const [name, src, cls] of L5) {
    const host = q(cls);
    import(src).then((m) => m.mount(host, ctx))
      .catch((e) => {
        if (cls === "analysis__cursors") return;
        host.innerHTML = `<span class="analysis__placeholder">（${name} 模組尚未載入）</span>`;
        if (name === "toolbar") host.append(openButton());
        console.warn(`L5 ${name} 載入失敗`, e?.message);
      });
  }
  function openButton() {
    const b = document.createElement("button");
    b.className = "btn btn--small"; b.type = "button"; b.textContent = "開啟波形檔…";
    b.addEventListener("click", () => store.command("file.open"));
    return b;
  }

  // 顯示控制：縮圖由 L5 以 command("preview.visible", bool)、FFT 以 command("fft.visible", bool) 切換；FFT 有結果時自動顯示
  store.onCommand("preview.visible", (on) => { overview.hidden = !on; });
  store.onCommand("fft.visible", (on) => { fft.hidden = !on; });
  store.on(["fftResult"], (s) => { if (s.fftResult?.ok) fft.hidden = false; });

  // viewport.intent 的唯一處理者
  store.onCommand("viewport.intent", (p) => { const v = cleanView(p); if (v) store.set({ view: v }, "user"); });
  store.onCommand("view.reset", () => { const f = fullRange(store.get().file); if (f && f.t1 > f.t0) store.set({ view: f }, "user"); });

  // 開檔流程：file.open {path?}；未給路徑則用 ui.pickPath
  let opening = 0;
  bindOpen(store, async (p) => {
    const token = ++opening;
    try {
      const path = p?.path ?? await ui.pickPath(ctx, "file", ctx.appState?.config?.waveform_dir ?? null);
      if (!path) return;
      const info = await bridge.job("open_waveform", { path });
      if (token !== opening) return; // 使用者又開了別的檔：丟棄舊結果
      applyFile(info);
    } catch (e) {
      if (token === opening) ui.showError(e, "開檔失敗");
    }
  });
  function applyFile(info) {
    const colors = ctx.appState?.catalog?.channel_colors ?? FALLBACK_COLORS;
    const f = fullRange(info) ?? { t0: 0, t1: 1 };
    store.set({ file: info, fftResult: null, rfPos: null, view: f }, "program");
    store.setChannels(channelsFromFile(info, colors));
    // 游標初值由 L5 cursors.js 依檔案範圍自設（唯一寫入者）
  }
  if (new URLSearchParams(location.search).get("mock") === "1" && new URLSearchParams(location.search).get("autoopen") === "1") store.command("file.open", { path: "/mock/demo.h5" });
}
