// FFT 工作排程與峰快取接線；沿用既有契約，不更動頻譜後端。
import { fftMarkerModel } from './fft_markers.js';
const num = Number.isFinite;
const rangeOf = (st) => (st.rangeMode === "cursors" && num(st.cursors.x1) && num(st.cursors.x2) ? [st.cursors.x1, st.cursors.x2] : null);
const dxOf = (chs) => Object.fromEntries(chs.map((c) => [c.name, c.time_offset || 0]));
/** FFT 參數；阻抗 Ω 缺或 ≤0 回 null。 */
export function fftParams(st, p, catalog) {
  const imp = (catalog.fft_impedances ?? [])[p.imp]?.[1] ?? p.manualR;
  if (!(imp > 0) || !st.file || !p.source) return null;
  return { source: p.source, range: rangeOf(st), dx: dxOf(st.channels), window: p.window, unit: p.unit, r_ohm: imp, peak_count: p.peakCount, peak_level: p.peakLevel, peak_sort: p.peakSort, rbw: p.unit === 'Phase' ? null : p.rbw ?? p.autoRbw ?? null, vbw: p.unit === 'Phase' ? null : p.vbw ?? null };
}

/** FFT 控制器（不碰 DOM）：參數或範圍變動 → 防抖 → bridge.job("fft")；過期結果丟棄；結果帶 peak_level 供 cursors.js 的 RF 使用。 */
export function createFft({ store, bridge }, catalog, p, { delay = 150, onError = () => {}, onReset = () => {} } = {}) {
  const markers = fftMarkerModel({ store }, p); markers.bind(p);
  let dirty = true, pending = false;
  let token = 0, timer = null, lastGen = store.get().file?.gen;
  /** manual＝使用者手動觸發（可用 modal）；自動重跑失敗只 toast 並在 FFT 窗格顯示原因，不擋畫面。 */
  async function run(manual = false) {
    clearTimeout(timer); timer = null;
    const my = ++token, st = store.get(), gen = st.file?.gen, raw = p.on ? fftParams(st, p, catalog) : null;
    if (raw) markers.resistance(raw.r_ohm);
    const args = raw ? markers.request(raw) : null;
    if (!args) return store.set({ fftResult: null, rfPos: null }, "program");
    dirty = false; pending = true;
    try {
      const r = await bridge.job("fft", args);
      if (my !== token || store.get().file?.gen !== gen || (r.gen !== undefined && r.gen !== gen)) { if (my === token) markers.cancel(); return; }
      markers.accept(r, args);
      store.set({ fftResult: { ...r, peak_level: markers.state().level }, ...(r.unit === "°" ? { rfPos: null } : {}) }, "program"); // Phase 無 RF
    } catch (e) { if (my === token) { markers.fail(); onError(e, manual); store.set({ fftResult: { ok: false, reason: e.message, spectrum_id: null, peaks: [] } }, "program"); } }
    finally { if (my === token) pending = false; }
  }
  const invalidate = () => { if (pending || timer) dirty = true; token++; pending = false; clearTimeout(timer); timer = null; markers.cancel(); };
  const schedule = (wait = delay) => { dirty = true; invalidate(); if (p.on) timer = setTimeout(() => run(false), wait); };
  const ensure = () => { if (p.on && !pending && !timer && (dirty || !store.get().fftResult)) schedule(); };
  let markerSig = JSON.stringify([markers.state().level, markers.state().unit]);
  store.on(['fftMarker'], () => {
    const s = markers.state(), next = JSON.stringify([s.level, s.unit]);
    if (next === markerSig) return;
    markerSig = next;
    const args = fftParams(store.get(), p, catalog);
    if (args && markers.needs(args)) schedule();
  });
  const signature = st => JSON.stringify([st.file?.gen, st.rangeMode, st.cursors.x1, st.cursors.x2, dxOf(st.channels)]);
  let sig = signature(store.get());
  store.on(["file", "rangeMode", "cursors", "channels"], (st) => {
    if ((st.file?.gen) !== lastGen) { // 開新檔或關檔：FFT 勾選重置為關閉，進行中的 job 失效
      lastGen = st.file?.gen; p.on = false; invalidate(); dirty = true; store.set({ fftResult: null, rfPos: null }, "program"); onReset();
    }
    const s = signature(st);
    if (s === sig) return;
    sig = s;
    schedule();
  });
  return { run, schedule, invalidate, ensure, get dirty() { return dirty; } };
}

