// L5：固定摘要；來源真值仍由 cursors.js 持有。
import { cursorSource, onCursorSource } from './cursors.js';
import { fmt } from '../fmt.js';
export function summaryText(mode, source, cur, values) {
  const dx = Number.isFinite(cur.x1) && Number.isFinite(cur.x2) ? cur.x2 - cur.x1 : null;
  const dy = Number.isFinite(values.y1) && Number.isFinite(values.y2) ? values.y2 - values.y1 : null;
  return `${mode ?? '傳統游標'}｜來源 ${source?.name ?? '—'}｜ΔX ${fmt(dx,'s')}｜1/ΔX ${dx ? fmt(1/dx,'Hz') : '—'}｜ΔY ${fmt(dy,source?.unit ?? '')}`;
}
export function mountSummary(el, store) {
  const box = document.createElement('span'); box.className = 'analysis__cursorSummary'; el.append(box);
  const render = () => {
    const s = store.get(), src = cursorSource(store);
    const tracked = s.markerMode === 'Track Waveforms' && src.readout?.mode === s.markerMode ? src.readout : null;
    box.textContent = box.title = summaryText(s.markerMode, src.channel,
      tracked ? {x1:tracked.t1,x2:tracked.t2} : s.cursors, tracked ? {y1:tracked.v1,y2:tracked.v2} : src);
  };
  store.on(['cursors','markerMode','channels','file'],render); onCursorSource(store,render); render();
}
/** 後端目錄可能尚未列出此模式；永遠只加一個且禁用。 */
export function disableTrackMeasurements(select) {
  let option = [...(select.options ?? select.children)].find(o => o.value === 'Track Measurements');
  if (!option) { option = new Option('Track Measurements','Track Measurements'); select.append(option); }
  option.disabled = true; option.title = '需先補後端事件座標，暫未提供';
}
