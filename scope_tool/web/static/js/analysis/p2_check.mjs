// L8：P2a 純函式、真實產品事件與提交路徑；不建立另一套手勢實作。
import assert from "node:assert/strict";
import { createStore } from "./store.js";
import { zoomToRect, viewLimits, limitView, createHistory, gestureFor, shortcutFor, editableTarget, bindViewport, bindGestures, DEFAULT_MODE } from "./gestures.js";
import { step125Strict, stepPosition, horizontalOf, rangeOf, formatHorizontal, mount as mountAxes } from "./axes.js";
import { mount as mountOverview } from "./overview.js";
import { parseSI } from "../fmt.js";
const near = (a, b, tol = 1e-12) => assert.ok(Math.abs(a - b) <= tol, `${a} != ${b}`);
const f = { gen: 1, channels: [{ name: "CH1", t0: -1, t1: 9, points: 1001 }] };
const limits = viewLimits(f), v = { t0: -1, t1: 9 }, r = { l: 100, t: 10, w: 1000, h: 300 };
assert.equal(DEFAULT_MODE, "pan"); near(limits.minSpan, 0.1);
const rectZoom = zoomToRect(v, 300, 700, r, limits);
assert.deepEqual(rectZoom, { t0: 1, t1: 5 });
assert.deepEqual(zoomToRect(v, 700, 300, r, limits), rectZoom);
assert.equal(zoomToRect(v, 300, 300, r, limits), null);
assert.equal(zoomToRect(v, 300, 305.9, r, limits), null);
const tiny = zoomToRect(v, 300, 306, r, limits); near(tiny.t1 - tiny.t0, 0.1);
const clipped = zoomToRect({ t0: -20, t1: 20 }, 100, 1100, r, limits);
assert.deepEqual(clipped, v);
const partial = zoomToRect({ t0: -5, t1: 5 }, 100, 900, r, limits);
assert.ok(partial.t0 >= -1 && partial.t1 <= 9);
assert.equal(limitView({ t0: 1, t1: 1 }, limits), null);
near(limitView({ t0: -100, t1: 100 }, limits).t1 - limitView({ t0: -100, t1: 100 }, limits).t0, 100);
assert.ok(viewLimits({ channels: [{ t0: 1, t1: 1 + 1e-12, points: 1e9 }] }).minSpan >= Number.EPSILON * 32);
for (const [n, up, want] of [[13.4e-9, false, 10e-9], [13.4e-9, true, 20e-9], [10e-9, false, 5e-9], [10e-9, true, 20e-9], [20e-9, false, 10e-9], [50e-9, true, 100e-9], [1, false, 0.5], [1, true, 2]]) near(step125Strict(n, up), want, Math.abs(want) * 1e-13);
assert.ok(Number.isNaN(step125Strict(0, true)));
assert.equal(stepPosition(-13.4, true, 1), -12.4); assert.equal(stepPosition(-13.4, false, 1), -14.4);
assert.equal(stepPosition(0, true, 1), 1); assert.equal(stepPosition(0, false, 1), -1);
assert.equal(formatHorizontal(27, 3000), "27 s");
assert.equal(formatHorizontal(-499.999999999e-6, 100e-6), "-500 µs");
assert.equal(formatHorizontal(-499.999e-6, 1e-9), "-499.999 µs");
assert.equal(formatHorizontal(196.1023e-6, 20e-9), "196.1023 µs");
for (const q of [v, rectZoom, { t0: 196.0023e-6, t1: 196.2023e-6 }]) {
  const p = horizontalOf(q), back = rangeOf(p.scale, p.position); near(back.t0, q.t0); near(back.t1, q.t1);
}
for (const text of ["20n", "20 ns"]) near(rangeOf(parseSI(text), 0).t1 - rangeOf(parseSI(text), 0).t0, 200e-9, 1e-22);
const h = createHistory(), a = { t0: 0, t1: 1 }, b = { t0: 1, t1: 2 }, c = { t0: 2, t1: 3 };
h.record(a, b, { key: "wheel", time: 0 }); h.record(b, c, { key: "wheel", time: 200 });
assert.equal(h.status().undo, 1); assert.deepEqual(h.undo(c), a); assert.deepEqual(h.redo(a), c);
h.undo(c); h.record(a, b); assert.equal(h.status().redo, 0);
h.clear(); h.record(a, b, { key: "wheel", time: 0 }); h.record(b, c, { key: "wheel", time: 301 }); assert.equal(h.status().undo, 2);
h.clear(); h.record(a, b, { key: "pan", time: 0, continuous: true }); h.record(b, c, { key: "pan", time: 2000, continuous: true }); assert.equal(h.status().undo, 1);
h.end(); h.record(c, b, { key: "pan", time: 2001, continuous: true }); assert.equal(h.status().undo, 2);
h.clear(); for (let i = 0; i < 60; i++) h.record({ t0: i, t1: i + 1 }, { t0: i + 1, t1: i + 2 });
assert.equal(h.status().undo, 50); let current = { t0: 60, t1: 61 }; for (let i = 0; i < 50; i++) current = h.undo(current);
assert.deepEqual(current, { t0: 10, t1: 11 }); assert.equal(h.undo(current), null);
// P2a 手勢表逐列（未納入本期的軸區／垂直縮放留待後期）。
for (const [opts, want] of [[{}, "pan"], [{ mode: "zoom" }, "zoom"], [{ shiftKey: true }, "zoom"], [{ mode: "zoom", space: true }, "pan"], [{ mode: "zoom", button: 1 }, "pan"], [{ cursor: true }, "cursor"], [{ mode: "zoom", cursor: true }, "zoom"], [{ shiftKey: true, cursor: true }, "zoom"], [{ handle: true, edge: true, cursor: true }, "handle"], [{ mode: "zoom", edge: true }, "edge"], [{ inside: false }, null], [{ button: 2 }, null]]) assert.equal(gestureFor(opts), want, JSON.stringify(opts));
assert.equal(shortcutFor({ code: "Space" }), "space");
for (const key of [{ key: "z", ctrlKey: true }, { key: "Z", metaKey: true, shiftKey: true }, { code: "Space" }, { key: "y", ctrlKey: true }]) {
  for (const tagName of ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "SUMMARY", "A"]) assert.equal(shortcutFor(key, { tagName }), null);
  assert.equal(shortcutFor(key, { isContentEditable: true }), null);
}
assert.ok(editableTarget({ closest: (selector) => selector.includes('[role="button"]') ? {} : null }));
assert.equal(shortcutFor({ key: "y", ctrlKey: true }), "view.redo");
assert.equal(shortcutFor({ key: "Y", metaKey: true }), "view.redo");
assert.equal(shortcutFor({ key: "z", ctrlKey: true }), "view.undo");
assert.equal(shortcutFor({ key: "Z", metaKey: true, shiftKey: true }), "view.redo");
// 真實產品提交：只改 view、完整時間可復原、換檔清歷史。
const store = createStore(); store.set({ file: f, view: v }); const history = bindViewport(store);
const saved = JSON.stringify([store.get().channels, store.get().cursors]);
store.command("viewport.intent", rectZoom); store.command("view.reset"); store.command("view.undo"); assert.deepEqual(store.get().view, rectZoom);
store.command("view.undo"); assert.deepEqual(store.get().view, v); store.command("view.redo"); assert.deepEqual(store.get().view, rectZoom);
assert.equal(JSON.stringify([store.get().channels, store.get().cursors]), saved);
store.set({ file: { ...f, gen: 2 } }); assert.deepEqual(history.status(), { undo: 0, redo: 0 });
// 用簡單 DOM 外殼掛載產品事件，不複製互動邏輯。
function element(tag = "div") {
  return { tagName: tag.toUpperCase(), dataset: {}, children: [], style: {}, listeners: {}, value: "", captured: false,
    append(...nodes) { this.children.push(...nodes); }, setAttribute() {},
    addEventListener(k, fn) { this.listeners[k] = fn; }, removeEventListener(k) { delete this.listeners[k]; },
    setPointerCapture() { this.captured = true; }, hasPointerCapture() { return this.captured; }, releasePointerCapture() { this.captured = false; },
    getBoundingClientRect: () => ({ left: 0, top: 0 }) };
}
globalThis.document = { activeElement: null, createElement: element };
globalThis.window = element();
const canvas = element("canvas"), gestures = bindGestures(canvas, { store, ui: {} }, () => r, () => {});
const fire = (name, x, extra = {}) => { const e = { clientX: x, clientY: 120, pointerId: 1, button: 0, preventDefault() { this.prevented = true; }, ...extra }; canvas.listeners[name](e); return e; };
store.set({ view: v }); store.command("view.mode", "zoom");
fire("pointerdown", 300); fire("pointermove", 700); fire("pointerup", 700); assert.deepEqual(store.get().view, rectZoom);
store.command("view.undo"); assert.deepEqual(store.get().view, v);
fire("pointerdown", 700); fire("pointermove", 300); window.listeners.keydown({ key: "Escape" }); fire("pointerup", 300); assert.deepEqual(store.get().view, v);
for (const name of ["pointercancel", "lostpointercapture"]) { fire("pointerdown", 300); fire("pointermove", 700); fire(name, 700); fire("pointerup", 700); assert.deepEqual(store.get().view, v); }
fire("pointerdown", 300); fire("pointermove", 700); window.listeners.blur(); fire("pointerup", 700); assert.deepEqual(store.get().view, v);
store.command("view.mode", "pan"); fire("pointerdown", 300, { shiftKey: true }); fire("pointermove", 700); fire("pointerup", 700); assert.deepEqual(store.get().view, rectZoom);
store.set({ view: v }); store.command("view.mode", "zoom");
window.listeners.keydown({ code: "Space", preventDefault() {} });
fire("pointerdown", 300); fire("pointermove", 400); fire("pointerup", 400); assert.deepEqual(store.get().view, { t0: -2, t1: 8 });
window.listeners.keyup({ code: "Space" });
store.set({ view: v }); document.activeElement = { tagName: "INPUT" };
const inputSpace = { code: "Space", preventDefault() { throw Error("輸入框 Space 不可攔截"); } }; window.listeners.keydown(inputSpace);
fire("pointerdown", 300); fire("pointermove", 700); fire("pointerup", 700); assert.deepEqual(store.get().view, rectZoom);
document.activeElement = null; store.set({ view: v });
fire("pointerdown", 300, { button: 1 }); fire("pointermove", 400); fire("pointerup", 400); assert.deepEqual(store.get().view, { t0: -2, t1: 8 });
const bar = element(); mountAxes(bar, { store });
const preview = bar.children.find(e => e.className === "analysis__preview").children[0];
let previewIntent;
store.onCommand("preview.visible", on => { previewIntent = on; });
preview.checked = false; preview.onchange(); assert.equal(previewIntent, false);
store.command("layout.state", { overview: false, blocked: true });
assert.equal(preview.checked, false); assert.equal(preview.disabled, true); assert.match(preview.title, /視窗高度不足/);
store.command("layout.state", { overview: true, blocked: false });
assert.equal(preview.checked, true); assert.equal(preview.disabled, false); assert.equal(preview.title, "");
assert.ok(!bar.children.some(e => e.className === "analysis__cursorSummary"));

const scaleInput = bar.children.flatMap((e) => e.children).find((e) => e.dataset.axis === "scale");
scaleInput.value = "20n"; scaleInput.onkeydown({ key: "Enter", preventDefault() {} });
// 此檔案的取樣界線會夾到 0.1s；另換成 ns 取樣檔測 20n 輸入。
store.set({ file: { channels: [{ t0: -1e-6, t1: 1e-6, points: 20001 }] }, view: { t0: -1e-6, t1: 1e-6 } });
scaleInput.value = "20n"; scaleInput.onkeydown({ key: "Enter", preventDefault() {} }); near(store.get().view.t1 - store.get().view.t0, 200e-9, 1e-21);
const count = history.status().undo; scaleInput.onblur(); assert.equal(history.status().undo, count, "Enter 後 blur 不可多記一筆");
assert.equal(JSON.stringify([store.get().channels, store.get().cursors]), saved);
// 模式下的把手／游標命中優先序、主圖滾輪合併與實際鍵盤 Undo/Redo。
const hits = [];
store.onCommand("channel.scale_intent", (p) => hits.push(["handle", p]));
store.onCommand("cursor.intent", (p) => hits.push(["cursor", p]));
store.set({ channels: [{ name: "CH1", visible: true, position: 0 }], cursors: { x1: null, x2: null, y1: 0, y2: null } });
store.command("view.mode", "zoom");
fire("pointerdown", 8, { clientY: 160 }); fire("pointermove", 8, { clientY: 130 }); fire("pointerup", 8, { clientY: 130 });
assert.equal(hits.at(-1)[0], "handle");
store.command("view.mode", "pan");
fire("pointerdown", 300, { clientY: 160 }); fire("pointermove", 350, { clientY: 130 }); fire("pointerup", 350, { clientY: 130 });
assert.equal(hits.at(-1)[0], "cursor");
store.set({ channels: [], cursors: { x1: null, x2: null, y1: null, y2: null } });
const wheelBefore = { ...store.get().view }, wheelCount = history.status().undo;
for (let i = 0; i < 2; i++) fire("wheel", 600, { deltaY: -120 });
assert.equal(history.status().undo, wheelCount + 1);
const wheelAfter = { ...store.get().view };
window.listeners.keydown({ key: "z", ctrlKey: true, preventDefault() {} }); assert.deepEqual(store.get().view, wheelBefore);
window.listeners.keydown({ key: "Z", metaKey: true, shiftKey: true, preventDefault() {} }); assert.deepEqual(store.get().view, wheelAfter);
document.activeElement = { tagName: "INPUT" };
window.listeners.keydown({ key: "z", ctrlKey: true, preventDefault() { throw Error("輸入框 Undo 不可攔截"); } }); assert.deepEqual(store.get().view, wheelAfter);
document.activeElement = null;
fire("dblclick", 600, { timeStamp: 2000 });
near(store.get().view.t1 - store.get().view.t0, 2e-6); store.command("view.undo"); assert.deepEqual(store.get().view, wheelAfter);
// 回歸：兩次獨立拖曳各一步；拖曳中滾輪不破壞群組。
store.set({ file: f, view: v }); store.command("view.mode", "pan");
const panCount = history.status().undo;
fire("pointerdown", 300); fire("pointermove", 320);
const midPan = { ...store.get().view }; fire("wheel", 600, { deltaY: -120 }); assert.deepEqual(store.get().view, midPan);
for (let i = 1; i <= 30; i++) fire("pointermove", 320 + i);
fire("pointerup", 350);
fire("pointerdown", 300); fire("pointermove", 340); fire("pointerup", 340);
assert.equal(history.status().undo, panCount + 2);
// 失焦必須清掉 Space，即使沒收到 keyup；下一次仍為框選。
store.set({ view: v }); store.command("view.mode", "zoom");
window.listeners.keydown({ code: "Space", preventDefault() {} }); window.listeners.blur();
fire("pointerdown", 300); fire("pointermove", 700); fire("pointerup", 700); assert.deepEqual(store.get().view, rectZoom);
canvas.closest = () => ({});
const hiddenView = { ...store.get().view }, hiddenHistory = history.status();
window.listeners.keydown({ key: "z", ctrlKey: true, preventDefault() { assert.fail("隱藏分頁不可攔截 Undo"); } });
assert.deepEqual(store.get().view, hiddenView); assert.deepEqual(history.status(), hiddenHistory); delete canvas.closest;
for (const target of [{ tagName: "BUTTON" }, { tagName: "SUMMARY" }, { tagName: "A" }, { closest: () => ({}) }]) {
  document.activeElement = target;
  window.listeners.keydown({ code: "Space", preventDefault() { assert.fail("互動元素 Space 不可攔截"); } });
}
document.activeElement = null;
assert.equal(fire("mousedown", 300, { button: 1 }).prevented, true);
assert.notEqual(fire("mousedown", 300).prevented, true);
window.listeners.keydown({ key: "z", ctrlKey: true, preventDefault() {} });
window.listeners.keydown({ key: "y", ctrlKey: true, preventDefault() {} }); assert.deepEqual(store.get().view, hiddenView);
gestures.dispose();
console.log("P2a self-check OK：框選／界線／嚴格檔位／歷史／換算／手勢／輸入焦點／產品事件");
// 有號中心與接近檔位但尚未到檔位的數值都必須嚴格相鄰。
near(step125Strict(10e-9 * (1 + 1e-10), false), 10e-9, 1e-22);
near(step125Strict(10e-9 * (1 - 1e-10), true), 10e-9, 1e-22);
store.set({ file: { channels: [{ t0: -1e-6, t1: 1e-6, points: 20001 }] }, view: { t0: -1e-6, t1: 1e-6 } });
const previous = { ...store.get().view };
scaleInput.value = "bad"; scaleInput.onblur(); assert.deepEqual(store.get().view, previous);
scaleInput.value = "13.4n"; scaleInput.onblur();
const scaleField = bar.children.find((e) => e.children.includes(scaleInput));
scaleField.children.find((e) => e.textContent === "◀").onclick(); near(horizontalOf(store.get().view).scale, 10e-9, 1e-22);
store.command("view.undo"); near(horizontalOf(store.get().view).scale, 13.4e-9, 1e-22);
store.command("view.redo"); near(horizontalOf(store.get().view).scale, 10e-9, 1e-22);
const beforeWheel = { ...store.get().view }, beforeCount = history.status().undo;
for (let i = 0; i < 2; i++) scaleInput.listeners.wheel({ deltaY: -100, preventDefault() {} });
assert.equal(history.status().undo, beforeCount + 1); near(horizontalOf(store.get().view).scale, 50e-9, 1e-22);
store.command("view.undo"); assert.deepEqual(store.get().view, beforeWheel);
const zeroButton = bar.children.find((e) => e.textContent === "0"); assert.equal(zeroButton.disabled, false);
store.set({ file: { channels: [{ t0: 1, t1: 2, points: 10001 }] } }); assert.equal(zeroButton.disabled, true);
console.log("Horizontal 實際欄位／滾輪合併／0 啟用條件 self-check OK");
// 欄位有焦點但未編輯時，外部更新後 Enter／blur 要重繪且不提交舊值。
const positionInput = bar.children.flatMap((e) => e.children).find((e) => e.dataset.axis === "position");
store.set({ file: f, view: v });
for (const action of [() => positionInput.onkeydown({ key: "Enter", preventDefault() {} }), () => positionInput.onblur()]) {
  document.activeElement = positionInput;
  const oldText = positionInput.value, next = { t0: store.get().view.t0 + 1, t1: store.get().view.t1 + 1 };
  store.set({ view: next }); assert.equal(positionInput.value, oldText);
  const n = history.status().undo; action(); assert.deepEqual(store.get().view, next);
  assert.equal(positionInput.value, formatHorizontal(horizontalOf(next).position, 1)); assert.equal(history.status().undo, n);
}
document.activeElement = null;
const positionField = bar.children.find((e) => e.children.includes(positionInput));
store.set({ view: { t0: -5, t1: 5 } });
for (const [label, want] of [["▶", 1], ["◀", 0], ["◀", -1]]) {
  positionField.children.find((e) => e.textContent === label).onclick(); near(horizontalOf(store.get().view).position, want);
}
store.set({ view: { t0: -999.999999998e-6, t1: 0 } });
assert.equal(positionInput.value, "-500 µs"); assert.equal(store.get().view.t0, -999.999999998e-6);
// 掛載真正縮圖：Undo/Redo 後殘留 pointermove 不得重送 intent 或清 redo。
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const originalElement = document.createElement;
document.createElement = (tag) => { const e = element(tag); e.getContext = () => new Proxy({}, { get: () => () => {} }); return e; };
const host = element(); host.getBoundingClientRect = () => ({ width: 1000, height: 56 });
const overviewStore = createStore(); overviewStore.set({ file: f, view: { t0: 1, t1: 5 } });
const oh = bindViewport(overviewStore), ov = mountOverview(host, { store: overviewStore, bridge: {} });
await Promise.resolve();
const oc = host.children[0], oe = (x) => ({ button: 0, clientX: x, pointerId: 7 });
const mainDuringOverview = bindGestures(canvas, { store: overviewStore, ui: {} }, () => r, () => {});
oc.listeners.pointerdown(oe(400)); oc.listeners.pointermove(oe(450));
const overviewMid = { ...overviewStore.get().view };
fire("wheel", 600, { deltaY: -120 }); assert.deepEqual(overviewStore.get().view, overviewMid);
for (let i = 1; i <= 30; i++) oc.listeners.pointermove(oe(450 + i));
assert.equal(oh.status().undo, 1);
overviewStore.command("view.undo");
const undoneOverview = { ...overviewStore.get().view };
oc.listeners.pointermove(oe(490)); oc.listeners.pointerup(oe(490));
assert.deepEqual(overviewStore.get().view, undoneOverview); assert.deepEqual(oh.status(), { undo: 0, redo: 1 });
// 尚未移動的第二次拖曳中直接 Redo，後續 pointermove 也必須失效。
oc.listeners.pointerdown(oe(400)); overviewStore.command("view.redo");
const redoneOverview = { ...overviewStore.get().view };
oc.listeners.pointermove(oe(490)); oc.listeners.pointerup(oe(490));
assert.deepEqual(overviewStore.get().view, redoneOverview); assert.deepEqual(oh.status(), { undo: 1, redo: 0 });
mainDuringOverview.dispose();
ov.dispose(); document.createElement = originalElement;
console.log("P2a 審核回歸 self-check OK");
// 可重現變異驗證：node scope_tool/web/static/js/analysis/p2_check.mjs --mutations
// 只在暫存副本變異；中斷不會留下產品檔修改。
if (process.argv.includes("--mutations")) {
  const { readFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } = await import("node:fs");
  const { spawnSync } = await import("node:child_process");
  const { fileURLToPath } = await import("node:url");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const mutations = [
    ["反轉矩形方向", "gestures.js", "t0: X.inv(Math.min(a, b)), t1: X.inv(Math.max(a, b))", "t0: X.inv(Math.max(a, b)), t1: X.inv(Math.min(a, b))"],
    ["移除夾限", "gestures.js", "}, limits, true);", "}, limits, false);"],
    ["不清 redo", "gestures.js", "      future = [];", "      // 變異：保留 redo"],
    ["最近檔再步進", "axes.js", "  const e = Math.floor(Math.log10(value));", "  const p = 10 ** Math.floor(Math.log10(value)); value = [1,2,5,10].map(m=>m*p).sort((a,b)=>Math.abs(Math.log(a/value))-Math.abs(Math.log(b/value)))[0];\n  const e = Math.floor(Math.log10(value));"],
    ["失焦不解除 Space", "gestures.js", 'space = false; end();', 'end();'],
    ["獨立拖曳未結束群組", "gestures.js", 'if (d?.type === "pan") store.command("view.historyGroup", { end: true });', '// 變異：不結束群組'],
    ["隱藏分頁仍攔截", "gestures.js", 'if (canvas.closest?.("[hidden]")) return;', '// 變異：仍攔截'],
    ["Shift 暫時框選失效", "gestures.js", 'mode === "zoom" || shiftKey', 'mode === "zoom"'],
  ];
  const temp = mkdtempSync(join(tmpdir(), "scope-p2-"));
  try {
    cpSync(fileURLToPath(new URL("../", import.meta.url)), temp, { recursive: true });
    for (const [name, file, old, changed] of mutations) {
      const path = join(temp, "analysis", file), original = readFileSync(path, "utf8");
      assert.ok(original.includes(old), `${name}：找不到變異位置`);
      try {
        writeFileSync(path, original.replace(old, changed));
        const result = spawnSync(process.execPath, [join(temp, "analysis/p2_check.mjs")], { encoding: "utf8" });
        assert.notEqual(result.status, 0, `${name}：未抓到變異`);
        assert.match(result.stderr, /AssertionError/, `${name}：應因斷言失敗：${result.stderr}`);
        console.log(`${name}：如預期失敗`);
      } finally { writeFileSync(path, original); }
    }
  } finally { rmSync(temp, { recursive: true, force: true }); }
  console.log(`P2a 變異驗證 ${mutations.length}/${mutations.length} self-check OK（暫存副本）`);
}
