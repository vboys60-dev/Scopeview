import { fftManualModel } from './fft_manual.js';
import { plotColors, tickLabel } from './plotcore.js';
// 基準線優先於頻譜平移；預覽只更新模型，放開才定案與判斷是否補抓。
import { fftMarkerModel } from './fft_markers.js';
export function fftGesture(rect, x, y, lineY) {
  if (x < rect.l || x > rect.l + rect.w || y < rect.t || y > rect.t + rect.h) return null;
  return Number.isFinite(lineY) && lineY >= rect.t && lineY <= rect.t + rect.h && Math.abs(y - lineY) <= 4 ? 'baseline' : 'pan';
}
export function createFftMarkerLayer(canvas, ctx, geometry, ymap, result, draw, fmap = () => null) {
  const model = fftMarkerModel(ctx), manual = fftManualModel(ctx);
  let active = null, drag = null;
  const local = e => { const b = canvas.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
  const rawY = () => ymap()(model.displayLevel(result()));
  // 超出 Y 軸範圍時貼上／下邊緣，仍可點到、拖回。
  const lineY = () => { const r = geometry(), y = rawY(); return Number.isFinite(y) ? Math.max(r.t, Math.min(r.t + r.h, y)) : y; };
  const available = () => result()?.ok && result().unit !== '°';
  const visible = () => {
    const F = fmap(), r = geometry();
    return F && available() ? manual.points().filter(p => Number.isFinite(p.y) && Number.isFinite(F(p.x)) && F(p.x) >= r.l && F(p.x) <= r.l + r.w) : [];
  };
  const kind = e => {
    if (!available()) return null;
    const [x, y] = local(e), F = fmap();
    const p = visible().find(p => Math.abs(x - F(p.x)) <= 8 && Math.abs(y - ymap()(p.y)) <= 8);
    return p ?? fftGesture(geometry(), x, y, lineY());
  };
  const finish = (e, commit) => {
    if (active === null || e && e.pointerId !== active) return;
    const id = active, v = model.state().preview; active = null;
    const moved = drag; drag = null;
    if (moved) {
      if (commit && moved.moved) manual.move(moved.id, moved.x).then(reason => { if (reason) ctx.ui?.toast(reason, 'warning'); }).catch(e => ctx.ui?.toast(`手動 Marker 失敗：${e.message}`, 'error'));
      draw();
    } else if (commit && v !== null) model.level(v); else model.preview(null);
    if (canvas.hasPointerCapture?.(id)) canvas.releasePointerCapture(id);
  };
  const down = e => {
    const target = kind(e);
    if (e.button !== 0 || !target || target === 'pan') return;
    if (typeof target === 'object') drag = { id: target.id, start: local(e)[0], x: target.x, moved: false };
    active = e.pointerId; e.preventDefault(); canvas.setPointerCapture(e.pointerId);
  };
  const move = e => {
    if (active === null) { if (available()) { const k = kind(e); canvas.style.cursor = typeof k === 'object' && k ? 'ew-resize' : k === 'baseline' ? 'ns-resize' : 'grab'; } return; }
    if (e.pointerId !== active) return;
    const r = geometry(), y = Math.max(r.t, Math.min(r.t + r.h, local(e)[1]));
    if (drag) {
      const x = Math.max(r.l, Math.min(r.l + r.w, local(e)[0]));
      drag.x = fmap().inv(x); drag.moved ||= Math.abs(local(e)[0] - drag.start) >= 3;
      canvas.style.cursor = 'ew-resize'; draw(); return;
    }
    const value = ymap().inv(y);
    // 頻譜換單位期間仍用目前頻譜座標，轉回模型單位。
    model.previewFromSpectrum(value, result());
  };
  const up = e => finish(e, true), cancel = e => finish(e, false);
  const key = e => { if (e.key === 'Escape') finish(null, false); };
  const events = [['pointerdown', down], ['pointermove', move], ['pointerup', up], ['pointercancel', cancel], ['lostpointercapture', cancel]];
  events.forEach(([name, fn]) => canvas.addEventListener(name, fn)); window.addEventListener?.('keydown', key);
  const off = ctx.store.on(['fftMarker'], draw), offFile = ctx.store.on(['file'], () => finish(null, false));
  // 拖曳中結果更新不取消預覽；只有換了頻譜（spectrum_id）才取消。
  let sid = result()?.spectrum_id;
  const offRes = ctx.store.on(['fftResult'], () => { const n = result()?.spectrum_id; if (n !== sid) { sid = n; finish(null, false); } });
  return {
    owns: () => active !== null,
    hit: e => { const k = kind(e); return k != null && k !== 'pan'; },
    draw(g) {
      if (!available()) return;
      const r = geometry(), y = lineY(), raw = rawY();
      if (!Number.isFinite(y)) return;
      g.save(); g.strokeStyle = plotColors().amber; g.fillStyle = plotColors().amber; g.lineWidth = 1.5; g.setLineDash([6, 4]);
      g.beginPath(); g.moveTo(r.l, y); g.lineTo(r.l + r.w, y); g.stroke();
      if (raw !== y) { // 超出畫面：箭頭＋數值標籤
        const up = raw < y, v = model.displayLevel(result()), u = result().unit;
        g.setLineDash([]); g.textAlign = 'right'; g.textBaseline = up ? 'top' : 'bottom';
        g.fillText(`${up ? '▲' : '▼'} ${Number(v.toPrecision(4))} ${u}（超出畫面）`, r.l + r.w - 6, y + (up ? 3 : -3));
      }
      g.restore();
      g.save(); g.fillStyle = g.strokeStyle = '#2dd4bf'; g.textAlign = 'center'; g.setLineDash([]);
      const F = fmap();
      for (const p of visible()) {
        if (drag?.id === p.id && drag.moved) continue;
        const x = F(p.x), y = ymap()(p.y);
        g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x + 6, y); g.lineTo(x, y + 6); g.lineTo(x - 6, y); g.closePath(); g.fill();
        g.fillText(`M${p.id}`, x, y - 10);
      }
      if (drag?.moved) {
        const x = F(drag.x); g.setLineDash([4, 3]); g.beginPath(); g.moveTo(x, r.t); g.lineTo(x, r.t + r.h); g.stroke();
        g.fillText(`M${drag.id} ${tickLabel(drag.x, 'Hz')}`, x, r.t + 24);
      }
      g.restore();
    },
    dispose() { finish(null, false); events.forEach(([name, fn]) => canvas.removeEventListener?.(name, fn)); window.removeEventListener?.('keydown', key); off(); offFile(); offRes(); },
  };
}
