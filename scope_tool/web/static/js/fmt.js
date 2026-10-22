// 數值格式化與解析（SI 前綴）。全部純函式，node 可直接測。行為對齊 Qt 版 ui/analysis_results.fmt：
// 單位為 ""、"%" 或以 "dB" 開頭 → 不加前綴（%.6g）；其餘（含 V²、°）照 pg.siFormat 加前綴。
const PRE = ["p", "n", "µ", "m", "", "k", "M", "G", "T"]; // µ 為 U+00B5
const noPrefix = (unit) => unit === "" || unit === "%" || unit.startsWith("dB");

/** fmt(1.5e-6,"s") → "1.5 µs"；fmt(-0.02,"dBm") → "-0.02 dBm"。prec = 有效位數。 */
export function fmt(x, unit = "", prec = 6) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  if (!Number.isFinite(x)) return (x < 0 ? "-" : "") + "∞" + (unit ? " " + unit : "");
  let i = 4;
  if (x !== 0 && !noPrefix(unit)) {
    i = Math.min(Math.max(Math.floor(Math.log10(Math.abs(x)) / 3) + 4, 0), 8);
    // 四捨五入後若進位到 1000，改用上一級前綴
    if (Math.abs(Number((x / 10 ** ((i - 4) * 3)).toPrecision(prec))) >= 1000 && i < 8) i++;
  }
  const n = Number((x / 10 ** ((i - 4) * 3)).toPrecision(prec));
  return `${n} ${PRE[i]}${unit}`.trim();
}

// 數字＋可選前綴＋任意尾巴單位（含中文，如「2 mV/格」「500 µV/div」）。
// 前綴只在其後還有單位字元或字串結尾時才算前綴，避免把單位 "m"（公尺）誤判；"mV" → m＋V，"m" 單獨 → 毫。
const RE = /^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([pnuµμmkKMGT]?)\s*[^\d\s.+-]*\s*$/u;
const MUL = { p: 1e-12, n: 1e-9, u: 1e-6, "µ": 1e-6, "μ": 1e-6, m: 1e-3, k: 1e3, K: 1e3, M: 1e6, G: 1e9, T: 1e12 };

/** parseSI("200u") → 2e-4；"1.5 ms"、"10k"、"1e-3"、"2 mV/格" 皆可；失敗回 NaN。µ（U+00B5）與 μ（U+03BC）都收。 */
export function parseSI(s) {
  const m = RE.exec(String(s));
  return m ? Number(m[1]) * (MUL[m[2]] ?? 1) : NaN;
}

/** 位元組數 → "12.3 MB"（檔案大小顯示用）。 */
export function fmtBytes(n) {
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${Number(n.toPrecision(3))} ${u[i]}`;
}
