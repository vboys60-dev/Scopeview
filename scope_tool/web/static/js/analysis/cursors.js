// 游標與 Marker：cursors 的唯一寫入者。store.cursors 的 x＝顯示時間（秒）、y＝顯示格數；
// 送後端前在此換成來源座標：x_src＝x−dx[ch]、y_src＝(y−position)×scale。對照 ui/analysis_marker.py。
// 防迴圈：吸附回寫一律 origin="snap"，本模組遇 snap 不再觸發重算；回寫值與現值幾乎相同就不寫。
// 處理 cursor.intent、rf.intent；寫 store.markerResult={mode, points:[{x,y,label}]}（顯示座標，主圖繪製）。
// 待真人驗證：拖曳手感、DOM 排版。

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const num = (v) => typeof v === "number" && Number.isFinite(v);

export const dxMap = (chs) => Object.fromEntries(chs.map((c) => [c.name, c.time_offset || 0]));
const chan = (st, name) => st.channels.find((c) => c.name === name) ?? null;
/** 顯示座標 → 來源座標（null 保持 null）。 */
export function toSource(cur, ch) {
  const t = (v) => (num(v) ? v - ch.time_offset : null), y = (v) => (num(v) ? (v - ch.position) * ch.scale : null);
  return { x1: t(cur.x1), x2: t(cur.x2), y1: y(cur.y1), y2: y(cur.y2) };
}
/** 來源 (x,y) → 顯示 (x,y)。 */
export const toDisplay = (x, y, ch) => [x + (ch.time_offset || 0), y / ch.scale + ch.position];
const differs = (a, b) => (a === null) !== (b === null) || (a !== null && Math.abs(a - b) > 1e-12 * Math.max(1, Math.abs(a)));
/** 預設游標：X 在範圍 25%／75%、Y 在 ±2 格。 */
export const defaultCursors = (v) => ({ x1: v.t0 + 0.25 * (v.t1 - v.t0), x2: v.t0 + 0.75 * (v.t1 - v.t0), y1: 2, y2: -2 });
export const MODE_AXES = (m) => ({ x: m === null || ["Manual X only", "Manual X and Y", "Track Waveforms"].includes(m), y: m === null || ["Manual Y only", "Manual X and Y"].includes(m) });

/** 控制器：不碰 DOM，方便純邏輯測試。onReadout(readout|null) 通知畫面。 */
export function createController({ store, bridge }, { delay = 40, onReadout = () => {}, onError = () => {} } = {}) {
  let token = 0, rfToken = 0, timer = null, pendingInit = false;
  const ctl = { readout: null };
  const emit = (r) => { ctl.readout = r; onReadout(r); };

  function setSnap(patch) { // 只在真的不同時以 snap 回寫
    const cur = store.get().cursors;
    if (Object.keys(patch).some((k) => differs(cur[k], patch[k]))) store.set({ cursors: { ...cur, ...patch } }, "snap");
  }
  function schedule() {
    token++;
    clearTimeout(timer);
    timer = setTimeout(refresh, delay);
  }

  async function refresh() {
    const my = token, st = store.get(), cur = st.cursors, gen = st.file?.gen;
    const alive = () => my === token && store.get().file?.gen === gen;
    if (!st.file) return emit(null);
    const mode = st.markerMode, ch = chan(st, st.selected);
    try {
      if (mode === null) {
        if (!num(cur.x1) && !num(cur.x2)) return emit(null);
        const r = await bridge.call("cursor_readout", { t1: cur.x1 ?? cur.x2, t2: cur.x2 ?? cur.x1, dx: dxMap(st.channels) });
        if (!alive()) return;
        const p = {}; // 吸附第一通道取樣點；只回寫有設定的那條
        if (num(cur.x1)) p.x1 = r.t1;
        if (num(cur.x2)) p.x2 = r.t2;
        setSnap(p);
        const v = (y) => (ch && num(y) ? (y - ch.position) * ch.scale : null);
        const [v1, v2] = [v(cur.y1), v(cur.y2)];
        emit({ kind: "legacy", t1: r.t1, t2: r.t2, v1, v2, unit: ch?.unit ?? "", source: ch?.name ?? "", y: r.y, mode });
        store.set({ markerResult: null }, "program");
        return;
      }
      if (!ch) return emit(null);
      if (mode === "Track Measurements") { // MeasureResult 無事件座標，已知限制：明確提示，不送空陣列
        store.set({ markerResult: null }, "program");
        return emit({ kind: "unsupported", reason: "Track Measurements 尚未支援" });
      }
      const src = toSource(cur, ch), v = st.view;
      const r = await bridge.call("marker_eval", { mode, channel: ch.name, ...src, screen_width: v.t1 - v.t0, measurements: [] }); // 只有非 Track Measurements 模式會走到這裡
      if (!alive()) return;
      const p = r.position, dx1 = ch.time_offset || 0;
      if (mode === "Track Waveforms" && r.available) {
        const [x1] = toDisplay(p.x1, 0, ch), [x2] = toDisplay(p.x2, 0, ch);
        setSnap({ x1, x2 });
      }
      const pts = r.points.map(([x, y, label]) => [...toDisplay(x, y, ch), label]);
      store.set({ markerResult: { mode, available: r.available, reason: r.reason, points: pts.map(([x, y, label]) => ({ x, y, label })) } }, "program");
      emit({ kind: "marker", mode, t1: num(p.x1) ? p.x1 + dx1 : null, t2: num(p.x2) ? p.x2 + dx1 : null, v1: p.y1, v2: p.y2, unit: ch.unit, source: ch.name,
        dx: r.delta_x, inv: r.inverse_delta_x, dy: r.delta_y, available: r.available, reason: r.reason, read_only: r.read_only, y: {} });
    } catch (e) { if (alive()) { emit(null); if (e.code !== "STALE") onError(e); } }
  }

  /** 新檔載入後放預設游標（每次換檔一次，須在通道到位後）。 */
  function ensureDefaults() {
    const st = store.get();
    if (!st.file || !pendingInit) return;
    const cs = st.channels.filter((c) => num(c.t0) && num(c.t1));
    if (!cs.length) return;
    pendingInit = false; // 以檔案時間範圍（不依賴 view，避免吃到上一檔的舊視圖）
    store.set({ cursors: defaultCursors({ t0: Math.min(...cs.map((c) => c.t0)), t1: Math.max(...cs.map((c) => c.t1)) }) }, "program");
  }
  const chSig = () => store.get().channels.map((c) => `${c.name}:${c.time_offset}:${c.scale}:${c.position}`).join(",") + "|" + store.get().selected;
  let lastSig = chSig();
  store.on(["file", "view", "cursors", "markerMode", "selected", "channels"], (s, keys, origin) => {
    if (keys.includes("file")) { // 換檔／關檔：游標清空，等新通道（L4 的 setChannels 在 file 之後）到位再放預設
      pendingInit = !!s.file; token++; emit(null);
      store.set({ cursors: { x1: null, x2: null, y1: null, y2: null }, markerResult: null }, "program");
    }
    if (keys.includes("channels")) ensureDefaults();
    if (origin === "snap") return;
    const sig = chSig();
    const chChanged = keys.some((k) => k === "channels" || k === "selected") && sig !== lastSig;
    lastSig = sig;
    if (keys.some((k) => ["file", "cursors", "markerMode"].includes(k)) || chChanged || (keys.includes("view") && s.markerMode === "Track Waveforms")) schedule();
  });
  store.onCommand("cursor.intent", ({ which, value }) => {
    if (!["x1", "x2", "y1", "y2"].includes(which) || !(value === null || num(value))) return;
    store.set({ cursors: { ...store.get().cursors, [which]: value } }, "user");
  });
  store.onCommand("rf.intent", async ({ direction, x }) => {
    const fr = store.get().fftResult;
    if (!fr?.spectrum_id || ![-1, 0, 1].includes(direction) || !num(x)) return;
    const my = ++rfToken, sid = fr.spectrum_id;
    try {
      const r = await bridge.call("fft_track_rf", { spectrum_id: sid, x, direction, level: fr.peak_level ?? -40 });
      if (my !== rfToken || store.get().fftResult?.spectrum_id !== sid) return; // 過期丟棄
      store.set({ rfPos: { x: r.x, y: r.y, available: r.available, reason: r.reason } }, "user");
    } catch (e) { if (e.code !== "STALE") onError(e); }
  });
  return Object.assign(ctl, { refresh, schedule });
}

/** 游標表讀值；ΔY/ΔX 的缺值與有限值規則對齊 analysis/marker.py。 */
export function cursorRows(r, fmt) {
  if (!r || r.kind === "unsupported") return [];
  const m = r.kind === "marker", L = m ? ["X1", "X2", "ΔX", "1/ΔX", "Y1", "Y2", "ΔY"] : ["t1", "t2", "Δt", "1/Δt", "v1", "v2", "ΔV"];
  const dt = m ? r.dx : (num(r.t1) && num(r.t2) ? r.t2 - r.t1 : null), dy = m ? r.dy : (num(r.v1) && num(r.v2) ? r.v2 - r.v1 : null);
  const inv = m ? r.inv : dt ? 1 / dt : null;
  const f = [[r.t1, "s"], [r.t2, "s"], [dt, "s"], [inv, "Hz"], [r.v1, r.unit], [r.v2, r.unit], [dy, r.unit]];
  const rows = L.map((l, i) => [l, fmt(f[i][0], f[i][1])]);
  const slope = num(dt) && num(dy) && dt !== 0 ? dy / dt : null;
  rows.push(["ΔY/ΔX", num(slope) ? fmt(slope, r.unit ? `${r.unit}/s` : "1/s") : ""]);
  rows.push(["換算來源", r.source]);
  if (m) rows.push(["Delta To", "X1↔X2；Y1↔Y2"]);
  return rows;
}

export function mount(el, ctx) {
  const { store, ui, fmt } = ctx;
  el.classList.add("cursors");
  const info = h("div", "muted"), inputs = h("div", "row"), tbl = h("table", "table table--num"), chTbl = h("table", "table table--num");
  const boxes = {};
  for (const [k, label] of [["x1", "X1"], ["x2", "X2"], ["y1", "Y1"], ["y2", "Y2"]]) {
    const i = h("input", "input"); i.style.width = "7em"; i.title = k[0] === "x" ? `${label}（時間，如 1.5m）` : `${label}（格數）`;
    i.onchange = () => {
      const t = i.value.trim(), v = t === "" ? null : k[0] === "x" ? fmt.parseSI(t) : Number(t);
      if (v === null || Number.isFinite(v)) store.command("cursor.intent", { which: k, value: v }); else syncInputs();
    };
    boxes[k] = i;
    const f = h("label", "field", label + " "); f.append(i); inputs.append(f);
  }
  function syncInputs() {
    const { cursors, markerMode } = store.get(), ax = MODE_AXES(markerMode);
    for (const k of Object.keys(boxes)) {
      boxes[k].parentNode.hidden = !ax[k[0]];
      if (document.activeElement !== boxes[k]) boxes[k].value = cursors[k] === null ? "" : k[0] === "x" ? fmt.fmt(cursors[k], "s") : String(Number(cursors[k].toFixed(3)));
    }
  }
  const fill = (t, head, rows) => t.replaceChildren(...[head, ...rows].filter(Boolean).map((r, i) => { const tr = h("tr"); r.forEach((c) => tr.append(h(i === 0 && head ? "th" : "td", "", c))); return tr; }));
  function render(r) {
    syncInputs();
    info.textContent = r?.kind === "unsupported" ? r.reason : r && r.kind === "marker" && !r.available ? r.reason : r?.read_only ? "Track Measurements 為唯讀位置" : "";
    fill(tbl, null, cursorRows(r, fmt.fmt));
    const cs = store.get().channels;
    fill(chTbl, ["通道", "@t1", "@t2", "Δ(t2−t1)"], r?.kind === "legacy"
      ? cs.filter((c) => r.y[c.name]).map((c) => { const { y1, y2 } = r.y[c.name]; return [c.name, fmt.fmt(y1, c.unit), fmt.fmt(y2, c.unit), y1 === null || y2 === null ? "—" : fmt.fmt(y2 - y1, c.unit)]; }) : []);
  }
  createController(ctx, { onReadout: render, onError: (e) => ui.toast(e.message, "error") });
  store.on(["cursors", "markerMode"], syncInputs);
  el.append(inputs, info, tbl, chTbl);
  render(null);
}
