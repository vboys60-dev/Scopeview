// 自繪 Canvas 圖表的共用元件：座標轉換、刻度、HiDPI、包絡轉像素、過期請求保護。純邏輯可在 node 測。
// 顯示座標：display_time = source + dx；display_y_div = value / scale + position（縱軸 ±5 格）。
import { fmt } from "../fmt.js";

export const DIVS = 5;

/** 線性映射 [d0,d1] → [r0,r1]；回傳函式，附 .inv。 */
export function linear(d0, d1, r0, r1) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  const f = (v) => r0 + (v - d0) * k;
  f.inv = (p) => (k === 0 ? d0 : d0 + (p - r0) / k);
  return f;
}
/** 對數映射（d0,d1 須 >0）。 */
export function logmap(d0, d1, r0, r1) {
  const a = Math.log10(d0), k = (r1 - r0) / (Math.log10(d1) - a);
  const f = (v) => r0 + (Math.log10(v) - a) * k;
  f.inv = (p) => 10 ** (a + (p - r0) / k);
  return f;
}

/** 時間軸固定切 10 格（對齊 Qt _DivAxis）。 */
export function divTicks(lo, hi, n = 10) {
  const step = (hi - lo) / n;
  return step > 0 ? Array.from({ length: n + 1 }, (_, k) => lo + k * step) : [];
}
/** 1-2-5 好看刻度（FFT 線性軸）。 */
export function niceTicks(lo, hi, target = 8) {
  if (!(hi > lo)) return [];
  const raw = (hi - lo) / target, p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}
/** 對數刻度：每個十進位的 1、2、5。 */
export function logTicks(lo, hi) {
  const out = [];
  if (!(lo > 0 && hi > lo)) return out;
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
    for (const m of [1, 2, 5]) { const v = m * 10 ** e; if (v >= lo && v <= hi) out.push(v); }
  }
  return out;
}
/** 時間／電壓文字依格距量化，整軸共用前綴與小數位；不回寫數值座標。 */
export function tickLabel(v, unit, step = 0, max = Math.abs(v)) {
  if (!(step > 0)) return fmt(v, unit, 4);
  // 去除浮點運算尾差，再取格距最末有效位與格距十分之一中較細者。
  const [mantissa, exponent] = Number(step.toPrecision(12)).toExponential().split("e");
  const last = Number(exponent) - (mantissa.split(".")[1]?.length ?? 0);
  const resolutionOrder = Math.min(Math.floor(Math.log10(step)) - 1, last);
  const res = 10 ** resolutionOrder;
  const q = Math.sign(v) * Math.round(Math.abs(v) / res) * res;
  if (q === 0) return `0 ${unit}`;
  const e = unit === "" || unit === "%" || unit.startsWith("dB") ? 0 : Math.min(12, Math.max(-12, Math.floor(Math.log10(max) / 3) * 3));
  const prefix = ["p", "n", "µ", "m", "", "k", "M", "G", "T"][(e + 12) / 3];
  const decimals = Math.min(100, Math.max(0, e - resolutionOrder));
  return `${(q / 10 ** e).toFixed(decimals)} ${prefix}${unit}`;
}
/** 超過 9 位有效數字：中心保留完整絕對值，其餘顯示相對中心偏移。 */
export function timeTickLabels(lo, hi, n = 10) {
  const step = (hi - lo) / n, max = Math.max(Math.abs(lo), Math.abs(hi));
  const relative = step > 0 && Math.floor(Math.log10(max)) - Math.floor(Math.log10(step)) + 2 > 9;
  // 時窗相減可能帶入尾差；依消去誤差限制有效位數，最多保留九位。
  const digits = Math.max(1, Math.min(9, Math.floor(Math.log10(step / Math.max(Number.MIN_VALUE, max * Number.EPSILON))) - 1));
  const labelStep = Number(step.toPrecision(digits));
  const center = lo + (hi - lo) / 2;
  return divTicks(lo, hi, n).map((v, i) => {
    if (!relative) return tickLabel(v, "s", labelStep, max);
    if (i === n / 2) return `${center} s`;
    const offset = (i - n / 2) * step;
    return (offset > 0 ? "+" : "") + tickLabel(offset, "s", labelStep, (hi - lo) / 2);
  });
}

/** deltaMode：行以 16px、頁以實際圖高換算；捏合較敏感，單次倍率限制在 0.5～2。 */
export function wheelFactor({ deltaY, deltaMode = 0, ctrlKey = false }, pageHeight = 800) {
  if (!Number.isFinite(deltaY) || deltaY === 0) return 1;
  const dy = deltaY * (deltaMode === 1 ? 16 : deltaMode === 2 ? pageHeight : 1);
  const exponent = dy * Math.LN2 / (ctrlKey ? 120 : 480);
  return Math.exp(Math.max(-Math.LN2, Math.min(Math.LN2, exponent)));
}

/**
 * 包絡／原始解碼結果 → 像素。X(source_t) 與 Y(value) 由呼叫端組（含 dx、scale、position）。
 * 回傳 {x, top, bot}：top＝hi 的 py（較小）、bot＝lo 的 py；NaN 保留（斷線）。
 */
export function envPixels(env, X, Y) {
  const n = env.n, x = new Float32Array(n), top = new Float32Array(n), bot = new Float32Array(n);
  for (let i = 0; i < n; i++) { x[i] = X(env.x[i]); top[i] = Y(env.hi[i]); bot[i] = Y(env.lo[i]); }
  return { x, top, bot, mode: env.mode };
}
/** 畫像素點：mode 0 為折線（NaN 斷線）；mode 1 每桶畫 lo~hi 垂直線（至少 1px 高）。 */
export function drawPixels(ctx, p, color) {
  ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath();
  const n = p.x.length;
  if (p.mode === 0) {
    let pen = false;
    for (let i = 0; i < n; i++) {
      if (Number.isNaN(p.top[i])) { pen = false; continue; }
      if (pen) ctx.lineTo(p.x[i], p.top[i]); else { ctx.moveTo(p.x[i], p.top[i]); pen = true; }
    }
  } else {
    for (let i = 0; i < n; i++) {
      if (Number.isNaN(p.top[i]) || Number.isNaN(p.bot[i])) continue;
      ctx.moveTo(p.x[i], p.top[i]); ctx.lineTo(p.x[i], Math.max(p.bot[i], p.top[i] + 1));
    }
  }
  ctx.stroke();
}
/** 找距離 (px,py) 最近、且在 tol 像素內的點；回傳 py 距離或 Infinity（命中測試用）。 */
export function nearestDist(p, px, py, tol = 8) {
  let best = Infinity;
  for (let i = 0; i < p.x.length; i++) {
    if (Math.abs(p.x[i] - px) > tol) continue;
    const a = p.top[i], b = p.mode === 0 ? a : p.bot[i];
    if (Number.isNaN(a) || Number.isNaN(b)) continue;
    const d = py < a ? a - py : py > b ? py - b : 0;
    if (d < best) best = d;
  }
  return best <= tol ? best : Infinity;
}

/** 過期請求保護：begin() 會中止前一個，回傳 {id, signal, ok()}；ok() 為假＝已被新請求取代，結果應丟棄。 */
export function makeLatest() {
  let seq = 0, ctl = null;
  return {
    begin() {
      ctl?.abort();
      ctl = typeof AbortController === "function" ? new AbortController() : { signal: undefined, abort() {} };
      const id = ++seq;
      return { id, signal: ctl.signal, ok: () => id === seq };
    },
    cancel() { seq++; ctl?.abort(); },
  };
}
/** 防抖（trailing）；附 .cancel()。 */
export function debounce(fn, ms) {
  let t = null;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => { t = null; fn(...a); }, ms); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export const cssVar = (name, fb) => {
  try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fb; } catch { return fb; }
};

/** 建 canvas 並追蹤尺寸（HiDPI）。onResize(w, h) 以 CSS 像素回報；回傳 {canvas, ctx, size(), dispose}。 */
export function createCanvas(host, onResize, cls = "plot__canvas") {
  const canvas = document.createElement("canvas");
  canvas.className = cls;
  host.append(canvas);
  const ctx = canvas.getContext("2d");
  let w = 0, h = 0, frame = 0, disposed = false;
  const fit = () => {
    frame = 0; if (disposed) return;
    const r = host.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    w = Math.max(0, Math.round(r.width)); h = Math.max(0, Math.round(r.height));
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    canvas.style.width = w + "px"; canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (w && h) onResize(w, h);
  };
  // 一律非同步呼叫 fit：呼叫端的 const cv = createCanvas(...) 尚未完成指派前，callback 不得被執行
  const schedule = () => {
    if (typeof requestAnimationFrame !== 'function') { queueMicrotask(fit); return; }
    if (!frame) frame = requestAnimationFrame(fit);
  };
  const ro = new ResizeObserver(schedule);
  // 跨螢幕 DPR 改變通常伴隨 resize；重新訂閱 resolution 補上僅 DPR 改變的情形。
  let media;
  const dprChanged = () => {
    media?.removeEventListener?.('change',dprChanged);
    media = window.matchMedia?.(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    media?.addEventListener?.('change',dprChanged); schedule();
  };
  dprChanged(); window.addEventListener?.('resize',schedule);
  ro.observe(host);
  queueMicrotask(fit);
  return { canvas, ctx, size: () => [w, h], dispose: () => {
    disposed = true; ro.disconnect(); if (frame) cancelAnimationFrame(frame);
    window.removeEventListener?.('resize',schedule); media?.removeEventListener?.('change',dprChanged);
  } };
}

/** 通用：畫格線與座標軸文字。xt/yt＝[{p:像素, label}]；rect＝{l,t,w,h}。 */
export function drawGrid(ctx, rect, xt, yt, colors) {
  ctx.save();
  ctx.strokeStyle = colors.grid; ctx.fillStyle = colors.text; ctx.font = "11px sans-serif"; ctx.lineWidth = 1;
  ctx.beginPath();
  for (const t of xt) { const x = Math.round(t.p) + 0.5; ctx.moveTo(x, rect.t); ctx.lineTo(x, rect.t + rect.h); }
  for (const t of yt) { const y = Math.round(t.p) + 0.5; ctx.moveTo(rect.l, y); ctx.lineTo(rect.l + rect.w, y); }
  ctx.stroke();
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (const t of xt) if (t.label) ctx.fillText(t.label, t.p, rect.t + rect.h + 4);
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  ctx.fillStyle = colors.yText ?? colors.text;
  for (const t of yt) if (t.label) {
    ctx.textBaseline = t.p >= rect.t + rect.h ? "bottom" : "middle";
    ctx.fillText(t.label, rect.l - 4, t.p);
  }
  ctx.strokeStyle = colors.axis; ctx.strokeRect(rect.l + 0.5, rect.t + 0.5, rect.w, rect.h);
  ctx.restore();
}
export const plotColors = () => ({
  bg: cssVar("--c-plot-bg", "#000"), grid: cssVar("--c-plot-grid", "#333"), axis: cssVar("--c-plot-axis", "#888"),
  text: cssVar("--c-plot-text", "#ccc"), c1: cssVar("--c-cursor1", "#fff"), c2: cssVar("--c-cursor2", "#aaa"),
});
