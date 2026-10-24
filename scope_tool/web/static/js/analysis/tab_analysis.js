// 離線分析頁：開檔指令 "file.open" 與 "open_waveform"（payload {path?}）等同處理；L3 擷取頁完成後會先切到本分頁再發 open_waveform。
// 佈局組裝主圖／縮圖／FFT 窗格，掛載 L5 模組（動態載入，缺檔顯示佔位），處理開檔與 viewport.intent。
import { autoScale } from "./scales.js";
import { bindViewport } from "./gestures.js";
import { fullRange } from "./overview.js";

const FALLBACK_COLORS = ["#ffcc00", "#00d0ff", "#ff5fbf", "#7be36b", "#ff8a3d", "#b79cff"];

/** FileSummary → 通道記錄（color 依序取用；scale／position 由 autoScale；time_offset 起始 0）。 */
export function channelsFromFile(info, colors = FALLBACK_COLORS) {
  return info.channels.map((c, i) => {
    const [scale, position] = autoScale(c.vmin ?? 0, c.vmax ?? 0, c.unit);
    return { name: c.name, unit: c.unit, derived: !!c.derived, color: colors[i % colors.length], visible: true, scale, position, vmin: c.vmin, vmax: c.vmax, t0: c.t0, t1: c.t1, time_offset: 0 };
  });
}
/** 開檔結果 → 單一 store patch（file、channels、selected、view 一起換）。 */
export function openPatch(info, colors = FALLBACK_COLORS) {
  const channels = channelsFromFile(info, colors);
  return { file: info, channels, selected: channels[0]?.name ?? null, fftResult: null, rfPos: null, view: fullRange(info) ?? { t0: 0, t1: 1 } };
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
  // 版面骨架（grid 區域由 app.css 的 .analysis 定義：tool／side／plot／results；細節見 analysis.css）
  el.innerHTML = `<div class="analysis">
    <div class="analysis__toolbar"></div>
    <div class="analysis__sidepanel">
      <button type="button" class="btn btn--small analysis__sidetoggle" aria-expanded="true" aria-controls="analysis-side-body">收折量測欄</button>
      <div class="analysis__side" id="analysis-side-body"></div>
    </div>
    <div class="analysis__plot">
      <div class="analysis__chanbar chanbar"></div>
      <div class="analysis__overview" title="來源時間概觀（原始通道共用電壓範圍）"></div>
      <div class="analysis__main plot"></div>
      <div class="analysis__horizontal"></div>
      <section class="analysis__fftsection" hidden>
        <button type="button" class="btn btn--small analysis__ffttoggle" aria-expanded="true" aria-controls="analysis-fft-body">收折 FFT 窗格</button>
        <div class="analysis__fft" id="analysis-fft-body"></div>
      </section>
    </div>
    <div class="analysis__lower">
      <button type="button" class="btn btn--small analysis__lowertoggle" aria-expanded="true" aria-controls="analysis-lower-body"></button>
      <div class="analysis__lowerbody" id="analysis-lower-body"><div class="analysis__results"></div>
      <details class="analysis__cursorbox" open><summary>游標數值</summary><div class="analysis__cursors"></div></details></div>
    </div>
  </div>`;
  const q = (c) => el.querySelector("." + c);
  const fft = q("analysis__fft"), overview = q("analysis__overview");

  bindViewport(store);

  // 自家圖表
  const own = [["./axes.js", q("analysis__horizontal")], ["./mainplot.js", q("analysis__main")], ["./overview.js", overview], ["./fftpane.js", fft]];
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

  // 收折只記在本次頁面記憶體，不寫 store／不新增意圖。FFT 計算仍由工具列獨立管理。
  const root = q("analysis"), fftSection = q("analysis__fftsection");
  let fftOn = false, fftCollapsed = false, sideCollapsed = false, lowerCollapsed = false;
  const sideButton = q("analysis__sidetoggle"), lowerButton = q("analysis__lowertoggle"), fftButton = q("analysis__ffttoggle");
  function renderLayout() {
    root.classList.toggle("analysis--side-collapsed", sideCollapsed);
    root.classList.toggle("analysis--lower-collapsed", lowerCollapsed);
    root.classList.toggle("analysis--fft", fftOn && !fftCollapsed);
    fftSection.hidden = !fftOn;
    fftSection.classList.toggle("analysis__fftsection--collapsed", fftCollapsed);
    q("analysis__side").hidden = sideCollapsed;
    q("analysis__lowerbody").hidden = lowerCollapsed;
    fft.hidden = fftCollapsed;
    sideButton.textContent = sideCollapsed ? "展開" : "收折量測欄";
    sideButton.title = sideCollapsed ? "展開量測欄" : "收折量測欄";
    const st = store.get(), count = st.measurements.length, peaks = st.fftResult?.peaks?.length ?? 0;
    lowerButton.textContent = `${lowerCollapsed ? "展開" : "收折"}結果（量測 ${count}／FFT 峰值 ${peaks}）`;
    fftButton.textContent = `${fftCollapsed ? "展開" : "收折"} FFT 窗格`;
    for (const [button, collapsed] of [[sideButton, sideCollapsed], [lowerButton, lowerCollapsed], [fftButton, fftCollapsed]]) button.setAttribute("aria-expanded", String(!collapsed));
  }
  sideButton.onclick = () => { sideCollapsed = !sideCollapsed; renderLayout(); };
  lowerButton.onclick = () => { lowerCollapsed = !lowerCollapsed; renderLayout(); };
  fftButton.onclick = () => { fftCollapsed = !fftCollapsed; renderLayout(); };
  store.onCommand("preview.visible", (on) => { overview.hidden = !on; });
  store.onCommand("fft.visible", (on) => { fftOn = !!on; renderLayout(); });
  store.on(["measurements", "fftResult"], renderLayout); // 更新數量，絕不改使用者的收折狀態
  renderLayout();

  // 開檔流程：file.open {path?}；未給路徑則用 ui.pickPath。序列化：進行中再開檔一律忽略並提示；
  // store.opening 在開檔期間為 true（toolbar 據此禁用關檔／開檔）。
  let busy = false;
  bindOpen(store, async (p) => {
    if (busy) { ui.toast("正在開檔，請稍候", "info"); return; }
    busy = true; store.set({ opening: true }, "program");
    try {
      const path = p?.path ?? await ui.pickPath(ctx, "file", ctx.appState?.config?.waveform_dir ?? null);
      if (path) applyFile(await bridge.job("open_waveform", { path }));
    } catch (e) {
      ui.showError(e, "開檔失敗");
    } finally {
      busy = false; store.set({ opening: false }, "program");
    }
  });
  function applyFile(info) {
    const colors = ctx.appState?.catalog?.channel_colors ?? FALLBACK_COLORS;
    store.set(openPatch(info, colors), "program"); // file 與 channels／selected 同一次 set，監聽者不會看到新檔配舊通道
    // 游標初值由 L5 cursors.js 依檔案範圍自設（唯一寫入者）
  }
  if (new URLSearchParams(location.search).get("mock") === "1" && new URLSearchParams(location.search).get("autoopen") === "1") store.command("file.open", { path: "/mock/demo.h5" });
}
