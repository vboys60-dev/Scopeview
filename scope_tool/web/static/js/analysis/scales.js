// 通道 V/格 檔位與自動縮放純函式；逐條移植自 ui/analysis_chanbar.py（語義不變）。
export const DIVS = 5; // 縱軸 ±5 格，共 10 格

// 單位為 V 的通道只用這張表；其他單位（V²、V/s…）用 1-2-5。
export const V_TABLE = [500e-6, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0];
export const STEPS_125 = [];
for (let e = -12; e < 13; e++) for (const m of [1, 2, 5]) STEPS_125.push(Number(`${m}e${e}`));

export const scaleSteps = (unit) => (unit === "V" ? V_TABLE : STEPS_125);

/** 忽略 NaN／inf 的 [min, max]；全無有限值回 [0, 0]。 */
export function valueRange(v) {
  let lo = Infinity, hi = -Infinity;
  for (const x of v) if (Number.isFinite(x)) { if (x < lo) lo = x; if (x > hi) hi = x; }
  return lo > hi ? [0, 0] : [lo, hi];
}

/** 回傳 [V/格, 位置格數]：波形佔 8 格並置中；超出檔位上限就夾在最大檔。 */
export function autoScale(lo, hi, unit) {
  const steps = scaleSteps(unit);
  const target = hi !== lo ? (hi - lo) / 8 : Math.abs(hi) / 4;
  let scale = 1.0;
  if (target) scale = steps.find((s) => s >= target) ?? steps[steps.length - 1];
  return [scale, -((hi + lo) / 2) / scale + 0]; // +0 把 -0 轉成 0
}

/** 往大（up）或往小走一檔，到端點就停；最近檔位以 log 距離判定。 */
export function stepScale(scale, unit, up) {
  const steps = scaleSteps(unit);
  let best = 0, bd = Infinity;
  steps.forEach((s, k) => { const d = Math.abs(Math.log(s / scale)); if (d < bd) { bd = d; best = k; } });
  return steps[Math.min(Math.max(best + (up ? 1 : -1), 0), steps.length - 1)];
}

/** 以波形目前中心為準換檔，回傳 [新位置, 是否仍在 ±5 格內]。 */
export function rescale(lo, hi, scale, pos, next) {
  const center = (lo + hi) / 2;
  const yc = center / scale + pos;
  return [yc - center / next, Math.abs(yc) + (hi - lo) / 2 / next <= DIVS + 1e-9];
}
