// FFT 基準線唯一真值；峰快取保留後端原始單位，顯示才過濾／排序。
const models = new WeakMap();
export const PEAK_LIMIT = 1000;
export const FFT_UNITS = ['dBm', 'Vrms', 'dBV', 'dBmV', 'dBµV', 'Watt'];
// 換算以 Vrms 為中介：P=V²/R，dBm=10 log10(P/0.001)。
// dBV=20 log10(V)，dBmV=dBV+60，dBµV=dBV+120。
// 反算：V=sqrt(R*0.001*10^(dBm/10))；Watt→V=sqrt(P*R)。
export function convertLevel(value, from, to, r = 50) {
  if (from === to) return value;
  if (!(r > 0) || !Number.isFinite(r)) return NaN;
  const v = from === 'Vrms' ? value : from === 'Watt' ? Math.sqrt(value * r)
    : from === 'dBm' ? Math.sqrt(r * 0.001) * 10 ** (value / 20)
    : 10 ** ((value - ({ dBV: 0, dBmV: 60, 'dBµV': 120 }[from] ?? NaN)) / 20);
  if (!(v >= 0)) return NaN;
  // 與後端一致，對數零點以 1e-20 Vrms 為底。
  const db = 20 * Math.log10(Math.max(v, 1e-20));
  return to === 'Vrms' ? v : to === 'Watt' ? v * v / r : to === 'dBm' ? db - 10 * Math.log10(r * 0.001)
    : db + ({ dBV: 0, dBmV: 60, 'dBµV': 120 }[to] ?? NaN);
}
export function selectPeaks(peaks, { level, count, sort }) {
  const rows = peaks.filter(p => p.y > level);
  const compare = sort === 'Increasing Frequency' ? (a, b) => a.x - b.x
    : sort === 'Decreasing Frequency' ? (a, b) => b.x - a.x
    : sort === 'Increasing Magnitude' ? (a, b) => a.y - b.y : (a, b) => b.y - a.y;
  return rows.sort((a, b) => compare(a, b) || a.x - b.x).slice(0, count);
}
// 抓滿上限且基準線仍在已抓最小峰值之下，才可能有峰被截掉。
export const peaksTruncated = (peaks, level = -Infinity) => peaks.length >= PEAK_LIMIT && level < Math.min(...peaks.map(p => p.y));
export const needsRefetch = (cache, key, level) => !cache || cache.key !== key || level < cache.floor;
export function fftMarkerModel({ store }, initial = {}) {
  if (models.has(store)) return models.get(store);
  store.set({ fftMarker: { level: initial.peakLevel ?? -40, unit: initial.unit ?? 'dBm', count: initial.peakCount ?? 5,
    sort: initial.peakSort ?? 'Decreasing Magnitude', r: 50, preview: null, shown: 0 } });
  let cache = null, pending = null;
  const state = () => store.get().fftMarker;
  const patch = p => {
    const next = { ...state(), ...p }, r = store.get().fftResult;
    const v = next.preview ?? next.level;
    const level = FFT_UNITS.includes(r?.unit) ? convertLevel(v, next.unit, r.unit, next.r) : v;
    next.shown = r?.ok && r.unit !== '°' ? selectPeaks(r.peaks ?? [], { ...next, level }).length : 0;
    store.set({ fftMarker: next }, 'user');
  };
  const model = {
    state,
    level(v) { if (Number.isFinite(v) && (!['Vrms', 'Watt'].includes(state().unit) || v >= 0)) patch({ level: v, preview: null }); },
    preview(v) { patch({ preview: Number.isFinite(v) ? Math.max(['Vrms', 'Watt'].includes(state().unit) ? 0 : -Infinity, v) : null }); },
    unit(u) {
      if (![...FFT_UNITS, 'Phase'].includes(u)) return;
      const s = state(), level = convertLevel(s.level, s.unit, u, s.r);
      patch({ unit: u, level: Number.isFinite(level) ? level : s.level, preview: null });
    },
    count(n) { if (Number.isInteger(n) && n >= 1) patch({ count: n }); },
    sort(s) { if (['Decreasing Magnitude', 'Increasing Magnitude', 'Increasing Frequency', 'Decreasing Frequency'].includes(s)) patch({ sort: s }); },
    resistance(r) { if (r > 0 && Number.isFinite(r) && r !== state().r) patch({ r }); },
    // 相容既有工具列參數名稱；getter/setter 直接指向同一份 store 真值。
    bind(p) {
      for (const [key, name, set] of [['peakLevel', 'level', model.level], ['unit', 'unit', model.unit], ['peakCount', 'count', model.count], ['peakSort', 'sort', model.sort]]) {
        Object.defineProperty(p, key, { enumerable: true, configurable: true, get: () => state()[name], set });
      }
    },
    key(args) { const { peak_count, peak_level, peak_sort, ...rest } = args; return JSON.stringify([store.get().file?.gen, rest]); },
    needs(args) { return needsRefetch(pending ?? cache, model.key(args), state().level); },
    request(args) {
      const key = model.key(args), floor = cache?.key === key ? Math.min(cache.floor, state().level) : state().level;
      pending = { key, floor };
      return { ...args, peak_count: PEAK_LIMIT, peak_level: floor, peak_sort: 'Decreasing Magnitude' };
    },
    accept(r, args) {
      pending = null;
      cache = r.ok ? { key: model.key(args), floor: args.peak_level, id: r.spectrum_id } : null;
    },
    cancel() { pending = null; },
    fail() { pending = cache = null; }, // FFT 失敗：清快取，下次一定重抓
    reset() { cache = pending = null; model.preview(null); },
    displayLevel(r = store.get().fftResult, preview = true) {
      const s = state(), v = preview ? s.preview ?? s.level : s.level;
      // 衍生通道只有來源有效值，不能套用電壓／功率換算。
      return r?.unit && FFT_UNITS.includes(r.unit) ? convertLevel(v, s.unit, r.unit, s.r) : v;
    },
    previewFromSpectrum(v, r) {
      const s = state();
      model.preview(FFT_UNITS.includes(r?.unit) ? convertLevel(v, r.unit, s.unit, s.r) : v);
    },
    rows() {
      const r = store.get().fftResult, s = state();
      if (!r?.ok || r.unit === '°') return [];
      return selectPeaks(r.peaks ?? [], { ...s, level: model.displayLevel() });
    },
    get truncated() { const r = store.get().fftResult; return !!r?.ok && peaksTruncated(r.peaks ?? [], model.displayLevel(r)); },
  };
  for (const [name, fn] of [['level', model.level], ['unit', model.unit], ['count', model.count], ['sort', model.sort]]) store.onCommand(`fftMarker.${name}`, name === 'unit' ? u => FFT_UNITS.includes(u) && fn(u) : fn); // 指令不收 Phase／未知單位
  store.on(['file'], model.reset);
  store.on(['fftResult'], () => patch({}));
  models.set(store, model); return model;
}
