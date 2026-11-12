// 前端保存完整頻帶的頻譜快照，供兩個 FFT 窗格共用。
export const list = [];
const listeners = new Set(), colors = ['#ff5ca8', '#39d9ff', '#ffb347', '#b68cff'];
let serial = 0, epoch = 0, bound = null, off = null, generation;
const notify = () => { for (const fn of listeners) fn(); };
export function clear() { epoch++; list.length = 0; notify(); }
export function on(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function visible(unit) { return unit === '°' ? [] : list.filter(item => item.unit === unit); }
export function bind(ctx) {
  if (bound === ctx.store) return;
  off?.(); clear(); bound = ctx.store; generation = bound.get().file?.gen;
  off = bound.on(['file'], st => {
    if (!st.file || st.file.gen !== generation) { generation = st.file?.gen; clear(); }
  });
}
export async function pin(ctx) {
  bind(ctx);
  const st = ctx.store.get(), r = st.fftResult, gen = st.file?.gen, version = epoch;
  if (!st.file || !r?.ok || !r.spectrum_id) return;
  const f0 = Math.max(r.df, r.f_min), common = { id: r.spectrum_id, f1: r.f_max, px: 16384 };
  if (!(f0 > 0) || !(f0 < r.f_max)) throw new Error('頻譜頻率範圍無法建立對數快照');
  // ponytail: 疊圖快照每個頻率軸最多擷取 16384 px，放大時解析度受此上限限制。
  const [lin, log] = await Promise.all([
    ctx.bridge.fetchSpectrum({ ...common, f0: r.f_min, log: false }),
    ctx.bridge.fetchSpectrum({ ...common, f0, log: true }),
  ]);
  if (version !== epoch || bound !== ctx.store || ctx.store.get().file?.gen !== gen) return;
  const n = serial++;
  list.push({ label: `疊圖 ${n + 1}`, color: colors[n % colors.length], unit: r.unit, lin, log });
  if (list.length > 4) list.shift();
  notify();
}
