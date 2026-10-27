// 全域縮圖：整段原始通道的包絡，加上可拖曳的視窗方框（對應主圖 view）。只發 viewport.intent。
import { linear, envPixels, drawPixels, makeLatest, createCanvas, plotColors } from "./plotcore.js";

/** 檔案的整段時間範圍（所有通道的 t0 最小、t1 最大）；無通道回 null。 */
export function fullRange(file) {
  const cs = file?.channels ?? [];
  if (!cs.length) return null;
  return { t0: Math.min(...cs.map((c) => c.t0)), t1: Math.max(...cs.map((c) => c.t1)) };
}
/** 依拖曳起點判斷動作：edge0／edge1（調整邊界）、move（整框平移）、jump（點框外：以該處為中心）。 */
export function hitRegion(x, xa, xb, tol = 6) {
  if (Math.abs(x - xa) <= tol) return "edge0";
  if (Math.abs(x - xb) <= tol) return "edge1";
  return x > xa && x < xb ? "move" : "jump";
}
/** 依動作與位移（時間單位）算新視窗；至少保留 minSpan。 */
export function dragRegion(mode, v, dt, tAt, minSpan) {
  if (mode === "move") return { t0: v.t0 + dt, t1: v.t1 + dt };
  if (mode === "edge0") return { t0: Math.min(v.t0 + dt, v.t1 - minSpan), t1: v.t1 };
  if (mode === "edge1") return { t0: v.t0, t1: Math.max(v.t1 + dt, v.t0 + minSpan) };
  const half = (v.t1 - v.t0) / 2;
  return { t0: tAt - half, t1: tAt + half };
}

export function mount(el, { store, bridge }) {
  const cache = new Map(); // name → env
  const latest = makeLatest();
  let drag = null, W = 0, H = 0, draggingLayout = false, missed = false, loadedWidth = 0;
  const cv = createCanvas(el, (w, h) => {
    W = w; H = h; draw();
    if (w !== loadedWidth && !draggingLayout) { loadedWidth = w; load(); }
  });
  store.onCommand('layout.dragging', (on) => {
    draggingLayout = on;
    if (!on && (missed || W !== loadedWidth)) { missed = false; loadedWidth = W; load(); }
  });
  const { canvas, ctx: g } = cv;
  const rawChannels = () => store.get().channels.filter((c) => !c.derived && c.visible);
  const full = () => fullRange(store.get().file);
  const X = () => { const f = full() ?? { t0: 0, t1: 1 }; return linear(f.t0, f.t1, 0, W); };

  function draw() {
    if (!W || !H) return;
    const s = store.get(), col = plotColors();
    g.fillStyle = col.bg; g.fillRect(0, 0, W, H);
    const x = X(), cs = rawChannels();
    const los = cs.map((c) => c.vmin).filter((v) => v != null), his = cs.map((c) => c.vmax).filter((v) => v != null);
    const lo = Math.min(...los), hi = Math.max(...his), span = hi > lo ? hi - lo : 1;
    const Y = (v) => 3 + (hi - v) / span * (H - 6);
    for (const c of cs) {
      const env = cache.get(c.name);
      if (env) drawPixels(g, envPixels(env, (t) => x(t + c.time_offset), Y), c.color); // 與主圖同樣套用顯示時間位移
    }
    if (full()) {
      const a = x(s.view.t0), b = x(s.view.t1);
      g.fillStyle = col.ovShade; g.fillRect(a, 0, Math.max(b - a, 1), H);
      g.strokeStyle = col.ovWin; g.strokeRect(a + 0.5, 0.5, Math.max(b - a, 1), H - 1);
    }
  }
  function load() {
    if (draggingLayout) { missed = true; return; }
    const s = store.get(), f = full();
    if (!f || W < 2 || s.file?.gen === undefined) return;
    const req = latest.begin(), gen = s.file.gen;
    for (const c of rawChannels()) {
      bridge.fetchWave({ ch: c.name, t0: f.t0, t1: f.t1, px: Math.min(16384, W), gen, signal: req.signal })
        .then((env) => { if (req.ok()) { cache.set(c.name, env); draw(); } })
        .catch(() => {}); // 縮圖失敗不打擾使用者（主圖會提示）
    }
  }
  store.on(["file", "dataRev", "channels"], (_s, keys) => {
    if (keys.includes("file") || keys.includes("dataRev")) cache.clear();
    draw();
    // 只有檔案或可見的原始通道集合改變才重抓（改 scale／position／dx 不必）
    const sig = rawChannels().map((c) => c.name).join();
    if (keys.includes("file") || keys.includes("dataRev") || sig !== load.sig) { load.sig = sig; load(); }
  });
  store.on(["view"], draw);

  const px = (e) => e.clientX - canvas.getBoundingClientRect().left;
  canvas.addEventListener("pointerdown", (e) => {
    const f = full();
    if (!f || e.button !== 0) return;
    const v = store.get().view, x = X(), mode = hitRegion(px(e), x(v.t0), x(v.t1));
    store.command("view.historyGroup", { key: "overview", continuous: true });
    drag = { mode, x0: px(e), view: v };
    canvas.setPointerCapture(e.pointerId);
    if (mode === "jump") emit(e);
  });
  function emit(e) {
    const f = full(), x = X(), dt = x.inv(px(e)) - x.inv(drag.x0);
    store.command("viewport.intent", dragRegion(drag.mode, drag.view, dt, x.inv(px(e)), (f.t1 - f.t0) / Math.max(W, 1) * 4));
  }
  canvas.addEventListener("pointermove", (e) => {
    if (drag) { emit(e); return; }
    const v = store.get().view, x = X(), m = full() ? hitRegion(px(e), x(v.t0), x(v.t1)) : "jump";
    canvas.style.cursor = m.startsWith("edge") ? "ew-resize" : m === "move" ? "grab" : "default";
  });
  const end = () => { if (drag) store.command("view.historyGroup", { end: true }); drag = null; };
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  canvas.addEventListener("lostpointercapture", end);
  window.addEventListener?.("blur", end);
  const escape = (e) => { if (e.key === "Escape") end(); };
  window.addEventListener?.("keydown", escape);
  store.on(["file"], end);
  const offHistory = ["view.undo", "view.redo"].map((name) => store.onCommand(name, end));
  return { draw, dispose() { end(); offHistory.forEach((off) => off()); window.removeEventListener?.("blur", end); window.removeEventListener?.("keydown", escape); cv.dispose(); latest.cancel(); } };
}
