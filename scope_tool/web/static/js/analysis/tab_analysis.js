import { markerModel } from "./markers.js";
import { mount as mountMarkerTable } from "./marker_table.js";
// 離線分析頁：開檔指令 "file.open" 與 "open_waveform"（payload {path?}）等同處理；L3 擷取頁完成後會先切到本分頁再發 open_waveform。
// 佈局組裝主圖／縮圖／FFT 窗格，掛載 L5 模組（動態載入，缺檔顯示佔位），處理開檔與 viewport.intent。
import { autoScale } from "./scales.js";
import { bindViewport } from "./gestures.js";
import { fullRange } from "./overview.js";
import { clampLayout, loadPrefs, savePrefs, validatePrefs, resetPref } from "./layout.js";
import { mountTabs } from "./bpanel.js";
import { mountFloat } from "./floatpanel.js";
import { mountSplitter } from "./splitter.js";
import * as fmt from "../fmt.js";

const FALLBACK_COLORS = ["#F0E442", "#56B4E9", "#E58FC4", "#3DD6A3", "#E69F00", "#b79cff"];

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

// L5 模組與掛載點；B 區由量測／游標／FFT 峰值面板共用標題列。
const L5 = [["toolbar", "./toolbar.js", "analysis__toolbar"], ["measure", "./measure.js", "analysis__side"],
  ["chanbar", "./chanbar.js", "analysis__chanbar"], ["results", "./results.js", "analysis__results"], ["cursors", "./cursors.js", "analysis__cursors"]];

// 產品與自檢共用 command 接線；起點永遠取偏好，不把自動退讓當成使用者設定。
export function bindLayoutCommands(store, { schedule, dragging = () => {}, initial = loadPrefs(), persist = savePrefs, lowerLocked = () => false, viewport = () => innerWidth }) {
  let prefs = initial, effective, drawerOpen = false;
  const change = (p) => { const overview = p.overview; prefs = { ...validatePrefs(p), overview }; persist(prefs); schedule(); };
  const valid = (kind) => ['side','lower','fft'].includes(kind) && !(kind === 'lower' && lowerLocked());
  const state = (kind) => {
    const e = effective, value = prefs[kind] ?? (kind === 'side' ? 240 : kind === 'lower' ? 180 : 180);
    const shown = kind === 'side' ? (e.drawer ? e.drawerWidth : e.side) : e[kind];
    const max = kind === 'side' ? 360 : shown + Math.max(0,e.main-270);
    return { value, max, collapsed:e[kind+'Collapsed'], disabled:kind === 'fft' && e.tabbed, prefs };
  };
  store.onCommand('layout.resize', ({ kind, value }) => { if (valid(kind) && !state(kind).disabled) change({ ...prefs,[kind]:value,[kind+'Collapsed']:false }); });
  store.onCommand('layout.toggle', (kind) => {
    if (!valid(kind) || state(kind).disabled) return;
    if (kind === 'side' && viewport() <= 899) { drawerOpen = !drawerOpen; schedule(); }
    else change({ ...prefs,[kind+'Collapsed']:!effective[kind+'Collapsed'] });
  });
  store.onCommand('layout.reset', (kind) => { if (valid(kind)) { if (kind === 'side') drawerOpen = false; change(resetPref(prefs,kind)); } });
  store.onCommand('layout.markerSide', (on) => change({ ...prefs,markerSide:on ?? !prefs.markerSide }));
  store.onCommand('layout.restore', change);
  store.onCommand('layout.dragging', dragging);
  store.onCommand('preview.visible', (on) => { prefs = { ...prefs,overview:!!on }; schedule(); });
  store.onCommand('layout.query', () => { if (effective) store.command('layout.state',{ overview:!!effective.overview, blocked:!!effective.steps?.includes('overview') }); });
  return { state, get prefs() { return prefs; }, get drawerOpen() { return drawerOpen; },
    update(e) { effective = e; store.command('layout.state',{ overview:!!e.overview, blocked:!!e.steps?.includes('overview') }); } };
}

export function lowerSummary(st, fftOn) {
  return `量測 ${st.measurements.length}／FFT 峰值 ${fftOn && st.fftResult?.ok ? st.fftMarker?.shown ?? st.fftResult.peaks?.length ?? 0 : 0}${st.markerMode === 'Manual Y only' ? '' : '／ΔX ' + fmt.fmt(Number.isFinite(st.cursors.x1) && Number.isFinite(st.cursors.x2) ? st.cursors.x2-st.cursors.x1 : null, 's')}`;
}

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
      <div class="analysis__cursors"></div><div class="analysis__markers"></div><div class="analysis__peaks"></div></div>
    </div>
  </div>`;
  const q = (c) => el.querySelector("." + c);
  const fft = q("analysis__fft"), overview = q("analysis__overview");

  bindViewport(store);
  markerModel(ctx); mountMarkerTable(q("analysis__markers"), ctx);

  // 自家圖表
  const own = [["./axes.js", q("analysis__horizontal")], ["./mainplot.js", q("analysis__main")], ["./overview.js", overview], ["./fftpane.js", fft]];
  for (const [src, host] of own) import(src).then((m) => m.mount(host, ctx)).catch((e) => { host.textContent = `（圖表載入失敗：${e.message}）`; console.warn(src, e); });

  const actions = document.createElement('div'); actions.className = 'results__actions';
  for (const name of ['pointerdown','dblclick','keydown']) actions.addEventListener(name,e => e.stopPropagation());
  const resultsCtx = Object.assign(Object.create(ctx), { resultActions:actions, fftPeaks:q('analysis__peaks') });

  // L5 模組：缺檔或掛載失敗只影響該區塊
  for (const [name, src, cls] of L5) {
    const host = q(cls);
    import(src).then((m) => m.mount(host, name === "results" ? resultsCtx : ctx))
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

  // 原 P1 按鈕移入 splitter，只有同一份偏好與 effective 狀態。
  const root = q("analysis"), fftSection = q("analysis__fftsection");
  let fftOn = false, effective, frame = 0, activeTab = 'wave', floatPanel;
  const controller = bindLayoutCommands(store,{ schedule, lowerLocked:() => !!floatPanel?.floating || !!effective?.docked, dragging:(on) => { root.dataset.dragging = String(on); } });
  const buttons = { side:q('analysis__sidetoggle'), lower:q('analysis__lowertoggle'), fft:q('analysis__ffttoggle') };
  const tabs = document.createElement('div'); tabs.className = 'analysis__plotTabs'; tabs.setAttribute('role','tablist');
  tabs.innerHTML = '<button type="button" role="tab" data-pane="wave">波形</button><button type="button" role="tab" data-pane="fft">FFT</button>';
  q('analysis__plot').insertBefore(tabs,q('analysis__main'));
  tabs.onclick = (e) => { if (e.target.dataset.pane) { activeTab = e.target.dataset.pane; schedule(); } };
  const state = controller.state;
  const splitters = {};
  for (const kind of ['side','lower','fft']) {
    const host = document.createElement('div');
    if (kind === 'side') root.append(host);
    else if (kind === 'lower') q('analysis__lower').prepend(host);
    else fftSection.prepend(host);
    splitters[kind] = mountSplitter(host,{ kind, button:buttons[kind], store, getState:() => state(kind) });
  }
  const lowerHeader = buttons.lower.parentNode;
  const resultTabs = mountTabs(lowerHeader,{ measure:q('analysis__results'), cursor:q('analysis__cursors'), marker:q('analysis__markers'), peaks:q('analysis__peaks') },{ actions });
  lowerHeader.append(actions);
  const dockBtn = document.createElement('button'); dockBtn.type = 'button'; dockBtn.className = 'btn btn--small analysis__dockbtn';
  dockBtn.onclick = () => store.command('layout.markerSide');
  for (const name of ['pointerdown','dblclick','keydown']) dockBtn.addEventListener(name,e => e.stopPropagation());
  lowerHeader.append(dockBtn);
  const lowerBody = q('analysis__lowerbody');
  floatPanel = mountFloat(el,{ store, lower:q('analysis__lower'), header:lowerHeader, body:lowerBody,
    tabs:lowerHeader.querySelector('.analysis__resultTabs'), actions, schedule });
  function schedule() { if (!frame) frame = requestAnimationFrame(renderLayout); }
  function renderLayout() {
    frame = 0;
    const H = Math.max(0,root.clientHeight-q('analysis__toolbar').getBoundingClientRect().height-8);
    const chrome = q('analysis__chanbar').getBoundingClientRect().height+28;
    const floating = floatPanel.update();
    effective = clampLayout({ W:root.clientWidth, H, vw:innerWidth, vh:innerHeight, prefs:controller.prefs, lowerFloating:!!floating, drawerOpen:controller.drawerOpen, fftOn, chrome });
    controller.update(effective);
    const e = effective, plot = q('analysis__plot');
    root.style.gridTemplateColumns = `${e.side}px 10px minmax(0,1fr)${e.docked ? ` ${e.dockWidth}px` : ''}`;
    root.classList.toggle('analysis--dock',e.docked);
    dockBtn.hidden = !e.canDock; dockBtn.textContent = e.docked ? '⇤ 底部' : '⇥ 右側欄';
    dockBtn.title = e.docked ? '結果移回底部' : '結果移到右側欄'; dockBtn.setAttribute('aria-pressed',String(e.docked));
    root.style.gridTemplateRows = `auto minmax(0,1fr) ${e.lower}px`;
    root.classList.toggle('analysis--side-collapsed',e.sideCollapsed);
    root.classList.toggle('analysis--drawer',e.drawer);
    root.style.setProperty('--side-drawer-width',e.drawerWidth+'px');
    root.classList.toggle('analysis--lower-collapsed',e.lowerCollapsed);
    root.classList.toggle('analysis--fft',fftOn && !e.fftCollapsed);
    root.dataset.tabbed = String(e.tabbed);
    q('analysis__side').hidden = e.sideCollapsed;
    lowerBody.hidden = floating ? floating.collapsed : e.lowerCollapsed;
    buttons.lower.hidden = !!floating || e.docked;
    q('analysis__lower').style.height = e.docked ? '' : e.lower+'px';
    overview.hidden = !e.overview; overview.style.height = e.overview+'px';
    tabs.hidden = !e.tabbed;
    const waveHidden = e.tabbed && activeTab === 'fft';
    q('analysis__main').hidden = waveHidden; q('analysis__horizontal').hidden = waveHidden;
    q('analysis__main').style.height = e.main+'px';
    // 分頁共用同一塊空間；Horizontal 列在頻譜分頁留在尺寸預算內。
    fftSection.hidden = !fftOn || (e.tabbed && activeTab !== 'fft');
    fft.hidden = e.fftCollapsed; fft.style.height = e.fft+'px';
    plot.style.overflowY = e.scroll ? 'auto' : 'hidden';
    for (const tab of tabs.children) tab.setAttribute('aria-selected',String(tab.dataset.pane === activeTab));
    resultTabs.update({ width:floating?.width ?? lowerBody.clientWidth, height:floating?.height ?? e.lower, lowerCollapsed:floating ? floating.collapsed : e.lowerCollapsed, fftOn, docked:e.docked, count:store.get().fftResult?.ok ? store.get().fftMarker?.shown ?? store.get().fftResult.peaks?.length ?? 0 : 0 });
    const st = store.get();
    buttons.side.textContent = e.sideCollapsed ? '›' : '‹'; buttons.side.title = e.sideCollapsed ? '展開量測欄' : '收折量測欄';
    buttons.side.setAttribute('aria-label',buttons.side.title);
    buttons.lower.textContent = e.lowerCollapsed ? `▴ 展開結果（${lowerSummary(st,fftOn)}）` : '▾';
    buttons.lower.title = e.lowerCollapsed ? '展開結果' : '收折結果';
    buttons.lower.setAttribute('aria-label',buttons.lower.title);
    buttons.fft.textContent = `${e.fftCollapsed ? '▾ 展開' : '▴ 收折'} FFT 窗格`;
    for (const kind of ['side','lower','fft']) splitters[kind].update(state(kind));
    lowerHeader.tabIndex = floating ? -1 : 0; lowerHeader.setAttribute('aria-disabled',String(!!floating));
  }
  store.onCommand('fft.visible', (on) => { fftOn = !!on; schedule(); });
  store.on(['measurements','fftResult','fftMarker','cursors'],schedule);
  const observer = new ResizeObserver(schedule);
  for (const host of [root,q('analysis__toolbar'),q('analysis__chanbar')]) observer.observe(host);
  schedule();

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
