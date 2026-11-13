// node --experimental-default-type=module popover_fallback_check.mjs
import assert from 'node:assert/strict';
const mk = () => { const l = {}, a = new Set(); return { l, hidden: false, addEventListener: (t, f) => (l[t] ??= []).push(f), fire: (t, e) => (l[t] || []).forEach(f => f(e)),
  dispatchEvent(e) { this.fire(e.type, e); }, toggleAttribute: (n, v) => v ? a.add(n) : a.delete(n), has: n => a.has(n), contains: x => x === 'in' }; };
globalThis.HTMLElement = class {}; globalThis.Event = class { constructor(t) { this.type = t; } };
const docs = mk(); globalThis.document = docs;
const { popoverFallback } = await import('./popover_fallback.js');
const b = mk(), p = mk(), seen = [], ancestor = mk();
ancestor.classList = { add: n => ancestor.toggleAttribute(n, true), remove: n => ancestor.toggleAttribute(n, false) };
p.parentElement = ancestor; globalThis.getComputedStyle = () => ({ zIndex: '3' });
p.addEventListener('toggle', e => seen.push(e.newState));
assert.equal(popoverFallback(b, p), true); assert.equal(p.hidden, true);
b.fire('click'); assert.equal(p.hidden, false); assert.ok(p.has('data-open')); assert.ok(ancestor.has('popover-fallback-stack'));
docs.fire('pointerdown', { target: 'in' }); assert.equal(p.hidden, false, '面板內點擊不關');
docs.fire('pointerdown', { target: 'out' }); assert.equal(p.hidden, true);
assert.ok(!ancestor.has('popover-fallback-stack'));
b.fire('click'); docs.fire('keydown', { key: 'Escape' }); assert.equal(p.hidden, true);
b.fire('click'); b.fire('click'); assert.equal(p.hidden, true);
assert.ok(!ancestor.has('popover-fallback-stack'));
assert.deepEqual(seen, ['open', 'closed', 'open', 'closed', 'open', 'closed']);
globalThis.HTMLElement.prototype.popover = null;
assert.equal(popoverFallback(mk(), mk()), false, '支援原生時不介入');
console.log('popover_fallback self-check OK');
