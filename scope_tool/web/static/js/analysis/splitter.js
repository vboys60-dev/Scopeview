// L4：三條分隔線共用 pointer／鍵盤事件；偏好更新一律走 layout.* command。
import { resizeValue } from './layout.js';
export function mountSplitter(host, { kind, button, store, getState }) {
  const vertical = kind === 'side', attr = (k,v) => host.setAttribute(k,String(v));
  host.className = `analysis__splitter analysis__splitter--${kind}`;
  host.tabIndex = 0; attr('role','separator'); attr('aria-orientation',vertical ? 'vertical' : 'horizontal');
  attr('aria-label', { side:'量測欄寬度', lower:'結果區高度', fft:'FFT 高度' }[kind]);
  host.append(button);
  let drag = null, pending = null, frame = 0;
  const coordinate = (e) => vertical ? e.clientX : e.clientY;
  const send = (value) => store.command('layout.resize', { kind, value });
  const flush = () => { frame = 0; if (pending !== null) { send(pending); pending = null; } };
  function end(cancel = false) {
    if (!drag) return;
    if (frame) cancelAnimationFrame(frame); frame = 0;
    const d = drag; drag = null;
    if (cancel) { pending = null; store.command('layout.restore', d.prefs); } else flush();
    if (host.hasPointerCapture(d.id)) host.releasePointerCapture(d.id);
    store.command('layout.dragging', false);
  }
  host.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target === button) return;
    if (!vertical && host.getBoundingClientRect) {
      const r = host.getBoundingClientRect(); if (Math.abs(e.clientY-r.top-r.height/2) > 5) return;
    }
    const s = getState(); if (s.collapsed || s.disabled) return;
    e.preventDefault(); drag = { id:e.pointerId, at:coordinate(e), value:s.value, max:s.max, prefs:{ ...s.prefs } };
    host.setPointerCapture(e.pointerId); store.command('layout.dragging',true);
  });
  host.addEventListener('pointermove', (e) => {
    if (!drag || drag.id !== e.pointerId) return;
    pending = resizeValue(kind,drag.value,(coordinate(e)-drag.at)*(vertical ? 1 : -1),drag.max);
    if (!frame) frame = requestAnimationFrame(flush);
  });
  host.addEventListener('pointerup', () => end());
  for (const name of ['pointercancel','lostpointercapture']) host.addEventListener(name, () => end(true));
  const escape = (e) => { if (e.key === 'Escape') end(true); };
  const blur = () => end(true);
  window.addEventListener('keydown',escape); window.addEventListener('blur',blur);
  host.addEventListener('dblclick', (e) => { if (e.target !== button) store.command('layout.reset',kind); });
  button.onclick = () => store.command('layout.toggle',kind);
  host.addEventListener('keydown', (e) => {
    if (e.target === button) return;
    if (e.key === 'Escape') { end(true); return; }
    if (getState().disabled) return;
    if (e.key === 'Enter') { e.preventDefault(); store.command('layout.toggle',kind); return; }
    const keys = vertical ? ['ArrowLeft','ArrowRight'] : ['ArrowUp','ArrowDown'];
    if (!keys.includes(e.key)) return;
    e.preventDefault(); const s = getState(); if (s.collapsed) return;
    send(resizeValue(kind,s.value,(e.key === keys[0] ? -1 : 1)*(vertical ? 1 : -1)*(e.shiftKey ? 40 : 10),s.max));
  });
  return { update({ value, collapsed, max, disabled = false }) {
    host.hidden = disabled; host.tabIndex = disabled ? -1 : 0; attr('aria-disabled',disabled);
    attr('aria-valuenow',Math.round(value)); attr('aria-valuemin',collapsed ? (vertical ? 36 : 28) : vertical ? 180 : kind === 'lower' ? 120 : 160);
    attr('aria-valuemax',Math.round(Math.max(value,max))); button.setAttribute('aria-expanded',String(!collapsed));
  }, dispose() { end(true); window.removeEventListener('keydown',escape); window.removeEventListener('blur',blur); } };
}
