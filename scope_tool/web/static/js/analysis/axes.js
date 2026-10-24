import { mountSummary } from "./summary.js";
// Horizontal 列：中心參考點固定 0.5；只發 viewport.intent，不強制吸附非標準尺度。
import { fmt, parseSI } from "../fmt.js";
import { DEFAULT_MODE } from "./gestures.js";
import { fullRange } from "./overview.js";
export const horizontalOf = (v) => ({ scale: (v.t1 - v.t0) / 10, position: (v.t0 + v.t1) / 2 });
export const rangeOf = (scale, position) => ({ t0: position - 5 * scale, t1: position + 5 * scale });
/** 嚴格相鄰 1-2-5，僅容忍機器浮點誤差；不先找最近檔。 */
export function step125Strict(value, up) {
  if (!(value > 0) || !Number.isFinite(value)) return NaN;
  const e = Math.floor(Math.log10(value));
  const steps = [];
  for (let k = e - 1; k <= e + 1; k++) for (const m of [1, 2, 5]) steps.push(Number(`${m}e${k}`));
  const eps = value * Number.EPSILON * 8;
  return up ? steps.find((s) => s > value + eps) ?? value : steps.reverse().find((s) => s < value - eps) ?? value;
}
/** 中心位置每次移動一格（±S），零與負值同樣處理。 */
export function stepPosition(value, up, scale) {
  return value + (up ? scale : -scale);
}
/** 僅顯示四捨五入至時間/格的千分之一；不改 store 真值。 */
export function formatHorizontal(value, scale) {
  const resolution = scale / 1000;
  if (!(resolution > 0) || !Number.isFinite(value)) return fmt(value, "s");
  const rounded = Math.round(value / resolution) * resolution;
  const digits = rounded ? Math.max(1, Math.min(15, Math.floor(Math.log10(Math.abs(rounded))) - Math.floor(Math.log10(resolution)) + 1)) : 1;
  return fmt(rounded, "s", digits);
}
const h = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
export function mount(el, { store }) {
  const button = (text, fn, title = text) => { const b = h("button", text, "btn btn--small"); b.type = "button"; b.title = title; b.onclick = fn; return b; };
  let mode = DEFAULT_MODE;
  const modes = ["pan", "zoom"].map((v, i) => button(i ? "⬚ 框選放大" : "✥ 平移", () => store.command("view.mode", v)));
  const syncMode = () => modes.forEach((b, i) => b.setAttribute("aria-pressed", String(mode === (i ? "zoom" : "pan"))));
  store.onCommand("view.mode", (v) => { if (["pan", "zoom"].includes(v)) { mode = v; syncMode(); } });
  syncMode();
  const undo = button("↶", () => store.command("view.undo"), "復原視圖（Ctrl/Cmd+Z）"), redo = button("↷", () => store.command("view.redo"), "重做視圖（Shift+Ctrl/Cmd+Z 或 Ctrl/Cmd+Y）");
  undo.disabled = redo.disabled = true;
  store.onCommand("view.history", (s) => { undo.disabled = !s.undo; redo.disabled = !s.redo; });
  const reset = button("完整時間", () => store.command("view.reset"));
  const modeGroup = h("div", undefined, "analysis__hmodes"); modeGroup.append(...modes, undo, redo); el.append(modeGroup);
  function field(label, key) {
    const wrap = h("label", undefined, "analysis__hfield"), input = h("input", undefined, "input");
    input.type = "text"; input.setAttribute("aria-label", label); input.dataset.axis = key;
    const apply = () => {
      if (input.value === input.dataset.rendered) { render(true); return; }
      const value = parseSI(input.value), v = horizontalOf(store.get().view);
      if (!input.disabled && Number.isFinite(value) && (key !== "scale" || value > 0)) store.command("viewport.intent", rangeOf(key === "scale" ? value : v.scale, key === "position" ? value : v.position));
      render(true);
    };
    const step = (up) => {
      const v = horizontalOf(store.get().view), value = parseSI(input.value), base = Number.isFinite(value) && (key !== "scale" || value > 0) ? value : v[key];
      input.value = String(key === "scale" ? step125Strict(base, up) : stepPosition(base, up, v.scale)); apply();
    };
    input.onblur = apply;
    input.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); apply(); } };
    input.addEventListener("wheel", (e) => { if (input.disabled || !e.deltaY) return; e.preventDefault(); store.command("view.historyGroup", { key: `axis.${key}` }); step(e.deltaY < 0); store.command("view.historyGroup"); }, { passive: false });
    const down = button("◀", () => step(false), `${label}減小一${key === "scale" ? "檔" : "格"}`), up = button("▶", () => step(true), `${label}增大一${key === "scale" ? "檔" : "格"}`);
    wrap.append(h("span", label), down, input, up); el.append(wrap);
    return { input, down, up };
  }
  const scale = field("時間/格", "scale"), position = field("位置（中心）", "position");
  const zero = button("0", () => { const v = horizontalOf(store.get().view); store.command("viewport.intent", rangeOf(v.scale, 0)); }, "檔案時間 0 置中");
  el.append(zero);
  const range = h("span", undefined, "analysis__hrange"); el.append(range, reset);
  mountSummary(el, store);
  function render(force = false) {
    const s = store.get(), v = horizontalOf(s.view), f = fullRange(s.file);
    for (const [key, field] of [["scale", scale], ["position", position]]) {
      for (const e of Object.values(field)) e.disabled = !f;
      if (force || document.activeElement !== field.input) field.input.value = field.input.dataset.rendered = formatHorizontal(v[key], v.scale);
    }
    zero.disabled = !f || f.t0 > 0 || f.t1 < 0; reset.disabled = !f;
    range.textContent = `範圍 ${formatHorizontal(s.view.t0, v.scale)} ～ ${formatHorizontal(s.view.t1, v.scale)}`;
    range.title = `${s.view.t0} ～ ${s.view.t1} s`;
  }
  store.on(["file", "view"], () => render()); render();
}
