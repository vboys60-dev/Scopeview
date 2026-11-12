// 版面 C（右側欄）自檢：node --experimental-default-type=module dock_check.mjs
import assert from 'node:assert/strict';
import { clampLayout, defaults, validatePrefs, DOCK_WIDTH } from './layout.js';
import { mountTabs } from './bpanel.js';

const base = { W: 1400, H: 700, vw: 1400, vh: 900, fftOn: false };
const on = { ...defaults(), markerSide: true };
const off = clampLayout({ ...base, prefs: defaults() }), d = clampLayout({ ...base, prefs: on });
assert.equal(off.docked, false); assert.equal(d.docked, true);
assert.equal(d.lower, 0); assert.equal(d.dockWidth, DOCK_WIDTH);
assert.equal(d.plotWidth, off.plotWidth - DOCK_WIDTH);
assert.ok(d.main > off.main, '結果欄移走後主圖變高');
// <1280px 與浮動時不啟用，也不改偏好
assert.equal(clampLayout({ ...base, vw: 800, prefs: on }).docked, false);
assert.equal(clampLayout({ ...base, vw: 800, prefs: on }).canDock, false);
assert.equal(clampLayout({ ...base, prefs: on, lowerFloating: true }).docked, false);
assert.equal(validatePrefs({ ...on, version: 1 }).markerSide, true);
assert.equal(validatePrefs({ version: 1, markerSide: 'x' }).markerSide, false);
// 右側欄：游標／Marker 兩表同時顯示（即使 B 寬度很窄）
const el = () => { const e = { hidden: false, dataset: {}, setAttribute() {}, append() {}, addEventListener() {}, parentNode: { dataset: {} } }; return e; };
globalThis.document = { createElement: el };
const panels = { measure: el(), cursor: el(), marker: el(), peaks: el() };
const t = mountTabs(el(), panels, { initial: { version: 1, columns: ['mean'], tab: 'marker' }, persist() {} });
t.update({ width: 340, height: 600, docked: true });
assert.equal(panels.cursor.hidden, false); assert.equal(panels.marker.hidden, false);
t.update({ width: 340, height: 600, docked: false });
assert.equal(panels.cursor.hidden, true); assert.equal(panels.marker.hidden, false);
console.log('dock_check OK');
