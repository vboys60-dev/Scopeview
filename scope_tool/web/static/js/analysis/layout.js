// L4：版面偏好與純尺寸計算；自動退讓只存在 effective，不回寫 prefs。
export const VERSION = 1, STORAGE_KEY = 'scope.analysis.layout.v1';
export const defaults = () => ({ version: VERSION, side: 240, lower: null, fft: null, sideCollapsed: null, lowerCollapsed: null, fftCollapsed: false, overview: null });
const clip = (n, a, b) => Math.min(b, Math.max(a, n));
export function validatePrefs(raw) {
  const p = defaults();
  if (!raw || typeof raw !== 'object' || raw.version !== VERSION) return p;
  for (const [k, lo, hi] of [['side',180,360], ['lower',120,600], ['fft',160,900]]) {
    if (typeof raw[k] === 'number' && Number.isFinite(raw[k])) p[k] = clip(raw[k], lo, hi);
  }
  for (const k of ['sideCollapsed','lowerCollapsed','fftCollapsed']) if (typeof raw[k] === 'boolean') p[k] = raw[k];
  return p;
}
let memory = defaults();
export function loadPrefs(storage = () => globalThis.localStorage) {
  try { const value = storage().getItem(STORAGE_KEY); if (value) {
    try { memory = validatePrefs(JSON.parse(value)); } catch { memory = defaults(); }
  } } catch { /* 儲存不可用時保留記憶體 */ }
  return { ...memory };
}
export function savePrefs(p, storage = () => globalThis.localStorage) {
  memory = validatePrefs(p);
  try { storage().setItem(STORAGE_KEY, JSON.stringify({ ...memory, overview:undefined })); } catch { /* 私密模式也正常運作 */ }
}
/** H 為工具列以下可用高度；chrome 為實測通道列＋Horizontal 列。 */
export function clampLayout({ W, H, prefs, fftOn, chrome = 56, vw = W, vh = H, drawerOpen = false }) {
  const p = validatePrefs(prefs), steps = [];
  W = Math.max(0, Number.isFinite(W) ? W : 0); H = Math.max(0, Number.isFinite(H) ? H : 0);
  const narrow = vw <= 899, drawer = narrow && drawerOpen;
  const sideCollapsed = narrow ? !drawer : (p.sideCollapsed ?? vw < 1100);
  const side = narrow || sideCollapsed ? 36 : p.side;
  let lowerCollapsed = p.lowerCollapsed ?? (vh <= 700 && fftOn);
  let lower = lowerCollapsed ? 0 : (p.lower ?? clip(H * .23,160,200)) - 28;
  let overview = (prefs?.overview ?? vh > 700) ? (fftOn ? 40 : 56) : 0;
  const fftCollapsed = p.fftCollapsed;
  const separators = 28 + (fftOn ? 28 : 0);
  const preferredFFT = Math.max(160,Math.min(200,H-chrome-separators-lower-overview-330));
  let fft = fftOn && !fftCollapsed ? p.fft ?? preferredFFT : 0;
  const room = () => H - chrome - separators - lower - overview - fft;
  if (room() < (fftOn ? 330 : 270) && overview) { overview = 0; steps.push('overview'); }
  if (room() < 270 && lower && p.lowerCollapsed !== false) { lower = 0; lowerCollapsed = true; steps.push('lower'); }
  if (room() < 270 && fft > 160) { fft = 160; steps.push('fft'); }
  let tabbed = fftOn && !fftCollapsed && (room() < 270 || vw < 1100);
  if (tabbed) { steps.push('tabs'); fft = Math.max(160, H - chrome - separators - lower - overview); }
  let main = tabbed ? Math.max(270, fft) : Math.max(270, room());
  if (tabbed) fft = main;
  const usedHeight = chrome + separators + lower + overview + (tabbed ? main : main + fft);
  const scroll = usedHeight > H;
  if (scroll) steps.push('scroll');
  return { side, sideCollapsed, drawer, drawerWidth:p.side, lower: lower + 28, lowerBody: lower, lowerCollapsed, fft, fftCollapsed, overview, main,
    mainGrid: main - 30, tabbed, scroll, usedHeight, plotWidth: Math.max(0,W-side-10), steps };
}
/** splitter 數值邏輯：拖曳與方向鍵共用，絕不以越界觸發收折。 */
export function resizeValue(kind, start, delta, max = Infinity) {
  const min = kind === 'side' ? 180 : kind === 'lower' ? 120 : 160;
  return clip(start + delta, min, Math.max(min, Math.min(max, kind === 'side' ? 360 : kind === 'lower' ? 600 : 900)));
}
export function resetPref(prefs, kind) {
  return { ...prefs, [kind]: defaults()[kind], [kind + 'Collapsed']: defaults()[kind + 'Collapsed'] };
}
