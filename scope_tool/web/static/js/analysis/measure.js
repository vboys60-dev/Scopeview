// 量測項目管理：新增／刪除、防抖 150 ms 呼叫 bridge.measure，結果寫入 store.measurements。
// store.measurements 每筆：{id, channel, name, rising, mode, result: MeasureResult|null（null＝計算中）}。
// 來源通道與邊緣方向在加入時固定；範圍、閾值、dx、游標（rangeMode=cursors 時）變動都會重算；過期（token／gen）結果丟棄。

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const num = (v) => typeof v === "number" && Number.isFinite(v);

/** 量測範圍（顯示時間）：rangeMode=cursors 且 x1、x2 都有值才切，否則 null＝全部。 */
export const rangeOf = (st) => (st.rangeMode === "cursors" && num(st.cursors.x1) && num(st.cursors.x2) ? [st.cursors.x1, st.cursors.x2] : null);
export const dxOf = (chs) => Object.fromEntries(chs.map((c) => [c.name, c.time_offset || 0]));
/** catalog 單位樣板（"{u}"、"{u}/s"）換成通道單位。 */
export const unitFor = (tpl, chUnit) => String(tpl ?? "").replace("{u}", chUnit);
export const failure = (reason, gen = 0, revision = 0) => ({ ok: false, stats: null, reason, gen, revision, channel: "", name: "", unit: "" });

export function createMeasure({ store, bridge }, { delay = 150, onError = () => {} } = {}) {
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
    const live = list.filter((e) => st.channels.some((c) => c.name === e.channel));
    let results = [];
    try {
      if (live.length) {
        const r = await bridge.job("measure", { entries: live.map(({ channel, name, rising, mode = "full" }) => ({ channel, name, rising, mode })), range: rangeOf(st), dx: dxOf(st.channels), threshold: st.threshold });
        if (my !== token || store.get().file?.gen !== gen || r.gen !== gen) return; // 過期丟棄
        results = r.results; lastRev = r.revision;
      }
    } catch (e) {
      if (my !== token) return;
      onError(e);
      results = live.map(() => failure(e.message, gen, lastRev));
    }
    // 前端自產的失敗列帶目前 gen／revision，rowState 才會視為「失敗」而非計算中，匯出也不被鎖
    const byId = new Map(live.map((e, i) => [e.id, results[i] ?? failure("沒有結果", gen, lastRev)]));
    setEntries(store.get().measurements.map((e) => ({ ...e, result: byId.get(e.id) ?? failure("來源通道已刪除", gen, lastRev) })));
  }
  function add(name, channel, rising, mode = "full") {
    if (!channel) return;
    store.set({ measurements: [...store.get().measurements, { id: nextId++, channel, name, rising, mode, result: null }] }, "program");
    schedule();
  }
  function remove(id) { store.set({ measurements: store.get().measurements.filter((e) => e.id !== id) }, "program"); schedule(); }
  function clear() { store.set({ measurements: [] }, "program"); token++; }

  let lastSig = "";
  const sigOf = (st) => JSON.stringify([rangeOf(st), dxOf(st.channels), st.threshold, st.channels.map((c) => c.name)]);
  store.on(["file", "channels", "threshold", "rangeMode", "cursors"], (st, keys) => {
    if (keys.includes("file")) { if (st.measurements.length) clear(); lastSig = sigOf(st); return; }
    const s = sigOf(st);
    if (s === lastSig) return; // 只有會影響結果的才重算
    lastSig = s;
    if (st.measurements.length) schedule();
  });
  lastSig = sigOf(store.get());
  return Object.assign(ctl, { add, remove, clear, schedule, run });
}

export function mount(el, ctx) {
  const { store } = ctx, cat = ctx.appState?.catalog ?? {};
  el.classList.add("measure");
  const m = createMeasure(ctx, { onError: (e) => ctx.ui.toast(e.message, "error") });
  // 結果表的刪除／清除由 results.js 發出 measure.remove／measure.clear 指令
  store.onCommand("measure.remove", (id) => m.remove(id));
  store.onCommand("measure.clear", () => m.clear());
  const slope = h("select", "select");
  slope.append(new Option("上升緣 ↑", "1"), new Option("下降緣 ↓", "0"));
  slope.title = "週期、頻率、工作週期、過衝、前衝及整數週期使用的邊緣方向";
  const mode = h("select", "select"); mode.title = "Vavg／Vrms 的區間";
  mode.append(new Option("整段（Full Screen）", "full"), new Option("整數週期（N Cycles）", "cycles"));
  el.append(slope, h("label", "field__label", "區間"), mode);
  for (const category of ["時間", "電壓"]) {
    const box = h("div", "field"); box.append(h("div", "field__label", `${category}量測`));
    for (const it of (cat.measurements ?? []).filter((x) => x.category === category)) {
      const b = h("button", "btn btn--small", it.name + (it.sloped ? " ↕" : ""));
      b.title = it.tip; b.type = "button";
      b.onclick = () => {
        const st = store.get();
        if (!st.file) return;
        m.add(it.name, st.selected, slope.value === "1", mode.value);
      };
      box.append(b);
    }
    el.append(box);
  }
}
