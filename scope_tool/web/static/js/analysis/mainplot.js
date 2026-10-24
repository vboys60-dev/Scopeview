// 主圖：多通道波形（/wave 包絡）、游標線。只發意圖事件，不直接改別人的狀態。
// 意圖：viewport.intent／channel.scale_intent／cursor.intent（payload 皆絕對值，見契約 intents）。
import { DIVS, linear, divTicks, timeTickLabels, envPixels, drawPixels, makeLatest, debounce, createCanvas, drawGrid, plotColors } from "./plotcore.js";
import { channelHandles, drawHandles } from "./handles.js";
import { bindGestures } from "./gestures.js";
export const MARGIN = { l: 84, t: 8, r: 10, b: 22 };
export const layoutRect = (w, h, left = MARGIN.l) => ({ l: left, t: MARGIN.t, w: Math.max(1, w - left - MARGIN.r), h: Math.max(1, h - MARGIN.t - MARGIN.b) });
/** 顯示格數 → 像素 y（置頂為 +5 格）。 */
export const divY = (rect, d) => rect.t + (DIVS - d) * rect.h / (2 * DIVS);
export const yToDiv = (rect, py) => DIVS - (py - rect.t) * (2 * DIVS) / rect.h;
/** 通道數值 → 像素 y：value/scale + position。 */
export const valueY = (rect, scale, pos) => (v) => divY(rect, v / scale + pos);
/** 拖曳平移：像素位移 → 新 view。 */
export const panView = (v, dpx, rectW) => { const dt = -dpx * (v.t1 - v.t0) / rectW; return { t0: v.t0 + dt, t1: v.t1 + dt }; };
/** 以 anchor 為中心縮放（factor>1 縮小視野）。 */
export const zoomView = (v, anchor, f) => ({ t0: anchor - (anchor - v.t0) * f, t1: anchor + (v.t1 - anchor) * f });
/** Marker 點 → 像素：store.markerResult={mode,points:[{x(顯示時間),y(顯示格數),label}]}；缺值（非有限數）就略過。 */
export function markerPixels(mr, X, rect) {
  const out = [];
  for (const p of mr?.points ?? []) {
    if (!p || !Number.isFinite(p.x) || !Number.isFinite(p.y)) continue;
    out.push({ px: X(p.x), py: divY(rect, p.y), label: p.label ?? "" });
  }
  return out;
}
/** 該抓哪些通道：可見、且存在於目前檔案（避免新檔 gen 搭配舊通道名）。 */
export const fetchTargets = (s) => {
  const names = new Set((s.file?.channels ?? []).map((c) => c.name));
  return s.channels.filter((c) => c.visible && names.has(c.name));
};
/** /wave 請求鍵（來源時間 = 顯示時間 − dx）；相同鍵不重抓。 */
export const waveKey = (name, v, dx, px, gen) => [name, v.t0 - dx, v.t1 - dx, px, gen].join("|");

export function mount(el, ctx) {
  const { store, bridge, ui } = ctx;
  const cache = new Map(); // name → {env, key, px}
  const latest = new Map();
  let rect = layoutRect(1, 1), warned = 0, gestures = null;
  const cv = createCanvas(el, (w, h) => { rect = layoutRect(w, h); draw(); fetchSoon(); });
  const { canvas, ctx: g } = cv;

  const Xmap = (v) => linear(v.t0, v.t1, rect.l, rect.l + rect.w);

  function draw() {
    const [w, h] = cv.size();
    if (!w || !h) return;
    const s = store.get();
    // 通道很多且同零位時擴充左緣，始終保留刻度數字的空間。
    const left = Math.max(MARGIN.l, ...channelHandles(s.channels, rect).map((b) => b.x + b.w + 24));
    rect = layoutRect(w, h, left);
    const X = Xmap(s.view), col = plotColors();
    g.fillStyle = col.bg; g.fillRect(0, 0, w, h);
    const labels = timeTickLabels(s.view.t0, s.view.t1);
    g.font = "11px sans-serif";
    const dense = labels.some((label) => g.measureText(label).width + 8 > rect.w / 10);
    drawGrid(g, rect, divTicks(s.view.t0, s.view.t1).map((v, i) => ({ p: X(v), label: !dense || i % 2 === 1 ? labels[i] : "" })),
      Array.from({ length: 2 * DIVS + 1 }, (_, i) => ({ p: divY(rect, DIVS - i), label: String(DIVS - i) })), col);
    g.save(); g.beginPath(); g.rect(rect.l, rect.t, rect.w, rect.h); g.clip();
    for (const c of s.channels) {
      const e = cache.get(c.name);
      if (!c.visible || !e) continue;
      e.px = envPixels(e.env, (t) => X(t + c.time_offset), valueY(rect, c.scale, c.position));
      drawPixels(g, e.px, c.color);
    }
    const cu = s.cursors;
    g.lineWidth = 1; g.font = "11px sans-serif"; g.textBaseline = "top";
    for (const [k, color] of [["x1", col.c1], ["x2", col.c2], ["y1", col.c1], ["y2", col.c2]]) {
      const v = cu[k];
      if (v === null || v === undefined) continue;
      g.strokeStyle = g.fillStyle = color; g.setLineDash(k[0] === "y" ? [5, 4] : []);
      g.beginPath();
      if (k[0] === "x") { const x = Math.round(X(v)) + 0.5; g.moveTo(x, rect.t); g.lineTo(x, rect.t + rect.h); g.stroke(); g.fillText("t" + k[1], x + 3, rect.t + 2); }
      else { const y = Math.round(divY(rect, v)) + 0.5; g.moveTo(rect.l, y); g.lineTo(rect.l + rect.w, y); g.stroke(); g.fillText("v" + k[1], rect.l + 3, y + 2); }
    }
    g.fillStyle = g.strokeStyle = col.c1; g.setLineDash([]); g.textBaseline = "bottom";
    for (const k of markerPixels(s.markerResult, X, rect)) {
      g.beginPath(); g.arc(k.px, k.py, 4, 0, 2 * Math.PI); g.stroke();
      if (k.label) g.fillText(k.label, k.px + 6, k.py - 3);
    }
    g.restore();
    drawHandles(g, s.channels, s.cursors, s.view, rect);
    gestures?.overlay(g);
  }

  function fetchNow() {
    const s = store.get(), gen = s.file?.gen, px = Math.min(16384, Math.max(2, Math.round(rect.w)));
    if (gen === undefined || rect.w < 2) return;
    for (const c of fetchTargets(s)) {
      const key = waveKey(c.name, s.view, c.time_offset, px, gen);
      if (cache.get(c.name)?.key === key) continue;
      if (!latest.has(c.name)) latest.set(c.name, makeLatest());
      const req = latest.get(c.name).begin();
      bridge.fetchWave({ ch: c.name, t0: s.view.t0 - c.time_offset, t1: s.view.t1 - c.time_offset, px, gen, signal: req.signal })
        .then((env) => { if (req.ok()) { cache.set(c.name, { env, key }); draw(); } })
        .catch((e) => {
          if (e?.name === "AbortError" || e?.code === "STALE" || !req.ok()) return; // 過期／換檔：正常流程
          if (Date.now() - warned > 5000) { warned = Date.now(); ui.toast(`讀取波形失敗：${e.message}`, "error"); }
        });
    }
  }
  const fetchSoon = debounce(fetchNow, 150);

  store.on(["view", "channels", "cursors", "selected", "file", "markerResult"], (_s, keys) => {
    if (keys.includes("file")) { cache.clear(); latest.forEach((l) => l.cancel()); latest.clear(); }
    const names = new Set(store.get().channels.map((c) => c.name));
    for (const k of [...cache.keys()]) if (!names.has(k)) cache.delete(k);
    draw();
    if (keys.includes("file")) fetchNow(); else fetchSoon();
  });

  gestures = bindGestures(canvas, ctx, () => rect, draw);
  draw();
  return { draw, dispose() { gestures.dispose(); cv.dispose(); fetchSoon.cancel(); } };
}
