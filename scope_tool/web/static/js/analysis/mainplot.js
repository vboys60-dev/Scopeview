import { createMarkerLayer, nearestChannel } from "./marker_layer.js";
import { cursorSource, onCursorSource } from "./cursors.js";
import { fmt } from "../fmt.js";
// 主圖：多通道波形（/wave 包絡）、游標線。只發意圖事件，不直接改別人的狀態。
// 意圖：viewport.intent／channel.scale_intent／cursor.intent（payload 皆絕對值，見契約 intents）。
import { DIVS, linear, divTicks, timeTickLabels, envPixels, drawPixels, makeLatest, debounce, createCanvas, drawGrid, plotColors } from "./plotcore.js";
import { channelHandles, drawHandles } from "./handles.js";
import { voltageAxis, voltageLeft } from "./voltage.js";
import { bindGestures } from "./gestures.js";
import { withGrids, gridsOf, rowOf, bindGrids } from "./grids.js";
export const MARGIN = { l: 84, t: 8, r: 10, b: 22 };
const NO_FETCH = new Set(["grids", "decodeResult", "decodeSel"]);
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
    out.push({ px: X(p.x), py: divY(p.ch ? rowOf(rect, p.ch) : (rect.cy ?? rect), p.y), label: p.label ?? "" });
  }
  return out;
}
/** 該抓哪些通道：目前主檔、槽位及衍生通道；數學結果只寫 channels。 */
export const fetchTargets = (s) => {
  if (!s.file) return [];
  const names = new Set([...(s.file?.channels ?? []).map((c) => c.name), ...(s.slots ?? []).flatMap(slot => slot.channels)]);
  return s.channels.filter((c) => c.visible && (c.derived || names.has(c.name)));
};
/** /wave 請求鍵（來源時間 = 顯示時間 − dx）；相同鍵不重抓。 */
export const waveKey = (name, v, dx, px, gen) => [name, v.t0 - dx, v.t1 - dx, px, gen].join("|");
/** 選取解碼事件的格位與顯示時間；來源消失時不可退回第零格。 */
export function decodeMarks(s, rect, X) {
  const r = s.decodeResult, sel = s.decodeSel;
  if (!r || sel == null) return [];
  const f = r.frames.find(f => f.i === sel) /* ponytail: 每次重畫 O(n)，幀數很大時改索引 */, base = s.channels.find(c => c.name === r.base);
  if (!f || !base) return [];
  const t = f.t0 + (base.time_offset ?? 0), rows = new Map();
  if (t < s.view.t0 || t > s.view.t1) return [];
  for (const name of Object.values(r.summary?.channels ?? {}).filter(Boolean)) if (s.channels.some(c => c.name === name)) { const row = rowOf(rect, name); rows.set(row.index, row); }
  return [...rows.values()].map(row => ({ x: X(t), row, stale: !!r.stale }));
}

export function mount(el, ctx) {
  const { store, bridge, ui } = ctx;
  const offGrids = bindGrids(store);
  const cache = new Map(); // name → {env, key, px}
  const latest = new Map();
  let rect = layoutRect(1, 1), warned = 0, gestures = null, markers = null, draggingLayout = false, missed = false, lastWidth = 0;
  const cv = createCanvas(el, (w, h) => {
    rect = layoutRect(w, h); draw();
    if (w !== lastWidth && !draggingLayout) { lastWidth = w; fetchSoon(); }
  });
  store.onCommand('layout.dragging', (on) => {
    draggingLayout = on;
    if (!on) { const [w] = cv.size(); if (missed || w !== lastWidth) { missed = false; lastWidth = w; fetchSoon(); } }
  });
  const { canvas, ctx: g } = cv;

  const pxOf = () => Math.min(16384, Math.max(2, Math.round(rect.w)));
  const Xmap = (v) => linear(v.t0, v.t1, rect.l, rect.l + rect.w);

  function draw() {
    const [w, h] = cv.size();
    if (!w || !h) { (canvas.dataset ?? {}).pending = ""; return; }
    const s = store.get();
    // 通道很多且同零位時擴充左緣，始終保留刻度數字的空間。
    const grids = gridsOf(s), source = cursorSource(store).channel?.name;
    rect = withGrids(layoutRect(w, h), grids, s.channels, source);
    const axisChannel = row => s.channels.find(c => c.name === s.selected && row.names.includes(c.name))
      ?? (grids.n === 1 ? undefined : s.channels.find(c => c.visible && row.names.includes(c.name)));
    g.font = "12px sans-serif";
    const handles = channelHandles(s.channels, rect);
    const left = Math.max(...rect.rows.map(row => voltageLeft(text => g.measureText(text).width, voltageAxis(axisChannel(row)), handles, MARGIN.l)));
    rect = withGrids(layoutRect(w, h, left), grids, s.channels, source);
    store.set({ plotRect: { l: rect.l, w: rect.w } }, "program");
    const X = Xmap(s.view), col = plotColors();
    g.fillStyle = col.bg; g.fillRect(0, 0, w, h);
    const labels = timeTickLabels(s.view.t0, s.view.t1);
    g.font = "12px sans-serif";
    const dense = labels.some((label) => g.measureText(label).width + 8 > rect.w / 10);
    for (const row of rect.rows) {
      const selected = axisChannel(row), axis = voltageAxis(selected);
      drawGrid(g, row, divTicks(s.view.t0, s.view.t1).map((v, i) => ({ p: X(v), label: row.index === grids.n - 1 && (!dense || i % 2 === 1) ? labels[i] : "" })),
        axis.ticks.map(t => ({ p: divY(row, t.division), label: (grids.n === 1 || row.h >= 110 || (row.h >= 44 ? Math.abs(t.division) === 5 || t.division === 0 : t.division === 0))
          && !(selected && !Number.isInteger(selected.position) && Math.abs(t.division - selected.position) * row.h / 10 < 12) ? t.label : "" })), { ...col, yText: axis.color, center: true });
      if (selected && Math.abs(selected.position) <= DIVS && !Number.isInteger(selected.position)) {
        g.fillStyle = selected.color; g.textAlign = "right"; g.textBaseline = "middle";
        const y = divY(row, selected.position);
        g.fillText(`0 ${selected.unit}`, row.l - 4, y);
        g.strokeStyle = selected.color; g.beginPath(); g.moveTo(row.l - 3, y); g.lineTo(row.l + 3, y); g.stroke();
      }
      g.fillStyle = axis.color ?? col.text; g.textAlign = "left"; g.textBaseline = "top";
      g.fillText(axis.title, row.l + 6, row.t + 2);
    }
    g.save(); g.beginPath(); g.rect(rect.l, rect.t, rect.w, rect.h); g.clip();
    for (const c of s.channels) {
      const e = cache.get(c.name);
      if (!c.visible || !e) continue;
      const row = rowOf(rect, c.name);
      g.save(); g.beginPath(); g.rect(row.l, row.t, row.w, row.h); g.clip();
      e.px = envPixels(e.env, (t) => X(t + c.time_offset), valueY(row, c.scale, c.position));
      drawPixels(g, e.px, c.color); g.restore();
    }
    const cu = s.cursors;
    g.lineWidth = 1; g.font = "12px sans-serif"; g.textBaseline = "top";
    for (const [k, color] of [["x1", col.c1], ["x2", col.c2], ["y1", col.c1], ["y2", col.c2]]) {
      const v = cu[k];
      if (v === null || v === undefined) continue;
      g.lineWidth = gestures?.hovered() === k ? 3 : 1;
      g.strokeStyle = g.fillStyle = color; g.setLineDash(k[0] === "y" ? [5, 4] : []);
      g.beginPath();
      if (k[0] === "x") { const x = Math.round(X(v)) + 0.5; g.moveTo(x, rect.t); g.lineTo(x, rect.t + rect.h); g.stroke(); g.fillText("t" + k[1], x + 3, rect.t + 2); }
      else { g.save(); g.beginPath(); g.rect(rect.cy.l, rect.cy.t, rect.cy.w, rect.cy.h); g.clip(); g.beginPath(); const y = Math.round(divY(rect.cy, v)) + 0.5; g.moveTo(rect.l, y); g.lineTo(rect.l + rect.w, y); g.stroke(); g.fillText(`v${k[1]} ${fmt(cursorSource(store)[k], cursorSource(store).channel?.unit ?? "")}`, rect.l + 3, y + 2); g.restore(); }
    }
    g.save(); g.fillStyle = col.amber; g.strokeStyle = "#000"; g.lineWidth = 0.8; g.setLineDash([]);
    for (const m of decodeMarks(s, rect, X)) { const y = m.row.t + m.row.h; g.globalAlpha = m.stale ? 0.55 : 1; g.beginPath(); g.moveTo(m.x, y - 10); g.lineTo(m.x + 5, y); g.lineTo(m.x - 5, y); g.closePath(); g.fill(); g.stroke(); }
    g.restore();
    g.fillStyle = g.strokeStyle = col.c1; g.setLineDash([]); g.textBaseline = "bottom";
    for (const k of markerPixels(s.markerResult, X, rect)) {
      g.beginPath(); g.arc(k.px, k.py, 4, 0, 2 * Math.PI); g.stroke();
      if (k.label) g.fillText(k.label, k.px + 6, k.py - 3);
    }
    markers?.draw(g);
    g.restore();
    drawHandles(g, s.channels, s.cursors, s.view, rect);
    gestures?.overlay(g);
    // 報告截圖前據此等待：任一通道快取不是目前範圍的包絡即標 pending（取得後 draw 會清掉）。自檢假 canvas 無 dataset。
    (canvas.dataset ?? {}).pending = rect.w >= 2 && fetchTargets(s).some((c) => cache.get(c.name)?.key !== waveKey(c.name, s.view, c.time_offset, pxOf(), s.file?.gen)) ? "1" : "";
  }

  function fetchNow() {
    if (draggingLayout) { missed = true; return; }
    const s = store.get(), gen = s.file?.gen, px = pxOf();
    if (gen === undefined || rect.w < 2) return;
    for (const c of fetchTargets(s)) {
      const key = waveKey(c.name, s.view, c.time_offset, px, gen);
      if (cache.get(c.name)?.key === key) { latest.get(c.name)?.cancel(); continue; } // 切回已快取範圍：作廢舊範圍的在途請求，免得晚到回應蓋掉
      if (!latest.has(c.name)) latest.set(c.name, makeLatest());
      const req = latest.get(c.name).begin();
      bridge.fetchWave({ ch: c.name, t0: s.view.t0 - c.time_offset, t1: s.view.t1 - c.time_offset, px, gen, signal: req.signal })
        .then((env) => { if (req.ok()) { cache.set(c.name, { env, key }); draw(); } })
        .catch((e) => {
          if (e?.name === "AbortError" || e?.code === "STALE" || !req.ok()) return; // 過期／換檔：正常流程
          (canvas.dataset ?? {}).pending = ""; // 讀取真的失敗：別讓匯出報告空等 3 秒再報「尚未載入」，錯誤已由下方 toast 告知
          if (Date.now() - warned > 5000) { warned = Date.now(); ui.toast(`讀取波形失敗：${e.message}`, "error"); }
        });
    }
  }
  const fetchSoon = debounce(fetchNow, 150);

  store.on(["view", "channels", "cursors", "selected", "file", "dataRev", "markerResult", "grids", "decodeResult", "decodeSel"], (_s, keys) => {
    if (keys.includes("file") || keys.includes("dataRev")) { cache.clear(); latest.forEach((l) => l.cancel()); latest.clear(); }
    const names = new Set(store.get().channels.map((c) => c.name));
    for (const k of [...cache.keys()]) if (!names.has(k)) cache.delete(k);
    draw();
    if (keys.includes("file") || keys.includes("dataRev")) fetchNow(); else if (keys.some(k => !NO_FETCH.has(k))) fetchSoon();
  });

  const offSource = onCursorSource(store, draw);
  canvas.hitChannel = (cx, cy) => { const b = canvas.getBoundingClientRect(); return nearestChannel(store.get().channels, cache, cx - b.left, cy - b.top, null, rect); }; // 量測鈕拖放目標
  canvas.gridRect = () => rect;
  canvas.decodeMarks = () => decodeMarks(store.get(), rect, Xmap(store.get().view));
  markers = createMarkerLayer(canvas, ctx, canvas.gridRect, cache, draw);
  gestures = bindGestures(canvas, ctx, canvas.gridRect, draw, markers);
  draw();
  return { draw, dispose() { offGrids(); offSource(); gestures.dispose(); markers.dispose(); cv.dispose(); fetchSoon.cancel(); } };
}
