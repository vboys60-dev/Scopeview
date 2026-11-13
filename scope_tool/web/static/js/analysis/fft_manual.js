// 手動點獨立於峰值篩選；只有本模組寫入 fftMarker.manual。
import { fftMarkerModel } from './fft_markers.js';
const models = new WeakMap();
export const MANUAL_LIMIT = 10;
export function fftManualModel(ctx) {
  const { store } = ctx;
  if (models.has(store)) return models.get(store);
  const peaks = fftMarkerModel(ctx), state = () => store.get().fftMarker.manual;
  const points = () => state()?.points ?? [], bins = new Map();
  let refresh = Promise.resolve();
  let epoch = 0, gen = store.get().file?.gen, sid = store.get().fftResult?.spectrum_id, queue = Promise.resolve();
  const write = (list, source = state()?.source ?? store.get().fftResult?.source ?? null) =>
    store.set({ fftMarker: { ...store.get().fftMarker, manual: { source, points: list } } });
  const usable = r => r?.ok && r.spectrum_id && r.unit !== '°';
  const read = async (r, x) => {
    const level = peaks.displayLevel(r, false);
    return ctx.bridge.call('fft_track_rf', { spectrum_id: r.spectrum_id, x, direction: 0, level: Number.isFinite(level) ? level : -40 });
  };
  const clear = () => { epoch++; bins.clear(); write([]); };
  // 新增／拖動依序定案，避免快速連按突破上限或覆蓋另一筆結果。
  const edit = (id, x) => {
    const token = epoch;
    const run = async () => {
      await refresh;
      if (token !== epoch) return null;
      const r = store.get().fftResult;
      if (r?.unit === '°') return 'Phase 模式不支援手動 Marker';
      if (!usable(r) || !Number.isFinite(x)) return '目前沒有可用頻譜';
      if (id == null && points().length >= MANUAL_LIMIT) return '手動 Marker 已達上限 10 個，請先刪除';
      const original = id == null ? null : points().find(p => p.id === id);
      if (id != null && !original) return null;
      let value;
      try { value = await read(r, x); }
      catch (e) { return e?.code === 'STALE' ? null : '讀取手動 Marker 失敗'; }
      if (token !== epoch || id != null && !points().includes(original)) return null;
      if (store.get().fftResult?.spectrum_id !== r.spectrum_id) return '頻譜已更新，請再試';
      if (!Number.isFinite(value?.x)) return '讀取手動 Marker 失敗';
      const duplicate = points().find(p => p.id !== id && (bins.get(p.id) ?? p.x) === value.x);
      if (duplicate) return `此頻率已有 M${duplicate.id}`;
      const nextId = id ?? Array.from({ length: MANUAL_LIMIT }, (_, i) => i + 1).find(n => !points().some(p => p.id === n));
      const p = { id: nextId, x: value.x, y: Number.isFinite(value.y) ? value.y : null };
      bins.set(nextId, value.x);
      write(id == null ? [...points(), p] : points().map(old => old.id === id ? p : old), r.source);
      return null;
    };
    const pending = queue.then(run); queue = pending.catch(() => {}); return pending;
  };
  const model = { points, add: x => edit(null, x), move: (id, x) => edit(id, x),
    remove(id) { bins.delete(id); write(points().filter(p => p.id !== id)); }, clear };
  models.set(store, model);
  write(points());
  store.on(['file', 'fftResult'], st => {
    if (st.file?.gen !== gen) { gen = st.file?.gen; clear(); }
    const r = st.fftResult, next = r?.spectrum_id;
    if (r?.ok && state().source !== r.source) { epoch++; bins.clear(); write([], r.source); }
    if (next === sid) return;
    sid = next; bins.clear(); const token = ++epoch;
    if (!usable(r)) return;
    // 保留原頻率；不同解析度只更新振幅。逐點回寫時核對物件，避免復活已刪或已拖的點。
    refresh = Promise.all(points().map(p => {
      return read(r, p.x).then(v => update(v)).catch(e => { if (e?.code !== 'STALE') update(null); });
      function update(v) {
        if (epoch !== token || !points().includes(p) || store.get().fftResult?.spectrum_id !== next) return;
        if (Number.isFinite(v?.x)) bins.set(p.id, v.x);
        write(points().map(old => old === p ? { ...p, y: Number.isFinite(v?.y) ? v.y : null } : old));
      }
    }));
  });
  return model;
}
