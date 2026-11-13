// 共用祖先可能同時有多個浮層，最後一個關閉才還原層級。
const stackingUsers = new WeakMap();
// 不支援原生 Popover 的視窗（舊版 WebKit）：以 hidden／data-open 補上 show／hidePopover 與 toggle 事件。
export function popoverFallback(button, panel) {
  if (!globalThis.HTMLElement || 'popover' in globalThis.HTMLElement.prototype) return false;
  let open = false, ancestors = [];
  const stack = v => {
    if (v) {
      for (let a = panel.parentElement; a; a = a.parentElement) {
        if (getComputedStyle(a).zIndex === 'auto') continue;
        ancestors.push(a); stackingUsers.set(a, (stackingUsers.get(a) ?? 0) + 1);
        a.classList.add('popover-fallback-stack');
      }
    } else {
      for (const a of ancestors) {
        const users = stackingUsers.get(a) - 1;
        if (users) stackingUsers.set(a, users);
        else { stackingUsers.delete(a); a.classList.remove('popover-fallback-stack'); }
      }
      ancestors = [];
    }
  };
  const set = v => {
    if (v === open) return;
    open = v; stack(v); panel.hidden = !v; panel.toggleAttribute('data-open', v);
    panel.dispatchEvent(Object.assign(new Event('toggle'), { newState: v ? 'open' : 'closed' }));
  };
  panel.hidden = true; panel.showPopover = () => set(true); panel.hidePopover = () => set(false);
  button.addEventListener('click', () => set(!open));
  document.addEventListener('pointerdown', e => { if (open && !panel.contains(e.target) && !button.contains(e.target)) set(false); }, true);
  document.addEventListener('keydown', e => { if (open && e.key === 'Escape') set(false); });
  return true;
}
