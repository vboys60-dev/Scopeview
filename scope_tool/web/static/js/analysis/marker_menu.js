// 右鍵選單獨立管理生命週期；座標以視窗為準，碰到邊緣就翻轉。
export function menuPosition(x, y, w, h, vw, vh) {
  return { left: Math.max(0, Math.min(x + w > vw ? x - w : x, vw - w)),
    top: Math.max(0, Math.min(y + h > vh ? y - h : y, vh - h)) };
}
import { popoverFallback } from './popover_fallback.js';
export function markerMenuItems(state, ch, t, hit, model) {
  const full = state.markerTable.filter(p => !p.link && p.ch === ch).length >= 10;
  return [
    { text: state.markerTable.some(p => p.link) ? '移動 M1 到此' : '在此放 M1（連動，各通道）', run: () => model.add({ ch, t, link: true }) },
    { text: `在 ${ch} 新增獨立 Marker${full ? '（已達 10 點上限）' : ''}`, disabled: full, run: () => model.add({ ch, t }) },
    ...(hit ? [{ text: hit.link ? '刪除連動組（M1 全部通道）' : '刪除', run: () => model.remove(hit.id) }] : []),
  ];
}
function menuKey(panel, e, onEsc) {
  if (e.target?.getAttribute?.('role') !== 'menuitem') return;
  const items = [...panel.querySelectorAll('[role=menuitem]:not(:disabled)')];
  const i = items.indexOf(e.target);
  if (e.key === 'Escape') { e.preventDefault(); onEsc(); return; }
  if (!items.length || i < 0) return;
  const next = { ArrowDown: (i + 1) % items.length, ArrowUp: (i + items.length - 1) % items.length, Home: 0, End: items.length - 1 }[e.key];
  if (next !== undefined) { e.preventDefault(); items[next].focus(); }
}
export function createMarkerMenu() {
  let menu = null, previous = null;
  const close = () => {
    if (!menu) return;
    const m = menu; menu = null; m.remove(); // 先清 menu：移除焦點按鈕會同步觸發 focusout，不可重入
    document.removeEventListener('pointerdown', outside, true);
    document.removeEventListener('keydown', key, true);
    window.removeEventListener('resize', close);
    window.removeEventListener('blur', close);
  };
  // 點外面只關選單，這次點擊不穿透到主圖。
  const outside = e => { if (!menu?.contains(e.target)) { e.stopPropagation?.(); e.preventDefault?.(); close(); } };
  const focusout = e => { if (e.relatedTarget && !menu?.contains(e.relatedTarget)) close(); };
  const key = e => { if (menu) menuKey(menu, e, () => { e.stopPropagation(); close(); previous?.focus?.({ preventScroll: true }); }); };
  return { close, open(x, y, items) {
    close(); previous = document.activeElement;
    menu = document.createElement('div'); menu.className = 'marker-menu'; menu.setAttribute('role', 'menu');
    Object.assign(menu.style, { position: 'fixed', zIndex: '10000', display: 'grid', padding: '4px', background: 'var(--c-surface)', color: 'var(--c-text)', border: '1px solid var(--c-border)', borderRadius: '4px', boxShadow: '0 2px 8px #0004', maxWidth: '100vw', maxHeight: '100vh', overflow: 'auto' });
    for (const item of items) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'btn btn--small';
      b.textContent = item.text; b.disabled = !!item.disabled; b.setAttribute('role', 'menuitem');
      b.onclick = () => { close(); item.run(); previous?.focus?.({ preventScroll: true }); }; menu.append(b);
    }
    document.body.append(menu);
    const r = menu.getBoundingClientRect(), p = menuPosition(x, y, r.width, r.height, innerWidth, innerHeight);
    menu.style.left = `${p.left}px`; menu.style.top = `${p.top}px`;
    document.addEventListener('pointerdown', outside, true); document.addEventListener('keydown', key, true);
    menu.addEventListener('mousedown', e => e.preventDefault()); // 保留焦點，避免 WebKit 在 click 前關閉選單。
    menu.addEventListener('focusout', focusout);
    window.addEventListener('resize', close); window.addEventListener('blur', close);
    menu.querySelector('button:not(:disabled)')?.focus();
  } };
}

export function popMenu(button, panel, place) {
  panel.popover = 'auto'; button.popoverTargetElement = panel; popoverFallback(button, panel);
  button.setAttribute('aria-haspopup', panel.getAttribute?.('role') === 'menu' ? 'menu' : 'true');
  button.setAttribute('aria-expanded', 'false');
  panel.addEventListener?.('keydown', e => {
    if (panel.getAttribute?.('role') === 'menu') menuKey(panel, e, () => panel.hidePopover?.());
  });
  panel.addEventListener?.('toggle', e => {
    button.setAttribute('aria-expanded', String(e.newState === 'open'));
    if (e.newState !== 'open') { if (panel.contains?.(document.activeElement)) button.focus(); return; }
    if (panel.getAttribute?.('role') === 'menu') panel.querySelectorAll('[role=menuitem]:not(:disabled)')[0]?.focus();
    if (place) { place(); return; }
    const r = button.getBoundingClientRect(), { width, height } = panel.getBoundingClientRect();
    const p = menuPosition(r.left, r.bottom, width, height, globalThis.innerWidth, globalThis.innerHeight);
    panel.style.left = `${p.left}px`; panel.style.top = `${p.top}px`;
  });
  panel.addEventListener?.('click', e => { if (e.target?.closest?.('[role=menuitem]')) panel.hidePopover?.(); });
  globalThis.window?.addEventListener?.('resize', () => panel.hidePopover?.());
  return panel;
}
