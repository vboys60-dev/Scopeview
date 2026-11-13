// L8：P2b-2a 純函式、產品掛載事件／實際繪圖與暫存副本變異驗證。
import assert from "node:assert/strict";
import { createStore } from "./store.js";
import * as scales from "./scales.js";
import * as fmt from "../fmt.js";
import { mount as mountBar, scaleChange } from "./chanbar.js";
import { centerPotential, positionOf, hasDx, fitEnvelope } from "./vertical.js";
import { voltageAt, voltageAxis, voltageLeft } from "./voltage.js";
import { mount as mountPlot, layoutRect, divY } from "./mainplot.js";
import { tickLabel, timeTickLabels } from "./plotcore.js";
import { channelHandles, hitHandle } from "./handles.js";
const near = (a, b) => assert.ok(Math.abs(a - b) <= Math.max(1e-15, Math.abs(b) * 1e-12), `${a} != ${b}`);
for (const scale of [2, 0.137, 0.002, 2e-6]) for (const position of [-7.25, -1, 0, 2.5]) {
  const c = { scale, position, vmin: 100, vmax: 500 };
  near(positionOf(centerPotential(c), scale), position);
  const patch = scaleChange(c, scale * 2, scales);
  near(patch.position, position / 2);
  near(centerPotential({ ...c, ...patch }), centerPotential(c));
  assert.deepEqual(patch, scaleChange({ ...c, vmin: null, vmax: null }, scale * 2, scales));
}
const base = { name: "CH2", unit: "V", scale: 0.002, position: -2, color: "#00ff00", time_offset: 0, visible: true };
assert.equal(voltageAt(3, base), 0.01);
assert.equal(voltageAxis(base).ticks[5].label, "4.0 mV");
assert.equal(voltageAxis({ ...base, scale: 2e-6 }).ticks[5].label, "4.0 µV");
assert.equal(voltageAxis({ ...base, scale: 0.1, position: 0 }).ticks[2].label, "300 mV");
for (const unit of ["V²", "V/s"]) {
  const axis = voltageAxis({ ...base, unit });
  assert.equal(axis.ticks[5].label, `4.0 m${unit}`);
  assert.equal(axis.title, `CH2 · 2 m${unit}/格`);
  assert.equal(axis.color, base.color);
}
assert.deepEqual(voltageAxis(null).ticks.map((t) => t.label), ["5", "4", "3", "2", "1", "0", "-1", "-2", "-3", "-4", "-5"]);
for (const dx of [0, -0, undefined, NaN, Infinity]) assert.equal(hasDx({ time_offset: dx }), false);
for (const dx of [1e-15, -2]) assert.equal(hasDx({ time_offset: dx }), true);
const env = { n: 3, lo: [-0.004, NaN, -0.002], hi: [0.004, NaN, 0.006] };
assert.deepEqual(fitEnvelope(env, "V", scales), { scale: 0.002, position: -0.5 });
assert.deepEqual(fitEnvelope({ n: 1, lo: [2], hi: [2] }, "V²", scales), { scale: 0.5, position: -4 });
assert.equal(fitEnvelope({ n: 1, lo: [NaN], hi: [Infinity] }, "V", scales), null);
assert.equal(voltageAxis({ ...base, unit: "dB", scale: 1000 }).ticks[5].label, "2000 dB");
const axis137 = voltageAxis({ ...base, scale: 0.137, position: 0 });
assert.deepEqual(axis137.ticks.map(t => t.label), ["685 mV", "548 mV", "411 mV", "274 mV", "137 mV", "0 V", "-137 mV", "-274 mV", "-411 mV", "-548 mV", "-685 mV"]);
for (const step of [0.137, 0.5, 2e-6]) for (const value of [0.025, 0.125, 0.137, 0.685]) {
  assert.equal(tickLabel(-value, "V", step), "-" + tickLabel(value, "V", step));
}
assert.deepEqual(timeTickLabels(-0.685, 0.685), axis137.ticks.map(t => t.label.replace("V", "s")).reverse());
const texts = [];
const g = new Proxy({}, { get: (t, k) => k === "measureText" ? (s) => ({ width: s.length * 9 })
  : k === "fillText" ? (text, x, y) => texts.push({ text, x, y, color: t.fillStyle, baseline: t.textBaseline }) : t[k] ?? (() => {}), set: (t, k, v) => ((t[k] = v), true) });
function element(tag = "div") {
  return { tag, tagName: tag.toUpperCase(), children: [], dataset: {}, style: {}, classList: { add() {}, toggle() {} }, listeners: {}, value: "",
    closest(selectors) { return selectors.split(",").includes(this.tag) ? this : this.parentNode?.closest(selectors) ?? null; },
    blur() { this.onblur?.(); },
    click() { this.clicks = (this.clicks ?? 0) + 1; },
    append(...cs) { for (const c of cs) { this.children.push(c); c.parentNode = this; } },
    replaceChildren(...cs) { this.children = []; this.append(...cs); },
    addEventListener(k, fn) { this.listeners[k] = fn; }, removeEventListener() {}, setAttribute() {},
    setPointerCapture() {}, getContext: () => g, getBoundingClientRect: () => ({ width: 800, height: 308, left: 0, top: 0 }) };
}
globalThis.document = { createElement: element, activeElement: null };
globalThis.window = { devicePixelRatio: 1 };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
const store = createStore(), requests = [];
let resolveFit = null;
const ctx = { store, fmt, scales, ui: { async confirm() { return true; }, toast() {}, showError(e) { throw e; } }, bridge: {
  fetchWave: async (args) => { requests.push(args); return resolveFit ? await new Promise((r) => { resolveFit = r; }) : env; },
} };
store.set({ file: { gen: 3, channels: [] }, view: { t0: 10, t1: 12 }, selected: "CH1", channels: [
  { ...base, name: "CH1", color: "#ff0000" }, { ...base, time_offset: 0.25 },
] });
const bar = element(); mountBar(bar, ctx);
const columns = () => bar.children.filter(e => e.className === "chanbar__col");
assert.ok(columns().every(e => e.children[1].hidden));
bar.children[0].onclick();
assert.ok(columns().every(e => !e.children[1].hidden));
const vertical = columns()[1].children[1], fields = vertical.children.filter((e) => e.className === "vertical__field");
const input = (key) => fields.flatMap((e) => e.children).find((e) => e.dataset?.vertical === key);
const press = (key, text) => fields.find((e) => e.children.includes(input(key))).children.find((e) => e.textContent === text).onclick();
const fit = fields[2].children.find((e) => e.textContent === "適配");
const first = { ...store.get().channels[0] };
// 真實 checkbox 冒泡與雙擊不得改選取／開啟換色器。
const chip2 = columns()[1].children[0], check2 = chip2.children[0], color2 = chip2.children[2];
check2.checked = false; check2.onchange(); chip2.onclick({ target: check2 });
assert.equal(store.get().selected, "CH1"); assert.equal(store.get().channels[1].visible, false);
chip2.ondblclick({ target: check2 }); assert.equal(color2.clicks, undefined);
check2.checked = true; check2.onchange();
// CH2 欄位綁定名稱，選取 CH1 時編輯也不影響 CH1。
const position1 = columns()[0].children[1].children[1].children[2], value1 = position1.value;
input("scale").value = "4m"; input("scale").onchange();
assert.equal(store.get().channels[1].scale, 0.004); assert.deepEqual(store.get().channels[0], first);
input("scale").value = "2m"; input("scale").onchange();
document.activeElement = input("position"); input("position").value = "unfinished";
chip2.onclick({ target: chip2 });
assert.equal(store.get().selected, "CH2"); assert.equal(input("position").value, "unfinished");
document.activeElement = null;
input("position").value = "-4m"; input("position").onchange();
assert.equal(store.get().channels[1].position, 2); assert.deepEqual(store.get().channels[0], first);
assert.equal(position1.value, value1);
press("position", "▲"); near(centerPotential(store.get().channels[1]), -0.002);
press("position", "▼"); near(centerPotential(store.get().channels[1]), -0.004);
press("position", "歸零"); assert.equal(store.get().channels[1].position, 0);
input("scale").value = "137m"; input("scale").onchange();
press("scale", "+"); assert.equal(store.get().channels[1].scale, 0.147);
press("scale", "▼"); assert.equal(store.get().channels[1].scale, 0.1);
input("dx").value = "0"; input("dx").onchange();
assert.equal(columns()[1].children[0].children.at(-1).hidden, true);
input("dx").value = "250m"; input("dx").onchange();
assert.equal(columns()[1].children[0].children.at(-1).hidden, false);
await fit.onclick();
assert.deepEqual(requests.at(-1), { ch: "CH2", t0: 9.75, t1: 11.75, px: 2048, gen: 3 });
assert.equal(store.get().channels[1].scale, 0.002); assert.equal(store.get().channels[1].position, -0.5);
assert.deepEqual(store.get().channels[0], first);
// 適配回應過期時不可把舊視窗結果套到新視窗。
resolveFit = true; const pending = fit.onclick();
store.set({ view: { t0: 20, t1: 22 } });
resolveFit({ n: 1, lo: [9], hi: [9] }); await pending; resolveFit = null;
assert.equal(store.get().channels[1].scale, 0.002);
// 飛行中通道資料改變必須丟棄；只切換選取仍套用原通道。
for (const change of [() => store.updateChannel("CH2", { position: 1.25 }, "user")]) {
  resolveFit = true; const pending = fit.onclick(); change();
  const before = structuredClone(store.get().channels);
  resolveFit({ n: 1, lo: [9], hi: [9] }); await pending; resolveFit = null;
  assert.deepEqual(store.get().channels, before);
}
resolveFit = true; const selectedPending = fit.onclick();
store.set({ selected: "CH1" });
resolveFit(env); await selectedPending; resolveFit = null;
assert.equal(store.get().channels[1].position, -0.5); assert.deepEqual(store.get().channels[0], first);
store.set({ selected: "CH2" }); store.updateChannel("CH2", { position: -0.5 });
const host = element(), plot = mountPlot(host, ctx); await new Promise((r) => setTimeout(r, 0));
const c = store.get().channels[1], axis = voltageAxis(c), nominal = layoutRect(800, 308);
const handles = channelHandles(store.get().channels, nominal), left = voltageLeft((s) => s.length * 9, axis, handles);
const wide = channelHandles([{ ...c, name: "Mem4.CHAN12" }], nominal);
assert.ok(voltageLeft(s => s.length * 9, axis, wide) >= wide[0].x + wide[0].w + 18 + Math.max(...axis.ticks.map(t => t.label.length * 9)), "長標籤右側仍須保留完整刻度寬度");
assert.ok(left > 84); const rect = layoutRect(800, 308, left);
const tick = texts.findLast((t) => t.text === axis.ticks[0].label);
assert.equal(tick.color, c.color); near(tick.x, left - 4); near(tick.y, divY(rect, 5));
assert.ok(texts.some((t) => t.text === `▲${axis.title}` && t.color === c.color));
const zero = texts.findLast((t) => t.text === "0 V"), handle = channelHandles(store.get().channels, rect)[1];
near(zero.y, handle.y + handle.h / 2);
assert.equal(hitHandle(store.get().channels, rect, handle.x + 6, zero.y).name, c.name);
for (const position of [-5, -2.5, 0, 3, 5]) {
  const h = channelHandles([{ ...c, position }], rect)[0]; near(h.y + h.h / 2, Math.min(rect.t + rect.h - 10, Math.max(10, divY(rect, position))));
  assert.ok(h.y >= 0);
}
// 拖把手後欄位字串有限精度；未編輯的 change/blur 不回寫量化值。
store.command("channel.scale_intent", { name: "CH2", position: 1.23456789012345 });
assert.ok(input("position").value.length <= 12, input("position").value);
const unchanged = store.get().channels[1]; input("position").onchange(); input("position").onblur();
assert.equal(store.get().channels[1], unchanged);
// 等值輸入不更新；輸入中不提交，Enter 交由 blur 提交。
input("dx").value = "0.250 s";
const same = store.get().channels[1]; input("dx").onchange(); assert.equal(store.get().channels[1], same);
input("position").value = "1m";
assert.equal(store.get().channels[1], same);
input("position").onkeydown({ key: "Enter", preventDefault() {} });
near(centerPotential(store.get().channels[1]), 0.001);
// 零位附近的格線標籤隱藏，但距離足夠時保留。
for (const position of [0.1, 0.8, 0]) {
  texts.length = 0; store.updateChannel("CH2", { position });
  const label = voltageAxis(store.get().channels[1]).ticks[5].label;
  assert.equal(texts.some(t => t.text === label && t.x > 20), position !== 0.1);
}
// 四通道同零位：垂直避讓，所有刻度文字左緣在把手右緣之外。
const four = Array.from({ length: 4 }, (_, i) => ({ ...c, name: `CH${i+1}`, position: 0 }));
texts.length = 0; store.set({ channels: four, selected: "CH2" });
const hs = channelHandles(four, nominal), ax = voltageAxis(four[1]);
assert.equal(new Set(hs.map(h => h.y)).size, 4);
const edge = Math.max(...hs.map(h => h.x + h.w));
for (const t of ax.ticks) {
  const drawn = texts.findLast(d => d.text === t.label);
  assert.ok(drawn.x - t.label.length * 9 >= edge, JSON.stringify({ drawn, edge }));
}
assert.equal(texts.findLast(t => t.text === ax.ticks.at(-1).label).baseline, "bottom");
// 衍生通道刪除按鈕的冒泡不選取，雙擊也不開換色器。
store.set({ channels: [...four, { ...c, name: "F1", derived: true }], selected: "CH1" });
ctx.bridge.call = async () => ({});
const derived = columns()[4].children[0], remove = derived.children.at(-1), color = derived.children[2];
derived.onclick({ target: remove }); derived.ondblclick({ target: remove });
assert.equal(store.get().selected, "CH1"); assert.equal(color.clicks, undefined);
await remove.onclick(); assert.equal(store.get().selected, "CH1");
store.set({ channels: [first, c], selected: "CH2" });
store.set({ selected: "CH1" });
assert.equal(texts.findLast((t) => t.text === voltageAxis(first).ticks[0].label).color, first.color);
store.set({ selected: null });
assert.ok(host.children[0].labelLayout()[0].labels.length > 0);
plot.dispose();
console.log("P2b2 self-check OK：中心換算／畫面中心換檔／單位與位數／dx／可見範圍適配／選取隔離／實際繪製與把手");
if (process.argv.includes("--mutations")) {
  const { readFileSync, writeFileSync, cpSync, mkdtempSync, rmSync } = await import("node:fs");
  const { spawnSync } = await import("node:child_process");
  const { fileURLToPath } = await import("node:url");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");
  const mutations = [
    ["中心符號反轉", "vertical.js", "-value / scale + 0", "value / scale + 0"],
    ["舊整檔中點換檔", "chanbar.js", "ch.position * ch.scale / next + 0", "_scales.rescale(ch.vmin, ch.vmax, ch.scale, ch.position, next)[0]"],
    ["刻度忽略 position", "voltage.js", "(division - c.position)", "(division + c.position)"],
    ["刻度固定四位", "plotcore.js", "if (!(step > 0))", "if (unit !== 's' || !(step > 0))"],
    ["dx 零仍有徽章", "vertical.js", "c.time_offset !== 0", "true"],
    ["適配忽略 dx", "vertical.js", "view.t0 - (c.time_offset ?? 0)", "view.t0"],
    ["適配不置中", "vertical.js", "return { scale, position };", "return { scale, position: 0 };"],
    ["左軸無通道顏色", "mainplot.js", "yText: axis.color", "yText: col.text"],
    ["左邊界固定", "voltage.js", "return Math.max(minimum, Math.ceil(edge", "return Math.max(minimum, Math.ceil(0 * edge"],
  ];
  mutations.push(
    ["四通道不避讓", "handles.js", "!placed.some((b) => b.lane === lane && Math.abs(b.y - v) < 24)", "true"],
    ["左邊界忽略把手", "voltage.js", "Math.max(14, ...handles.map((b) => b.x + b.w))", "14"],
    ["適配忽略通道變更", "vertical.js", " || current() !== c", ""],
    ["零位附近不隱藏", "mainplot.js", "< 12 ?", "< 0 ?"],
    ["欄位跟隨選取", "vertical.js", "c.name === name", "c.name === store.get().selected"],
    ["勾選框也選取", "chanbar.js", 'if (e.target.closest?.("input,button")) return;', ""],
    ["雙擊控件開換色", "chanbar.js", 'box.ondblclick = (e) => { if (e.target.closest?.("input,button")) return;', 'box.ondblclick = (e) => {'],
    ["把手超出畫布", "handles.js", "- 10, 0,", "- 10, -10,"],
    ["中心欄位過多位數", "vertical.js", 'tickLabel(centerPotential(c), c.unit, c.scale / 100)', 'fmt.fmt(centerPotential(c), c.unit, 15)'],
    ["格距忽略最末有效位", "plotcore.js", "Math.min(floor - 1, last)", "floor - 1"],
    ["負數捨入不對稱", "plotcore.js", "Math.sign(v) * Math.round(Math.abs(v) / res)", "Math.round(v / res)"],
    ["左下文字相黏", "plotcore.js", 't.p >= rect.t + rect.h ? "bottom" : "middle"', '"middle"'],
  );
  const temp = mkdtempSync(join(tmpdir(), "scope-p2b2-"));
  try {
    cpSync(fileURLToPath(new URL("../", import.meta.url)), temp, { recursive: true });
    for (const [name, file, old, changed] of mutations) {
      const path = join(temp, "analysis", file), original = readFileSync(path, "utf8");
      assert.ok(original.includes(old), `${name}：找不到變異位置`);
      try {
        writeFileSync(path, original.replace(old, changed));
        const result = spawnSync(process.execPath, [join(temp, "analysis/p2b2_check.mjs")], { encoding: "utf8" });
        assert.notEqual(result.status, 0, `${name}：未抓到變異`);
        assert.match(result.stderr, /AssertionError/, `${name}：應因斷言失敗：${result.stderr}`);
        console.log(`${name}：如預期失敗`);
      } finally { writeFileSync(path, original); }
    }
  } finally { rmSync(temp, { recursive: true, force: true }); }
  console.log(`P2b2 變異驗證 ${mutations.length}/${mutations.length} self-check OK（暫存副本）`);
}
