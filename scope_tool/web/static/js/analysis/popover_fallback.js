// 不支援原生 Popover 的視窗（舊版 WebKit）：以 hidden／data-open 補上 show／hidePopover 與 toggle 事件。
export function popoverFallback(button, panel) {
  if (!globalThis.HTMLElement || 'popover' in globalThis.HTMLElement.prototype) return false;
  let open = false;
  const set = v => {
    if (v === open) return;
    open = v; panel.hidden = !v; panel.toggleAttribute('data-open', v);
    panel.dispatchEvent(Object.assign(new Event('toggle'), { newState: v ? 'open' : 'closed' }));
  };
  panel.hidden = true; panel.showPopover = () => set(true); panel.hidePopover = () => set(false);
  button.addEventListener('click', () => set(!open));
  document.addEventListener('pointerdown', e => { if (open && !panel.contains(e.target) && !button.contains(e.target)) set(false); }, true);
  document.addEventListener('keydown', e => { if (open && e.key === 'Escape') set(false); });
  return true;
}
