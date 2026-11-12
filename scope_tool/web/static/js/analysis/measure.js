// 量測項目管理：新增／刪除、防抖 150 ms 呼叫 bridge.measure，結果寫入 store.measurements。
// store.measurements 每筆：{id, channel, channel2?, name, rising, rising2?, mode, all_edges, result: MeasureResult|null（null＝計算中）}。
// 來源通道與邊緣方向在加入時固定；範圍、閾值、dx、游標（rangeMode=cursors 時）變動都會重算；過期（token／gen）結果丟棄。
import { T } from "./terms.js";
import { RECT_MIN_PX } from "./gestures.js";

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const num = (v) => typeof v === "number" && Number.isFinite(v);

/** 量測範圍（顯示時間）：rangeMode=cursors 且 x1、x2 都有值才切，否則 null＝全部。 */
export const rangeOf = (st) => (st.rangeMode === "cursors" && num(st.cursors.x1) && num(st.cursors.x2) ? [st.cursors.x1, st.cursors.x2] : null);
export const dxOf = (chs) => Object.fromEntries(chs.map((c) => [c.name, c.time_offset || 0]));
/** catalog 單位樣板（"{u}"、"{u}/s"）換成通道單位。 */
export const unitFor = (tpl, chUnit) => String(tpl ?? "").replace("{u}", chUnit);
export const failure = (reason, gen = 0, revision = 0) => ({ ok: false, stats: null, reason, gen, revision, channel: "", name: "", unit: "" });

/** 位移達 RECT_MIN_PX（6 px）才算拖曳，未達視為點擊。 */
export const isDrag = (dx, dy) => Math.hypot(dx, dy) >= RECT_MIN_PX;
/** 放置目標：元素所在的通道列欄位（[data-channel]）通道名，沒有就是 null。 */
export const dropChannel = (el, x, y) => el?.closest?.("[data-channel]")?.dataset.channel ?? el?.hitChannel?.(x, y) ?? null; // 主圖 canvas 由 hitChannel 回傳游標下最近的波形

// 視窗層監聽（Esc、blur、pointerup）整個模組只掛一次，交給最近一次 mount 的處理函式。
let winHooks = null, winHooked = false;
function hookWindow(hooks) {
  winHooks?.blur(); // 先結束舊 mount 的拖曳／長按等待（清計時器、標籤、樣式、capture，不新增）
  winHooks = hooks;
  const w = globalThis.window;
  if (winHooked || !w?.addEventListener) return;
  winHooked = true;
  for (const k of ["keydown", "blur"]) w.addEventListener(k, (e) => winHooks[k](e));
  // 指標事件掛在 window 的 capture 階段：按下後快速移出按鈕（尚未 setPointerCapture）也收得到
  for (const k of ["pointermove", "pointerup", "pointercancel"]) w.addEventListener(k, (e) => winHooks[k](e), true);
}

export function createMeasure({ store, bridge, appState }, { delay = 150, onError = () => {} } = {}) {
  const dual = name => (appState?.catalog?.measurements ?? []).some(m => m.name === name && m.sources === 2);
  let token = 0, timer = null, nextId = 1, lastRev = 0;
  const ctl = {};
  const setEntries = (list) => store.set({ measurements: list }, "program");

  function schedule() {
    token++;
    clearTimeout(timer);
    const list = store.get().measurements;
    if (!list.length) return;
    setEntries(list.map((e) => ({ ...e, result: null }))); // 先顯示「…」，舊值不留
    timer = setTimeout(run, delay);
  }
  async function run() {
    const my = token, st = store.get(), gen = st.file?.gen, list = st.measurements;
    if (!list.length || !st.file) return;
    // 刪除來源也送入同一批，讓後端快照與畫面保留相同列數。
    let results = [];
    try {
      const entries = list.map(({ channel, channel2, name, rising, rising2, mode = "full", all_edges = true, edge_num, edge_num2, edge_level, edge_level2, track }) => ({
        channel, name, rising, mode, all_edges,
        ...(channel2 === undefined ? {} : { channel2, rising2: rising2 ?? rising }),
        ...(name === "Delta Time" ? { edge_num, edge_num2, edge_level, edge_level2 } : {}), ...(track ? { track: true } : {}),
      }));
      const r = await bridge.job("measure", { entries, range: rangeOf(st), dx: dxOf(st.channels), threshold: st.threshold });
      if (my !== token || store.get().file?.gen !== gen || r.gen !== gen) return; // 過期丟棄
      results = r.results; lastRev = r.revision;
    } catch (e) {
      if (my !== token) return;
      onError(e);
      results = list.map(() => failure(e.message, gen, lastRev));
    }
    // 前端自產的失敗列帶目前 gen／revision，rowState 才會視為「失敗」而非計算中，匯出也不被鎖
    const byId = new Map(list.map((e, i) => [e.id, results[i] ?? failure("沒有結果", gen, lastRev)]));
    const names = new Set(st.channels.map(c => c.name));
    setEntries(store.get().measurements.map(e => {
      const result = byId.get(e.id), deleted = !names.has(e.channel) || (dual(e.name) && !names.has(e.channel2));
      return { ...e, result: deleted ? { ...result, channel:e.channel, name:e.name,
        ...(dual(e.name) ? {channel2:e.channel2} : {}), ok:false, stats:null, reason:"來源通道已刪除" } : result };
    }));
  }
  function add(name, channel, rising, mode = "full", channel2, rising2 = rising, all_edges = true, delta = {}) {
    if (!channel) return;
    store.set({ measurements: [...store.get().measurements, { id: nextId++, channel, name, rising, mode, all_edges, ...(channel2 === undefined ? {} : { channel2, rising2 }), ...(name === "Delta Time" ? { edge_num: 1, edge_num2: 1, edge_level: "middle", edge_level2: "middle", ...delta } : {}), result: null }] }, "program");
    if (store.get().markerMode === "Track Measurements" && !store.get().measurements.some(e => e.track)) track(store.get().measurements[0].id); else schedule();
  }
  function track(id) {
    const list = store.get().measurements;
    if (!list.some(e => e.id === id) || list.some(e => e.id === id && e.track)) return;
    setEntries(list.map(e => ({ ...e, track: e.id === id }))); schedule();
  }
  store.on(["markerMode"], st => {
    if (st.markerMode === "Track Measurements") { if (!st.measurements.some(e => e.track) && st.measurements.length) track(st.measurements[0].id); }
    else if (st.measurements.some(e => e.track)) setEntries(st.measurements.map(({ track, ...e }) => e));
  });
  function remove(id) { store.set({ measurements: store.get().measurements.filter((e) => e.id !== id) }, "program"); schedule(); }
  function clear() { store.set({ measurements: [] }, "program"); token++; }

  let lastSig = "";
  const sigOf = (st) => JSON.stringify([st.dataRev, rangeOf(st), dxOf(st.channels), st.threshold, st.channels.map((c) => c.name)]);
  store.on(["file", "dataRev", "channels", "threshold", "rangeMode", "cursors"], (st, keys) => {
    if (keys.includes("file")) { if (st.measurements.length) clear(); lastSig = sigOf(st); return; }
    const s = sigOf(st);
    if (s === lastSig) return; // 只有會影響結果的才重算
    lastSig = s;
    if (st.measurements.length) schedule();
  });
  lastSig = sigOf(store.get());
  return Object.assign(ctl, { add, remove, clear, track, schedule, run });
}

export function mount(el, ctx) {
  const { store } = ctx, cat = ctx.appState?.catalog ?? {};
  el.classList.add("measure");
  const head = h("div", "measure__head"), source = h("select", "select"), range = h("select", "select"), threshold = h("select", "select");
  range.append(new Option("全部", "all"), new Option("游標區間", "cursors")); range.title = "量測與 FFT 的計算範圍";
  threshold.append(...Object.keys(cat.thresholds ?? { "10/50/90 %": 0 }).map(k => new Option(k, k)));
  for (const [label, ctl, key] of [["來源", source, "selected"], ["範圍", range, "rangeMode"], ["閾值", threshold, "threshold"]]) {
    const caption = h("label", "field__label", label); ctl.id = `measure-${key}`; caption.htmlFor = ctl.id;
    head.append(caption, ctl); ctl.onchange = () => store.set({ [key]: ctl.value }, "user");
  }
  el.append(head);
  const syncHead = (st) => { source.replaceChildren(...st.channels.map(c => new Option(c.name, c.name))); source.value = st.selected ?? ""; range.value = st.rangeMode; threshold.value = st.threshold; for (const ctl of [source, range, threshold]) ctl.disabled = !st.file; };
  store.on(["channels", "selected", "rangeMode", "threshold", "file"], syncHead); syncHead(store.get());
  const m = createMeasure(ctx, { onError: (e) => ctx.ui.toast(e.message, "error") });
  // 結果表的刪除／清除由 results.js 發出 measure.remove／measure.clear 指令
  store.onCommand("measure.track", (id) => m.track(id));
  store.onCommand("measure.remove", (id) => m.remove(id));
  store.onCommand("measure.clear", () => m.clear());
  const slope = h("select", "select");
  slope.append(new Option("上升緣 ↑", "1"), new Option("下降緣 ↓", "0"));
  slope.title = "週期、頻率、工作週期、過衝、前衝、延遲、相位及整數週期使用的來源 1 邊緣方向";
  const mode = h("select", "select"); mode.title = "Vavg／Vrms 的區間";
  mode.append(new Option("Full Screen", "full"), new Option("N Cycles", "cycles"), new Option("One Cycle", "cycle"));
  const allEdges = h("input"); allEdges.type = "checkbox"; allEdges.checked = true;
  allEdges.title = "只影響之後新增的量測；未勾選時統計只取最接近參考點的單一事件（相位仍使用全部邊緣）";
  const edgesLabel = h("label", "field__label"); edgesLabel.title = allEdges.title; edgesLabel.append(allEdges, h("span", "", "全部邊緣"));
  el.append(slope, h("label", "field__label", T("區間")), mode, edgesLabel);
  const source2 = h("select", "select"), slope2 = h("select", "select"), dualButtons = [];
  let source2Set = false;
  source2.onchange = () => { source2Set = true; };
  source2.title = "來源 2"; slope2.title = "來源 2 邊緣";
  slope2.append(new Option("同來源 1", "same"), new Option("上升緣 ↑", "1"), new Option("下降緣 ↓", "0"));
  slope2.value = "same";
  const nums = [1, 2].map(() => { const e = h("input", "input"); e.type = "number"; e.min = 1; e.max = 65534; e.step = 1; e.value = 1; return e; });
  const levels = [1, 2].map(() => { const e = h("select", "select"); e.append(new Option("下", "lower"), new Option("中", "middle"), new Option("上", "upper")); e.value = "middle"; return e; });
  // 拖放：量測鈕拖到通道列欄位＝以該通道為來源 1 新增；位移 <6 px 仍是點擊，觸控需長按 300 ms。
  let drag = null, swallow = false;
  const targets = () => [...(document.querySelectorAll?.("[data-channel]") ?? [])];
  function addFrom(it, channel) { // 點擊與拖放共用
    const st = store.get();
    if (!st.file || (it.sources === 2 && st.channels.length < (it.name === "Delta Time" ? 1 : 2))) return;
    const rising2 = slope2.value === "same" ? slope.value === "1" : slope2.value === "1";
    m.add(it.name, channel, slope.value === "1", mode.value, it.sources === 2 ? source2.value : undefined, rising2, allEdges.checked, { edge_num: Number(nums[0].value), edge_num2: Number(nums[1].value), edge_level: levels[0].value, edge_level2: levels[1].value });
  }
  function over(x, y) {
    const ch = dropChannel(document.elementFromPoint(x, y), x, y);
    for (const c of targets()) c.classList.toggle("is-dropover", c.dataset.channel === ch);
    Object.assign(drag.tag.style, { left: `${x + 12}px`, top: `${y + 12}px` });
    drag.tag.textContent = `${T(drag.it.name)} → ${ch ?? "?"}`;
    return ch;
  }
  function begin(x, y) {
    const st = store.get();
    if (!st.file || (drag.it.sources === 2 && st.channels.length < (drag.it.name === "Delta Time" ? 1 : 2))) return end();
    drag.active = true;
    drag.b.setPointerCapture?.(drag.id);
    drag.tag = h("div", "measure__dragtag"); document.body.append(drag.tag);
    for (const c of targets()) c.classList.add("is-droptarget");
    over(x, y);
  }
  function end(drop, x, y) {
    if (!drag) return;
    const d = drag; clearTimeout(d.timer);
    const ch = d.active && drop ? dropChannel(document.elementFromPoint(x, y), x, y) : null;
    drag = null;
    if (!d.active) { if (!drop) swallow = true; return; } // 按住等待中被取消（Esc／blur／換 mount／短滑）：緊接的指標 click 也不新增
    swallow = true; // 吞掉緊接的指標 click（放下或取消都不可再新增到 selected）；鍵盤 click 不受影響
    d.tag.remove();
    for (const c of targets()) c.classList.remove("is-droptarget", "is-dropover");
    if (d.b.hasPointerCapture?.(d.id)) d.b.releasePointerCapture(d.id);
    if (ch) addFrom(d.it, ch);
  }
  const hooks = {
    // Esc：拖曳中或觸控長按等待中都取消（end 會清計時器）
    keydown: (e) => { if (e.key === "Escape" && drag) { if (drag.active) e.preventDefault(); end(); } },
    blur: () => end(),
    pointermove: (e) => {
      if (drag?.id !== e.pointerId) return;
      if (drag.active) { e.preventDefault(); over(e.clientX, e.clientY); return; }
      if (!isDrag(e.clientX - drag.x, e.clientY - drag.y)) return;
      if (drag.touch) end(); else begin(e.clientX, e.clientY); // 觸控未滿 300 ms 就移動＝短滑，不拖
    },
    // 放下；之後（含其 click）解除吞 click，沒有 pointerup 時由下一次 pointerdown 解除
    pointerup: (e) => { if (drag?.id === e.pointerId) end(true, e.clientX, e.clientY); setTimeout(() => { swallow = false; }); },
    pointercancel: (e) => { if (drag?.id === e.pointerId) end(); },
  };
  hookWindow(hooks);
  function draggable(b, it) {
    b.style.touchAction = "pan-y";
    b.addEventListener("pointerdown", (e) => {
      end(); swallow = false;
      if (e.button !== 0 || winHooks !== hooks) return; // 已被新 mount 取代：只留點擊，不再拖曳
      drag = { b, it, id: e.pointerId, x: e.clientX, y: e.clientY, active: false, touch: e.pointerType === "touch" };
      if (drag.touch) drag.timer = setTimeout(() => drag && begin(drag.x, drag.y), 300);
    });
    b.addEventListener("lostpointercapture", () => { if (drag?.b === b) end(); }); // pointermove／up／cancel 在 window 層
    b.addEventListener("contextmenu", (e) => { if (drag?.b === b && drag.touch) e.preventDefault(); }); // 長按不跳出選單
  }
  const hint = (st) => `\n點擊：加到目前通道（${st.selected ?? "?"}）；拖到通道列可指定來源`;
  const allButtons = [];
  function sources(st) {
    const old = source2.value;
    source2.replaceChildren(...st.channels.map(c => new Option(c.name, c.name)));
    if (!st.channels.some(c => c.name === old)) source2Set = false;
    const keep = st.channels.some(c => c.name === old) && (source2Set || old !== st.selected);
    const other = st.channels.find(c => c.name !== st.selected)?.name;
    source2.value = keep ? old : (other ?? st.channels[0]?.name ?? "");
    for (const [b, tip] of allButtons) b.title = tip + hint(st);
    for (const [b, tip, name] of dualButtons) { b.disabled = st.channels.length < (name === "Delta Time" ? 1 : 2); b.title = b.disabled ? "至少需要兩個來源通道" : tip + hint(st); }
  }
  store.on(["channels", "selected"], sources);
  for (const category of ["時間", "電壓", "雙來源"]) {
    const box = h("div", "field"); box.append(h("div", "field__label", `${T(category)} Measurements`));
    if (category === "雙來源") {
      box.append(h("label", "field__label", "來源 2"), source2, h("label", "field__label", "來源 2 邊緣"), slope2);
      if ((cat.measurements ?? []).some(it => it.name === "Delta Time")) {
        const grid = h("div", "measure__dual");
        for (const [label, control] of [["邊緣 #1", nums[0]], ["邊緣 #2", nums[1]], ["閾值層 1", levels[0]], ["閾值層 2", levels[1]]]) { const l = h("label", "field__label", label); l.append(control); grid.append(l); }
        box.append(grid);
      }
    }
    for (const it of (cat.measurements ?? []).filter((x) => x.category === category)) {
      const b = h("button", "btn btn--small", T(it.name) + (it.sloped ? " ↕" : ""));
      if (it.sources === 2) dualButtons.push([b, it.tip, it.name]);
      else allButtons.push([b, it.tip]);
      b.title = it.tip; b.type = "button";
      // 鍵盤觸發的 click（detail===0）一律不吞，取消後殘留的旗標不會吃掉 Enter／Space
      b.onclick = (e) => { if (swallow && e?.detail !== 0) { swallow = false; return; } addFrom(it, store.get().selected); };
      draggable(b, it);
      box.append(b);
    }
    el.append(box);
  }
  sources(store.get());
}
