// L4：版面偏好與純尺寸計算；自動退讓只存在 effective，不回寫 prefs。
// FFT 預算與 analysis.css 同步：40px 同行控制列＋至少 120px 繪圖區。
export const FFT_BAR_HEIGHT = 40, FFT_PLOT_MIN = 120, FFT_MIN_HEIGHT = FFT_BAR_HEIGHT + FFT_PLOT_MIN;
export const VERSION = 1, STORAGE_KEY = 'scope.analysis.layout.v1';
export const defaults = () => ({ version: VERSION, side: 240, lower: null, fft: null, sideCollapsed: null, lowerCollapsed: null, fftCollapsed: false, markerSide: false, overview: null });
/** 版面 C：B 區搬到圖右側的直欄寬度；視窗 <1280px 不啟用（避免圖區被 340px 右欄擠到控制列溢出）。 */
export const DOCK_WIDTH = 340, DOCK_MIN_VW = 1280, DOCK_PLOT_MIN = 904;
const clip = (n, a, b) => Math.min(b, Math.max(a, n));
export function validatePrefs(raw) {
  const p = defaults();
  if (!raw || typeof raw !== 'object' || raw.version !== VERSION) return p;
  for (const [k, lo, hi] of [['side',180,360], ['lower',120,600], ['fft',FFT_MIN_HEIGHT,900]]) {
    if (typeof raw[k] === 'number' && Number.isFinite(raw[k])) p[k] = clip(raw[k], lo, hi);
  }
  for (const k of ['sideCollapsed','lowerCollapsed','fftCollapsed']) if (typeof raw[k] === 'boolean') p[k] = raw[k];
  if (typeof raw.markerSide === 'boolean') p.markerSide = raw.markerSide;
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
export function clampLayout({ W, H, prefs, fftOn, chrome = 56, vw = W, vh = H, drawerOpen = false, lowerFloating = false }) {
  const p = validatePrefs(prefs), steps = [];
  W = Math.max(0, Number.isFinite(W) ? W : 0); H = Math.max(0, Number.isFinite(H) ? H : 0);
  const narrow = vw <= 899, drawer = narrow && drawerOpen;
  const sideCollapsed = narrow ? !drawer : (p.sideCollapsed ?? vw < 1100);
  const side = narrow || sideCollapsed ? 36 : p.side;
  // ponytail: FFT 關閉時可更早停靠，需要時再分成兩個門檻。
  const canDock = vw >= DOCK_MIN_VW && !lowerFloating && W - side - 10 - DOCK_WIDTH >= DOCK_PLOT_MIN, docked = canDock && p.markerSide;
  let lowerCollapsed = !docked && (lowerFloating || (p.lowerCollapsed ?? (vh <= 700 && fftOn)));
  let lower = lowerCollapsed || docked ? 0 : (p.lower ?? clip(H * .21,150,180)) - 28;
  let overview = (prefs?.overview ?? vh > 700) ? (fftOn ? 40 : 56) : 0;
  const fftCollapsed = p.fftCollapsed;
  const separators = (docked ? 0 : 28) + (fftOn ? 28 : 0);
  const preferredFFT = Math.max(FFT_MIN_HEIGHT,Math.min(200,H-chrome-separators-lower-overview-330));
  let fft = fftOn && !fftCollapsed ? p.fft ?? preferredFFT : 0;
  const room = () => H - chrome - separators - lower - overview - fft;
  if (room() < (fftOn ? 330 : 270) && overview) { overview = 0; steps.push('overview'); }
  if (room() < 270 && lower && p.lowerCollapsed !== false) { lower = 0; lowerCollapsed = true; steps.push('lower'); }
  if (room() < 270 && fft > FFT_MIN_HEIGHT) { fft = FFT_MIN_HEIGHT; steps.push('fft'); }
  let tabbed = fftOn && !fftCollapsed && (room() < 270 || vw < 1100);
  if (tabbed) { steps.push('tabs'); fft = Math.max(FFT_MIN_HEIGHT, H - chrome - separators - lower - overview); }
  let main = tabbed ? Math.max(270, fft) : Math.max(270, room());
  if (tabbed) fft = main;
  const usedHeight = chrome + separators + lower + overview + (tabbed ? main : main + fft);
  const scroll = usedHeight > H;
  if (scroll) steps.push('scroll');
  return { side, sideCollapsed, drawer, drawerWidth:p.side, lower: docked ? 0 : lower + 28, docked, canDock, dockWidth: docked ? DOCK_WIDTH : 0, lowerBody: lower, lowerCollapsed, fft, fftCollapsed, overview, main,
    mainGrid: main - 30, tabbed, scroll, usedHeight, plotWidth: Math.max(0,W-side-10-(docked ? DOCK_WIDTH : 0)), steps };
}
/** splitter 數值邏輯：拖曳與方向鍵共用，絕不以越界觸發收折。 */
export function resizeValue(kind, start, delta, max = Infinity) {
  const min = kind === 'side' ? 180 : kind === 'lower' ? 120 : FFT_MIN_HEIGHT;
  return clip(start + delta, min, Math.max(min, Math.min(max, kind === 'side' ? 360 : kind === 'lower' ? 600 : 900)));
}
export function resetPref(prefs, kind) {
  return { ...prefs, [kind]: defaults()[kind], [kind + 'Collapsed']: defaults()[kind + 'Collapsed'] };
}
