// 既有工具列直接綁定模型；拖線預覽也更新同一組輸入框。
import { fftMarkerModel } from './fft_markers.js';
export function bindFftMarkerControls(ctx, p, { unit, lvl, cnt, sort, imp, man }, catalog = {}) {
  const model = fftMarkerModel(ctx);
  const resistance = () => model.resistance((catalog.fft_impedances ?? [])[p.imp]?.[1] ?? p.manualR);
  for (const input of [imp, man].filter(Boolean)) {
    const previous = input.onchange;
    input.onchange = () => { previous?.(); resistance(); };
  }
  resistance();
  const sync = () => {
    const s = model.state();
    const set = (el, v) => { if (document.activeElement !== el) el.value = v; }; // 使用者正在輸入就不覆寫
    set(unit, s.unit); set(lvl, String(s.preview ?? s.level)); set(cnt, String(s.count)); set(sort, s.sort);
  };
  lvl.onchange = () => { p.peakLevel = Number(lvl.value); sync(); };
  cnt.onchange = () => { p.peakCount = Number(cnt.value); sync(); };
  sort.onchange = () => { p.peakSort = sort.value; sync(); };
  unit.onchange = () => { p.unit = unit.value; sync(); };
  ctx.store.on(['fftMarker'], sync); sync();
}
