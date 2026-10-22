// mock 用的純函式：二進位編碼、二分搜尋、min/max 包絡（含 NaN 規則）、合成資料。供 mock_backend.js 使用。

/** 編碼 /wave、/fft 二進位（與 bridge.decodeWave 對稱）。x: Float64Array，lo／hi: Float32Array。 */
export function encodeWave(x, lo, hi, mode) {
  const n = x.length, buf = new ArrayBuffer(16 + 16 * n);
  const dv = new DataView(buf);
  dv.setUint32(0, n, true); dv.setUint32(4, mode, true);
  new Float64Array(buf, 16, n).set(x);
  new Float32Array(buf, 16 + 8 * n, n).set(lo);
  new Float32Array(buf, 16 + 12 * n, n).set(hi);
  return buf;
}

/** 第一個 t[i] >= x（strict=true 時為 > x）的索引；t 遞增。 */
export function bound(t, x, strict = false) {
  let a = 0, b = t.length;
  while (a < b) { const m = (a + b) >> 1; if (strict ? t[m] <= x : t[m] < x) a = m + 1; else b = m; }
  return a;
}
/** 兩端含的區間 [x0,x1] → 索引 [a,b)。 */
export const span = (t, x0, x1) => [bound(t, x0), bound(t, x1, true)];
/** 最近取樣點索引，同距取右。 */
export function nearest(t, x) {
  const i = bound(t, x);
  return i <= 0 ? 0 : i >= t.length ? t.length - 1 : x - t[i - 1] < t[i] - x ? i - 1 : i;
}

/** 降採樣：區間內（左右各多取一點）點數 ≤ 2px 回原始點（mode 0, hi==lo），否則分桶（mode 1，x＝每桶起點）。
 *  桶內含 NaN → 該桶 lo／hi 皆 NaN（不產生 ±Infinity）。log＝true 時按對數等距分桶並排除 x≤0（需 x0>0）。 */
export function envelope(x, y, x0, x1, px, log = false) {
  let [a, b] = span(x, x0, x1);
  a = Math.max(0, a - 1); b = Math.min(x.length, b + 1);
  if (log) a = Math.max(a, bound(x, 0, true));
  const m = b - a;
  if (m <= 2 * px) {
    const v = Float32Array.from(y.subarray(a, b));
    return encodeWave(x.slice(a, b), v, v, 0);
  }
  const starts = Array.from({ length: px + 1 }, (_, i) => (log
    ? Math.min(b, Math.max(a, bound(x, x0 * (x1 / x0) ** (i / px))))
    : a + Math.floor((i * m) / px)));
  starts[0] = a; starts[px] = b;
  const xs = [], los = [], his = [];
  for (let i = 0; i < px; i++) {
    const s = starts[i], e = starts[i + 1];
    if (e <= s) continue; // 對數分桶低頻端可能沒有取樣點
    let mn = Infinity, mx = -Infinity;
    for (let j = s; j < e; j++) { const q = y[j]; if (Number.isNaN(q)) { mn = mx = NaN; break; } if (q < mn) mn = q; if (q > mx) mx = q; }
    xs.push(x[s]); los.push(mn); his.push(mx);
  }
  return encodeWave(Float64Array.from(xs), Float32Array.from(los), Float32Array.from(his), 1);
}

/** 合成「開檔」資料：各通道時間軸不同（起點、點數不同），CHAN2 中間有一段 NaN 缺口。 */
export function makeFile() {
  const mk = (n, t0, dt, f) => { const t = Float64Array.from({ length: n }, (_, i) => t0 + i * dt); return { t, v: Float64Array.from(t, f), unit: "V" }; };
  const dt = 1e-3 / 2000;
  const f = {
    CHAN1: mk(20000, -5e-3, dt, (t) => (Math.sin(2 * Math.PI * 1000 * t) >= 0 ? 1 : -1)),
    CHAN2: mk(16000, -4.0003e-3, dt, (t) => 0.5 * Math.sin(2 * Math.PI * 1000 * t)),
  };
  for (let i = 6000; i < 6020; i++) f.CHAN2.v[i] = NaN;
  return f;
}

/** 合成頻譜（dBm）：df=100 Hz、0 ~ 1 MHz，底噪 -90，奇次諧波 1k~9k 為峰。 */
export function makeSpectrum() {
  const M = 10001, x = Float64Array.from({ length: M }, (_, i) => i * 100), y = new Float32Array(M).fill(-90);
  [1, 3, 5, 7, 9].forEach((k) => { y[k * 10] = -10 - 9.5 * (k - 1) / 2; });
  return { x, y };
}
/** 原始頻格上的局部峰（y 嚴格大於左鄰、不小於右鄰，且 ≥ level）索引。 */
export function peakBins(y, level) {
  const out = [];
  for (let i = 1; i < y.length - 1; i++) if (y[i] >= level && y[i] > y[i - 1] && y[i] >= y[i + 1]) out.push(i);
  return out;
}
