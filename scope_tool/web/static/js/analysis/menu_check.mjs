// 無框架驗證 Popover 接線與邊界定位。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { menuPosition, popMenu } from './marker_menu.js';

class Element {
  constructor(rect = {}) { this.rect = rect; this.style = {}; this.attrs = {}; this.listeners = {}; this.closed = 0; }
  setAttribute(name, value) { this.attrs[name] = value; }
  getAttribute(name) { return this.attrs[name] ?? null; }
  querySelectorAll() { return (this.items ?? []).filter(e => !e.disabled); }
  contains(e) { return (this.items ?? []).includes(e); }
  focus() { document.activeElement = this; }
  addEventListener(name, listener) { (this.listeners[name] ??= []).push(listener); }
  emit(name, event = {}) { for (const listener of this.listeners[name] ?? []) listener(event); }
  getBoundingClientRect() { return this.rect; }
  hidePopover() { this.closed++; }
}

assert.deepEqual(menuPosition(790, 100, 100, 80, 800, 600), { left: 690, top: 100 });
assert.deepEqual(menuPosition(100, 590, 100, 80, 800, 600), { left: 100, top: 510 });
globalThis.document = { activeElement: null };
globalThis.innerWidth = 800; globalThis.innerHeight = 600;
globalThis.window = new Element();
const button = new Element({ left: 790, bottom: 590 });
const panel = new Element({ width: 100, height: 80 });
assert.equal(popMenu(button, panel), panel);
assert.equal(panel.popover, 'auto');
assert.equal(button.popoverTargetElement, panel);
assert.equal(button.attrs['aria-haspopup'], 'true');
panel.emit('toggle', { newState: 'closed' });
assert.equal(panel.style.left, undefined);
panel.emit('toggle', { newState: 'open' });
assert.equal(panel.style.left, '690px'); assert.equal(panel.style.top, '510px');
panel.emit('click', { target: { closest: selector => selector === '[role=menuitem]' ? {} : null } });
assert.equal(panel.closed, 1);
panel.emit('click', { target: { closest: () => null } });
assert.equal(panel.closed, 1);
window.emit('resize'); assert.equal(panel.closed, 2);
let placed = 0;
const custom = new Element();
popMenu(button, custom, () => { placed++; });
custom.emit('toggle', { newState: 'open' }); assert.equal(placed, 1);
const menu = new Element({ width: 20, height: 20 }), trigger = new Element({ left: 0, bottom: 0 });
menu.setAttribute('role', 'menu');
menu.items = [new Element(), new Element(), new Element()];
for (const item of menu.items) item.setAttribute('role', 'menuitem');
menu.items[1].disabled = true;
menu.hidePopover = () => { menu.closed++; menu.emit('toggle', { newState: 'closed' }); };
popMenu(trigger, menu); menu.emit('toggle', { newState: 'open' });
assert.equal(document.activeElement, menu.items[0]); assert.equal(trigger.getAttribute('aria-expanded'), 'true');
const key = (panel, target, name) => { let prevented = false; panel.emit('keydown', { target, key: name, preventDefault() { prevented = true; } }); return prevented; };
assert.ok(key(menu, menu.items[0], 'ArrowUp')); assert.equal(document.activeElement, menu.items[2]);
assert.ok(key(menu, menu.items[2], 'ArrowDown')); assert.equal(document.activeElement, menu.items[0]);
assert.ok(key(menu, menu.items[0], 'End')); assert.equal(document.activeElement, menu.items[2]);
assert.ok(key(menu, menu.items[2], 'Home')); assert.equal(document.activeElement, menu.items[0]);
assert.ok(key(menu, menu.items[0], 'Escape')); assert.equal(document.activeElement, trigger);
assert.equal(trigger.getAttribute('aria-expanded'), 'false');
assert.equal(key(custom, menu.items[0], 'ArrowDown'), false);
menu.items.forEach(e => { e.disabled = true; }); assert.doesNotThrow(() => key(menu, menu.items[0], 'ArrowDown'));
delete globalThis.window;
const bare = new Element({ width: 20, height: 20 });
bare.hidePopover = undefined;
assert.doesNotThrow(() => {
  popMenu(button, bare); bare.emit('toggle', { newState: 'open' });
  bare.emit('click', { target: { closest: () => ({}) } });
});
console.log('menu self-check OK');

const toolbar = readFileSync(new URL('./toolbar.js', import.meta.url), 'utf8');
assert.match(toolbar, /menu\("分析", bFft, bMath, bStack, bOverlay, h\("hr"\), \.\.\.gridItems\)/);
assert.match(toolbar, /el\.append\(fieldOf\("FFT 計算", on\), fieldOf\("Marker", marker\)/);
